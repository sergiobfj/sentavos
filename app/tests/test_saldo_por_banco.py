"""Meu mês quando o saldo agregado dá lugar ao saldo de cada banco.

O caso de 29/10/2026: o único saldo observado era o agregado de 11/10, a conta
Nubank nunca tinha tido saldo próprio — e por isso nada lançado nela mexia no
"Tenho agora". Cada asserção é uma regra do dinheiro que a troca não pode
quebrar: não contar em dobro, não somar o que ainda vai entrar, não tirar da
conta a compra no cartão, não tratar Caixinha como dinheiro livre.
"""

import datetime as dt

import pytest

from app.tests.apoio_planejamento import Montagem

HOJE = dt.date(2026, 10, 29)
BRT = dt.timezone(dt.timedelta(hours=-3))
D = dt.date
LIDO = dt.datetime(2026, 10, 29, 23, 0, tzinfo=BRT)


@pytest.fixture(name="m")
def montagem(client, monkeypatch):
    monkeypatch.setattr("app.planejamento.hoje", lambda: HOJE)
    monkeypatch.setattr("app.rotas_cartao.hoje", lambda: HOJE)
    return Montagem(client)


def conta(m, nome, tipo="checking") -> int:
    r = m.c.post("/accounts", json={"name": nome, "type": tipo})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def saldo(m, cid, valor, quando: dt.datetime):
    r = m.c.post(f"/accounts/{cid}/snapshots", json={"balance": valor, "observed_at": quando.isoformat()})
    assert r.status_code == 200, r.text


def lancar(m, cat, data, pago=None, previsto=None, conta_id=None, ocorrido=None):
    corpo = {"date": data.isoformat(), "description": "x", "category_id": cat, "amount_paid": pago,
             "amount_planned": previsto, "payment_method": "cash", "account_id": conta_id}
    if ocorrido is not None:
        corpo["occurred_at"] = ocorrido.isoformat()
    r = m.c.post("/transactions", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def meu_mes(m) -> dict:
    r = m.c.get("/months/summary?year=2026&month=10")
    assert r.status_code == 200, r.text
    return r.json()


def test_saldo_por_banco_substitui_o_agregado_sem_contar_em_dobro(m):
    agregado = conta(m, "Saldo agregado", "reconciliation")
    nubank = conta(m, "Nubank")
    mp = conta(m, "Mercado Pago", "payment")
    saldo(m, agregado, 684.39, dt.datetime(2026, 10, 11, 18, 45, tzinfo=BRT))
    meta = m.categoria("Meta", "income")
    comida = m.categoria("Alimentação")
    caixinha = m.categoria("Caixinha", "investment")

    # Lançado na conta Nubank ANTES de ela ter saldo: não entra no total.
    lancar(m, caixinha, D(2026, 10, 23), pago=550.0, conta_id=nubank)
    recebimento = lancar(m, meta, D(2026, 10, 20), previsto=700.0)
    antes = meu_mes(m)
    assert (antes["money_now"], antes["balance_date"], antes["balance_pending"]) == (684.39, "2026-10-11", True)
    assert antes["to_receive"] == 700.0  # pendente: fora do saldo
    assert "Saldo incompleto" in antes["reasons"]

    # 29/10: recebido, duas despesas no débito já dentro da leitura, e o saldo de cada banco.
    r = m.c.patch(f"/transactions/{recebimento['id']}", json={"amount_paid": 700.0, "account_id": nubank})
    assert r.status_code == 200, r.text
    for valor in (45.0, 34.0):
        lancar(m, comida, HOJE, pago=valor, conta_id=nubank, ocorrido=LIDO - dt.timedelta(minutes=1))
    # Compra no cartão do mesmo dia é gasto, mas não sai da conta agora.
    m.comprar(m.cartao(), comida, 40.0, HOJE)
    saldo(m, nubank, 696.0, LIDO)
    saldo(m, mp, 0.0, LIDO)

    # Agregado ainda com saldo + bancos com saldo: o app se recusa a somar os dois.
    assert meu_mes(m)["money_now"] is None

    saldo(m, agregado, 0.0, LIDO)
    depois = meu_mes(m)
    # O que o banco mostra — sem somar o agregado antigo de novo, sem descontar
    # outra vez o que já saiu antes da leitura, sem o cartão.
    assert (depois["money_now"], depois["balance_date"], depois["balance_pending"]) == (696.0, "2026-10-29", False)
    assert (depois["to_receive"], depois["contributed"], depois["reasons"]) == (0.0, 550.0, [])
    contas = m.c.get("/accounts/summary").json()
    assert (contas["total"], contas["to_distribute"], contas["possible_overlap"]) == (696.0, 0.0, False)

    caixa = m.c.get("/budgets/summary?year=2026&month=10").json()["caixa"]
    # Gasto do mês = débito + cartão; o aporte não é gasto nem o recebimento.
    assert (caixa["gasto_total"], caixa["no_cartao"], caixa["entrou"], caixa["investido"]) == (119.0, 40.0, 700.0, 550.0)


def test_caixinha_nao_entra_no_dinheiro_em_conta(m):
    nubank = conta(m, "Nubank")
    saldo(m, nubank, 696.0, LIDO)
    caixinha = m.c.post("/assets", json={"name": "Caixinha Nubank", "asset_class": "fixed_income"}).json()["id"]
    assert m.c.put("/assets/snapshots", json={"asset_id": caixinha, "year": 2026, "month": 10,
                                              "value": 1500.0, "observed_on": "2026-10-29"}).status_code == 200

    assert meu_mes(m)["money_now"] == 696.0
    patrimonio = m.c.get("/assets/summary?year=2026&month=10").json()
    assert (patrimonio["accounts_total"], patrimonio["net_worth"]) == (696.0, 2196.0)
