"""Troca as cores das categorias pelas da paleta fechada, sem repetir.

    uv run python -m scripts.redistribuir_cores --usuario sjunior1557@gmail.com
    uv run python -m scripts.redistribuir_cores --usuario sjunior1557@gmail.com --aplicar

Sem `--aplicar` só mostra o que mudaria. Com ele, tira backup antes (o mesmo de
`scripts/backup.py`) e grava. Mexe SÓ na coluna `color`: id, nome, ícone, tipo,
lançamentos, compras e metas continuam exatamente como estão.

## Por que existe

As cores vieram de um seletor livre, e o resultado foi o esperado: 13 das 16
categorias de despesa em cinco tons de vermelho e terracota. Numa lista isso
incomoda; numa rosca, vira uma mancha só — não dá pra saber onde termina
Alimentação e começa Casa.

## Como escolhe

Por tipo, a categoria que mais movimentou dinheiro recebe a primeira cor da
paleta, a segunda recebe a segunda, e assim por diante. As mais usadas são as
que aparecem juntas na rosca, e a ordem da paleta (frontend/src/lib/paleta.ts)
foi validada justamente pra vizinhas se distinguirem. Arquivadas vão por último.

Com mais de 12 categorias num tipo, a 13ª repete a 1ª. A rosca mostra no
máximo seis fatias mais "Outras", então duas cores iguais só se encontram se
duas categorias de pouco uso subirem juntas pro topo no mesmo mês.

Não roda sozinho em lugar nenhum: nem na migração, nem no deploy.
"""

import argparse
import os
import sys

from sqlmodel import Session, func, select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine  # noqa: E402
from app.models import Category, CategoryType, Transaction, User  # noqa: E402

# Espelho de PALETA_CATEGORIAS em frontend/src/lib/paleta.ts, na mesma ordem.
PALETA = [
    "#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#6aa84f",
    "#9085e9", "#e66767", "#1f94ad", "#8f9a2e", "#b066c9", "#b8703f",
]


def plano(s: Session, dono: User) -> list[tuple[Category, str]]:
    """[(categoria, cor nova)] só das que mudam."""
    movimento = {
        cid: abs(float(total or 0.0))
        for cid, total in s.exec(
            select(Transaction.category_id, func.sum(Transaction.amount_paid))
            .where(Transaction.user_id == dono.id)
            .group_by(Transaction.category_id)
        ).all()
    }
    mudancas = []
    for tipo in CategoryType:
        categorias = s.exec(
            select(Category).where(Category.user_id == dono.id, Category.type == tipo)
        ).all()
        categorias.sort(key=lambda c: (c.archived, -movimento.get(c.id, 0.0), c.name))
        for i, c in enumerate(categorias):
            nova = PALETA[i % len(PALETA)]
            if c.color.lower() != nova:
                mudancas.append((c, nova))
    return mudancas


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--usuario", required=True)
    ap.add_argument("--aplicar", action="store_true", help="grava (sem isso, só mostra)")
    args = ap.parse_args()

    with Session(engine) as s:
        dono = s.exec(select(User).where(User.email == args.usuario.strip().lower())).first()
        if dono is None:
            print(f"Conta não encontrada: {args.usuario}", file=sys.stderr)
            return 1

        mudancas = plano(s, dono)
        if not mudancas:
            print("Nada a mudar: as cores já seguem a paleta.")
            return 0

        for c, nova in mudancas:
            print(f"  {c.type.value:10} {c.icon} {c.name:28} {c.color} -> {nova}"
                  f"{'  (arquivada)' if c.archived else ''}")

        if not args.aplicar:
            print(f"\n{len(mudancas)} categoria(s) mudariam. Nada foi gravado — rode com --aplicar.")
            return 0

        from scripts.backup import salvar

        caminho = salvar(s, dono, "antes-de-redistribuir-cores")
        print(f"\nBackup: {caminho}")
        for c, nova in mudancas:
            c.color = nova
            s.add(c)
        s.commit()
        print(f"{len(mudancas)} cor(es) gravada(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
