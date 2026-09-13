"""Cobre as defesas de borda: cota por IP, cabeçalhos e tamanho de corpo.

O conftest zera os limites antes de cada teste, então cada um aqui começa com a
cota cheia e conta a partir do zero.
"""

import pytest

from app import security


def test_cabecalhos_de_seguranca_vem_na_resposta(client):
    r = client.get("/categories")

    assert r.status_code == 200
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    # Extrato financeiro não pode ficar em cache de proxy.
    assert r.headers["Cache-Control"] == "no-store"


def test_sem_hsts_em_http(client):
    """HSTS em http:// travaria o navegador do dev no localhost."""
    r = client.get("/categories")

    assert "Strict-Transport-Security" not in r.headers


def test_docs_desligados_por_padrao(anon_client):
    """O mapa da API não fica aberto pra quem só tem a URL."""
    for rota in ("/docs", "/redoc", "/openapi.json"):
        assert anon_client.get(rota).status_code == 404, rota


def test_estouro_da_cota_geral_da_429(client, monkeypatch):
    monkeypatch.setattr(security, "TETO_POR_JANELA", 5)

    for _ in range(5):
        assert client.get("/categories").status_code == 200

    r = client.get("/categories")

    assert r.status_code == 429
    # Sem o Retry-After o cliente honesto fica martelando e afunda na cota.
    assert r.headers["Retry-After"] == str(security.JANELA_SEGUNDOS)


def test_falhas_de_credencial_tem_cota_propria_e_mais_apertada(anon_client, monkeypatch):
    """Tentar token até acertar tem que ficar inviável.

    O anon_client não manda token, então toda chamada é 401. Depois do teto, a
    resposta vira 429 — e o atacante deixa de conseguir medir se o token estava
    perto ou longe de certo.
    """
    monkeypatch.setattr(security, "TETO_DE_FALHAS", 3)

    for _ in range(3):
        assert anon_client.get("/transactions").status_code == 401

    r = anon_client.get("/transactions")

    assert r.status_code == 429
    assert r.headers["Retry-After"] == str(security.JANELA_FALHAS_SEGUNDOS)


def test_cota_de_falhas_e_menor_que_a_geral_na_pratica(anon_client, monkeypatch):
    """Quem erra credencial é barrado antes de quem só está usando o app.

    É a razão de existirem duas cotas: se fossem a mesma, ou o uso normal
    apertaria demais, ou a sondagem de token ficaria barata.

    Só o anon_client entra aqui de propósito: pedir a fixture `client` junto
    registraria o override de require_user no mesmo `app`, e o anon_client
    passaria a responder 200 — o teste mediria a coisa errada.
    """
    monkeypatch.setattr(security, "TETO_DE_FALHAS", 2)
    monkeypatch.setattr(security, "TETO_POR_JANELA", 100)

    for _ in range(2):
        anon_client.get("/transactions")

    # Estourou a cota de falhas com 2 chamadas, muito antes das 100 gerais.
    assert anon_client.get("/transactions").status_code == 429


def test_healthcheck_nao_gasta_cota(anon_client, monkeypatch):
    """O Railway bate no / de minuto em minuto.

    Se isso gastasse cota, o próprio healthcheck acabaria derrubando o serviço
    que veio checar.
    """
    monkeypatch.setattr(security, "TETO_POR_JANELA", 3)

    for _ in range(10):
        assert anon_client.get("/").status_code == 200


def test_corpo_grande_demais_da_413(client):
    gigante = "x" * (security.TAMANHO_MAXIMO_DO_CORPO + 1)

    r = client.post("/categories", content=gigante, headers={"Content-Type": "application/json"})

    assert r.status_code == 413


def test_corpo_de_tamanho_normal_passa(client):
    r = client.post(
        "/categories",
        json={"name": "Mercado", "type": "expense", "color": "#fff", "icon": "🛒"},
    )

    assert r.status_code == 200


@pytest.mark.parametrize("valor", ["abc", "", " "])
def test_content_length_invalido_nao_derruba_a_api(client, valor):
    """Cabeçalho malformado é 400, não 500.

    O httpx recalcula o Content-Length real, então o que se exercita aqui é o
    parse não estourar exceção — que era o risco do int() sem guarda.
    """
    r = client.post(
        "/categories",
        json={"name": "X", "type": "expense", "color": "#fff", "icon": "x"},
        headers={"Content-Length": valor},
    )

    assert r.status_code in (200, 400)
