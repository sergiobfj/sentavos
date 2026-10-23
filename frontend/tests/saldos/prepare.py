"""Usuários fictícios para E2E em PostgreSQL isolado, sem dados bancários reais."""
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

url = os.environ["DATABASE_URL"]
parsed = make_url(url)
assert parsed.host in {"127.0.0.1", "localhost"}
assert parsed.database.startswith("sentavos_reconciliacao_20261023_sintetico")
assert os.environ.get("APP_ENV") == "test"
with create_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT").connect() as conn:
    if not conn.scalar(text("select 1 from pg_database where datname=:name"), {"name": parsed.database}):
        conn.exec_driver_sql('CREATE DATABASE ' + conn.dialect.identifier_preparer.quote(parsed.database))
from app.database import create_db_and_tables, engine
from app.auth import gerar_hash
from app.models import User
from sqlmodel import Session

create_db_and_tables()
suffix = uuid4().hex[:10]
fixture = dict(email=f"saldos-{suffix}@local.test", password=f"Local-{uuid4().hex}!")
with Session(engine) as session:
    session.add(User(email=fixture["email"], name="Validação sintética", password_hash=gerar_hash(fixture["password"])))
    session.commit()
(ROOT / ".local").mkdir(exist_ok=True)
(ROOT / ".local/saldos-users.json").write_text(json.dumps(fixture), encoding="utf-8")
print("Usuário sintético criado em banco isolado; credenciais somente em .local/saldos-users.json")
