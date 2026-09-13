"""Defesas que valem pra API inteira: limite de requisições e cabeçalhos.

Vivem aqui, como middleware, e não espalhadas nas rotas. O motivo é o mesmo do
`APIRouter(dependencies=[...])` no main: rota nova nasce protegida. Se cada
endpoint tivesse que lembrar de se defender, o primeiro que esquecesse abriria
um buraco que nenhum teste pegaria.
"""

import os
import time
from collections import deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response


def _inteiro_do_ambiente(nome: str, padrao: int) -> int:
    try:
        valor = int(os.getenv(nome, "") or padrao)
    except ValueError:
        return padrao
    return valor if valor > 0 else padrao


# Teto geral por IP. Generoso de propósito: o app é de uma pessoa só, e abrir
# uma aba dispara várias chamadas de uma vez (resumo + lista + categorias). O
# alvo aqui é script varrendo a API, não uso humano intenso.
JANELA_SEGUNDOS = 60
TETO_POR_JANELA = _inteiro_do_ambiente("RATE_LIMIT_POR_MINUTO", 240)

# Teto separado, muito mais apertado, pra resposta 401/403. É o que transforma
# "tentar token até acertar" num ataque inviável: quem erra credencial gasta
# esta cota, e ela não se mistura com o uso normal de quem já está autenticado.
JANELA_FALHAS_SEGUNDOS = 300
TETO_DE_FALHAS = _inteiro_do_ambiente("RATE_LIMIT_FALHAS", 10)

# Corpo maior que isto é recusado antes de virar JSON. Nenhum lançamento do
# Sentavos chega perto disso; o que chega é quem quer ocupar memória do processo.
TAMANHO_MAXIMO_DO_CORPO = 256 * 1024  # 256 KB


class _Balde:
    """Janela deslizante de timestamps. Uma por IP, por tipo de cota."""

    __slots__ = ("marcas",)

    def __init__(self) -> None:
        self.marcas: deque[float] = deque()

    def podar(self, agora: float, janela: int) -> None:
        limite = agora - janela
        while self.marcas and self.marcas[0] <= limite:
            self.marcas.popleft()

    def estourou(self, agora: float, janela: int, teto: int) -> bool:
        self.podar(agora, janela)
        return len(self.marcas) >= teto

    def registrar(self, agora: float) -> None:
        self.marcas.append(agora)


def _recusa(mensagem: str, retry_after: int) -> JSONResponse:
    # O Retry-After é o que diz ao cliente honesto quando voltar, em vez de
    # deixá-lo martelando a API e afundando mais fundo na própria cota.
    return JSONResponse(
        {"detail": mensagem},
        status_code=429,
        headers={"Retry-After": str(retry_after)},
    )


def _corpo_excede(request) -> JSONResponse | None:
    bruto = request.headers.get("content-length")
    if not bruto:
        return None
    try:
        tamanho = int(bruto)
    except ValueError:
        return JSONResponse({"detail": "Content-Length inválido."}, status_code=400)
    if tamanho > TAMANHO_MAXIMO_DO_CORPO:
        return JSONResponse({"detail": "Corpo da requisição grande demais."}, status_code=413)
    return None


# O estado mora no módulo, não na instância do middleware, por uma razão
# prática: o `app` é um singleton e o Starlette só constrói a pilha de
# middlewares na primeira requisição, então alcançar a instância de fora (pra
# zerar entre testes, por exemplo) seria frágil. Com o estado aqui, o
# `zerar_limites()` abaixo é uma chamada direta.
_GERAIS: dict[str, _Balde] = {}
_FALHAS: dict[str, _Balde] = {}


