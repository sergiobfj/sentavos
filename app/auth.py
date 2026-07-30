import os

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# Valida o JWT que o Supabase Auth emite pro front. O Sentavos é app pessoal:
# não existe dono por linha, existe uma conta que pode entrar e mais nenhuma.

# auto_error=False pra devolver 401 na falta de token. O padrão do HTTPBearer é
# 403, que significa "te conheço e não pode" — o certo aqui é "não te conheço".
bearer = HTTPBearer(auto_error=False)


def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Faltou o token de acesso.")

    # Lido a cada chamada (e não no import) pra o teste conseguir trocar.
    secret = os.getenv("SUPABASE_JWT_SECRET")
    allowed_user = os.getenv("SENTAVOS_ALLOWED_USER_ID")

    # Falha fechada de propósito. Se faltasse config e a gente deixasse passar,
    # um projeto Supabase com cadastro aberto viraria porta de entrada: qualquer
    # pessoa cria conta, recebe token válido e entra nas suas finanças.
    if not secret or not allowed_user:
        raise HTTPException(
            status_code=500,
            detail="Autenticação não configurada no servidor.",
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            secret,
            algorithms=["HS256"],
            # O Supabase emite aud="authenticated" pra usuário logado.
            audience="authenticated",
        )
    except jwt.PyJWTError:
        # Assinatura errada, expirado e malformado caem todos aqui: pro cliente
        # é a mesma coisa (entre de novo), e detalhar só ajudaria quem sonda.
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada.")

    if payload.get("sub") != allowed_user:
        raise HTTPException(status_code=403, detail="Esta conta não tem acesso ao Sentavos.")

    return payload["sub"]
