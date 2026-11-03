"""Reset dirigido e idempotente, SOMENTE em cópia SQLite local.

Seco por padrão: --database <cópia> --usuario-id <id> --plan <json privado>.
Depois de revisar o plano congelado, --apply o executa numa transação única.
Não lê credenciais de produção, não aceita Postgres e não restaura banco algum.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

import sqlalchemy as sa

from scripts.reiniciar_novembro_2026 import read_tables, require
from app.dominio.tempo import FUSO

CUT = "2026-11-01"
ACTION = "reset_total.desde_2026_11"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def prepare(connection, user_id):
    tables = read_tables(connection)
    users = tables["users"]
    owner = next((r for r in users if r["id"] == user_id), None)
    require(owner is not None and not owner["read_only"], "Titular inválido")
    if any(r["user_id"] == user_id and r["action"] == ACTION for r in tables["audit_events"]):
        return {"user_id": user_id, "cutoff": CUT, "already_applied": True}
    owned = {t: [r for r in rows if r.get("user_id") == user_id] for t, rows in tables.items()}
    plan = {"user_id": user_id, "cutoff": CUT, "already_applied": False, "delete": {}, "update": {},
            "before_hash": digest(tables), "counts_before": {t: len(r) for t, r in owned.items()}}

    def remove(table, predicate):
        plan["delete"][table] = [r for r in owned[table] if predicate(r)]

    def update(table, row, values):
        changes = {k: v for k, v in values.items() if row.get(k) != v}
        if changes:
            plan["update"].setdefault(table, []).append({"before": row, "set": changes})

    def monthly(r):
        return f'{r["year"]:04}-{r["month"]:02}-01' >= CUT

    for table in ("transactions", "invoice_payments", "transfers", "investment_movements", "investment_plans"):
        remove(table, lambda r: r["date"] >= CUT)
    remove("purchases", lambda r: r["purchase_date"] >= CUT)
    remove("budgets", monthly)
    remove("reconciliation_items", lambda r: monthly(r) or (r["date"] or "") >= CUT)
    remove("asset_snapshots", lambda r: monthly(r) or (r["observed_on"] or "") >= CUT)

    def observed_date(r):
        value = dt.datetime.fromisoformat(r["observed_at"])
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(FUSO).date().isoformat()

    remove("account_balance_snapshots", lambda r: observed_date(r) >= CUT)
    remove("provisions", lambda r: r["created_on"] >= CUT)
    for r in owned["provisions"]:
        if r["created_on"] < CUT and (not r["released_on"] or r["released_on"] >= CUT):
            update("provisions", r, {"released_on": CUT})

    # Cancela a geração após o corte, sem apagar contratos nem suas baixas históricas.
    for r in owned["commitments"]:
        if not r["cancelled_on"] or r["cancelled_on"] > CUT:
            update("commitments", r, {"cancelled_on": CUT})
    from app.models import Commitment
    from app.planejamento import vencimento
    commitments = {r["id"]: Commitment.model_validate(dict(r)) for r in connection.execute(
        sa.select(Commitment.__table__).where(Commitment.user_id == user_id)).mappings()}
    remove("commitment_skips", lambda r: vencimento(commitments[r["commitment_id"]], r["number"]).isoformat() >= CUT)

    future_invoices = {r["id"] for r in owned["invoices"] if monthly(r) or r["due_date"] >= CUT}
    for r in owned["invoices"]:
        if r["id"] in future_invoices:
            update("invoices", r, {"reset_on": CUT, "manual_total": None})
    stopped = {r["purchase_id"] for r in owned["transactions"]
               if r["date"] >= CUT or r["invoice_id"] in future_invoices}
    for r in owned["purchases"]:
        if r["purchase_date"] < CUT and r["id"] in stopped:
            update("purchases", r, {"installments_stopped_from": CUT})

    remove("scenario_items", lambda r: r["date"] >= CUT)
    for r in owned["scenario_items"]:
        if r["date"] < CUT:
            date = dt.date.fromisoformat(r["date"])
            months = (2026 - date.year) * 12 + 11 - date.month
            if r["repeat_months"] > months:
                update("scenario_items", r, {"repeat_months": months})
    remaining_scenarios = {r["scenario_id"] for r in owned["scenario_items"] if r["date"] < CUT}
    remove("scenarios", lambda r: str(r["created_at"])[:10] >= CUT and r["id"] not in remaining_scenarios)
    update("users", owner, {"operations_start": CUT})
    # O plano carrega cada estado original, não uma consulta aberta que apagaria registros novos.
    plan["summary"] = {
        t: {"deleted": len(rows), "planned": round(sum(r.get("amount_planned") or 0 for r in rows), 2),
            "paid": round(sum(r.get("amount_paid") or 0 for r in rows), 2),
            "amount": round(sum(r.get("amount") or r.get("value") or 0 for r in rows), 2)}
        for t, rows in plan["delete"].items()
    }
    plan["changed_counts"] = {t: len(rows) for t, rows in plan["update"].items()}
    return plan


def apply(connection, plan):
    require(connection.dialect.name == "sqlite", "Reset exclusivamente na cópia SQLite local")
    require(plan["cutoff"] == CUT, "Data de corte inválida")
    before = read_tables(connection)
    if any(r["user_id"] == plan["user_id"] and r["action"] == ACTION for r in before["audit_events"]):
        return {"already_applied": True, "changed": 0}
    require(not plan["already_applied"], "Plano não contém ações")
    require(digest(before) == plan["before_hash"], "Banco mudou desde a simulação: gere e revise outro plano")
    require(digest(plan) == digest(prepare(connection, plan["user_id"])),
            "Plano alterado ou fora do escopo: histórico anterior ao corte é protegido")
    meta = sa.MetaData()
    meta.reflect(connection)
    expected = {t: [dict(r) for r in rows] for t, rows in before.items()}
    for table, changes in plan["update"].items():
        for change in changes:
            original = change["before"]
            require(original["id"] == plan["user_id"] if table == "users" else original["user_id"] == plan["user_id"], "Outro titular")
            connection.execute(meta.tables[table].update().where(meta.tables[table].c.id == original["id"]).values(**{
                k: dt.date.fromisoformat(v) if isinstance(meta.tables[table].c[k].type, sa.Date) and v else v
                for k, v in change["set"].items()}))
            next(r for r in expected[table] if r["id"] == original["id"]).update(change["set"])
    # Dependentes antes dos pais; itens/pagamentos de outubro nunca são excluídos.
    order = ["investment_plans", "investment_movements", "invoice_payments", "transactions", "commitment_skips",
             "provisions", "scenario_items", "scenarios", "reconciliation_items", "purchases", "budgets",
             "asset_snapshots", "account_balance_snapshots", "transfers"]
    for table in order:
        rows = plan["delete"].get(table, [])
        for r in rows:
            require(r["user_id"] == plan["user_id"], "Outro titular")
            connection.execute(meta.tables[table].delete().where(meta.tables[table].c.id == r["id"]))
        ids = {r["id"] for r in rows}
        expected[table] = [r for r in expected[table] if r["id"] not in ids]
    require(read_tables(connection) == expected, "Uma linha fora do plano foi alterada")
    require(not connection.execute(sa.text("PRAGMA foreign_key_check")).all(), "Integridade referencial violada")
    details = {"cutoff": CUT, "plan_sha256": digest(plan), "removed": plan["summary"], "changed": plan["changed_counts"]}
    connection.execute(meta.tables["audit_events"].insert().values(user_id=plan["user_id"],
        actor="script:reset_total_novembro_2026", action=ACTION, details=details, created_at=dt.datetime.now(dt.timezone.utc)))
    return {"already_applied": False, **details}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--usuario-id", required=True, type=int)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    db = args.database.resolve()
    require(db.exists() and db.parent == (Path.cwd() / ".local").resolve()
            and db.name.startswith("reinicio-novembro-total-work-"), "Use uma cópia local de trabalho dedicada")
    require(args.plan.resolve().parent == (Path.cwd() / ".local").resolve(), "Plano financeiro deve ficar na pasta privada .local")
    engine = sa.create_engine(f"sqlite:///{db.as_posix()}")
    @sa.event.listens_for(engine, "connect")
    def foreign_keys(c, _):
        c.execute("PRAGMA foreign_keys=ON")
    with engine.begin() as c:
        if args.apply:
            plan = json.loads(args.plan.read_text(encoding="utf-8"))
            require(plan["user_id"] == args.usuario_id, "Titular diverge do plano")
            result = apply(c, plan)
        else:
            require(not args.plan.exists(), "Não sobrescrever planos existentes")
            result = prepare(c, args.usuario_id)
            args.plan.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"database": str(db), "applied": args.apply, "plan": str(args.plan),
                      "summary": result.get("summary", result.get("removed")), "changes": result.get("changed_counts", result.get("changed"))}))


if __name__ == "__main__":
    main()
