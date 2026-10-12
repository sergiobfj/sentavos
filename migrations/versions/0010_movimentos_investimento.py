"""Movimento de investimento: aporte, resgate e ajuste com ativo e conta.

Revision ID: 0010_movimentos_investimento
Revises: 0009_contas
Create Date: 2026-10-12

`investment_movements` dá a semântica que o "investimento negativo" não dava:
qual ativo, qual conta, aporte ou resgate. O lado caixa continua sendo o
lançamento de categoria investimento (`transaction_id`) — o "investido" e o
saldo do mês de todo mês passado leem o que liam.

Chaves compostas (user_id, …) pra ativo, conta e lançamento: o banco recusa
movimento apontando pra dado de outro dono. Por isso `assets` e `transactions`
ganham um único em (user_id, id). Nenhuma linha é preenchida.
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_movimentos_investimento"
down_revision = "0009_contas"
branch_labels = None
depends_on = None


def inspetor():
    return sa.inspect(op.get_bind())


def tem_tabela(nome: str) -> bool:
    return nome in inspetor().get_table_names()


def tem_unico(tabela: str, nome: str) -> bool:
    return nome in {u["name"] for u in inspetor().get_unique_constraints(tabela)}


def upgrade() -> None:
    for tabela, nome in (("assets", "uq_assets_user_id"), ("transactions", "uq_transactions_user_id")):
        if not tem_unico(tabela, nome):
            with op.batch_alter_table(tabela, recreate="auto") as b:
                b.create_unique_constraint(nome, ["user_id", "id"])

    if not tem_tabela("investment_movements"):
        op.create_table(
            "investment_movements",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("asset_id", sa.Integer(), nullable=False),
            sa.Column("type", sa.String(length=16), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("account_id", sa.Integer(), nullable=True),
            sa.Column("note", sa.String(), nullable=True),
            sa.Column("transaction_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id", "asset_id"], ["assets.user_id", "assets.id"],
                                    name="fk_investment_movements_asset"),
            sa.ForeignKeyConstraint(["user_id", "account_id"],
                                    ["financial_accounts.user_id", "financial_accounts.id"],
                                    name="fk_investment_movements_account"),
            sa.ForeignKeyConstraint(["user_id", "transaction_id"], ["transactions.user_id", "transactions.id"],
                                    name="fk_investment_movements_transaction", ondelete="CASCADE"),
            sa.CheckConstraint("amount > 0", name="ck_investment_movements_valor_positivo"),
        )
        op.create_index("ix_investment_movements_user_id", "investment_movements", ["user_id"])
        op.create_index("uq_investment_movements_transaction", "investment_movements", ["transaction_id"], unique=True)
        op.create_index("ix_investment_movements_asset_date", "investment_movements", ["asset_id", "date"])


def downgrade() -> None:
    op.drop_table("investment_movements")
    for tabela, nome in (("transactions", "uq_transactions_user_id"), ("assets", "uq_assets_user_id")):
        with op.batch_alter_table(tabela, recreate="auto") as b:
            b.drop_constraint(nome, type_="unique")
