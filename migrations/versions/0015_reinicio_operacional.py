"""Faturas com valor desconhecido/manual e corte operacional explícito.

Não limpa dados. O reset é uma operação administrativa separada, só local.
"""
import sqlalchemy as sa
from alembic import op

revision = "0015_reinicio_operacional"
down_revision = "0014_investment_plans"
branch_labels = None
depends_on = None

FIELDS = {
    "users": [("operations_start", sa.Date())],
    "purchases": [("installments_stopped_from", sa.Date())],
    "invoices": [("manual_total", sa.Numeric(14, 2)), ("reset_on", sa.Date())],
}


def upgrade():
    for table, columns in FIELDS.items():
        existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
        for name, kind in columns:
            if name not in existing:
                op.add_column(table, sa.Column(name, kind, nullable=True))


def downgrade():
    for table, columns in reversed(list(FIELDS.items())):
        for name, _ in reversed(columns):
            if name in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}:
                op.drop_column(table, name)
