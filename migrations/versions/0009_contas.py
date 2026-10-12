"""Contas financeiras, saldo observado e transferência.

Revision ID: 0009_contas
Revises: 0008_auditoria
Create Date: 2026-10-12

| Onde | O quê |
| --- | --- |
| `financial_accounts` | onde existe dinheiro líquido (tipos em VARCHAR) |
| `account_balance_snapshots` | saldo observado, com hora e fuso |
| `transfers` | dinheiro mudando de conta — uma linha por operação |
| `transactions.account_id/occurred_at` | conta e instante do lançamento |
| `invoice_payments.account_id/occurred_at` | de onde saiu o pagamento da fatura |
| `assets.archived_on` | a partir de que mês o ativo deixa de contar |

Tudo nulável e nada preenchido: nenhum número de nenhum mês muda. As chaves
estrangeiras de conta são compostas — (user_id, account_id) → conta do mesmo
dono —, então o banco recusa apontar pra conta alheia. Toda criação confere
antes se já existe (a 0001 monta banco novo com o modelo de hoje).
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_contas"
down_revision = "0008_auditoria"
branch_labels = None
depends_on = None


def inspetor():
    return sa.inspect(op.get_bind())


def tem_tabela(nome: str) -> bool:
    return nome in inspetor().get_table_names()


def tem_coluna(tabela: str, coluna: str) -> bool:
    return coluna in {c["name"] for c in inspetor().get_columns(tabela)}


def tem_indice(tabela: str, nome: str) -> bool:
    return nome in {i["name"] for i in inspetor().get_indexes(tabela)}


def conta_fk(nome: str, coluna: str, ondelete: str | None = None) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["user_id", coluna], ["financial_accounts.user_id", "financial_accounts.id"],
        name=nome, ondelete=ondelete,
    )


def texto(tamanho: int = 16) -> sa.String:
    return sa.String(length=tamanho)


def upgrade() -> None:
    if not tem_tabela("financial_accounts"):
        op.create_table(
            "financial_accounts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("institution", sa.String(), nullable=True),
            sa.Column("type", texto(), nullable=False),
            sa.Column("currency", sa.String(), nullable=False, server_default="BRL"),
            sa.Column("include_in_planning", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("restricted", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("user_id", "id", name="uq_financial_accounts_user_id"),
        )
        op.create_index("ix_financial_accounts_user_id", "financial_accounts", ["user_id"])

    if not tem_tabela("account_balance_snapshots"):
        op.create_table(
            "account_balance_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("account_id", sa.Integer(), nullable=False),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("balance", sa.Float(), nullable=False),
            sa.Column("source", texto(), nullable=False),
            sa.Column("note", sa.String(), nullable=True),
            sa.Column("accepted_difference", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            conta_fk("fk_account_balance_snapshots_account", "account_id", ondelete="CASCADE"),
        )
        op.create_index("ix_account_balance_snapshots_user_id", "account_balance_snapshots", ["user_id"])
        op.create_index("ix_account_balance_snapshots_account", "account_balance_snapshots",
                        ["account_id", "observed_at"])

    if not tem_tabela("transfers"):
        op.create_table(
            "transfers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("from_account_id", sa.Integer(), nullable=False),
            sa.Column("to_account_id", sa.Integer(), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("description", sa.String(), nullable=True),
            sa.Column("note", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            conta_fk("fk_transfers_from_account", "from_account_id"),
            conta_fk("fk_transfers_to_account", "to_account_id"),
            sa.CheckConstraint("from_account_id <> to_account_id", name="ck_transfers_contas_diferentes"),
            sa.CheckConstraint("amount > 0", name="ck_transfers_valor_positivo"),
        )
        op.create_index("ix_transfers_user_id", "transfers", ["user_id"])
        op.create_index("ix_transfers_user_date", "transfers", ["user_id", "date"])

    for tabela, fk in (("transactions", "fk_transactions_account"),
                       ("invoice_payments", "fk_invoice_payments_account")):
        if not tem_coluna(tabela, "account_id"):
            with op.batch_alter_table(tabela, recreate="auto") as b:
                b.add_column(sa.Column("account_id", sa.Integer(), nullable=True))
                b.add_column(sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True))
                b.create_foreign_key(fk, "financial_accounts", ["user_id", "account_id"], ["user_id", "id"])

    if not tem_indice("transactions", "ix_transactions_user_date"):
        op.create_index("ix_transactions_user_date", "transactions", ["user_id", "date"])
    if not tem_indice("transactions", "ix_transactions_account_date"):
        op.create_index("ix_transactions_account_date", "transactions", ["account_id", "date"])

    if not tem_coluna("assets", "archived_on"):
        op.add_column("assets", sa.Column("archived_on", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("assets", recreate="auto") as b:
        b.drop_column("archived_on")
    op.drop_index("ix_transactions_account_date", table_name="transactions")
    op.drop_index("ix_transactions_user_date", table_name="transactions")
    for tabela, fk in (("transactions", "fk_transactions_account"),
                       ("invoice_payments", "fk_invoice_payments_account")):
        with op.batch_alter_table(tabela, recreate="auto") as b:
            b.drop_constraint(fk, type_="foreignkey")
            b.drop_column("occurred_at")
            b.drop_column("account_id")
    op.drop_table("transfers")
    op.drop_table("account_balance_snapshots")
    op.drop_table("financial_accounts")
