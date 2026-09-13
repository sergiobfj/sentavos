"""Cobre a autenticação: login contra o banco, token e fechamento das rotas.

Passou por três esquemas: Supabase Auth, depois uma conta só com e-mail e hash
em variável de ambiente, agora contas em tabela. Estes testes acompanham o
último — e o de isolamento, no arquivo ao lado, cobre o que muda quando há mais
de uma pessoa.
"""

import datetime as dt

import jwt
import pytest

from app import auth
from app.tests.conftest import SEGREDO_DE_TESTE

EMAIL = "sergio@exemplo.com"
SENHA = "uma-senha-longa-o-bastante"

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


@pytest.fixture(name="conta")
def conta_fixture(criar_usuario):
    return criar_usuario(EMAIL, "Sergio", SENHA)


def forjar(
    sub,
    segredo=SEGREDO_DE_TESTE,
    minutos=10,
    aud=auth.AUDIENCIA,
    iss=auth.EMISSOR,
    iat_offset=0,
    alg="HS256",
):
    agora = dt.datetime.now(dt.timezone.utc)
    corpo = {
        "sub": str(sub),
        "iss": iss,
        "aud": aud,
        "iat": agora + dt.timedelta(seconds=iat_offset),
        "exp": agora + dt.timedelta(minutes=minutos),
    }
    return jwt.encode(corpo, segredo, algorithm=alg)


# ---------- Login ----------

def test_login_com_credenciais_certas_devolve_token(anon_client, conta):
    r = anon_client.post("/auth/login", json={"email": EMAIL, "senha": SENHA})

    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"

    payload = jwt.decode(
        r.json()["access_token"], SEGREDO_DE_TESTE, algorithms=["HS256"],
        audience=auth.AUDIENCIA, issuer=auth.EMISSOR,
    )
    assert payload["sub"] == str(conta.id)
    assert payload["ro"] is False


def test_login_aceita_email_com_maiuscula_e_espaco(anon_client, conta):
    """Ninguém digita e-mail com cuidado no teclado do celular."""
    r = anon_client.post(
        "/auth/login", json={"email": f"  {EMAIL.upper()} ", "senha": SENHA}
    )

    assert r.status_code == 200


def test_senha_errada_da_401(anon_client, conta):
    r = anon_client.post("/auth/login", json={"email": EMAIL, "senha": "chute"})

    assert r.status_code == 401


def test_conta_inexistente_da_401(anon_client, conta):
    r = anon_client.post(
        "/auth/login", json={"email": "ninguem@exemplo.com", "senha": SENHA}
    )

    assert r.status_code == 401


def test_conta_inexistente_e_senha_errada_dao_a_mesma_mensagem(anon_client, conta):
    """Mensagens diferentes entregariam quais e-mails têm conta."""
    sem_conta = anon_client.post(
        "/auth/login", json={"email": "ninguem@exemplo.com", "senha": SENHA}
    )
    senha_ruim = anon_client.post("/auth/login", json={"email": EMAIL, "senha": "chute"})

    assert sem_conta.json()["detail"] == senha_ruim.json()["detail"]


def test_login_do_demo_marca_somente_leitura_no_token(anon_client, criar_usuario):
    """O front lê esta marca pra esconder os botões de escrita.

    É conveniência de tela: quem barra de verdade é a checagem no servidor, que
    não confia no que o cliente diz.
    """
    criar_usuario("demo@exemplo.com", "Demo", SENHA, read_only=True)

    r = anon_client.post("/auth/login", json={"email": "demo@exemplo.com", "senha": SENHA})

    payload = jwt.decode(
        r.json()["access_token"], SEGREDO_DE_TESTE, algorithms=["HS256"],
        audience=auth.AUDIENCIA, issuer=auth.EMISSOR,
    )
    assert payload["ro"] is True


def test_sem_segredo_no_servidor_da_500(anon_client, conta, monkeypatch):
    """Falta de configuração não pode virar porta aberta."""
    monkeypatch.delenv("SENTAVOS_JWT_SECRET", raising=False)

    r = anon_client.post("/auth/login", json={"email": EMAIL, "senha": SENHA})

    assert r.status_code == 500


# ---------- Token nas rotas ----------

