"""Data do abatimento contratual, distinta de pagamento e dispensa.

Revision ID: 0013_abatimento_compromisso
Revises: 0012_classe_despesa
"""
import sqlalchemy as sa
from alembic import op

revision = "0013_abatimento_compromisso"
down_revision = "0012_classe_despesa"
branch_labels = None
depends_on = None


def upgrade():
    if "abated_on" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("commitment_skips")}:
        op.add_column("commitment_skips", sa.Column("abated_on", sa.Date(), nullable=True))


def downgrade():
    if "abated_on" in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("commitment_skips")}:
        with op.batch_alter_table("commitment_skips") as batch:
            batch.drop_column("abated_on")
