"""Aporte, resgate e a regra única do rendimento.

O que este arquivo protege: resgate nunca vira prejuízo nem receita; aporte
nunca vira gasto; o patrimônio não muda quando o dinheiro só troca de lugar;
e o rendimento só aparece quando todas as parcelas da conta são conhecidas.
"""

import datetime as dt

import pytest

from app.tests.apoio_planejamento import Montagem

HOJE = dt.date(2026, 10, 11)
BRT = dt.timezone(dt.timedelta(hours=-3))
D = dt.date


@pytest.fixture(name="m")
def montagem(client, monkeypatch):
    monkeypatch.setattr("app.planejamento.hoje", lambda: HOJE)
    return Montagem(client)


def conta(m, nome="Nubank", saldo=None, quando=dt.datetime(2026, 10, 1, 10, 0, tzinfo=BRT)) -> int:
    c = m.c.post("/accounts", json={"name": nome, "type": "checking"}).json()
    if saldo is not None:
        assert m.c.post(f"/accounts/{c['id']}/snapshots", json={"balance": saldo, "observed_at": quando.isoformat()}).status_code == 200
    return c["id"]


def ativo(m, nome="Caixinha", classe="fixed_income") -> int:
    return m.c.post("/assets", json={"name": nome, "asset_class": classe}).json()["id"]


def saldo_ativo(m, aid, mes, valor, ano=2026, nota=None):
    corpo = {"asset_id": aid, "year": ano, "month": mes, "value": valor}
    if nota:
        corpo["reconciliation_note"] = nota
    assert m.c.put("/assets/snapshots", json=corpo).status_code == 200


def movimento(m, **corpo):
    return m.c.post("/investments/movements", json={"date": "2026-10-06", **corpo})


def resumo(m, mes=10):
    return m.c.get(f"/investments/summary?year=2026&month={mes}").json()


def caixa(m, mes=10):
    return m.c.get(f"/budgets/summary?year=2026&month={mes}").json()["caixa"]


def saldo_conta(m, cid):
    return m.c.get(f"/accounts/{cid}").json()["balance"]


def test_aporte_sai_da_conta_entra_no_ativo_e_nao_e_gasto(m):
    nubank = conta(m, saldo=1000.0)
    caixinha = ativo(m)
    cat = m.categoria("Caixinha", "investment")
    saldo_ativo(m, caixinha, 9, 0.0)
    patrimonio_antes = m.c.get("/assets/summary?year=2026&month=10").json()["net_worth"]

    r = movimento(m, asset_id=caixinha, type="contribution", amount=100.0, account_id=nubank, category_id=cat)
    assert r.status_code == 200, r.text
    saldo_ativo(m, caixinha, 10, 100.0)  # o banco mostra os 100 na caixinha

    assert saldo_conta(m, nubank) == 900.0
    assert caixa(m)["gasto_total"] == 0.0 and caixa(m)["entrou"] == 0.0
    assert caixa(m)["investido"] == 100.0
    assert m.c.get("/assets/summary?year=2026&month=10").json()["net_worth"] == patrimonio_antes


def test_resgate_volta_pra_conta_nao_e_receita_nem_prejuizo(m):
    nubank = conta(m, saldo=0.0)
    caixinha = ativo(m)
    cat = m.categoria("Caixinha", "investment")
    saldo_ativo(m, caixinha, 9, 1000.0)
    r = movimento(m, asset_id=caixinha, type="redemption", amount=100.0, account_id=nubank, category_id=cat)
    assert r.status_code == 200, r.text
    saldo_ativo(m, caixinha, 10, 905.0)  # 900 + 5 de rendimento

    assert saldo_conta(m, nubank) == 100.0
    assert caixa(m)["entrou"] == 0.0 and caixa(m)["gasto_total"] == 0.0
    r = resumo(m)
    assert (r["redeemed"], r["yield_status"], r["yield_amount"]) == (100.0, "apurado", 5.0)
    item = r["items"][0]
    assert (item["redeemed"], item["yield_status"], item["yield_amount"]) == (100.0, "apurado", 5.0)


def test_rendimento_nao_apurado_com_resgate_desconhecido(m):
    """O caso de outubro/2026: a caixinha zerou e o resgate não está no extrato."""
    caixinha = ativo(m, "Caixinha Mercado Pago")
    cat = m.categoria("Caixinha 5K", "investment")
    saldo_ativo(m, caixinha, 9, 1458.15)
    saldo_ativo(m, caixinha, 10, 0.0, nota="Caixinha usada na compra da Hunter; resgate não conciliado.")
    aporte = m.lancar(cat, D(2026, 10, 6), pago=800.0, descricao="Caixinha")
    assert movimento(m, asset_id=caixinha, type="contribution", amount=800.0, transaction_id=aporte["id"]).status_code == 200

    r = resumo(m)
    assert r["yield_status"] == "nao_apurado" and r["yield_amount"] is None
    assert r["contributed"] == 800.0 and r["redeemed"] == 0.0
    assert "resgate não conciliado" in r["reasons"][0]


def test_ativo_desatualizado_e_primeiro_mes_nao_inventam_rendimento(m):
    a = ativo(m, "A")
    b = ativo(m, "B")
    saldo_ativo(m, a, 9, 1000.0)
    saldo_ativo(m, b, 9, 500.0)
    saldo_ativo(m, a, 10, 1010.0)  # B fica com o saldo de setembro
    r = resumo(m)
    assert r["yield_status"] == "nao_apurado" and r["variation"] is None
    assert r["stale_names"] == ["B"] and r["total"] == 1010.0

    c = ativo(m, "C")
    saldo_ativo(m, c, 8, 300.0, ano=2026)
    primeiro = m.c.get("/investments/summary?year=2026&month=7").json()
    assert primeiro["yield_status"] == "sem_base"


