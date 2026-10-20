"""Fixture sintética isolada para test:refino. Nunca conecta a banco remoto.

Rodar da raiz: uv run python frontend/tests/refino/prepare.py
Postgres local precisa estar ativo na porta 54329.
"""
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
BASE = "postgresql://postgres@127.0.0.1:54329/"
with create_engine(BASE+"postgres",isolation_level="AUTOCOMMIT").connect() as conn:
    if not conn.scalar(text("select 1 from pg_database where datname='sentavos_refino'")):
        conn.execute(text("create database sentavos_refino"))
os.environ["APP_ENV"]="test"
os.environ["DATABASE_URL"]=BASE+"sentavos_refino"
from app.database import create_db_and_tables, engine  # noqa: E402
from app.auth import gerar_hash  # noqa: E402
from app.models import User  # noqa: E402
from sqlmodel import Session  # noqa: E402

create_db_and_tables()
suffix=uuid4().hex[:8]
email,demo=f"refino-{suffix}@local.test",f"demo-{suffix}@local.test"
password="Refino-local-2026!"
with Session(engine) as session:
    for addr,read_only in ((email,False),(demo,True)):
        session.add(User(email=addr,name="Validação local",password_hash=gerar_hash(password),read_only=read_only))
    session.commit()
(ROOT/".local").mkdir(exist_ok=True)
(ROOT/".local/refino-users.json").write_text(json.dumps(dict(email=email,demo=demo,password=password)),encoding="utf-8")
print("Fixture local preparada. Nenhum usuário ou histórico anterior foi alterado.")
