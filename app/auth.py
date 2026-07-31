import logging
import os
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# O cliente recebe 401 genérico de propósito (detalhar ajuda quem sonda), mas o
# servidor precisa saber o motivo — senão "recusou a sessão" é indepurável.
log = logging.getLogger("sentavos.auth")

# Valida o JWT que o Supabase Auth emite pro front. O Sentavos é app pessoal:
# não existe dono por linha, existe uma conta que pode entrar e mais nenhuma.

# O Supabase tem dois esquemas de assinatura, e projeto novo já nasce no segundo:
#
#   HS256  — segredo compartilhado (o "JWT Secret" do painel). Caminho legado.
#   ES256/RS256 — par de chaves; a pública sai no endpoint JWKS do projeto.
#
# Aceitar os dois evita que a auth quebre quando o projeto migra ou rotaciona a
# chave. A lista é fechada de propósito: ela é o que impede um token com
# alg="none" (ou trocado pra confundir o verificador) de ser aceito.
ALGORITMOS_ACEITOS = {"HS256", "ES256", "RS256"}

# Tolerância de relógio na verificação de exp/nbf/iat.
#
# Sem ela, um punhado de segundos de diferença entre esta máquina e o servidor do
# Supabase derruba o login: o token chega com iat "no futuro" e o PyJWT recusa
# com ImmatureSignatureError. Não é hipótese — foi o que aconteceu aqui com 2s de
# desvio, e nenhum relógio fica perfeitamente sincronizado.
#
# O preço é aceitar um token expirado por até este tempo a mais. Com token de 1
# hora e refresh automático no front, é troca barata; o alternativo é login que
# falha de forma intermitente e inexplicável.
FOLGA_DE_RELOGIO_SEGUNDOS = 60

# auto_error=False pra devolver 401 na falta de token. O padrão do HTTPBearer é
# 403, que significa "te conheço e não pode" — o certo aqui é "não te conheço".
bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=4)
def _cliente_jwks(url: str) -> jwt.PyJWKClient:
    # Cacheado: senão cada request buscaria as chaves do Supabase de novo.
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=3600)


def _jwks_url() -> str | None:
    base = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    return f"{base}/auth/v1/.well-known/jwks.json" if base else None


def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Faltou o token de acesso.")

    token = credentials.credentials

    # Lido a cada chamada (e não no import) pra o teste conseguir trocar.
    allowed_user = os.getenv("SENTAVOS_ALLOWED_USER_ID")
    secret = os.getenv("SUPABASE_JWT_SECRET")
    jwks_url = _jwks_url()

    # Falha fechada de propósito. Se faltasse config e a gente deixasse passar,
    # um projeto Supabase com cadastro aberto viraria porta de entrada: qualquer
    # pessoa cria conta, recebe token válido e entra nas suas finanças.
    if not allowed_user or not (secret or jwks_url):
        raise HTTPException(
            status_code=500,
            detail="Autenticação não configurada no servidor.",
        )

    try:
        cabecalho = jwt.get_unverified_header(token)
    except jwt.PyJWTError as e:
        log.warning("header ilegível: %s: %s", type(e).__name__, e)
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada.")

    alg = cabecalho.get("alg")
    if alg not in ALGORITMOS_ACEITOS:
        log.warning("alg recusado: %r (aceitos: %s)", alg, sorted(ALGORITMOS_ACEITOS))
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada.")

    # A chave vem do alg declarado, mas isso não é brecha: pra HS256 usamos um
    # segredo que o atacante não tem, e pra ES256/RS256 a pública do projeto.
    # Trocar o alg no header só troca a chave contra a qual ele precisa acertar.
    if alg == "HS256":
        if not secret:
            raise HTTPException(status_code=401, detail="Sessão inválida ou expirada.")
        chave = secret
    else:
        if not jwks_url:
            raise HTTPException(status_code=401, detail="Sessão inválida ou expirada.")
        try:
            chave = _cliente_jwks(jwks_url).get_signing_key_from_jwt(token).key
        except jwt.PyJWTError as e:
            log.warning(
                "chave não encontrada no JWKS (kid=%r, url=%s): %s: %s",
                cabecalho.get("kid"), jwks_url, type(e).__name__, e,
            )
            raise HTTPException(status_code=401, detail="Sessão inválida ou expirada.")
        except Exception as e:
            # JWKS fora do ar é problema do servidor, não credencial ruim. Dizer
            # 401 aqui mandaria o usuário tentar de novo pra sempre.
            log.warning("JWKS inacessível (url=%s): %s: %s", jwks_url, type(e).__name__, e)
            raise HTTPException(
                status_code=503,
                detail="Não consegui verificar a sessão agora. Tente em instantes.",
            )

    try:
        payload = jwt.decode(
            token,
            chave,
            algorithms=[alg],
            # O Supabase emite aud="authenticated" pra usuário logado.
            audience="authenticated",
            leeway=FOLGA_DE_RELOGIO_SEGUNDOS,
        )
    except jwt.PyJWTError as e:
        # Assinatura errada, expirado e malformado caem todos aqui: pro cliente
        # é a mesma coisa (entre de novo), e detalhar só ajudaria quem sonda.
        # No log vai o motivo, sem o token.
        log.warning("token recusado (alg=%s): %s: %s", alg, type(e).__name__, e)
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada.")

    if payload.get("sub") != allowed_user:
        log.warning("sub não autorizado: recebido=%r", payload.get("sub"))
        raise HTTPException(status_code=403, detail="Esta conta não tem acesso ao Sentavos.")

    return payload["sub"]
