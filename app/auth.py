"""Autenticação própria do Sentavos. Um usuário, uma senha, um token.

Antes isto era Supabase Auth. Saiu porque projeto free hiberna após ~1 semana
parado, e hibernar derruba o login junto — o que significava não conseguir abrir
o próprio app no celular depois de uma viagem. Auth de um usuário só é pequena o
bastante pra morar aqui, e o que se ganha é o app inteiro num lugar só, sem
depender de serviço que dorme nem de cota de organização de terceiro.

O desenho é deliberadamente mínimo:

  - A senha **nunca** é guardada. O que vai no ambiente é o hash Argon2id dela.
  - O login troca e-mail + senha por um JWT assinado por esta API.
  - As rotas de dados só olham o token. Não há sessão no servidor, então não há
    nada pra expirar, sincronizar ou perder num redeploy.

Não tem cadastro, não tem "esqueci minha senha", não tem multi-usuário. Nada
disso é esquecimento: cada um seria mais código e mais superfície pra proteger,
num app que tem exatamente um dono.
"""

import datetime as dt
import hmac
import logging
import os

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# O cliente recebe 401 genérico de propósito (detalhar ajuda quem sonda), mas o
# servidor precisa saber o motivo — senão "recusou a sessão" é indepurável.
log = logging.getLogger("sentavos.auth")

# Só HS256. A lista é fechada porque é ela que impede um token com alg="none"
# (ou trocado pra confundir o verificador) de ser aceito. Aqui quem assina e
# quem verifica é o mesmo processo, então não há razão pra aceitar mais nada.
ALGORITMO = "HS256"

# Validade do token. Longa de propósito: é um app pessoal aberto no celular, e
# token de 1 hora significaria digitar senha toda vez que abrisse. O preço é que
# um token roubado serve por até 30 dias — mitigado pelo SENTAVOS_TOKEN_EPOCH
# abaixo, que invalida tudo de uma vez quando preciso.
VALIDADE_DO_TOKEN = dt.timedelta(days=30)

# Identidade fixa do emissor. Serve pra recusar de cara um token que por acaso
# tenha sido assinado com o mesmo segredo pra outra finalidade.
EMISSOR = "sentavos"
AUDIENCIA = "sentavos-app"

# auto_error=False pra devolver 401 na falta de token. O padrão do HTTPBearer é
# 403, que significa "te conheço e não pode" — o certo aqui é "não te conheço".
bearer = HTTPBearer(auto_error=False)

# Parâmetros padrão do argon2-cffi (Argon2id). Não são customizados de propósito:
# a biblioteca os atualiza conforme o hardware evolui, e um número escolhido à
# mão hoje envelheceria mal e em silêncio.
hasher = PasswordHasher()


class ConfiguracaoIncompleta(RuntimeError):
    """Falta variável de ambiente pra autenticar alguém."""


def gerar_hash(senha: str) -> str:
    """Hash Argon2id da senha. Usado pelo `python -m app.criar_senha`."""
    return hasher.hash(senha)


def _config() -> tuple[str, str, str]:
    """E-mail, hash e segredo do ambiente. Lido a cada chamada pro teste trocar.

    Falha fechada de propósito: sem qualquer uma das três, ninguém entra. O
    contrário — deixar passar quando falta config — transformaria um deploy mal
    configurado numa porta aberta, que é o pior jeito de descobrir o problema.
    """
    email = (os.getenv("SENTAVOS_EMAIL") or "").strip().lower()
    hash_senha = os.getenv("SENTAVOS_SENHA_HASH") or ""
    segredo = os.getenv("SENTAVOS_JWT_SECRET") or ""

    if not email or not hash_senha or not segredo:
        faltando = [
            nome
            for nome, valor in (
                ("SENTAVOS_EMAIL", email),
                ("SENTAVOS_SENHA_HASH", hash_senha),
                ("SENTAVOS_JWT_SECRET", segredo),
            )
            if not valor
        ]
        log.error("autenticação não configurada; faltando: %s", ", ".join(faltando))
        raise ConfiguracaoIncompleta(", ".join(faltando))

    return email, hash_senha, segredo


