"""Categorias arquiváveis, primeiro passo das caixinhas.

Revision ID: 0002_caixinhas
Revises: 0001_multiusuario
Create Date: 2026-09-13

Arquivar existe porque as 28 categorias vieram de uma planilha e têm nomes que
só fazem sentido pra quem a escreveu ("CAIXINHA EM", "SECCO", "BIA"). Elas
precisam sair do formulário de lançamento sem sair do banco: 273 lançamentos
apontam pra elas, e apagá-las levaria um ano de histórico junto.

`archived` entra com default false e NOT NULL direto — diferente do `user_id` da
0001, aqui existe um valor óbvio pras linhas antigas (nenhuma nasce arquivada),
então não precisa do vaivém de três passos.

A parte de caixinha (sobra que acumula, não distribuído) não aparece aqui de
propósito: ela é cálculo em cima de `budgets` e `transactions`, não coluna nova.
O que uma caixinha tem a mais que um teto mensal é o saldo não zerar na virada —
e isso se deriva do histórico que já está no banco, sem dado novo pra guardar.
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_caixinhas"
down_revision = "0001_multiusuario"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "categories",
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Índice porque toda listagem de categoria filtra por arquivada a partir de
    # agora, e o formulário de lançamento faz isso a cada abertura.
    op.create_index("ix_categories_archived", "categories", ["user_id", "archived"])


def downgrade() -> None:
    op.drop_index("ix_categories_archived", table_name="categories")
    op.drop_column("categories", "archived")
