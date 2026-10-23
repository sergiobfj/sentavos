"""Reconciliação direcionada por plano revisável, seca por padrão e só LOCAL.

Atualizações usam IDs e estado completo; inserções têm chave idempotente explícita.
O plano contém evidência e estado proposto. Backup e auditoria
preservam inclusive a previsão retirada em favor de uma cotação. Não recria
compras, parcelas, pagamentos, saldos bancários individuais ou resgates.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa
from dotenv import load_dotenv
from sqlmodel import Session, select

from app.ambiente import banco_local
from app.cartao import ciclo_da_parcela, competencia_da_parcela
from app.dominio.auditoria import registrar
from app.escopo import consulta
from app.models import (
    AccountBalanceSnapshot, AccountType, Category, CategoryType, Commitment,
    CommitmentSkip, FinancialAccount, Invoice, Card, InvoicePayment, InvestmentMovement,
    InvestmentPlan, PaymentMethod, Provision, Purchase, ReconciliationItem, Transaction, User,
)

MODELS = {m.__tablename__: m for m in (
    AccountBalanceSnapshot, Commitment, CommitmentSkip, Purchase,
    ReconciliationItem, Transaction,
)}
UPDATE_FIELDS = {
    "transactions": {"description", "date", "expense_class", "note", "finalidade"},
    "purchases": {"description", "purchase_date"},
    "commitments": {"description", "first_due", "total_amount", "note"},
    "reconciliation_items": {"description", "amount", "date", "kind", "status",
                             "transaction_id", "commitment_id", "provision_id", "prefill", "note"},
}
INSERT_MATCH = {
    "account_balance_snapshots": {"account_id", "observed_at"},
    "commitment_skips": {"commitment_id", "number"},
    "transactions": {"description"},
    "reconciliation_items": {"year", "month", "source"},
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def local_only(url, app_env):
    parsed = sa.engine.make_url(url)
    require(banco_local(str(parsed)) and app_env in {"test", "development"},
            "Reconciliação aceita somente ambiente local test/development; produção bloqueada.")
    if parsed.get_backend_name() != "sqlite":
        require(parsed.host in {"127.0.0.1", "localhost", "::1"}
                and (parsed.database or "").startswith("sentavos_reconciliacao_202610"),
                "Use uma cópia nova de reconciliação; banco local cotidiano também é protegido.")


def state(row):
    data = row.model_dump(mode="json")
    # SQLite devolve datetime sem fuso; o domínio interpreta esses instantes como UTC.
    for key in data:
        value = getattr(row, key)
        if isinstance(value, dt.datetime):
            value = value.replace(tzinfo=dt.timezone.utc) if value.tzinfo is None else value.astimezone(dt.timezone.utc)
            data[key] = value.isoformat()
    return data


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def fingerprint(session, user):
    from scripts.backup import copiar
    data = copiar(session.connection(), user.email)
    return digest({t: data[t] for t in data["schema"]})


def owned(session, user, model, identity):
    row = session.exec(consulta(model, user).where(model.id == identity)).first()
    require(row is not None, f"{model.__tablename__}/{identity}: registro ausente ou de outro usuário.")
    return row


def check_insert(session, user, model, row):
    if model is AccountBalanceSnapshot:
        account = owned(session, user, FinancialAccount, row.account_id)
        require(account.type == AccountType.RECONCILIATION and not account.archived,
                "Saldo agregado não pode ser atribuído a banco individual.")
        later = session.exec(consulta(AccountBalanceSnapshot, user).where(
            AccountBalanceSnapshot.account_id == row.account_id,
            AccountBalanceSnapshot.observed_at > row.observed_at)).first()
        require(later is None, "Existe saldo posterior: não reintroduzir referência antiga.")
    elif model is CommitmentSkip:
        owned(session, user, Commitment, row.commitment_id)
        require(row.abated_on is not None, "Abatimento exige data confirmada.")
        paid = session.exec(consulta(Transaction, user).where(
            Transaction.commitment_id == row.commitment_id,
            Transaction.commitment_no == row.number)).first()
        require(paid is None, "Parcela já possui lançamento: não converter pagamento em abatimento.")
    elif model is Transaction:
        category = owned(session, user, Category, row.category_id)
        require(category.type == CategoryType.INCOME and row.amount_paid is None
                and row.amount_planned is not None and row.amount_planned > 0
                and row.purchase_id is None and row.invoice_id is None
                and row.commitment_id is None and row.account_id is None,
                "Só recebível pontual previsto sem atribuição bancária pode ser inserido.")
    elif model is ReconciliationItem:
        require(row.transaction_id is None and row.commitment_id is None and row.provision_id is None,
                "Nova pendência não pode criar vínculo financeiro por suposição.")


def prepare(session, user, plan):
    require(plan.get("user_id") == user.id, "Titular do plano diverge do usuário selecionado.")
    require(plan.get("period") == "2026-10", "Plano fora do período autorizado.")
    actions = []
    seen = set()
    for op in plan["operations"]:
        require(all(op.get(k) for k in ("reason", "evidence", "confidence", "cash_effect")),
                "Faltam justificativa, evidência, confiança ou impacto.")
        require(op["table"] in MODELS, "Entidade não permitida.")
        model = MODELS[op["table"]]
        identity = (op["table"], op.get("id", json.dumps(op.get("match"), sort_keys=True)))
        require(identity not in seen, "Duas operações sobre a mesma linha.")
        seen.add(identity)
        if op["kind"] == "insert":
            require(set(op["match"]) == INSERT_MATCH.get(op["table"]), "Chave idempotente inválida.")
            row = model.model_validate({**op["values"], "user_id": user.id})
            require(row.id is None, "IDs de novas linhas devem ser gerados pelo banco.")
            q = consulta(model, user)
            for key in op["match"]:
                matched = model.model_validate({**op["values"], **op["match"]})
                require(state(matched)[key] == state(row)[key], "Chave de busca difere dos valores propostos.")
                q = q.where(getattr(model, key) == getattr(row, key))
            matches = session.exec(q).all()
            require(len(matches) <= 1, "Chave idempotente já tem duplicatas; conferência necessária.")
            if matches:
                current = state(matches[0])
                require(all(current[k] == v for k, v in state(row).items()
                            if k not in {"id", "created_at"}), "Registro equivalente mudou; preservar estado mais recente.")
                continue
            check_insert(session, user, model, row)
            actions.append((op, row, None, state(row)))
            continue
        require(op["kind"] in {"update", "remove_prediction"}, "Operação desconhecida.")
        row = session.exec(consulta(model, user).where(model.id == op["id"])).first()
        expected = state(model.model_validate(op["expected"]))
        require(expected["id"] == op["id"] and expected["user_id"] == user.id, "Identidade esperada inválida.")
        if op["kind"] == "remove_prediction":
            require(model is Transaction, "Só previsão avulsa pode ser retirada.")
            if row is None:
                continue
            require(row.amount_paid is None and row.amount_planned is not None
                    and row.purchase_id is None and row.invoice_id is None and row.commitment_id is None,
                    "Nunca retirar lançamento realizado, parcela ou baixa de compromisso.")
            for related in (ReconciliationItem, InvestmentMovement, InvestmentPlan):
                if hasattr(related, "transaction_id"):
                    require(session.exec(consulta(related, user).where(related.transaction_id == row.id)).first() is None,
                            "Previsão possui vínculo; revisar antes de retirar.")
            after = None
        else:
            require(set(op["after"]) <= UPDATE_FIELDS.get(op["table"], set()), "Campo financeiro não autorizado.")
            after = state(model.model_validate({**op["expected"], **op["after"]}))
            if row is not None and state(row) == after:
                continue
            if model is Transaction and row is not None:
                if "finalidade" in op["after"]:
                    require(set(op["after"]) == {"finalidade"} and row.purchase_id is not None,
                            "Atribuição nesta rotina deve alterar somente a responsabilidade de uma parcela.")
                    owned(session, user, Purchase, row.purchase_id)
                    category = owned(session, user, Category, row.category_id)
                    require(category.type == CategoryType.EXPENSE and after["finalidade"] in {"pessoal", "familia", "empresa"},
                            "Responsabilidade exige despesa e finalidade válida.")
                unpaid_card = row.purchase_id is not None and row.payment_method == PaymentMethod.CREDIT and session.exec(
                    consulta(InvoicePayment, user).where(InvoicePayment.invoice_id == row.invoice_id)).first() is None
                require(row.amount_paid is None or set(op["after"]) <= {"description", "note", "finalidade"}
                        or unpaid_card and set(op["after"]) <= {"description", "date", "note"},
                        "Lançamento realizado só admite correção descritiva nesta rotina.")
                if unpaid_card and "date" in op["after"]:
                    purchase = owned(session, user, Purchase, row.purchase_id)
                    patch = next((o["after"] for o in plan["operations"] if o["kind"] == "update"
                                  and o["table"] == "purchases" and o["id"] == purchase.id), {})
                    proposed = Purchase.model_validate({**state(purchase), **patch})
                    require(Transaction.model_validate(after).date == competencia_da_parcela(proposed.purchase_date, row.installment_no),
                            "Competência deve acompanhar a compra, sem editar parcela isolada.")
            if model is Purchase and row is not None:
                txs = session.exec(consulta(Transaction, user).where(Transaction.purchase_id == row.id)).all()
                ids = {t.invoice_id for t in txs}
                require(not ids or session.exec(consulta(InvoicePayment, user).where(
                    InvoicePayment.invoice_id.in_(ids))).first() is None, "Compra com fatura paga: preservar histórico.")
                proposed = Purchase.model_validate(after)
                card = owned(session, user, Card, row.card_id)
                for tx in txs:
                    patch = next((o["after"] for o in plan["operations"] if o["kind"] == "update"
                                  and o["table"] == "transactions" and o["id"] == tx.id), {})
                    target = Transaction.model_validate({**state(tx), **patch})
                    invoice = owned(session, user, Invoice, tx.invoice_id)
                    closing, due = ciclo_da_parcela(proposed.purchase_date, card.closing_day, card.due_day, tx.installment_no)
                    require(target.date == competencia_da_parcela(proposed.purchase_date, tx.installment_no)
                            and (invoice.closing_date, invoice.due_date) == (closing, due),
                            "Correção mudaria ciclo/fatura ou deixaria competência inconsistente; conferência necessária.")
            if model is ReconciliationItem:
                for field, related in (("transaction_id", Transaction), ("commitment_id", Commitment), ("provision_id", Provision)):
                    if after.get(field) is not None:
                        owned(session, user, related, after[field])
        require(row is not None and state(row) == expected,
                f"{op['table']}/{op['id']}: precondição mudou; nada deve ser aplicado.")
        actions.append((op, row, state(row), after))
    return actions


def reconcile(session, user, plan, apply=False):
    local_only(session.get_bind().engine.url, os.getenv("APP_ENV", "test"))
    if apply and session.get_bind().dialect.name == "postgresql":
        session.exec(select(User).where(User.id == user.id).with_for_update()).one()
    actions = prepare(session, user, plan)
    if actions:
        require(fingerprint(session, user) == plan["baseline_sha256"],
                "Há alterações desde o plano. Gere outra auditoria; não sobrescrever novidades.")
    report = {"dry_run": not apply, "plan_sha256": digest(plan), "changes": [], "backup": None}
    if apply and actions:
        from scripts.backup import salvar
        report["backup"] = salvar(session, user, f"antes-reconciliacao-outubro-2026-{uuid4().hex}")
        report["backup_sha256"] = hashlib.sha256(Path(report["backup"]).read_bytes()).hexdigest()
    for op, row, before, after in actions:
        if apply:
            if op["kind"] == "remove_prediction":
                session.delete(row)
            elif op["kind"] == "insert":
                session.add(row)
            else:
                for field in op["after"]:
                    setattr(row, field, getattr(type(row).model_validate(after), field))
                session.add(row)
            session.flush()
        report["changes"].append({"table": op["table"], "id": row.id, "kind": op["kind"],
            "before": before, "after": state(row) if apply and after is not None else after,
            **{k: op[k] for k in ("reason", "evidence", "confidence", "cash_effect")}})
    if apply and actions:
        registrar(session, user_id=user.id, ator="script:reconciliar_outubro_2026",
                  acao="reconciliacao.outubro_2026", detalhes=report)
        # A CLI confirma a conexão externa, não Session.commit(). Enviar o
        # evento agora garante que a auditoria participe da mesma transação.
        session.flush()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--usuario", required=True)
    parser.add_argument("--plano", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path, help="JSON privado local; não versionar dados reais")
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--apply", action="store_true")
    modo.add_argument("--dry-run", action="store_true", help="Somente ler e relatar (padrão)")
    args = parser.parse_args()
    load_dotenv()
    url = os.environ["DATABASE_URL"]
    local_only(url, os.getenv("APP_ENV", "development"))
    plan = json.loads(args.plano.read_text(encoding="utf-8"))
    engine = sa.create_engine(url)
    with engine.connect() as conn:
        if conn.dialect.name == "postgresql":
            conn.execute(sa.text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE" if args.apply
                                 else "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            conn.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
        with Session(bind=conn, join_transaction_mode="rollback_only") as session:
            user = session.exec(select(User).where(User.email == args.usuario.strip().lower())).one()
            result = reconcile(session, user, plan, args.apply)
            if args.apply:
                conn.commit()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"dry_run": result["dry_run"], "changes": len(result["changes"]),
                          "report": str(args.report), "backup_created": bool(result["backup"])}))


if __name__ == "__main__":
    main()
