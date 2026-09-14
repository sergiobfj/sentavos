"""Taxa por aplicação e a taxa CDI do usuário.

Revision ID: 0003_rendimento
Revises: 0002_caixinhas
Create Date: 2026-09-13

A aba de Investimento só sabia comparar dois saldos digitados à mão, então o
"rendimento" que ela mostrava era a diferença entre dois números do próprio
dono — zero informação nova. Com a taxa declarada, dá pra dizer quanto a
aplicação *deveria* render e comparar com o que rendeu.

`cdi_percent` fica no ativo porque cada aplicação tem a sua ("Nubank Turbo,
115% do CDI"). O CDI em si fica no usuário, e não no ativo, porque é um número
só pro país inteiro: repetido por aplicação, atualizar a Selic viraria editar
cinco lugares e esquecer o sexto.

Nulo significa "não rende" — é o caso de conta corrente, imóvel e carro, que
são a maioria dos ativos. Um default de zero diria a mesma coisa, mas tornaria
impossível distinguir "não sei a taxa" de "a taxa é zero".
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_rendimento"
down_revision = "0002_caixinhas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("cdi_percent", sa.Float(), nullable=True))
    op.add_column("users", sa.Column("cdi_annual", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "cdi_annual")
    op.drop_column("assets", "cdi_percent")
