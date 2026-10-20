"""Previsões de investimento sem movimentos financeiros.

Rollback: exportar investment_plans antes de downgrade; ele remove só planos.
"""
from alembic import op
from app.models import InvestmentPlan

revision = "0014_investment_plans"
down_revision = "0013_abatimento_compromisso"
branch_labels = None
depends_on = None


def upgrade():
    InvestmentPlan.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    InvestmentPlan.__table__.drop(op.get_bind(), checkfirst=True)
