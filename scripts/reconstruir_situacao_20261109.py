"""Cadastro único da situação observada em 09/11, exclusivamente em cópia local.

Não importa app.database, não lê .env e não aceita URL remota. Os três vínculos
(conta, cartão, ativo) são explícitos. A data das obrigações é competência de
registro; due_unknown impede tratá-la como vencimento. Itens da fatura são
composição observada, sem presumir data de compra ou novo consumo no mês.
"""
import argparse
import datetime as dt
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from sqlmodel import Session, create_engine, select

from app.dominio import contas
from app.dominio.tempo import FUSO
from app.models import (AccountBalanceSnapshot, Asset, AssetSnapshot, AuditEvent, Card,
                        Category, CategoryType, FinancialAccount, Invoice, InvoiceStatementItem,
                        Provision, Transaction, User)

DAY = dt.date(2026, 11, 9)
ACTION = "situacao.observada.2026_11_09"
MARK = "[situacao-2026-11-09]"
D = Decimal
MODELS = {m.__tablename__: m for m in (Transaction, Provision, Invoice, InvoiceStatementItem,
                                      AssetSnapshot, AccountBalanceSnapshot)}


def fingerprint(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def record_state(session, ids):
    result = {}
    for table, keys in ids.items():
        rows = []
        for key in keys:
            record = session.get(MODELS[table], key)
            if record is None:
                raise ValueError("Registro da operação foi removido; confira antes de reaplicar")
            session.refresh(record)
            rows.append(record.model_dump(mode="json"))
        result[table] = rows
    return result


def apply(session, user_id, account_id, card_id, asset_id):
    user = session.exec(select(User).where(User.id == user_id).with_for_update()).one()
    if user.read_only or user.operations_start != dt.date(2026, 11, 1):
        raise ValueError("Requer titular editável com reset de novembro já concluído")
    bindings = dict(account_id=account_id, card_id=card_id, asset_id=asset_id)
    previous = session.exec(select(AuditEvent).where(AuditEvent.user_id == user_id,
                            AuditEvent.action == ACTION)).first()
    if previous:
        if previous.details["bindings"] != bindings:
            raise ValueError("Operação já aplicada com outros vínculos")
        if fingerprint(record_state(session, previous.details["ids"])) != previous.details["fingerprint"]:
            raise ValueError("Registros mudaram depois do cadastro; reaplicação recusada")
        return {**previous.details["result"], "changed": False}
    for model, key in ((FinancialAccount, account_id), (Card, card_id), (Asset, asset_id)):
        record = session.get(model, key)
        if record is None or record.user_id != user_id:
            raise ValueError("Vínculo inexistente ou de outro titular")
    account = session.get(FinancialAccount, account_id)
    asset = session.get(Asset, asset_id)
    if account.archived or account.restricted or not account.include_in_planning:
        raise ValueError("Conta principal não disponível")
    if asset.asset_class not in ("fixed_income", "equity", "crypto") or asset.include_in_planning:
        raise ValueError("A reserva precisa ser um investimento separado do caixa")
    invoice = session.exec(select(Invoice).where(Invoice.user_id == user_id, Invoice.card_id == card_id,
                           Invoice.year == 2026, Invoice.month == 11)).one()
    if invoice.manual_total is not None or invoice.reset_on != dt.date(2026, 11, 1):
        raise ValueError("Fatura não está vazia após o reset")
    from app.faturas import totais
    if totais(session, user)[invoice.id] != (None, 0.0, 0):
        raise ValueError("Fatura já possui itens ou pagamentos")
    snapshots = session.exec(select(AccountBalanceSnapshot).where(AccountBalanceSnapshot.user_id == user_id,
                             AccountBalanceSnapshot.account_id == account_id)).all()
    previous_snapshot = max(snapshots, key=lambda s: contas.utc(s.observed_at))
    if contas.dia_local(previous_snapshot.observed_at) != dt.date(2026, 10, 29) or previous_snapshot.balance != 696:
        raise ValueError("Saldo anterior difere da referência autorizada")
    existing = session.exec(select(Transaction).where(Transaction.user_id == user_id,
                            Transaction.date >= dt.date(2026, 11, 1))).all()
    if existing:
        raise ValueError("Novembro já possui lançamentos; confira antes de cadastrar")
    categories = session.exec(select(Category).where(Category.user_id == user_id)).all()
    def category(name, kind):
        matches = [c for c in categories if c.name.casefold() == name.casefold() and c.type == kind]
        if len(matches) != 1:
            raise ValueError(f"Categoria ambígua ou ausente: {name}")
        return matches[0].id

    ids = {}
    def add(record):
        session.add(record); session.flush()
        ids.setdefault(record.__tablename__, []).append(record.id)
        return record

    # Instantes técnicos documentam apenas a ordem declarada: salário antes
    # do saldo observado. Não são horários bancários fornecidos pelo titular.
    salary = add(Transaction(user_id=user_id, date=DAY, description="Salário", amount_paid=942.32,
        category_id=category("Salário", CategoryType.INCOME), payment_method="cash", account_id=account_id,
        occurred_at=dt.datetime(2026, 11, 9, 0, tzinfo=FUSO).astimezone(dt.timezone.utc),
        note=f"{MARK} salário recebido; instante técnico, anterior ao saldo observado."))
    obligations = []
    for description, amount, cat_name, reserved in (
        ("Seguro saúde da viagem para Argentina", 180, "Saúde", 180),
        ("Academia", 120, "Saúde", 120),
        ("Internet", 60, "Casa", 60),
        ("Emplacamento e seguro da moto", 227, "Moto", 0),
    ):
        tx = add(Transaction(user_id=user_id, date=DAY, description=description, amount_planned=amount,
            amount_paid=None, category_id=category(cat_name, CategoryType.EXPENSE),
            payment_method="cash", finalidade="pessoal", due_unknown=True,
            note=f"{MARK} obrigação pendente; data de registro, vencimento não informado."))
        obligations.append(tx)
        if reserved:
            add(Provision(user_id=user_id, description=description, amount=reserved, created_on=DAY,
                          transaction_id=tx.id, note=f"{MARK} destinação do saldo bancário, sem movimentação."))
    invoice.manual_total = D("815.85")
    invoice.due_unknown = True
    session.add(invoice); session.flush()
    ids.setdefault("invoices", []).append(invoice.id)
    for number, description, amount, responsibility in (
        (1, "Item 1", "69.90", "familia"), (2, "Item 2", "235.20", "empresa"),
        (3, "Item 3", "13.63", "pessoal"), (4, "Item 4", "164.36", "empresa"),
        (5, "Dentista", "113.00", "pessoal"), (6, "Item 6", "182.00", "familia"),
        (7, "Item 7", "38.56", "pessoal"),
    ):
        add(InvoiceStatementItem(user_id=user_id, invoice_id=invoice.id, source_key=f"{ACTION}:{number}",
                                description=description, amount=D(amount), finalidade=responsibility))
    add(Provision(user_id=user_id, description="Dentista · incluído na fatura", amount=113,
        created_on=DAY, invoice_id=invoice.id, note=f"{MARK} cobre parte da fatura; não é segunda dívida."))
    add(AssetSnapshot(user_id=user_id, asset_id=asset_id, year=2026, month=11, value=634,
        observed_on=DAY, purpose="emergency_reserve",
        reconciliation_note="Reserva de emergência observada; sem aporte, resgate ou rendimento apurado."))
    observation = dt.datetime(2026, 11, 9, 0, 0, 1, tzinfo=FUSO).astimezone(dt.timezone.utc)
    movements = contas.movimentos(session, user, {account_id}, dt.date(2026, 10, 29))
    unassigned = contas.movimentos(session, user, None, dt.date(2026, 10, 29))
    def between(m):
        return contas.depois(m.data, m.ocorrido_em, previous_snapshot.observed_at) and not contas.depois(m.data, m.ocorrido_em, observation)
    if any(between(m) or contas.ordem_ambigua(m, previous_snapshot.observed_at) for m in unassigned):
        raise ValueError("Movimentos sem conta exigem conferência antes do ajuste")
    selected = [m for m in movements if between(m)]
    if any(contas.ordem_ambigua(m, previous_snapshot.observed_at) for m in movements):
        raise ValueError("Ordem ambígua no saldo anterior")
    expected = D(str(previous_snapshot.balance)) + sum((D(str(m.valor)) for m in selected), D("0"))
    adjustment = (D("496.32") - expected).quantize(D("0.01"))
    snap = add(AccountBalanceSnapshot(user_id=user_id, account_id=account_id, balance=496.32,
        observed_at=observation, accepted_difference=float(adjustment), source="reconciliation",
        note=f"{MARK} SALDO DE AJUSTE. Saldo após salário; instante técnico registra só a ordem declarada."))
    assert contas.diferenca(session, user, snap) == float(adjustment)
    result = {"date": str(DAY), "money_now": 496.32, "salary": 942.32, "emergency_reserve": 634,
              "earmarked": 473, "unassigned": 23.32, "to_pay": 1402.85, "adjustment": float(adjustment),
              "invoice_total": 815.85, "items_total": 816.65, "discrepancy": 0.80,
              "responsibility": {"familia": 251.90, "empresa": 399.56, "pessoal": 165.19},
              "invoice_id": invoice.id, "salary_id": salary.id,
              "movements": [dict(origin=m.origem, id=m.origem_id, amount=m.valor, date=str(m.data)) for m in selected]}
    session.flush()
    state = record_state(session, ids)
    session.add(AuditEvent(user_id=user_id, actor="script:reconstruir_situacao_20261109", action=ACTION,
        entity_type="account_balance_snapshot", entity_id=snap.id,
        details={"bindings": bindings, "ids": ids, "fingerprint": fingerprint(state), "result": result}))
    session.flush()
    return {**result, "changed": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--user-id", required=True, type=int)
    parser.add_argument("--account-id", required=True, type=int)
    parser.add_argument("--card-id", required=True, type=int)
    parser.add_argument("--asset-id", required=True, type=int)
    args = parser.parse_args()
    path = args.database.resolve(strict=True)
    root = Path(__file__).resolve().parents[1] / ".local"
    if path.parent != root or not path.name.startswith("situacao-20261109-work") or path.suffix != ".sqlite3":
        raise SystemExit("Use somente uma cópia .local/situacao-20261109-work*.sqlite3; bases anteriores são protegidas")
    engine = create_engine("sqlite:///" + path.as_posix())
    with Session(engine) as session, session.begin():
        result = apply(session, args.user_id, args.account_id, args.card_id, args.asset_id)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
