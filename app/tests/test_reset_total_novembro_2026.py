import datetime as dt

import pytest
import sqlalchemy as sa
from sqlmodel import select

from app.models import (AccountBalanceSnapshot, Asset, AssetSnapshot, Card, Category, Commitment,
                        FinancialAccount, Invoice, InvoicePayment, Purchase, Transaction, User)
from scripts.reset_total_novembro_2026 import apply, prepare
from scripts.reiniciar_novembro_2026 import read_tables


@pytest.fixture
def reset_case(session, client, dono):
    expense = Category(user_id=dono.id, name="Despesa", type="expense", color="#000", icon="x")
    income = Category(user_id=dono.id, name="Receita", type="income", color="#000", icon="x")
    account = FinancialAccount(user_id=dono.id, name="Banco", type="checking")
    card = Card(user_id=dono.id, name="Cartão", closing_day=25, due_day=2)
    session.add_all([expense, income, account, card]); session.flush()
    session.add(AccountBalanceSnapshot(user_id=dono.id, account_id=account.id, balance=696,
                observed_at=dt.datetime(2026, 10, 29, 20, tzinfo=dt.timezone.utc)))
    session.add(Commitment(user_id=dono.id, category_id=expense.id, description="Contrato antigo",
                           first_due=dt.date(2026, 10, 9), amount=99, installments=48))
    session.commit()
    contract = session.exec(select(Commitment).where(Commitment.user_id == dono.id)).first()
    # Pagamento antecipado real permanece em outubro; não ressuscita a obrigação futura.
    session.add(Transaction(user_id=dono.id, category_id=expense.id, date=dt.date(2026,10,30),
                description="Parcela antecipada", amount_paid=99, commitment_id=contract.id, commitment_no=2))
    session.commit()
    purchase = client.post("/purchases", json=dict(card_id=card.id, category_id=expense.id,
               description="Compra histórica", total_amount=90, installments=3, purchase_date="2026-09-23")).json()
    invoices = client.get("/invoices").json()
    november = next(i for i in invoices if i["month"] == 11)
    assert client.post(f"/invoices/{november['id']}/payments", json={"date":"2026-10-23","amount":10,"account_id":account.id}).status_code == 200
    assert client.post("/transactions", json=dict(date="2026-11-03",description="Antiga",category_id=income.id,amount_planned=777)).status_code == 200
    asset = Asset(user_id=dono.id, name="Investimento", asset_class="fixed_income")
    session.add(asset); session.flush()
    session.add_all([AssetSnapshot(user_id=dono.id, asset_id=asset.id, year=2026, month=10, value=1000, observed_on=dt.date(2026,10,29)),
                     AssetSnapshot(user_id=dono.id, asset_id=asset.id, year=2026, month=11, value=1200, observed_on=dt.date(2026,11,2))])
    session.commit()
    return expense, income, account, card, purchase, november, asset


def run_reset(session, user):
    plan = prepare(session.connection(), user.id)
    result = apply(session.connection(), plan)
    session.commit(); session.expire_all()
    return plan, result


def test_reset_limpa_futuro_preserva_fluxo_passado_e_saldo(session, client, dono, reset_case):
    expense, _, account, _, purchase, november, asset = reset_case
    old_transactions = [t.model_dump() for t in session.exec(select(Transaction).where(Transaction.date < dt.date(2026,11,1))).all()]
    old_payments = [p.model_dump() for p in session.exec(select(InvoicePayment)).all()]
    old_reports = client.get("/reports/monthly?from=2026-09&to=2026-10").json()
    run_reset(session, dono)
    assert [t.model_dump() for t in session.exec(select(Transaction).where(Transaction.date < dt.date(2026,11,1))).all()] == old_transactions
    assert [p.model_dump() for p in session.exec(select(InvoicePayment)).all()] == old_payments
    assert client.get("/reports/monthly?from=2026-09&to=2026-10").json() == old_reports
    assert client.get("/transactions?year=2026&month=11").json() == []
    for year, month in [(2026,11),(2026,12),(2027,1),(2028,5)]:
        month_data = client.get(f"/months/summary?year={year}&month={month}").json()
        assert month_data["month"]["items"] == []
        assert month_data["month"]["reserves"] == []
        assert month_data["projected"] is None
        assert month_data["to_receive"] == month_data["to_pay"] == 0
    account_data = client.get(f"/accounts/{account.id}").json()
    assert account_data["observed_balance"] == account_data["balance"] == 696
    assert account_data["quality"] == "desatualizado"
    assert session.get(Asset, asset.id) is not None
    assert len(session.exec(select(AssetSnapshot).where(AssetSnapshot.asset_id == asset.id)).all()) == 1
    f = client.get(f"/invoices/{november['id']}").json()
    assert (f["total"],f["remaining"],f["paid"],f["status"],f["items"],f["payments"]) == (None,None,0,"a_preencher",[],[])
    assert session.get(Purchase, purchase["id"]).purchase_date == dt.date(2026,9,23)
    updated = client.post(f"/accounts/{account.id}/snapshots", json={"balance":900,
                          "observed_at":dt.datetime.now(dt.timezone.utc).isoformat()})
    assert updated.status_code == 200
    current = client.get(f"/accounts/{account.id}").json()
    assert current["balance"] == current["observed_balance"] == 900
    assert current["quality"] == "reconciliado"


