"""O esqueleto de todo script que mexe em dado.

  - **dry-run por padrão**: sem `--apply`, só mostra o que faria;
  - **usuário explícito**: `--usuario email` (nunca "todo mundo");
  - **ambiente visível**: APP_ENV, banco (sem senha), usuário e modo, antes de tudo;
  - **backup antes de gravar**: `scripts/backup.py`, num lugar só;
  - **rastro depois**: um `audit_event` por execução que gravou.

A trava contra produção é a do app (app/ambiente.py): banco remoto só com
APP_ENV=production E ALLOW_PRODUCTION_DATABASE=true.
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, select  # noqa: E402

from app import ambiente  # noqa: E402
from app.database import DATABASE_URL, engine  # noqa: E402
from app.dominio.auditoria import registrar  # noqa: E402
from app.models import User  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def argumentos(descricao: str, desfazer: bool = False) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=descricao)
    ap.add_argument("--usuario", required=True, help="e-mail da conta (obrigatório)")
    ap.add_argument("--apply", "--aplicar", dest="apply", action="store_true",
                    help="grava de verdade (sem isto: só mostra o que faria)")
    if desfazer:
        ap.add_argument("--undo", action="store_true", help="desfaz o que este script fez (idempotente)")
    return ap


def abrir(email: str) -> tuple[Session, User]:
    session = Session(engine)
    dono = session.exec(select(User).where(User.email == email.strip().lower())).first()
    if dono is None:
        session.close()
        sys.exit(f"Não existe conta para {email}.")
    return session, dono


def cabecalho(script: str, dono: User, aplicar: bool, extra: str = "") -> None:
    print("=" * 72)
    print(f"{script} | APP_ENV={ambiente.app_env()} | banco {ambiente.descrever(DATABASE_URL)}")
    print(f"usuário {dono.email} (id {dono.id}) | {'GRAVANDO' if aplicar else 'SECO (nada é gravado)'} {extra}")
    print("=" * 72)


def backup(session: Session, dono: User, rotulo: str) -> str:
    from scripts.backup import salvar

    caminho = salvar(session, dono, rotulo)
    print(f"backup: {caminho}")
    return caminho


def auditar(session: Session, dono: User, script: str, acao: str, detalhes: dict) -> None:
    registrar(session, acao=acao, ator=f"script:{script}", user_id=dono.id, detalhes=detalhes)
