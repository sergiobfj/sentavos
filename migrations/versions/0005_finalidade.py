"""Finalidade do gasto: pessoal, família ou empresa.

Revision ID: 0005_finalidade
Revises: 0004_cartao
Create Date: 2026-09-23

Uma coluna nulável em três tabelas — `cards`, `purchases` e `transactions` — e
nada mais. Nenhuma linha é preenchida.

## Por que nada é preenchido

Os três cartões do dono têm nomes que "dizem" a finalidade (Família, SECCO), e é
exatamente por isso que a migração não olha pra eles: palpite por nome é o tipo
de regra que acerta três vezes e erra calada na quarta. O cartão é classificado
pela tela, por quem sabe, e aí as compras dele que estão sem finalidade herdam.

Os lançamentos antigos ficam nulos para sempre, a menos que o dono os edite. O
filtro "Todos" continua somando tudo — então **nenhum número de nenhum mês muda**
no dia em que esta migração roda. Pessoal/Família/Empresa só enxergam o que tem
finalidade, e a tela diz quanto ficou de fora.

## O enum

Mesma armadilha da 0004: o ORM grava o NOME do membro (`PESSOAL`), não o valor
(`pessoal`). O tipo vem da classe pra os dois nunca divergirem.
"""

import sqlalchemy as sa
from alembic import op

from app.models import Finalidade

revision = "0005_finalidade"
down_revision = "0004_cartao"
branch_labels = None
depends_on = None


finalidade = sa.Enum(Finalidade, name="finalidade")

TABELAS = ("cards", "purchases", "transactions")


def tem_coluna(tabela: str, coluna: str) -> bool:
    """Ver a 0002: num banco vazio a 0001 já cria tudo com o modelo de hoje."""
    inspetor = sa.inspect(op.get_bind())
    if tabela not in inspetor.get_table_names():
        return False
    return coluna in {c["name"] for c in inspetor.get_columns(tabela)}


def upgrade() -> None:
    finalidade.create(op.get_bind(), checkfirst=True)

    for tabela in TABELAS:
        if tem_coluna(tabela, "finalidade"):
            continue
        # Batch pelo mesmo motivo da 0004: no SQLite recria a tabela copiando os
        # dados, o que permite ensaiar numa cópia local dos dados reais.
        with op.batch_alter_table(tabela, recreate="auto") as batch:
            batch.add_column(sa.Column("finalidade", finalidade, nullable=True))


def downgrade() -> None:
    for tabela in reversed(TABELAS):
        if tem_coluna(tabela, "finalidade"):
            with op.batch_alter_table(tabela, recreate="auto") as batch:
                batch.drop_column("finalidade")
    finalidade.drop(op.get_bind(), checkfirst=True)