def test_token_do_login_abre_as_rotas(anon_client, conta):
    token = anon_client.post(
        "/auth/login", json={"email": EMAIL, "senha": SENHA}
    ).json()["access_token"]

    r = anon_client.get("/transactions", headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 200


@pytest.mark.parametrize("metodo,rota", ROTAS)
def test_rota_sem_token_da_401(anon_client, conta, metodo, rota):
    r = getattr(anon_client, metodo)(rota)

    assert r.status_code == 401


def test_token_assinado_com_outro_segredo_da_401(anon_client, conta):
    intruso = forjar(conta.id, segredo="outro-segredo-qualquer-mas-do-tamanho-certo")

    r = anon_client.get("/transactions", headers={"Authorization": f"Bearer {intruso}"})

    assert r.status_code == 401


def test_token_expirado_da_401(anon_client, conta):
    r = anon_client.get(
        "/transactions",
        headers={"Authorization": f"Bearer {forjar(conta.id, minutos=-5)}"},
    )

    assert r.status_code == 401


def test_alg_none_e_recusado(anon_client, conta):
    """Sem a lista fechada de algoritmos, um token sem assinatura passaria."""
    sem_assinatura = jwt.encode(
        {"sub": str(conta.id), "iss": auth.EMISSOR, "aud": auth.AUDIENCIA},
        key=None,
        algorithm="none",
    )

    r = anon_client.get(
        "/transactions", headers={"Authorization": f"Bearer {sem_assinatura}"}
    )

    assert r.status_code == 401


def test_audiencia_errada_da_401(anon_client, conta):
    r = anon_client.get(
        "/transactions", headers={"Authorization": f"Bearer {forjar(conta.id, aud='outra')}"}
    )

    assert r.status_code == 401


def test_emissor_errado_da_401(anon_client, conta):
    r = anon_client.get(
        "/transactions", headers={"Authorization": f"Bearer {forjar(conta.id, iss='outro')}"}
    )

    assert r.status_code == 401


def test_token_de_conta_que_nao_existe_mais_da_401(anon_client, conta):
    """O usuário é relido do banco a cada requisição, e não tirado do token.

    É o que faz apagar uma conta valer na hora, em vez de só quando o token de
    30 dias vencer.
    """
    r = anon_client.get(
        "/transactions", headers={"Authorization": f"Bearer {forjar(99999)}"}
    )

    assert r.status_code == 401


def test_lixo_no_header_da_401(anon_client, conta):
    # Cabeçalho HTTP só aceita ASCII, então o lixo aqui é ASCII de propósito.
    r = anon_client.get("/transactions", headers={"Authorization": "Bearer nao.eh.jwt"})

    assert r.status_code == 401


# ---------- Revogação ----------

def test_token_epoch_invalida_tokens_antigos(anon_client, conta, monkeypatch):
    """O botão de "desconectar tudo".

    Sem sessão no servidor não há lista de tokens pra revogar um a um. Mover
    esta variável pra frente invalida todos de uma vez — é o que se usa quando
    um aparelho some.
    """
    cabecalho = {"Authorization": f"Bearer {forjar(conta.id)}"}
    assert anon_client.get("/transactions", headers=cabecalho).status_code == 200

    daqui_a_pouco = int(dt.datetime.now(dt.timezone.utc).timestamp()) + 60
    monkeypatch.setenv("SENTAVOS_TOKEN_EPOCH", str(daqui_a_pouco))

    assert anon_client.get("/transactions", headers=cabecalho).status_code == 401


def test_token_epoch_invalido_e_ignorado_em_vez_de_travar_tudo(
    anon_client, conta, monkeypatch
):
    """Erro de digitação nessa variável não pode trancar o dono pra fora."""
    monkeypatch.setenv("SENTAVOS_TOKEN_EPOCH", "ontem")

    r = anon_client.get(
        "/transactions", headers={"Authorization": f"Bearer {forjar(conta.id)}"}
    )

    assert r.status_code == 200


# ---------- Hash ----------

def test_hash_nao_contem_a_senha():
    h = auth.gerar_hash(SENHA)

    assert SENHA not in h
    assert h.startswith("$argon2id$")


def test_hashes_da_mesma_senha_sao_diferentes():
    """Salt aleatório: senhas iguais não podem gerar hashes iguais."""
    assert auth.gerar_hash(SENHA) != auth.gerar_hash(SENHA)
