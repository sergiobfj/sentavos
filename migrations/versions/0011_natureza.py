"""Natureza do gasto: consumo, aquisição de bem, financeiro.

Revision ID: 0011_natureza
Revises: 0010_movimentos_investimento
Create Date: 2026-10-12

Três colunas nulas, nenhuma linha preenchida: nulo = herda (lançamento →
categoria → consumo), então todo gasto antigo continua consumo e o gasto total
de todo mês fica onde estava. A entrada da moto e o financiamento ganham
natureza pelo script `foundation_v3`, com auditoria — não pela migração.
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_natureza"
down_revision = "0010_movimentos_investimento"
branch_labels = None
depends_on = None

COLUNAS = (("transactions", "nature"), ("categories", "default_nature"), ("commitments", "nature"))


def tem_coluna(tabela: str, coluna: str) -> bool:
    return coluna in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(tabela)}


def upgrade() -> None:
    for tabela, coluna in COLUNAS:
        if not tem_coluna(tabela, coluna):
            op.add_column(tabela, sa.Column(coluna, sa.String(length=20), nullable=True))


def downgrade() -> None:
    for tabela, coluna in COLUNAS:
        if tem_coluna(tabela, coluna):
            with op.batch_alter_table(tabela, recreate="auto") as b:
                b.drop_column(coluna)
