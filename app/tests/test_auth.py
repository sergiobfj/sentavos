"""Cobre a autenticação própria: login, token e o fechamento das rotas.

Substituiu os testes do Supabase Auth, que saíram junto com a dependência.
"""

import datetime as dt

import jwt
import pytest

from app import auth

EMAIL = "sergio@exemplo.com"
SENHA = "uma-senha-longa-o-bastante"
SEGREDO = "segredo-de-teste-com-tamanho-suficiente-pra-hs256"

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


@pytest.fixture(name="configurado")
def configurado_fixture(monkeypatch):
    """Servidor com acesso configurado, como estaria em produção."""
    monkeypatch.setenv("SENTAVOS_EMAIL", EMAIL)
    monkeypatch.setenv("SENTAVOS_SENHA_HASH", auth.gerar_hash(SENHA))
    monkeypatch.setenv("SENTAVOS_JWT_SECRET", SEGREDO)
    monkeypatch.delenv("SENTAVOS_TOKEN_EPOCH", raising=False)


def token_valido(anon_client) -> str:
    r = anon_client.post("/auth/login", json={"email": EMAIL, "senha": SENHA})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def forjar(
    sub=EMAIL,
    segredo=SEGREDO,
    minutos=10,
    aud=auth.AUDIENCIA,
    iss=auth.EMISSOR,
    iat_offset=0,
    alg="HS256",
):
    agora = dt.datetime.now(dt.timezone.utc)
    corpo = {
        "sub": sub,
        "iss": iss,
        "aud": aud,
        "iat": agora + dt.timedelta(seconds=iat_offset),
        "exp": agora + dt.timedelta(minutes=minutos),
    }
    return jwt.encode(corpo, segredo, algorithm=alg)


# ---------- Login ----------

def test_login_com_credenciais_certas_devolve_token(anon_client, configurado):
    r = anon_client.post("/auth/login", json={"email": EMAIL, "senha": SENHA})

    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"
    assert r.json()["access_token"]


def test_login_aceita_email_com_maiuscula_e_espaco(anon_client, configurado):
    """Ninguém digita e-mail com cuidado no teclado do celular."""
    r = anon_client.post(
        "/auth/login", json={"email": f"  {EMAIL.upper()} ", "senha": SENHA}
    )

    assert r.status_code == 200


def test_senha_errada_da_401(anon_client, configurado):
    r = anon_client.post("/auth/login", json={"email": EMAIL, "senha": "chute"})

    assert r.status_code == 401


def test_email_errado_da_401(anon_client, configurado):
    r = anon_client.post(
        "/auth/login", json={"email": "outro@exemplo.com", "senha": SENHA}
    )

    assert r.status_code == 401


def test_email_e_senha_errados_dao_a_mesma_mensagem(anon_client, configurado):
    """Mensagens diferentes entregariam quais e-mails têm conta."""
    so_email = anon_client.post(
        "/auth/login", json={"email": "outro@exemplo.com", "senha": SENHA}
    )
    so_senha = anon_client.post("/auth/login", json={"email": EMAIL, "senha": "chute"})

    assert so_email.json()["detail"] == so_senha.json()["detail"]


def test_sem_config_no_servidor_da_500_e_nao_deixa_entrar(anon_client, monkeypatch):
    """Falta de configuração não pode virar porta aberta."""
    for var in ("SENTAVOS_EMAIL", "SENTAVOS_SENHA_HASH", "SENTAVOS_JWT_SECRET"):
        monkeypatch.delenv(var, raising=False)

    r = anon_client.post("/auth/login", json={"email": EMAIL, "senha": SENHA})

    assert r.status_code == 500


# ---------- Token nas rotas ----------

