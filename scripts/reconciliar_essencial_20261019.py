"""Pré-voo e reconciliação pontual de outubro de 2026.

Por padrão, somente lê. A escrita exige --apply, backup integral com hash,
identificador de branch de recuperação Neon e autorização operacional separada.
Nunca importa linhas da cópia antiga nem escolhe IDs para linhas novas.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path

import sqlalchemy as sa
from dotenv import load_dotenv

from app.ambiente import banco_local, verificar_banco

if sys.flags.optimize:
    raise RuntimeError("Esta rotina exige Python sem -O para manter todas as pré-condições ativas.")

ROOT = Path(__file__).resolve().parent.parent
OBSERVED_AT = dt.datetime(2026, 10, 19, 11, 44, 15, tzinfo=dt.timezone.utc)


def canonical(rows):
    return sorted(json.dumps(row, sort_keys=True, ensure_ascii=False, default=str) for row in rows)


def inventory_matches(conn, baseline):
    """Recusa até uma única alteração concorrente depois do backup."""
    tables = baseline["tables"]
    names = set(sa.inspect(conn).get_table_names())
    assert names == set(tables), "O conjunto de tabelas mudou desde o backup."
    for table in sorted(tables):
        assert table.replace("_", "").isalnum()
        if "schema" in baseline:
            columns = [{"name": c["name"], "type": str(c["type"]), "nullable": c["nullable"]}
                       for c in sa.inspect(conn).get_columns(table)]
            assert sorted(columns, key=lambda c: c["name"]) == sorted(baseline["schema"][table], key=lambda c: c["name"]), (
                f"Schema de {table} mudou desde o backup."
            )
        now = [dict(r) for r in conn.execute(sa.text(f'SELECT * FROM "{table}"')).mappings()]
        assert canonical(now) == canonical(tables[table]), f"{table} mudou desde o backup."


def one(conn, sql, **params):
    return conn.execute(sa.text(sql), params).mappings().one()


def rows(conn, sql, **params):
    return conn.execute(sa.text(sql), params).mappings().all()


def preflight(conn):
    assert conn.scalar(sa.text("SELECT version_num FROM alembic_version")) == "0013_abatimento_compromisso"
    assert conn.scalar(sa.text("SELECT count(*) FROM financial_accounts WHERE user_id=1")) == 4
    assert {r["id"] for r in rows(conn, "SELECT id FROM financial_accounts WHERE user_id=1")} == {1, 2, 3, 4}
    account = one(conn, "SELECT id, type, archived FROM financial_accounts WHERE user_id=1 AND id=4")
    assert account["type"] == "RECONCILIATION" and not account["archived"]
    uber = one(conn, "SELECT id, date, amount_paid, purchase_id, invoice_id FROM transactions WHERE user_id=1 AND id=1168")
    assert str(uber["date"]) == "2026-10-13" and uber["amount_paid"] == 5.8 and uber["purchase_id"] == 49
    assert uber["invoice_id"] is not None
    assert conn.scalar(sa.text("SELECT total_amount FROM purchases WHERE user_id=1 AND id=49")) == 5.8
    assert conn.scalar(sa.text("SELECT count(*) FROM purchases WHERE user_id=1 AND total_amount=904")) == 0

    # Lançamentos de cartão com data futura e amount_paid representam compras
    # parceladas já lançadas, não pagamentos da fatura.
    cash = rows(conn, """SELECT id, date, amount_paid FROM transactions
        WHERE user_id=1 AND date >= DATE '2026-10-19' AND amount_paid IS NOT NULL
          AND purchase_id IS NULL AND invoice_id IS NULL
          AND payment_method IS DISTINCT FROM 'CREDIT'""")
    invoice_payments = rows(conn, "SELECT id FROM invoice_payments WHERE user_id=1 AND date >= DATE '2026-10-19'")
    transfers = rows(conn, "SELECT id FROM transfers WHERE user_id=1 AND date >= DATE '2026-10-19'")
    movements = rows(conn, "SELECT id FROM investment_movements WHERE user_id=1 AND date >= DATE '2026-10-19'")
    later_snapshots = rows(conn, "SELECT id, balance FROM account_balance_snapshots WHERE user_id=1 AND observed_at > :cutoff",
                           cutoff=OBSERVED_AT)
    assert not (cash or invoice_payments or transfers or movements or later_snapshots), (
        "Há entradas, pagamentos ou saldos posteriores; revisar o saldo antes de aplicar."
    )
    hunter = one(conn, "SELECT first_due, amount, installments, total_amount FROM commitments WHERE user_id=1 AND id=7")
    assert hunter["amount"] == 618.08 and hunter["installments"] == 48
    assert str(hunter["first_due"]) in ("2026-11-09", "2026-11-12")
    assert hunter["total_amount"] in (13990.0, 16469.24)
    advance = one(conn, "SELECT first_due, amount FROM commitments WHERE user_id=1 AND id=15")
    assert advance["amount"] == 720 and str(advance["first_due"]) in ("2026-10-15", "2026-10-20")
    planned = one(conn, "SELECT date, amount_planned, amount_paid FROM transactions WHERE user_id=1 AND id=936")
    assert planned["amount_planned"] == 720 and planned["amount_paid"] is None
    assert str(planned["date"]) in ("2026-10-15", "2026-10-20")
    assert conn.scalar(sa.text("SELECT amount_planned FROM transactions WHERE user_id=1 AND id=937")) == 700
    for number in (1, 2):
        assert conn.scalar(sa.text("""SELECT count(*) FROM transactions WHERE user_id=1
            AND commitment_id=7 AND commitment_no=:number"""), {"number": number}) == 0
        decisions = rows(conn, """SELECT abated_on FROM commitment_skips
            WHERE user_id=1 AND commitment_id=7 AND number=:number""", number=number)
        assert len(decisions) <= 1 and (not decisions or str(decisions[0]["abated_on"]) == "2026-10-15")
    return {"later_cash_transactions": len(cash), "later_invoice_payments": len(invoice_payments),
            "later_transfers": len(transfers), "later_investment_movements": len(movements),
            "later_snapshots": len(later_snapshots), "uber_preserved": True, "financial_accounts": 4}


def apply(conn, backup_sha, recovery_branch):
    changes = []
    latest = rows(conn, """SELECT id, balance, observed_at FROM account_balance_snapshots
        WHERE user_id=1 AND account_id=4 ORDER BY observed_at DESC, id DESC LIMIT 1""")
    assert latest
    if latest[0]["balance"] != 668.96:
        assert latest[0]["balance"] == 684.39 and latest[0]["observed_at"] < OBSERVED_AT
        conn.execute(sa.text("""INSERT INTO account_balance_snapshots
            (user_id, account_id, observed_at, balance, source, note, created_at)
            VALUES (1, 4, :at, 668.96, 'MANUAL', :note, now())"""),
            {"at": OBSERVED_AT, "note": "Saldo informado pelo titular: R$418,96 + R$250,00; origem bancária não identificada. Hora da referência local, não do extrato."})
        changes.append("snapshot:4")

    result = conn.execute(sa.text("""UPDATE commitments SET first_due=DATE '2026-10-20',
        description='Adiantamento (dia 20)' WHERE id=15 AND user_id=1 AND first_due=DATE '2026-10-15'"""))
    if result.rowcount: changes.append("commitment:15")
    result = conn.execute(sa.text("""UPDATE transactions SET date=DATE '2026-10-20'
        WHERE id=936 AND user_id=1 AND date=DATE '2026-10-15' AND amount_paid IS NULL"""))
    if result.rowcount: changes.append("transaction:936")

    category = rows(conn, """SELECT id, type FROM categories WHERE user_id=1 AND name='Reembolsos e estornos'""")
    assert len(category) <= 1 and (not category or category[0]["type"] == "INCOME")
    if category:
        category_id = category[0]["id"]
    else:
        category_id = conn.execute(sa.text("""INSERT INTO categories
            (user_id, name, type, color, icon, archived)
            VALUES (1, 'Reembolsos e estornos', 'INCOME', '#8ca993', '↩', false) RETURNING id""")).scalar_one()
        changes.append(f"category:{category_id}")
    refund = rows(conn, """SELECT id, date, amount_planned, amount_paid, category_id FROM transactions
        WHERE user_id=1 AND description='Reembolso Seguro Mão na Roda'""")
    assert len(refund) <= 1
    if refund:
        assert str(refund[0]["date"]) == "2026-10-28" and refund[0]["amount_planned"] == 550
        assert refund[0]["amount_paid"] is None and refund[0]["category_id"] == category_id
    else:
        new_id = conn.execute(sa.text("""INSERT INTO transactions
            (user_id, date, description, amount_planned, amount_paid, category_id, payment_method, note)
            VALUES (1, DATE '2026-10-28', 'Reembolso Seguro Mão na Roda', 550, NULL, :category_id, 'CASH',
                    'Prometido até 28/10; ainda não recebido na referência de 19/10.') RETURNING id"""),
            {"category_id": category_id}).scalar_one()
        changes.append(f"transaction:{new_id}")

    result = conn.execute(sa.text("""UPDATE commitments SET first_due=DATE '2026-11-12', total_amount=16469.24
        WHERE id=7 AND user_id=1 AND first_due=DATE '2026-11-09' AND total_amount=13990"""))
    if result.rowcount: changes.append("commitment:7")
    for number in (1, 2):
        exists = conn.scalar(sa.text("""SELECT count(*) FROM commitment_skips
            WHERE user_id=1 AND commitment_id=7 AND number=:number"""), {"number": number})
        if not exists:
            new_id = conn.execute(sa.text("""INSERT INTO commitment_skips
                (user_id, commitment_id, number, abated_on, note)
                VALUES (1, 7, :number, DATE '2026-10-15',
                        'Abatimento contratual pelo credor; sem saída de caixa.') RETURNING id"""),
                {"number": number}).scalar_one()
            changes.append(f"commitment_skip:{new_id}")

    for item_id, amount, description in ((4, 720, "Recebimento salarial de R$720 — previsto"),
                                         (5, 700, "Recebimento salarial de R$700 — previsto")):
        item = one(conn, """SELECT amount, status, transaction_id, commitment_id, provision_id,
            description, date FROM reconciliation_items WHERE user_id=1 AND id=:id""", id=item_id)
        expected_transaction = 936 if item_id == 4 else 937
        assert item["amount"] == amount and item["transaction_id"] == expected_transaction
        assert item["commitment_id"] is None and item["provision_id"] is None
        target_date = dt.date(2026, 10, 20)
        if item["status"] != "CONFIRMAR" or item["description"] != description or item["date"] != target_date:
            assert item["status"] in ("RESOLVIDO", "CONFIRMAR")
            conn.execute(sa.text("""UPDATE reconciliation_items
                SET status='CONFIRMAR', description=:description, date=DATE '2026-10-20'
                WHERE user_id=1 AND id=:id"""), {"description": description, "id": item_id})
            changes.append(f"reconciliation_item:{item_id}")

    if changes:
        conn.execute(sa.text("""INSERT INTO audit_events
            (user_id, actor, action, entity_type, entity_id, details, created_at)
            VALUES (1, 'script:reconciliar_essencial_20261019', 'release_reconciliation', 'user', 1,
                    CAST(:details AS json), now())"""),
            {"details": json.dumps({"backup_sha256": backup_sha, "recovery_branch": recovery_branch,
                                    "changes": changes}, ensure_ascii=False)})
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", required=True, type=Path, help="Backup JSON integral e recente da produção")
    parser.add_argument("--sha256", required=True, help="Hash SHA-256 esperado do backup")
    parser.add_argument("--apply", action="store_true", help="Exige autorização financeira separada")
    parser.add_argument("--recovery-branch", help="ID da branch Neon criada e verificada antes da escrita")
    parser.add_argument("--local-rehearsal", action="store_true", help="Permite escrita só na cópia local de ensaio")
    args = parser.parse_args()
    assert args.baseline.is_file()
    raw = args.baseline.read_bytes()
    actual_sha = hashlib.sha256(raw).hexdigest()
    assert actual_sha == args.sha256, "Hash do backup não confere."
    baseline = json.loads(raw)
    load_dotenv()
    url = os.environ["DATABASE_URL"]
    verificar_banco(url)
    local = banco_local(url)
    if args.apply:
        if local:
            assert args.local_rehearsal and url.endswith("/sentavos_prod_validation_release")
        else:
            assert not args.local_rehearsal and os.getenv("APP_ENV") == "production"
            assert os.getenv("ALLOW_PRODUCTION_DATABASE", "").lower() == "true"
            assert ".neon.tech" in sa.engine.make_url(url).host
            assert args.recovery_branch and args.recovery_branch.startswith("br-")
    engine = sa.create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        if args.apply:
            conn.execute(sa.text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
            conn.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
        else:
            conn.execute(sa.text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        assert conn.scalar(sa.text("SELECT current_database()")) == sa.engine.make_url(url).database
        inventory_matches(conn, baseline)
        report = preflight(conn)
        if args.apply:
            changes = apply(conn, actual_sha, args.recovery_branch or "local-rehearsal")
            conn.commit()
            print(json.dumps({"applied": changes, "preflight": report}, ensure_ascii=False))
        else:
            print(json.dumps({"dry_run": True, "preflight": report, "baseline_sha256": actual_sha}, ensure_ascii=False))


if __name__ == "__main__":
    main()
