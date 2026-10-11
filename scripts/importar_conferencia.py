"""Carrega candidatos de um arquivo na conferência de um mês — e só isso.

    uv run python -m scripts.importar_conferencia --usuario voce@exemplo.com \\
        --arquivo backups/conferencia-outubro-2026.json            # modo seco
    uv run python -m scripts.importar_conferencia ... --aplicar     # grava

O arquivo vira ITENS DA CONFERÊNCIA, nunca lançamento, compromisso ou reserva.
Cada item espera, na tela "Organizar o mês", que o dono diga o que ele é: já
existe, criar realizado, criar previsto, criar compromisso, ignorar. É a
diferença entre "importar tudo" e "revisar e aplicar".

O arquivo com os itens de verdade mora fora do repositório (em `backups/`, que
o git ignora): são valores reais, e o repositório não guarda dado financeiro.

Formato:

    {"year": 2026, "month": 10,
     "items": [{"description": "...", "amount": 120.0, "date": "2026-10-05",
                "kind": "saida", "suggestion": "...", "question": "...",
                "category_hint": "...", "prefill": {...}, "status": "pendente"}]}

Seguro de rodar duas vezes: item com a mesma descrição e o mesmo valor no
mesmo mês é pulado. Modo seco por padrão, e backup antes de gravar.
"""

import argparse
import datetime as dt
import json
import os
import sys

from sqlmodel import Session, select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.conferencia import candidatos  # noqa: E402
from app.database import engine  # noqa: E402
from app.models import (  # noqa: E402
    ReconciliationItem,
    ReconciliationKind,
    ReconciliationStatus,
    User,
)


def ler(caminho: str) -> tuple[int, int, list[dict]]:
    dados = json.load(open(caminho, encoding="utf-8"))
    return int(dados["year"]), int(dados["month"]), list(dados["items"])


def montar(dono: User, ano: int, mes: int, bruto: dict) -> ReconciliationItem:
    """O item como iria pro banco. Recusa o que não entende, em vez de adivinhar."""
    data = dt.date.fromisoformat(bruto["date"]) if bruto.get("date") else None
    return ReconciliationItem(
        user_id=dono.id,
        year=ano,
        month=mes,
        description=" ".join(str(bruto["description"]).split()),
        amount=float(bruto["amount"]) if bruto.get("amount") is not None else None,
        date=data,
        kind=ReconciliationKind(bruto.get("kind", "outro")),
        status=ReconciliationStatus(bruto.get("status", "pendente")),
        suggestion=bruto.get("suggestion"),
        question=bruto.get("question"),
        category_hint=bruto.get("category_hint"),
        prefill=bruto.get("prefill"),
        note=bruto.get("note"),
        source="arquivo",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--usuario", required=True)
    ap.add_argument("--arquivo", required=True)
    ap.add_argument("--aplicar", action="store_true", help="grava (sem isto, só mostra)")
    args = ap.parse_args()

    ano, mes, brutos = ler(args.arquivo)
    with Session(engine) as s:
        dono = s.exec(select(User).where(User.email == args.usuario.strip().lower())).first()
        if dono is None:
            print(f"Conta não encontrada: {args.usuario}", file=sys.stderr)
            return 1

        existentes = {
            (i.description.casefold(), i.amount)
            for i in s.exec(
                select(ReconciliationItem).where(
                    ReconciliationItem.user_id == dono.id,
                    ReconciliationItem.year == ano,
                    ReconciliationItem.month == mes,
                )
            ).all()
        }

        novos: list[ReconciliationItem] = []
        print(f"Conferência de {mes:02d}/{ano} — {args.usuario}")
        for bruto in brutos:
            item = montar(dono, ano, mes, bruto)
            valor = f"R$ {item.amount:,.2f}" if item.amount is not None else "sem valor"
            if (item.description.casefold(), item.amount) in existentes:
                print(f"  = já está na lista: {item.description} ({valor})")
                continue
            novos.append(item)
            print(f"  + {item.kind.value:9} {item.status.value:9} {item.description} ({valor})")
            # As correspondências que a tela vai mostrar — pra conferir já aqui.
            item.id = -1
            for c in candidatos(s, dono, item):
                print(f"      parece: {c.kind} #{c.id} {c.description} {c.amount} {c.date} — {', '.join(c.reasons)}")
            item.id = None

        if not args.aplicar:
            print(f"\nModo seco: {len(novos)} item(ns) seriam adicionados. Nada foi gravado.")
            print("Nenhum lançamento, compromisso ou reserva é criado por este script, nem com --aplicar.")
            return 0

        from scripts.backup import salvar

        caminho = salvar(s, dono, "antes-da-conferencia")
        print(f"\nBackup: {caminho}")
        for item in novos:
            s.add(item)
        s.commit()
        print(f"{len(novos)} item(ns) adicionados à conferência. Abra 'Organizar o mês' pra revisar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