def zerar_limites() -> None:
    """Esquece tudo que foi contado até agora.

    Existe pros testes: a suíte de auth provoca 401 de propósito, e sem isto o
    primeiro arquivo gastaria a cota de falhas e os seguintes receberiam 429 no
    lugar do status que estão verificando. Zerar entre testes mantém o
    middleware ligado em todos eles — desligá-lo seria testar um app que não é
    o que vai pra produção.
    """
    _GERAIS.clear()
    _FALHAS.clear()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Limita requisições por IP, com cota separada pra falha de credencial.

    O estado é em memória, o que é honesto pro tamanho do problema: uma única
    instância. Se um dia rodar replicado, cada réplica passa a ter a
    sua própria contagem e o teto real vira N vezes maior — aí é hora de trocar
    por Redis. Guardar em memória não é descuido, é a escolha certa pra uma
    instância só, e este comentário é o aviso de quando ela deixa de valer.
    """

    def __init__(self, app, isento: set[str] | None = None):
        super().__init__(app)
        # O healthcheck do host bate de minuto em minuto e não pode gastar cota:
        # se gastasse, ele mesmo derrubaria o serviço que veio checar.
        self.isento = isento or {"/"}
        self._ultima_limpeza = time.monotonic()

    def _ip(self, request) -> str:
        # O uvicorn sobe com --forwarded-allow-ips, então o ProxyHeaders dele já
        # troca o client.host pelo IP real do X-Forwarded-For. Ler o cabeçalho
        # aqui de novo seria pior: sem o proxy na frente, qualquer um forjaria.
        return request.client.host if request.client else "desconhecido"

    def _limpar_ociosos(self, agora: float) -> None:
        # Sem isto, um IP por requisição vira um dicionário que só cresce — é um
        # vazamento de memória lento com cara de funcionalidade.
        if agora - self._ultima_limpeza < 300:
            return
        self._ultima_limpeza = agora
        for mapa, janela in (
            (_GERAIS, JANELA_SEGUNDOS),
            (_FALHAS, JANELA_FALHAS_SEGUNDOS),
        ):
            ociosos = []
            for ip, balde in mapa.items():
                balde.podar(agora, janela)
                if not balde.marcas:
                    ociosos.append(ip)
            for ip in ociosos:
                mapa.pop(ip, None)

    async def dispatch(self, request, call_next):
        if request.url.path in self.isento:
            return await call_next(request)

        agora = time.monotonic()
        self._limpar_ociosos(agora)
        ip = self._ip(request)

        # A cota de falhas é checada primeiro: quem está sondando credencial
        # deve bater nela antes de gastar a cota geral.
        falhas = _FALHAS.setdefault(ip, _Balde())
        if falhas.estourou(agora, JANELA_FALHAS_SEGUNDOS, TETO_DE_FALHAS):
            return _recusa(
                "Muitas tentativas recusadas. Espere alguns minutos.",
                JANELA_FALHAS_SEGUNDOS,
            )

        geral = _GERAIS.setdefault(ip, _Balde())
        if geral.estourou(agora, JANELA_SEGUNDOS, TETO_POR_JANELA):
            return _recusa("Muitas requisições. Espere um pouco.", JANELA_SEGUNDOS)

        geral.registrar(agora)

        corpo_grande = _corpo_excede(request)
        if corpo_grande is not None:
            return corpo_grande

        resposta = await call_next(request)

        # 401 = não sei quem é você; 403 = sei e não pode. Os dois significam
        # credencial que não serve, e é isso que a cota apertada conta.
        if resposta.status_code in (401, 403):
            falhas.registrar(agora)

        return resposta


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Cabeçalhos de resposta da API.

    É uma API JSON, então boa parte do catálogo de cabeçalho web não se aplica.
    Os que ficam são os que mudam algo de verdade aqui.
    """

    async def dispatch(self, request, call_next):
        resposta: Response = await call_next(request)
        cabecalhos = resposta.headers

        # Impede o navegador de "adivinhar" que um JSON é HTML e executá-lo.
        cabecalhos.setdefault("X-Content-Type-Options", "nosniff")
        # A API não tem tela; nada dela deve aparecer dentro de um iframe.
        cabecalhos.setdefault("X-Frame-Options", "DENY")
        # Não vaza a URL da API (com querystring) pra sites de terceiros.
        cabecalhos.setdefault("Referrer-Policy", "no-referrer")
        # Trava qualquer tentativa de carregar recurso a partir de uma resposta.
        cabecalhos.setdefault(
            "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
        )
        # Extrato financeiro não fica em cache de proxy nem no disco do navegador.
        cabecalhos.setdefault("Cache-Control", "no-store")

        # HSTS só faz sentido servido por HTTPS — e só o mande quando for o caso,
        # senão um dev em http://localhost trava o próprio navegador no domínio.
        if request.url.scheme == "https":
            cabecalhos.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )

        return resposta
