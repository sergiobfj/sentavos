"""Relatórios: série mensal e distribuição por categoria.

O que já quebrou (ou quase) e está preso aqui:

  - percentual dividido pela soma das categorias VISÍVEIS em vez do total;
  - fatura contada duas vezes (compra + pagamento);
  - série que pula mês vazio e faz a queda sumir do desenho;
  - filtro de finalidade vazando pro caixa.
"""

import datetime as dt

import pytest

from app.models import Card, Category, CategoryType, Transaction


def categoria(client, nome, tipo="expense"):
    r = client.post(
        "/categories", json={"name": nome, "type": tipo, "color": "#3987e5", "icon": "•"}
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def lancar(client, cat, valor, data="2026-09-10", finalidade=None):
    corpo = {"date": data, "description": "x", "category_id": cat, "amount_paid": valor}
    if finalidade:
        corpo["finalidade"] = finalidade
    r = client.post("/transactions", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def cartao(client, finalidade="pessoal"):
    r = client.post(
        "/cards", json={"name": "Nubank", "closing_day": 25, "due_day": 2, "finalidade": finalidade}
    )
    return r.json()["id"]


def comprar(client, card, cat, valor, data="2026-09-10", parcelas=1, finalidade=None):
    corpo = {
        "card_id": card, "category_id": cat, "description": "compra",
        "total_amount": valor, "installments": parcelas, "purchase_date": data,
    }
    if finalidade:
        corpo["finalidade"] = finalidade
    r = client.post("/purchases", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def distribuicao(client, finalidade="todos", top=5, ano=2026, mes=9):
    r = client.get(
        f"/reports/categories?year={ano}&month={mes}&finalidade={finalidade}&top={top}"
    )
    assert r.status_code == 200, r.text
    return r.json()


def serie(client, de, ate, finalidade="todos"):
    r = client.get(f"/reports/monthly?from={de}&to={ate}&finalidade={finalidade}")
    assert r.status_code == 200, r.text
    return r.json()["months"]


# ---------- Distribuição ----------


def test_percentual_e_sobre_o_total_real_e_nao_sobre_as_visiveis(client):
    """Gasto total 2.000, Alimentação 400 -> 20%, mesmo mostrando só o top 2."""
    valores = {"Alimentação": 400, "Casa": 900, "Lazer": 300, "Saúde": 250, "Roupas": 150}
    for nome, v in valores.items():
        lancar(client, categoria(client, nome), v)

    d = distribuicao(client, top=2)

    assert d["total"] == 2000
    pct = {c["name"]: c["pct"] for c in d["categories"]}
    assert pct["Casa"] == pytest.approx(45.0)
    assert pct["Alimentação"] == pytest.approx(20.0)
    assert d["others"]["value"] == 700
    assert d["others"]["count"] == 3


def test_top_mais_outras_soma_cem_por_cento(client):
    for i, v in enumerate([500, 400, 300, 200, 100, 90, 80, 70]):
        lancar(client, categoria(client, f"Cat {i}"), v)

    d = distribuicao(client, top=5)

    soma = sum(c["pct"] for c in d["categories"]) + d["others"]["pct"]
    assert soma == pytest.approx(100.0)
    assert sum(c["value"] for c in d["categories"]) + d["others"]["value"] == d["total"]
    assert len(d["categories"]) == 5


def test_outras_de_uma_categoria_so_mostra_a_categoria(client):
    for i, v in enumerate([500, 400, 300, 200, 100, 50]):
        lancar(client, categoria(client, f"Cat {i}"), v)

    d = distribuicao(client, top=5)

    assert d["others"] is None
    assert len(d["categories"]) == 6


def test_mes_vazio(client):
    d = distribuicao(client)
    assert d["total"] == 0
    assert d["categories"] == []
    assert d["others"] is None


def test_categoria_arquivada_continua_contando_no_mes(client):
    cat = categoria(client, "Antiga")
    lancar(client, cat, 120)
    client.patch(f"/categories/{cat}", json={"archived": True})

    d = distribuicao(client)

    assert d["total"] == 120
    assert d["categories"][0]["archived"] is True


def test_receita_e_investimento_nao_entram_na_distribuicao(client):
    lancar(client, categoria(client, "Salário", "income"), 5000)
    lancar(client, categoria(client, "Reserva", "investment"), 800)
    lancar(client, categoria(client, "Mercado"), 300)

    assert distribuicao(client)["total"] == 300


def test_cartao_conta_no_mes_da_parcela_e_pagamento_nao_duplica(client):
    """Compra de 900 em 3x: 300 por mês de gasto. Pagar a fatura não é gasto."""
    cat = categoria(client, "Eletrônicos")
    card = cartao(client)
    compra = comprar(client, card, cat, 900, parcelas=3)
    fatura = client.get(f"/purchases/{compra['id']}").json()
    ids = client.get("/invoices").json()
    for f in ids:
        client.post(f"/invoices/{f['id']}/payments", json={"amount": f["total"], "date": "2026-10-02"})

    assert distribuicao(client, mes=9)["total"] == 300
    assert distribuicao(client, mes=10)["total"] == 300
    assert distribuicao(client, mes=11)["total"] == 300
    assert fatura["installments"] == 3


# ---------- Finalidade ----------


@pytest.fixture(name="mes_misto")
def mes_misto_fixture(client, session, dono):
    """Setembro com as três finalidades, cartão e à vista, e um lançamento antigo."""
    mercado = categoria(client, "Mercado")
    casa = categoria(client, "Casa")
    card = cartao(client, "familia")

    lancar(client, mercado, 100)                           # pessoal (padrão)
    lancar(client, casa, 200, finalidade="empresa")        # empresa
    comprar(client, card, mercado, 300)                    # família, herdado
    comprar(client, card, casa, 400, finalidade="pessoal") # pessoal, sobrescrito
    # Lançamento anterior à finalidade: nulo.
    session.add(Transaction(
        user_id=dono.id, date=dt.date(2026, 9, 3), description="antigo",
        amount_paid=50, category_id=mercado,
    ))
    session.commit()


@pytest.mark.parametrize(
    "filtro,esperado",
    [("pessoal", 500), ("familia", 300), ("empresa", 200), ("todos", 1050)],
)
def test_filtro_de_finalidade(client, mes_misto, filtro, esperado):
    assert distribuicao(client, filtro)["total"] == esperado
    ponto = serie(client, "2026-09", "2026-09", filtro)[0]
    assert ponto["expense"] == esperado


def test_sem_finalidade_fica_fora_dos_filtros_e_e_informado(client, mes_misto):
    d = distribuicao(client, "pessoal")
    assert d["sem_finalidade"] == {"count": 1, "value": 50}

    ponto = serie(client, "2026-09", "2026-09", "pessoal")[0]
    assert ponto["expense_sem_finalidade"] == 50
    assert ponto["expense_total"] == 1050


def test_finalidade_nao_filtra_o_caixa(client, mes_misto):
    """Se o dinheiro da família saiu da minha conta, ele mexeu no meu caixa."""
    todos = serie(client, "2026-09", "2026-09", "todos")[0]
    empresa = serie(client, "2026-09", "2026-09", "empresa")[0]

    for campo in ("income", "investment", "invoice_payments", "cash_flow", "expense_total"):
        assert todos[campo] == empresa[campo]


def test_filtro_invalido_da_422(client):
    assert client.get("/reports/categories?year=2026&month=9&finalidade=chefe").status_code == 422


# ---------- Série ----------


def test_serie_de_seis_meses_com_mes_vazio(client):
    cat = categoria(client, "Mercado")
    lancar(client, cat, 100, "2026-04-10")
    lancar(client, cat, 300, "2026-06-10")  # maio fica vazio

    pontos = serie(client, "2026-04", "2026-09")

    assert [(p["year"], p["month"]) for p in pontos] == [(2026, m) for m in range(4, 10)]
    assert [p["expense"] for p in pontos] == [100, 0, 300, 0, 0, 0]


def test_serie_de_doze_meses_atravessa_o_ano(client):
    cat = categoria(client, "Mercado")
    lancar(client, cat, 70, "2025-12-20")
    lancar(client, cat, 80, "2026-01-05")

    pontos = serie(client, "2025-10", "2026-09")

    assert len(pontos) == 12
    assert pontos[0]["year"] == 2025 and pontos[0]["month"] == 10
    assert pontos[-1]["year"] == 2026 and pontos[-1]["month"] == 9
    por_mes = {(p["year"], p["month"]): p["expense"] for p in pontos}
    assert por_mes[(2025, 12)] == 70
    assert por_mes[(2026, 1)] == 80


def test_saldo_da_serie_bate_com_o_resumo_do_mes(client):
    """Duas telas, o mesmo mês: série e Início não podem discordar."""
    entrada = categoria(client, "Salário", "income")
    reserva = categoria(client, "Reserva", "investment")
    gasto = categoria(client, "Mercado")
    card = cartao(client)
    lancar(client, entrada, 5000)
    lancar(client, reserva, 700)
    lancar(client, gasto, 400)
    comprar(client, card, gasto, 900, parcelas=3, data="2026-08-20")
    for f in client.get("/invoices").json():
        if (f["year"], f["month"]) == (2026, 9):
            client.post(f"/invoices/{f['id']}/payments", json={"amount": f["total"], "date": "2026-09-02"})

    for mes in (8, 9, 10):
        caixa = client.get(f"/budgets/summary?year=2026&month={mes}").json()["caixa"]
        ponto = serie(client, f"2026-{mes:02d}", f"2026-{mes:02d}")[0]
        assert ponto["cash_flow"] == caixa["carteira"]
        assert ponto["expense"] == caixa["gasto_total"]
        assert ponto["income"] == caixa["entrou"]
        assert ponto["investment"] == caixa["investido"]
        assert ponto["invoice_payments"] == caixa["faturas_pagas"]


def test_serie_recusa_intervalo_invertido_ou_longo(client):
    assert client.get("/reports/monthly?from=2026-09&to=2026-01").status_code == 400
    assert client.get("/reports/monthly?from=2020-01&to=2026-01").status_code == 400
    assert client.get("/reports/monthly?from=2026-13&to=2026-12").status_code == 400


# ---------- Isolamento ----------


def test_relatorios_nao_somam_dinheiro_alheio(cliente_de, criar_usuario, session):
    ana = criar_usuario("ana@exemplo.com", "Ana", "senha-da-ana-12345")
    bruno = criar_usuario("bruno@exemplo.com", "Bruno", "senha-do-bruno-12345")
    for dono, valor in ((ana, 100.0), (bruno, 9999.0)):
        cat = Category(name="Mercado", type=CategoryType.EXPENSE, color="#fff", icon="x", user_id=dono.id)
        session.add(cat)
        session.commit()
        session.add(Transaction(
            user_id=dono.id, date=dt.date(2026, 9, 5), description="x",
            amount_paid=valor, category_id=cat.id,
        ))
        session.commit()

    cliente = cliente_de(ana)
    assert distribuicao(cliente)["total"] == 100
    assert serie(cliente, "2026-09", "2026-09")[0]["expense"] == 100


def test_relatorios_exigem_login(anon_client):
    assert anon_client.get("/reports/monthly?from=2026-01&to=2026-06").status_code == 401
    assert anon_client.get("/reports/categories?year=2026&month=9").status_code == 401


def test_demo_le_relatorios(cliente_de, criar_usuario, session):
    demo = criar_usuario("demo@exemplo.com", "Demo", "senha-do-demo-12345", read_only=True)
    card = Card(user_id=demo.id, name="x", closing_day=25, due_day=2)
    session.add(card)
    session.commit()

    cliente = cliente_de(demo)
    assert cliente.get("/reports/monthly?from=2026-01&to=2026-06").status_code == 200
    assert cliente.get("/reports/categories?year=2026&month=9").status_code == 200
    # E não classifica cartão: finalidade também é escrita.
    assert cliente.patch(f"/cards/{card.id}", json={"finalidade": "familia"}).status_code == 403
