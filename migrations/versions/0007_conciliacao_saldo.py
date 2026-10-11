"""Saldo lançado por conferência: o rendimento do mês fica "não apurado".

Revision ID: 0007_conciliacao_saldo
Revises: 0006_planejamento
Create Date: 2026-10-11

Uma coluna nulável, `asset_snapshots.reconciliation_note`. Quando o saldo de
um ativo no mês foi lançado por conferência — o dono sabe quanto tem hoje, mas
no mês houve um movimento de valor desconhecido (o resgate da caixinha usado
numa compra, sem o extrato) —, a nota diz isso, e a tela de investimentos
mostra "não apurado" no lugar de um rendimento que seria inventado.

Nenhuma linha é preenchida: nenhum número de nenhum mês muda. Confere antes se
a coluna existe porque a 0001 monta o banco novo com o modelo de hoje.
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_conciliacao_saldo"
down_revision = "0006_planejamento"
branch_labels = None
depends_on = None


def tem_coluna(tabela: str, coluna: str) -> bool:
    inspetor = sa.inspect(op.get_bind())
    if tabela not in inspetor.get_table_names():
        return False
    return coluna in {c["name"] for c in inspetor.get_columns(tabela)}


def upgrade() -> None:
    if not tem_coluna("asset_snapshots", "reconciliation_note"):
        op.add_column("asset_snapshots", sa.Column("reconciliation_note", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("asset_snapshots", recreate="auto") as batch:
        batch.drop_column("reconciliation_note")
