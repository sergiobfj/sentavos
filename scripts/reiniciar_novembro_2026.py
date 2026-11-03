"""Ensaio PARCIAL de novembro; não aceita produção nem altera faturas.

Faturas manuais não são suportadas pelo domínio atual. Este script apenas
planeja e suspende ocorrências de novembro em uma cópia SQLite descartável.
O plano congela IDs e estados; reaplicação não alcança novos registros.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

import sqlalchemy as sa
from sqlmodel import SQLModel, Session, select

from app.models import AuditEvent, Commitment, CommitmentSkip, User
from app.planejamento import ocorrencias_ate

START = dt.date(2026, 11, 1)
END = dt.date(2026, 11, 30)
ACTION = "reinicio_novembro_2026.ensaio_parcial"
NOTE = "Reinício manual de novembro/2026: ocorrência suspensa, sem pagamento ou abatimento."


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_tables(connection):
    result = {}
    for name in sorted(sa.inspect(connection).get_table_names()):
        require(name.replace("_", "").isalnum(), "Nome de tabela inválido")
        result[name] = [dict(r) for r in connection.execute(sa.text(f'SELECT * FROM "{name}"')).mappings()]
    return result


def clone(source: Path, destination: Path):
    """Cópia nova exclusivamente local; jamais sobrescreve banco existente."""
    require(not destination.exists(), "A cópia local já existe")
    require(destination.resolve().parent == (Path.cwd() / ".local").resolve()
            and destination.name.startswith("reinicio-novembro-"), "Destino fora da pasta de ensaio")
    data = json.loads(source.read_text(encoding="utf-8"))
    require(data.get("read_only") is True, "Exige backup de transação somente leitura")
    require(set(data["tables"]) == set(SQLModel.metadata.tables) | {"alembic_version"},
            "Schema do backup diverge dos modelos: interromper")
    destination.parent.mkdir(exist_ok=True)
    engine = sa.create_engine(f"sqlite:///{destination.as_posix()}")

    @sa.event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    with engine.begin() as c:
        for table in SQLModel.metadata.sorted_tables:
            require({column["name"] for column in data["schema"][table.name]}
                    == set(table.c.keys()), f"Colunas divergentes: {table.name}")
            rows = []
            for original in data["tables"][table.name]:
                row = dict(original)
                for name, value in row.items():
                    if value is not None and isinstance(table.c[name].type, sa.DateTime):
                        row[name] = dt.datetime.fromisoformat(value)
                    elif value is not None and isinstance(table.c[name].type, sa.Date):
                        row[name] = dt.date.fromisoformat(value)
                rows.append(row)
            if rows:
                c.execute(table.insert(), rows)
            require(c.scalar(sa.select(sa.func.count()).select_from(table)) == len(rows), "Contagem divergente")
        c.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
        c.execute(sa.text("INSERT INTO alembic_version VALUES (:version_num)"), data["tables"]["alembic_version"])
    return engine


def prepare(session, user_id):
    user = session.get(User, user_id)
    require(user is not None and not user.read_only, "Titular ausente ou somente leitura")
    skips = {(s.commitment_id, s.number) for s in session.exec(select(CommitmentSkip).where(
        CommitmentSkip.user_id == user_id)).all()}
    targets = []
    for c in session.exec(select(Commitment).where(Commitment.user_id == user_id)).all():
        for number, due in ocorrencias_ate(c, END):
            if due < START or (c.cancelled_on and due >= c.cancelled_on) or (c.id, number) in skips:
                continue
            targets.append({"commitment_id": c.id, "number": number, "due": due.isoformat(),
                            "amount": c.amount, "before": c.model_dump(mode="json")})
    return {"user_id": user_id, "period": "2026-11", "partial": True,
            "blocked": ["Faturas sem valor manual e sem estado A preencher; parcelas históricas preservadas",
                        "Interface ainda exibe totais R$ 0,00 em alguns estados vazios; não alterada"],
            "targets": targets}


def apply_occurrences(session, plan):
    """Somente SQLite; uma transação, estados congelados e marcador idempotente."""
    require(session.get_bind().dialect.name == "sqlite", "Ensaio aceita somente cópia SQLite")
    require(plan["period"] == "2026-11" and plan["partial"] is True, "Plano fora do escopo")
    prior = session.exec(select(AuditEvent).where(AuditEvent.user_id == plan["user_id"],
                                                AuditEvent.action == ACTION)).first()
    if prior:
        return 0
    # Valida tudo antes de escrever. Nenhuma ocorrência paga é dispensada.
    from app.models import Transaction
    for target in plan["targets"]:
        c = session.get(Commitment, target["commitment_id"])
        require(c is not None and c.user_id == plan["user_id"]
                and c.model_dump(mode="json") == target["before"], "Compromisso mudou após simulação")
        due = dict(ocorrencias_ate(c, END)).get(target["number"])
        require(due is not None and START <= due <= END and due.isoformat() == target["due"], "Fora de novembro")
        paid = session.exec(select(Transaction).where(Transaction.commitment_id == c.id,
                            Transaction.commitment_no == target["number"])).first()
        require(paid is None, "Ocorrência tem lançamento vinculado: exige análise específica")
        require(session.exec(select(CommitmentSkip).where(CommitmentSkip.commitment_id == c.id,
                CommitmentSkip.number == target["number"])).first() is None, "Ocorrência mudou após simulação")
    for target in plan["targets"]:
        session.add(CommitmentSkip(user_id=plan["user_id"], commitment_id=target["commitment_id"],
                    number=target["number"], note=NOTE))
    session.add(AuditEvent(user_id=plan["user_id"], actor="script:reiniciar_novembro_2026",
                          action=ACTION, details={"plan_sha256": hashlib.sha256(json.dumps(plan,
                          sort_keys=True).encode()).hexdigest(), "period": "2026-11", "partial": True,
                          "occurrences": [{k: v for k, v in t.items() if k != "before"} for t in plan["targets"]]}))
    session.flush()
    return len(plan["targets"])


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--usuario-id", type=int, required=True)
    parser.add_argument("--apply-local-occurrences", action="store_true")
    args = parser.parse_args()
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = Path.cwd() / ".local" / f"reinicio-novembro-{stamp}.sqlite3"
    engine = clone(args.backup, destination)
    with Session(engine) as session:
        plan = prepare(session, args.usuario_id)
        with engine.connect() as c:
            before = read_tables(c)
        report = {"source": str(args.backup), "source_sha256": hashlib.sha256(args.backup.read_bytes()).hexdigest(),
                  "copy": str(destination), "plan": plan, "applied": 0}
        # O plano com IDs e estados fica no disco antes da primeira escrita financeira.
        path = destination.with_suffix(".json")
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if args.apply_local_occurrences:
            report["applied"] = apply_occurrences(session, plan)
            after = read_tables(session.connection())
            for name, rows in before.items():
                if name not in {"commitment_skips", "audit_events"}:
                    require(after[name] == rows, f"Dados originais mudaram: {name}")
                else:
                    require(all(row in after[name] for row in rows), f"Histórico alterado: {name}")
            # Todas as invariantes são conferidas antes do commit.
            session.commit()
            require(apply_occurrences(session, plan) == 0, "Reaplicação não idempotente")
            session.commit()
            with engine.connect() as c:
                require(read_tables(c) == after, "Reaplicação alterou dados")
            report["original_rows_preserved"] = True
            report["idempotent"] = True
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(path), "copy": str(destination), "partial": True,
                      "occurrences": len(plan["targets"]), "amount": round(sum(t["amount"] for t in plan["targets"]), 2),
                      "applied": report["applied"], "deleted": 0, "production_changed": False}))


if __name__ == "__main__":
    main()
