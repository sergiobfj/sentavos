"""Valida a reconstrução e as invariantes financeiras, sem banco do usuário."""
import datetime as dt
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlmodel import select

from app.models import (AccountBalanceSnapshot, Asset, AssetSnapshot, AuditEvent, Card, Category,
                        FinancialAccount, Invoice, InvoiceStatementItem, Provision, Transaction, User)
from scripts.reconstruir_situacao_20261109 import apply, record_state


@pytest.fixture
def situation(session, dono, client, monkeypatch):
    monkeypatch.setattr("app.planejamento.hoje", lambda: dt.date(2026, 11, 9))
    dono.operations_start = dt.date(2026, 11, 1)
    session.add(dono)
    categories = [Category(user_id=dono.id, name=name, type=kind, color="#000", icon="x")
                  for name, kind in [("Salário", "income"), ("Saúde", "expense"), ("Casa", "expense"), ("Moto", "expense")]]
    account = FinancialAccount(user_id=dono.id, name="Banco", type="checking")
    card = Card(user_id=dono.id, name="Cartão", closing_day=25, due_day=2)
    asset = Asset(user_id=dono.id, name="Caixinha", asset_class="fixed_income")
    session.add_all([*categories, account, card, asset]); session.flush()
    session.add_all([
        AccountBalanceSnapshot(user_id=dono.id, account_id=account.id, balance=696,
                               observed_at=dt.datetime(2026, 10, 30, 2, tzinfo=dt.timezone.utc)),
        Transaction(user_id=dono.id, date=dt.date(2026,10,29), description="Antes do saldo",
                    amount_paid=79, payment_method="cash", account_id=account.id, category_id=categories[1].id,
                    occurred_at=dt.datetime(2026,10,30,1,59,tzinfo=dt.timezone.utc)),
        Invoice(user_id=dono.id, card_id=card.id, year=2026, month=11,
                closing_date=dt.date(2026,10,25), due_date=dt.date(2026,11,2), reset_on=dt.date(2026,11,1)),
        AssetSnapshot(user_id=dono.id, asset_id=asset.id, year=2026, month=10, value=500),
    ]); session.commit()
    return dict(user_id=dono.id, account_id=account.id, card_id=card.id, asset_id=asset.id)


def test_situacao_exata_sem_duplica_saldo_dentista_ou_consumo(session, client, situation):
    result = apply(session, **situation); session.commit()
    assert result["adjustment"] == -1142
    summary = client.get("/months/summary?year=2026&month=11").json()
    assert {k: summary[k] for k in ("money_now", "emergency_reserve", "earmarked", "unassigned", "to_receive", "to_pay")} == {
        "money_now":496.32, "emergency_reserve":634, "earmarked":473, "unassigned":23.32, "to_receive":0, "to_pay":1402.85}
    assert summary["projected"] is None
    assert summary["balance_adjustments"][0]["amount"] == -1142
    assert summary["bank_observation"]["date"] == "2026-11-09"
    assert len(summary["due"]) == 5 and all(i["due_unknown"] for i in summary["due"])
    assert all(i["status"] == "pendente" for i in summary["due"])
    assert not any("Dentista" in i["description"] for i in summary["due"])
    invoice = client.get(f"/invoices/{result['invoice_id']}").json()
    assert (invoice["total"], invoice["paid"], invoice["remaining"], invoice["status"]) == (815.85,0,815.85,"aberta")
    assert invoice["items_total"] == 816.65 and invoice["discrepancy"] == .8
    assert invoice["responsibility_totals"] == {"familia":251.9,"empresa":399.56,"pessoal":165.19}
    assert len(invoice["statement_items"]) == invoice["item_count"] == 7
    assert invoice["items"] == []  # data de compra não foi informada
    rows=client.get("/transactions?year=2026&month=11").json()
    assert len(rows)==5 and sum(t["amount_paid"] or 0 for t in rows)==942.32
    assert sum(t["amount_paid"] is not None for t in rows)==1
    cash=client.get("/budgets/summary?year=2026&month=11").json()["caixa"]
    assert cash["entrou"]==942.32 and cash["gasto_total"]==cash["faturas_pagas"]==cash["saiu_a_vista"]==0
    investment=client.get("/investments/summary?year=2026&month=11").json()
    assert investment["total"]==634 and investment["contributed"]==investment["redeemed"]==0
    assert investment["yield_amount"] is None
    before = session.exec(select(AuditEvent)).all()
    assert apply(session, **situation)["changed"] is False
    session.commit()
    assert len(session.exec(select(AuditEvent)).all())==len(before)
    assert len(session.exec(select(Provision)).all())==4
    assert len(session.exec(select(InvoiceStatementItem)).all())==7
    assert isinstance(session.get(Invoice,result["invoice_id"]).manual_total, Decimal)
    column=next(c for c in sa.inspect(session.bind).get_columns("invoices") if c["name"]=="manual_total")
    assert isinstance(column["type"], sa.Numeric) and column["type"].scale==2


def test_ajuste_considera_movimentos_reais_e_recusa_sem_conta(session, situation):
    expense = session.exec(select(Category).where(Category.name=="Casa")).one()
    tx=Transaction(user_id=situation["user_id"],date=dt.date(2026,10,30),description="Saída real",amount_paid=10,
                   category_id=expense.id, payment_method="cash",account_id=None)
    session.add(tx);session.commit()
    with pytest.raises(ValueError,match="sem conta"):
        apply(session, **situation)
    session.rollback()
    tx=session.get(Transaction,tx.id);tx.account_id=situation["account_id"];session.add(tx);session.commit()
    assert apply(session, **situation)["adjustment"] == -1132


def test_reaplicacao_recusa_mudanca_ou_vinculo_de_outro_titular(session, situation):
    apply(session, **situation);session.commit()
    provision=session.exec(select(Provision)).first();provision.amount=999;session.add(provision);session.commit()
    with pytest.raises(ValueError,match="mudaram"):
        apply(session, **situation)


def test_reservas_nao_descontam_duas_vezes_e_se_cumprem_no_pagamento(session, client, situation):
    result=apply(session, **situation);session.commit()
    summary=client.get("/months/summary?year=2026&month=11").json()
    assert summary["month"]["available"]==pytest.approx(496.32-1402.85)
    tx=session.exec(select(Transaction).where(Transaction.description=="Academia")).one()
    tx.amount_paid=120;tx.account_id=situation["account_id"];session.add(tx);session.commit()
    summary=client.get("/months/summary?year=2026&month=11").json()
    assert summary["earmarked"]==353
    assert client.post(f"/invoices/{result['invoice_id']}/payments",json={"date":"2026-11-09","amount":815.85,
        "account_id":situation["account_id"]}).status_code==200
    assert client.get("/months/summary?year=2026&month=11").json()["earmarked"]==240