def _epoca_minima() -> int:
    """Tokens emitidos antes deste instante não valem mais.

    É o botão de "desconectar tudo". Sem sessão no servidor, não existe lista de
    tokens pra revogar um a um; mudar esta variável no host invalida todos de uma
    vez. Serve pra quando um aparelho some ou a senha vaza.

    O valor é um timestamp Unix. Vazio significa "nenhum corte".
    """
    bruto = (os.getenv("SENTAVOS_TOKEN_EPOCH") or "").strip()
    if not bruto:
        return 0
    try:
        return int(bruto)
    except ValueError:
        log.warning("SENTAVOS_TOKEN_EPOCH ignorado, não é inteiro: %r", bruto)
        return 0


def autenticar(email: str, senha: str) -> str:
    """Confere as credenciais e devolve um token. Estoura 401 se não baterem."""
    email_certo, hash_certo, segredo = _config()

    # compare_digest em vez de ==: comparação normal de string sai no primeiro
    # caractere diferente, e o tempo disso vaza o quanto o palpite chegou perto.
    email_bate = hmac.compare_digest(email.strip().lower(), email_certo)

    # A senha é verificada mesmo quando o e-mail já está errado. Parece
    # desperdício e não é: pular a verificação faria a resposta com e-mail errado
    # voltar muito mais rápido que a com e-mail certo, e esse tempo diria a quem
    # está sondando qual dos dois campos acertar. O Argon2 é lento por natureza,
    # então a diferença seria gritante.
    try:
        senha_bate = hasher.verify(hash_certo, senha)
    except (VerifyMismatchError, InvalidHashError):
        senha_bate = False
    except Exception as e:
        log.warning("falha ao verificar senha: %s: %s", type(e).__name__, e)
        senha_bate = False

    if not (email_bate and senha_bate):
        # Uma mensagem só pros dois casos: dizer "e-mail não existe" entregaria
        # de graça quais endereços têm conta.
        log.warning("login recusado")
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")

    agora = dt.datetime.now(dt.timezone.utc)
    return jwt.encode(
        {
            "sub": email_certo,
            "iss": EMISSOR,
            "aud": AUDIENCIA,
            "iat": agora,
            "exp": agora + VALIDADE_DO_TOKEN,
        },
        segredo,
        algorithm=ALGORITMO,
    )


def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    """Dependência que fecha as rotas de dados. Devolve o e-mail do dono."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Faltou o token de acesso.")

    try:
        email_certo, _, segredo = _config()
    except ConfiguracaoIncompleta:
        raise HTTPException(
            status_code=500, detail="Autenticação não configurada no servidor."
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            segredo,
            algorithms=[ALGORITMO],
            audience=AUDIENCIA,
            issuer=EMISSOR,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
    except jwt.PyJWTError as e:
        # Assinatura errada, expirado e malformado caem todos aqui: pro cliente é
        # a mesma coisa (entre de novo), e detalhar só ajudaria quem sonda. No
        # log vai o motivo, sem o token.
        log.warning("token recusado: %s: %s", type(e).__name__, e)
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada.")

    corte = _epoca_minima()
    if corte and payload.get("iat", 0) < corte:
        log.warning("token anterior ao corte de época (iat=%s)", payload.get("iat"))
        raise HTTPException(status_code=401, detail="Sessão encerrada. Entre de novo.")

    # O e-mail no token tem que ser o configurado agora. Sem isto, trocar o
    # SENTAVOS_EMAIL deixaria os tokens do endereço antigo valendo.
    if not hmac.compare_digest(str(payload.get("sub", "")), email_certo):
        log.warning("sub não confere com o e-mail configurado")
        raise HTTPException(status_code=403, detail="Esta conta não tem acesso.")

    return email_certo