def test_token_do_login_abre_as_rotas(anon_client, configurado):
    token = token_valido(anon_client)

    r = anon_client.get("/transactions", headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 200


@pytest.mark.parametrize("metodo,rota", ROTAS)
def test_rota_sem_token_da_401(anon_client, configurado, metodo, rota):
    r = getattr(anon_client, metodo)(rota)

    assert r.status_code == 401


def test_token_assinado_com_outro_segredo_da_401(anon_client, configurado):
    intruso = forjar(segredo="outro-segredo-qualquer-mas-do-tamanho-certo")

    r = anon_client.get("/transactions", headers={"Authorization": f"Bearer {intruso}"})

    assert r.status_code == 401


def test_token_expirado_da_401(anon_client, configurado):
    r = anon_client.get(
        "/transactions", headers={"Authorization": f"Bearer {forjar(minutos=-5)}"}
    )

    assert r.status_code == 401


def test_alg_none_e_recusado(anon_client, configurado):
    """Sem a lista fechada de algoritmos, um token sem assinatura passaria."""
    sem_assinatura = jwt.encode(
        {"sub": EMAIL, "iss": auth.EMISSOR, "aud": auth.AUDIENCIA},
        key=None,
        algorithm="none",
    )

    r = anon_client.get(
        "/transactions", headers={"Authorization": f"Bearer {sem_assinatura}"}
    )

    assert r.status_code == 401


def test_audiencia_errada_da_401(anon_client, configurado):
    r = anon_client.get(
        "/transactions", headers={"Authorization": f"Bearer {forjar(aud='outra')}"}
    )

    assert r.status_code == 401


def test_emissor_errado_da_401(anon_client, configurado):
    r = anon_client.get(
        "/transactions", headers={"Authorization": f"Bearer {forjar(iss='outro')}"}
    )

    assert r.status_code == 401


def test_token_de_outro_email_da_403(anon_client, configurado):
    """Trocar o SENTAVOS_EMAIL tem que invalidar o token do endereço antigo."""
    r = anon_client.get(
        "/transactions",
        headers={"Authorization": f"Bearer {forjar(sub='antigo@exemplo.com')}"},
    )

    assert r.status_code == 403


def test_lixo_no_header_da_401(anon_client, configurado):
    # Cabeçalho HTTP só aceita ASCII, então o lixo aqui é ASCII de propósito.
    r = anon_client.get("/transactions", headers={"Authorization": "Bearer nao.eh.jwt"})

    assert r.status_code == 401


# ---------- Revogação ----------

def test_token_epoch_invalida_tokens_antigos(anon_client, configurado, monkeypatch):
    """O botão de "desconectar tudo".

    Sem sessão no servidor não há lista de tokens pra revogar um a um. Mover
    esta variável pra frente invalida todos de uma vez — é o que se usa quando
    um aparelho some.
    """
    token = token_valido(anon_client)
    cabecalho = {"Authorization": f"Bearer {token}"}

    assert anon_client.get("/transactions", headers=cabecalho).status_code == 200

    daqui_a_pouco = int(dt.datetime.now(dt.timezone.utc).timestamp()) + 60
    monkeypatch.setenv("SENTAVOS_TOKEN_EPOCH", str(daqui_a_pouco))

    assert anon_client.get("/transactions", headers=cabecalho).status_code == 401


def test_token_epoch_invalido_e_ignorado_em_vez_de_travar_tudo(
    anon_client, configurado, monkeypatch
):
    """Erro de digitação nessa variável não pode trancar o dono pra fora."""
    monkeypatch.setenv("SENTAVOS_TOKEN_EPOCH", "ontem")
    token = token_valido(anon_client)

    r = anon_client.get("/transactions", headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 200


# ---------- Hash ----------

def test_hash_nao_contem_a_senha(monkeypatch):
    h = auth.gerar_hash(SENHA)

    assert SENHA not in h
    assert h.startswith("$argon2id$")


def test_hashes_da_mesma_senha_sao_diferentes():
    """Salt aleatório: senhas iguais não podem gerar hashes iguais."""
    assert auth.gerar_hash(SENHA) != auth.gerar_hash(SENHA)
