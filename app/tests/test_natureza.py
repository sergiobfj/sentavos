"""Natureza do gasto: três leituras do mesmo gasto, e o total não muda.

O caso real: em outubro, Moto teve a entrada da Hunter (7.000, aquisição), a
primeira parcela do financiamento (618,08, financeiro) e os equipamentos
(500,61, consumo). O gasto total é 8.118,69 com ou sem natureza; o custo de
vida só vê os equipamentos.
"""

import datetime as dt

import pytest

from app.tests.apoio_planejamento import Montagem

HOJE = dt.date(2026, 10, 11)
D = dt.date


@pytest.fixture(name="m")
def montagem(client, monkeypatch):
    monkeypatch.setattr("app.planejamento.hoje", lambda: HOJE)
    return Montagem(client)


def caixa(m, ano=2026, mes=10) -> dict:
    r = m.c.get("/budgets/summary", params={"year": ano, "month": mes})
    assert r.status_code == 200, r.text
    return r.json()["caixa"]


def serie(m, de="2026-10", ate="2026-10", **params) -> list[dict]:
    r = m.c.get("/reports/monthly", params={"from": de, "to": ate, **params})
    assert r.status_code == 200, r.text
    return r.json()["months"]


@pytest.fixture(name="moto")
def outubro_da_moto(m):
    moto = m.categoria("Moto")
    entrada = m.lancar(moto, D(2026, 10, 2), pago=7000.0, descricao="Entrada Hunter")
    m.lancar(moto, D(2026, 10, 3), pago=500.61, descricao="Equipamentos")
    hunter = m.compromisso(moto, 618.08, D(2026, 10, 5), parcelas=48, descricao="Financiamento Hunter")
    assert m.pagar(hunter["id"], 1, D(2026, 10, 5)).status_code == 200
    return {"categoria": moto, "entrada": entrada, "hunter": hunter}


def test_sem_natureza_tudo_e_consumo_e_nada_muda(m, moto):
    c = caixa(m)
    assert c["gasto_total"] == 8118.69
    assert (c["custo_de_vida"], c["aquisicoes"], c["financeiro"]) == (8118.69, 0.0, 0.0)


def test_entrada_e_aquisicao_e_financiamento_e_financeiro(m, moto):
    antes = caixa(m)
    r = m.c.patch(f"/transactions/{moto['entrada']['id']}", json={"nature": "asset_acquisition"})
    assert r.status_code == 200, r.text
    assert r.json()["effective_nature"] == "asset_acquisition"
    r = m.c.patch(f"/commitments/{moto['hunter']['id']}", json={"nature": "financial"})
    assert r.status_code == 200, r.text

    c = caixa(m)
    # O gasto total (e o saldo do mês) não se mexem.
    assert (c["gasto_total"], c["carteira"]) == (antes["gasto_total"], antes["carteira"])
    assert (c["custo_de_vida"], c["aquisicoes"], c["financeiro"]) == (500.61, 7000.0, 618.08)

    s = serie(m)[0]
    assert (s["expense"], s["consumption"], s["asset_acquisition"], s["financial"]) == (
        8118.69, 500.61, 7000.0, 618.08)

    # A próxima baixa já nasce financeiro.
    assert m.pagar(moto["hunter"]["id"], 2, D(2026, 11, 5)).status_code == 200
    assert caixa(m, 2026, 11)["financeiro"] == 618.08


def test_baixa_escolhida_a_mao_nao_e_levada_pelo_compromisso(m, moto):
    baixa = next(t for t in m.c.get("/transactions").json() if t["commitment_id"] == moto["hunter"]["id"])
    m.c.patch(f"/transactions/{baixa['id']}", json={"nature": "consumption"})
    m.c.patch(f"/commitments/{moto['hunter']['id']}", json={"nature": "financial"})
    assert caixa(m)["financeiro"] == 0.0


def test_categoria_da_a_natureza_padrao_e_o_lancamento_sobrescreve(m):
    juros = m.c.post("/categories", json={"name": "Juros", "type": "expense", "color": "#000000", "icon": "x",
                                          "default_nature": "financial"}).json()
    assert juros["default_nature"] == "financial"
    m.lancar(juros["id"], D(2026, 10, 4), pago=40.0)
    t = m.lancar(juros["id"], D(2026, 10, 6), pago=10.0)
    lido = m.c.get(f"/transactions/{t['id']}").json()
    assert (lido["nature"], lido["effective_nature"]) == (None, "financial")
    m.c.patch(f"/transactions/{t['id']}", json={"nature": "consumption"})
    c = caixa(m)
    assert (c["financeiro"], c["custo_de_vida"]) == (40.0, 10.0)


def test_receita_e_investimento_nao_tem_natureza(m):
    salario = m.categoria("Salário", "income")
    r = m.c.post("/transactions", json={"date": "2026-10-05", "description": "Salário", "amount_paid": 944.34,
                                        "category_id": salario, "nature": "financial"})
    assert r.status_code == 200
    assert r.json()["nature"] is None
    lido = m.c.get(f"/transactions/{r.json()['id']}").json()
    assert lido["effective_nature"] is None
    r = m.c.post("/categories", json={"name": "Bônus", "type": "income", "color": "#000000", "icon": "x",
                                      "default_nature": "financial"})
    assert r.status_code == 400


def test_lancamento_que_vira_receita_perde_a_natureza(m):
    casa = m.categoria("Casa")
    reembolso = m.categoria("Reembolso", "income")
    t = m.lancar(casa, D(2026, 10, 6), pago=50.0)
    m.c.patch(f"/transactions/{t['id']}", json={"nature": "asset_acquisition"})
    r = m.c.patch(f"/transactions/{t['id']}", json={"category_id": reembolso})
    assert (r.json()["nature"], r.json()["effective_nature"]) == (None, None)


def test_rosca_do_custo_de_vida(m, moto):
    m.c.patch(f"/transactions/{moto['entrada']['id']}", json={"nature": "asset_acquisition"})
    m.c.patch(f"/commitments/{moto['hunter']['id']}", json={"nature": "financial"})
    mercado = m.categoria("Mercado")
    m.lancar(mercado, D(2026, 10, 7), pago=300.0)

    total = m.c.get("/reports/categories", params={"year": 2026, "month": 10}).json()
    vida = m.c.get("/reports/categories", params={"year": 2026, "month": 10, "natureza": "consumption"}).json()
    assert total["total"] == 8418.69
    assert vida["total"] == 800.61
    assert {c["name"]: c["value"] for c in vida["categories"]} == {"Moto": 500.61, "Mercado": 300.0}
    assert m.c.get("/reports/categories", params={"year": 2026, "month": 10, "natureza": "x"}).status_code == 422


def test_compra_no_cartao_herda_a_da_categoria(m):
    eletro = m.c.post("/categories", json={"name": "Eletrônicos", "type": "expense", "color": "#000000",
                                           "icon": "x", "default_nature": "asset_acquisition"}).json()
    cartao = m.cartao()
    m.comprar(cartao, eletro["id"], 1200.0, D(2026, 10, 1), parcelas=3)
    c = caixa(m)
    assert (c["gasto_total"], c["aquisicoes"], c["custo_de_vida"]) == (400.0, 400.0, 0.0)
