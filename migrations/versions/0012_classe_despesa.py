"""Classificação opcional de despesa, sem inferir ou reescrever histórico.

Revision ID: 0012_classe_despesa
Revises: 0011_natureza
"""
import sqlalchemy as sa
from alembic import op

revision = "0012_classe_despesa"
down_revision = "0011_natureza"
branch_labels = None
depends_on = None

TABLES = ("transactions", "purchases", "commitments")


def upgrade():
    for table in TABLES:
        if "expense_class" not in {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}:
            op.add_column(table, sa.Column("expense_class", sa.String(8), nullable=True))


def downgrade():
    # Somente esta classificação é removida. Valores e vínculos ficam intactos.
    for table in reversed(TABLES):
        if "expense_class" in {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}:
            with op.batch_alter_table(table) as batch:
                batch.drop_column("expense_class")