def test_manual_fatura_nao_duplica_consumo_e_pagamento_nao_reutiliza_outubro(session, client, dono, reset_case):
    expense, income, account, card, purchase, november, _ = reset_case
    plan, _ = run_reset(session, dono)
    invoice_id = november["id"]
    assert client.post(f"/invoices/{invoice_id}/payments",json={"date":"2026-11-03","amount":10}).status_code == 409
    f = client.patch(f"/invoices/{invoice_id}",json={"total":500}).json()
    assert (f["total"],f["paid"],f["remaining"]) == (500,0,500)
    # Novo consumo entra no relatório; o valor informado da fatura continua sendo o total completo.
    assert client.post("/purchases",json=dict(card_id=card.id,category_id=expense.id,description="Nova compra",total_amount=25,installments=1,purchase_date="2026-11-03")).status_code == 200
    f = client.get(f"/invoices/{invoice_id}").json()
    assert f["total"] == 500  # A compra de novembro, neste cartão, vence em dezembro.
    result=client.post(f"/invoices/{invoice_id}/payments",json={"date":"2026-11-03","amount":120,"account_id":account.id})
    assert result.status_code == 200
    assert (result.json()["paid"],result.json()["remaining"]) == (120,380)
    assert client.post(f"/invoices/{invoice_id}/payments",json={"date":"2026-10-31","amount":1}).status_code == 409
    assert client.patch(f"/invoices/{invoice_id}",json={"total":100}).status_code == 409
    assert client.patch(f"/purchases/{purchase['id']}",json={"installments":5}).status_code == 409
    assert client.post("/transactions",json=dict(date="2026-11-03",description="Receita nova",category_id=income.id,amount_paid=50,account_id=account.id)).status_code == 200
    assert client.post("/transactions",json=dict(date="2026-11-03",description="Despesa nova",category_id=expense.id,amount_paid=7,payment_method="cash",account_id=account.id)).status_code == 200
    assert client.post("/commitments",json=dict(description="Conta nova",category_id=expense.id,amount=30,first_due="2026-11-20",installments=1)).status_code == 200
    before = read_tables(session.connection())
    assert apply(session.connection(),plan)["changed"] == 0
    session.commit()
    assert read_tables(session.connection()) == before
    rows=client.get("/transactions?year=2026&month=11").json()
    assert {r["description"] for r in rows} == {"Nova compra","Receita nova","Despesa nova"}


def test_fatura_manual_substitui_itens_da_mesma_fatura(session, client, dono, reset_case):
    expense, _, _, card, _, november, _ = reset_case
    run_reset(session, dono)
    # Cartão fecha e vence dentro do próprio mês.
    session.add(card); card.closing_day=8; card.due_day=13; session.commit()
    assert client.post("/purchases",json=dict(card_id=card.id,category_id=expense.id,description="Nova",total_amount=40,installments=1,purchase_date="2026-11-03")).status_code == 200
    assert client.get(f"/invoices/{november['id']}").json()["total"] == 40
    assert client.patch(f"/invoices/{november['id']}",json={"total":200}).json()["total"] == 200
    assert client.get("/budgets/summary?year=2026&month=11").json()["caixa"]["gasto_total"] == 40


def test_recusa_plano_desatualizado_sem_alterar_banco(session, dono, reset_case):
    plan=prepare(session.connection(),dono.id)
    import copy
    tampered=copy.deepcopy(plan)
    old=session.exec(select(Transaction).where(Transaction.date < dt.date(2026,11,1))).first()
    tampered["delete"]["transactions"].append(next(r for r in read_tables(session.connection())["transactions"] if r["id"]==old.id))
    with pytest.raises(ValueError,match="Plano alterado"):
        apply(session.connection(),tampered)
    expense=reset_case[0]
    session.add(Transaction(user_id=dono.id,category_id=expense.id,date=dt.date(2026,11,4),description="Recente",amount_paid=1))
    session.commit()
    before=read_tables(session.connection())
    with pytest.raises(ValueError,match="Banco mudou"):
        apply(session.connection(),plan)
    assert read_tables(session.connection()) == before


def test_fatura_vazia_criada_manualmente_nao_e_paga(client):
    card=client.post("/cards",json={"name":"Manual","closing_day":8,"due_day":13}).json()
    empty=client.post("/invoices",json={"card_id":card["id"],"year":2026,"month":11}).json()
    assert empty["status"] == "a_preencher" and empty["total"] is None and empty["paid"] == 0
    assert client.post("/invoices",json={"card_id":card["id"],"year":2026,"month":11,"total":10}).status_code == 409
    assert client.patch(f"/invoices/{empty['id']}",json={"total":-1}).status_code == 422
    assert client.patch(f"/invoices/{empty['id']}",json={"total":0}).json()["status"] != "paga"
