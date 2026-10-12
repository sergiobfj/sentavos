"""Auditoria mínima: quem mexeu em dinheiro fora do fluxo comum.

Revision ID: 0008_auditoria
Revises: 0007_conciliacao_saldo
Create Date: 2026-10-12

Uma tabela, `audit_events`. Conferência, transferências, movimentos de
investimento, scripts e migrações de dado registram aqui; navegação e edição
comum, não. Nenhuma linha existente é tocada.
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_auditoria"
down_revision = "0007_conciliacao_saldo"
branch_labels = None
depends_on = None


def tem_tabela(nome: str) -> bool:
    return nome in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if tem_tabela("audit_events"):
        return
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_audit_events_user_created", "audit_events", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_user_created", table_name="audit_events")
    op.drop_table("audit_events")
