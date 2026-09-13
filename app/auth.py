"""Autenticação do Sentavos: contas no banco, token assinado pela própria API.

Antes isto era Supabase Auth, e depois uma conta só com e-mail e hash em
variável de ambiente. Virou tabela quando apareceram três contas: a principal,
uma de demonstração pública e a de outra pessoa. O que continua no ambiente é o
`SENTAVOS_JWT_SECRET` — ele assina os tokens de todo mundo, então é do servidor
e não de uma pessoa.

O desenho segue mínimo de propósito:

  - A senha nunca é guardada; só o hash Argon2id, de onde não se volta.
  - O login troca e-mail + senha por um JWT que diz quem é o dono.
  - Não há sessão no servidor. Nada pra expirar, sincronizar ou perder num
    redeploy — e o preço disso está no SENTAVOS_TOKEN_EPOCH lá embaixo.

Não tem cadastro aberto: conta se cria pelo `python -m app.criar_usuario`. Num
app de três pessoas, um formulário de cadastro seria superfície pra proteger
sem ninguém pra usar.
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
from sqlmodel import Session, select

from app.database import get_session
from app.models import User

# O cliente recebe 401 genérico de propósito (detalhar ajuda quem sonda), mas o
# servidor precisa saber o motivo — senão "recusou a sessão" é indepurável.
log = logging.getLogger("sentavos.auth")

# Só HS256. A lista é fechada porque é ela que impede um token com alg="none"
# (ou trocado pra confundir o verificador) de ser aceito.
ALGORITMO = "HS256"

# Validade longa de propósito: é um app pessoal aberto no celular, e token de 1
# hora significaria digitar senha toda vez. O preço é um token roubado servir
# por até 30 dias — mitigado pelo SENTAVOS_TOKEN_EPOCH.
VALIDADE_DO_TOKEN = dt.timedelta(days=30)

EMISSOR = "sentavos"
AUDIENCIA = "sentavos-app"

# auto_error=False pra devolver 401 na falta de token. O padrão do HTTPBearer é
# 403, que significa "te conheço e não pode" — o certo aqui é "não te conheço".
bearer = HTTPBearer(auto_error=False)

# Parâmetros padrão do argon2-cffi (Argon2id). Não customizados de propósito: a
# biblioteca os atualiza conforme o hardware evolui, e um número escolhido à mão
# hoje envelheceria mal e em silêncio.
hasher = PasswordHasher()

# Hash descartável pra gastar tempo quando o e-mail não existe. Sem ele, "e-mail
# inexistente" responderia na hora e "e-mail certo, senha errada" levaria o
# tempo do Argon2 — e essa diferença diria a quem sonda quais contas existem.
_HASH_FALSO = hasher.hash("nao-existe-ninguem-com-esta-senha")


class ConfiguracaoIncompleta(RuntimeError):
    """Falta o segredo que assina os tokens."""


def gerar_hash(senha: str) -> str:
    """Hash Argon2id da senha. Usado pelo `python -m app.criar_usuario`."""
    return hasher.hash(senha)


def _segredo() -> str:
    valor = os.getenv("SENTAVOS_JWT_SECRET") or ""
    if not valor:
        log.error("SENTAVOS_JWT_SECRET não configurada")
        raise ConfiguracaoIncompleta("SENTAVOS_JWT_SECRET")
    return valor


def _epoca_minima() -> int:
    """Tokens emitidos antes deste instante não valem mais.

    É o botão de "desconectar tudo". Sem sessão no servidor, não existe lista de
    tokens pra revogar um a um; mudar esta variável no host invalida todos de
    uma vez. Serve pra quando um aparelho some ou uma senha vaza.
    """
    bruto = (os.getenv("SENTAVOS_TOKEN_EPOCH") or "").strip()
    if not bruto:
        return 0
    try:
        return int(bruto)
    except ValueError:
        log.warning("SENTAVOS_TOKEN_EPOCH ignorado, não é inteiro: %r", bruto)
        return 0


def autenticar(email: str, senha: str, session: Session) -> str:
    """Confere as credenciais e devolve um token. Estoura 401 se não baterem."""
    segredo = _segredo()
    alvo = (email or "").strip().lower()

    usuario = session.exec(select(User).where(User.email == alvo)).first()

    # A senha é verificada mesmo quando a conta não existe, contra um hash
    # descartável. Parece desperdício e não é: o Argon2 é lento por natureza, e
    # pular a verificação faria a resposta de e-mail inexistente voltar muito
    # mais rápido — o tempo entregaria quais contas existem.
    try:
        senha_bate = hasher.verify(usuario.password_hash if usuario else _HASH_FALSO, senha)
    except (VerifyMismatchError, InvalidHashError):
        senha_bate = False
    except Exception as e:
        log.warning("falha ao verificar senha: %s: %s", type(e).__name__, e)
        senha_bate = False

    if usuario is None or not senha_bate:
        # Uma mensagem só pros dois casos: dizer "e-mail não existe" entregaria
        # de graça quais endereços têm conta.
        log.warning("login recusado")
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")

    agora = dt.datetime.now(dt.timezone.utc)
    return jwt.encode(
        {
            "sub": str(usuario.id),
            "email": usuario.email,
            "nome": usuario.name,
            # O front lê isto pra esconder os botões de escrita da conta de
            # demonstração. É conveniência de tela: quem manda de verdade é a
            # checagem no servidor, que não confia no que o cliente diz.
            "ro": usuario.read_only,
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
    session: Session = Depends(get_session),
) -> User:
    """Dependência que fecha as rotas. Devolve o usuário dono da requisição.

    Devolve o objeto inteiro, e não só o id, porque é dele que sai o filtro de
    toda consulta e a trava de escrita da conta de demonstração — deixar as
    rotas irem buscar o usuário de novo seria uma ida ao banco por rota e uma
    chance a mais de alguém pular a checagem.
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Faltou o token de acesso.")

    try:
        segredo = _segredo()
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
        # Assinatura errada, expirado e malformado caem todos aqui: pro cliente
        # é a mesma coisa (entre de novo), e detalhar só ajudaria quem sonda.
        log.warning("token recusado: %s: %s", type(e).__name__, e)
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada.")

    corte = _epoca_minima()
    if corte and payload.get("iat", 0) < corte:
        log.warning("token anterior ao corte de época")
        raise HTTPException(status_code=401, detail="Sessão encerrada. Entre de novo.")

    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada.")

    # O usuário é relido do banco a cada requisição, e não tirado do token. É o
    # que faz "apagar a conta" e "virar somente-leitura" valerem na hora, em vez
    # de só quando o token de 30 dias vencer.
    usuario = session.get(User, user_id)
    if usuario is None:
        log.warning("token de usuário inexistente: %s", user_id)
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada.")

    return usuario


def exigir_escrita(usuario: User) -> None:
    """Barra escrita de conta somente-leitura.

    A conta de demonstração tem senha pública, então isto é o que impede o
    primeiro visitante de apagar o demo inteiro. Fica no servidor porque
    esconder botão no front não protege nada: qualquer um manda um POST na mão.
    """
    if usuario.read_only:
        raise HTTPException(
            status_code=403,
            detail="Esta é uma conta de demonstração: dá pra navegar, mas não alterar.",
        )


def email_igual(a: str, b: str) -> bool:
    """Comparação em tempo constante, pra não vazar acerto parcial pelo tempo."""
    return hmac.compare_digest(a.strip().lower(), b.strip().lower())
