"""Precisão do total manual e dados atuais sem vencimento presumido."""
import sqlalchemy as sa
from alembic import op

revision = "0016_situacao_observada"
down_revision = "0015_reinicio_operacional"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    invoice_columns = {c["name"]: c for c in inspector.get_columns("invoices")}
    # Corrige também bases que já passaram pela versão Float de 0015.
    with op.batch_alter_table("invoices") as batch:
        kind = invoice_columns["manual_total"]["type"]
        if isinstance(kind, sa.Float) or not isinstance(kind, sa.Numeric) or kind.scale != 2:
            batch.alter_column("manual_total", type_=sa.Numeric(14, 2),
                               postgresql_using="round(manual_total::numeric, 2)")
        if "due_unknown" not in invoice_columns:
            batch.add_column(sa.Column("due_unknown", sa.Boolean(), nullable=False, server_default=sa.false()))
        if "uq_invoices_user_id" not in {c["name"] for c in inspector.get_unique_constraints("invoices")}:
            batch.create_unique_constraint("uq_invoices_user_id", ["user_id", "id"])
    if "due_unknown" not in {c["name"] for c in inspector.get_columns("transactions")}:
        op.add_column("transactions", sa.Column("due_unknown", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "purpose" not in {c["name"] for c in inspector.get_columns("asset_snapshots")}:
        op.add_column("asset_snapshots", sa.Column("purpose", sa.String(), nullable=True))
    provision_columns = {c["name"] for c in inspector.get_columns("provisions")}
    with op.batch_alter_table("provisions") as batch:
        if "transaction_id" not in provision_columns:
            batch.add_column(sa.Column("transaction_id", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_provision_transaction", "transactions", ["transaction_id"], ["id"])
        if "invoice_id" not in provision_columns:
            batch.add_column(sa.Column("invoice_id", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_provision_invoice", "invoices", ["invoice_id"], ["id"])
    if "invoice_statement_items" in inspector.get_table_names():
        return
    op.create_table("invoice_statement_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("finalidade", sa.String(), nullable=False),
        sa.UniqueConstraint("user_id", "source_key", name="uq_statement_source"),
        sa.ForeignKeyConstraint(["user_id", "invoice_id"], ["invoices.user_id", "invoices.id"]),
    )
    op.create_index("ix_invoice_statement_items_user_id", "invoice_statement_items", ["user_id"])


def downgrade():
    op.drop_table("invoice_statement_items")
    fks = sa.inspect(op.get_bind()).get_foreign_keys("provisions")
    with op.batch_alter_table("provisions") as batch:
        for fk in fks:
            if fk["constrained_columns"] in (["invoice_id"], ["transaction_id"]) and fk["name"]:
                batch.drop_constraint(fk["name"], type_="foreignkey")
        batch.drop_column("invoice_id")
        batch.drop_column("transaction_id")
    op.drop_column("asset_snapshots", "purpose")
    op.drop_column("transactions", "due_unknown")
    with op.batch_alter_table("invoices") as batch:
        batch.drop_constraint("uq_invoices_user_id", type_="unique")
        batch.drop_column("due_unknown")
    # 0015 corrigida já usa Numeric: downgrade não reintroduz Float.
