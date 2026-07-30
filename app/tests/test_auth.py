import datetime as dt

import jwt
import pytest

# 32+ bytes: abaixo disso o pyjwt avisa que a chave é curta pra HS256, e o
# segredo real do Supabase é longo mesmo.
SECRET = "segredo-de-teste-com-tamanho-suficiente-pra-hs256"
USER_ID = "11111111-1111-1111-1111-111111111111"

# Uma rota de cada recurso. Se a proteção cair do router, alguma cai aqui.
ROTAS = [
    ("get", "/transactions"),
    ("post", "/transactions"),
    ("get", "/categories"),
    ("post", "/categories"),
    ("get", "/budgets"),
    ("put", "/budgets"),
    ("get", "/budgets/summary"),
    ("get", "/assets"),
    ("post", "/assets"),
    ("get", "/assets/summary"),
    ("put", "/assets/snapshots"),
]


@pytest.fixture(name="configured")
def configured_fixture(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setenv("SENTAVOS_ALLOWED_USER_ID", USER_ID)


def token(sub=USER_ID, secret=SECRET, expira_em_minutos=10, aud="authenticated"):
    agora = dt.datetime.now(dt.timezone.utc)
    return jwt.encode(
        {
            "sub": sub,
            "aud": aud,
            "exp": agora + dt.timedelta(minutes=expira_em_minutos),
            "iat": agora,
        },
        secret,
        algorithm="HS256",
    )


def chamar(client, metodo, rota, headers=None):
    return getattr(client, metodo)(rota, headers=headers or {}, **({} if metodo == "get" else {"json": {}}))


@pytest.mark.parametrize("metodo,rota", ROTAS)
def test_rota_sem_token_da_401(anon_client, configured, metodo, rota):
    assert chamar(anon_client, metodo, rota).status_code == 401


def test_raiz_continua_publica(anon_client):
    # Health check do host não pode exigir token, senão o deploy parece morto.
    assert anon_client.get("/").status_code == 200


def test_token_valido_entra(anon_client, configured):
    r = anon_client.get("/transactions", headers={"Authorization": f"Bearer {token()}"})

    assert r.status_code == 200


def test_token_assinado_com_outro_segredo_da_401(anon_client, configured):
    # É o caso que importa: sem verificar assinatura, qualquer um forja o sub.
    forjado = token(secret="outro-segredo-igualmente-longo-mas-errado")

    r = anon_client.get("/transactions", headers={"Authorization": f"Bearer {forjado}"})

    assert r.status_code == 401


def test_token_expirado_da_401(anon_client, configured):
    r = anon_client.get(
        "/transactions", headers={"Authorization": f"Bearer {token(expira_em_minutos=-5)}"}
    )

    assert r.status_code == 401


def test_outro_usuario_do_mesmo_projeto_da_403(anon_client, configured):
    # Projeto Supabase com cadastro aberto emite token válido pra qualquer um.
    # A assinatura confere; o que barra é o sub não ser o dono.
    intruso = token(sub="22222222-2222-2222-2222-222222222222")

    r = anon_client.get("/transactions", headers={"Authorization": f"Bearer {intruso}"})

    assert r.status_code == 403


def test_audience_errada_da_401(anon_client, configured):
    r = anon_client.get(
        "/transactions", headers={"Authorization": f"Bearer {token(aud='outra')}"}
    )

    assert r.status_code == 401


def test_lixo_no_header_da_401(anon_client, configured):
    r = anon_client.get("/transactions", headers={"Authorization": "Bearer nao-e-um-jwt"})

    assert r.status_code == 401


def test_sem_config_no_servidor_nao_libera(anon_client, monkeypatch):
    # Falha fechada: faltando variável, ninguém entra — nem com token bom.
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    monkeypatch.delenv("SENTAVOS_ALLOWED_USER_ID", raising=False)

    r = anon_client.get("/transactions", headers={"Authorization": f"Bearer {token()}"})

    assert r.status_code == 500
    assert r.status_code != 200