def test_rendimento_desconta_aporte_e_ajuste(m):
    caixinha = ativo(m)
    cat = m.categoria("Caixinha", "investment")
    saldo_ativo(m, caixinha, 9, 1000.0)
    aporte = m.lancar(cat, D(2026, 10, 6), pago=200.0)
    movimento(m, asset_id=caixinha, type="contribution", amount=200.0, transaction_id=aporte["id"])
    movimento(m, asset_id=caixinha, type="adjustment", amount=50.0)
    saldo_ativo(m, caixinha, 10, 1262.0)
    r = resumo(m)
    assert (r["contributed"], r["adjusted"], r["yield_amount"]) == (200.0, 50.0, 12.0)


def test_aporte_sem_ativo_deixa_o_rendimento_por_ativo_sem_conta(m):
    caixinha = ativo(m)
    cat = m.categoria("Caixinha", "investment")
    saldo_ativo(m, caixinha, 9, 1000.0)
    m.lancar(cat, D(2026, 10, 6), pago=200.0)  # sem movimento
    saldo_ativo(m, caixinha, 10, 1210.0)
    r = resumo(m)
    # No total a conta fecha (todo aporte de investimento conta)...
    assert (r["yield_status"], r["yield_amount"], r["unlinked"]) == ("apurado", 10.0, 1)
    # ...por ativo não dá pra saber pra qual foi.
    assert r["items"][0]["yield_status"] == "nao_apurado"


def test_vinculo_confere_sinal_valor_tipo_e_unicidade(m):
    caixinha = ativo(m)
    inv = m.categoria("Caixinha", "investment")
    casa = m.categoria("Casa")
    aporte = m.lancar(inv, D(2026, 10, 6), pago=800.0)
    despesa = m.lancar(casa, D(2026, 10, 6), pago=10.0)
    previsto = m.lancar(inv, D(2026, 10, 20), previsto=100.0)

    assert movimento(m, asset_id=caixinha, type="redemption", amount=800.0, transaction_id=aporte["id"]).status_code == 400
    assert movimento(m, asset_id=caixinha, type="contribution", amount=700.0, transaction_id=aporte["id"]).status_code == 400
    assert movimento(m, asset_id=caixinha, type="contribution", amount=10.0, transaction_id=despesa["id"]).status_code == 400
    assert movimento(m, asset_id=caixinha, type="contribution", amount=100.0, transaction_id=previsto["id"]).status_code == 400
    assert movimento(m, asset_id=caixinha, type="contribution", amount=800.0, transaction_id=aporte["id"]).status_code == 200
    assert movimento(m, asset_id=caixinha, type="contribution", amount=800.0, transaction_id=aporte["id"]).status_code == 409
    carro = ativo(m, "Carro", "vehicle")
    assert movimento(m, asset_id=carro, type="adjustment", amount=1.0).status_code == 400


def test_editar_o_lancamento_mantem_o_movimento_coerente(m):
    caixinha = ativo(m)
    inv = m.categoria("Caixinha", "investment")
    casa = m.categoria("Casa")
    aporte = m.lancar(inv, D(2026, 10, 6), pago=800.0)
    mov = movimento(m, asset_id=caixinha, type="contribution", amount=800.0, transaction_id=aporte["id"]).json()

    assert m.c.patch(f"/transactions/{aporte['id']}", json={"amount_paid": 750.0}).status_code == 200
    assert m.c.get("/investments/movements?year=2026&month=10").json()[0]["amount"] == 750.0
    assert m.c.patch(f"/transactions/{aporte['id']}", json={"amount_paid": -750.0}).status_code == 409
    assert m.c.patch(f"/transactions/{aporte['id']}", json={"category_id": casa}).status_code == 409

    # Apagar o lançamento leva o movimento junto (o lado caixa sumiu).
    assert m.c.delete(f"/transactions/{aporte['id']}").status_code == 200
    assert m.c.get("/investments/movements").json() == []
    assert mov["id"]


def test_desvincular_mantem_o_lancamento(m):
    caixinha = ativo(m)
    inv = m.categoria("Caixinha", "investment")
    aporte = m.lancar(inv, D(2026, 10, 6), pago=800.0)
    mov = movimento(m, asset_id=caixinha, type="contribution", amount=800.0, transaction_id=aporte["id"]).json()
    assert m.c.delete(f"/investments/movements/{mov['id']}").status_code == 200
    assert m.c.get(f"/transactions/{aporte['id']}").status_code == 200


def test_variacao_do_patrimonio_vem_pronta_e_some_com_ativo_desatualizado(m):
    a = ativo(m, "A")
    saldo_ativo(m, a, 9, 1000.0)
    saldo_ativo(m, a, 10, 1100.0)
    novo = ativo(m, "Novo")
    saldo_ativo(m, novo, 10, 300.0)
    r = m.c.get("/assets/summary?year=2026&month=10").json()
    assert (r["variation"], r["new_total"]) == (100.0, 300.0)

    b = ativo(m, "B")
    saldo_ativo(m, b, 9, 50.0)  # sem saldo de outubro
    assert m.c.get("/assets/summary?year=2026&month=10").json()["variation"] is None
