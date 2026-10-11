"""Planejamento: compromissos, reservas, cenários e a conferência do mês.

Revision ID: 0006_planejamento
Revises: 0005_finalidade
Create Date: 2026-10-10

Seis tabelas novas e cinco colunas nuláveis em tabelas que já existem. Nenhuma
linha existente é preenchida, então **nenhum número de nenhum mês muda** no dia
em que esta migração roda: saldo do mês, gasto, faturas, patrimônio, metas e
relatórios leem exatamente o que liam antes.

| Onde | O quê | Por quê |
| --- | --- | --- |
| `commitments` | compromisso fora do cartão | financiamento, parcelado direto, recorrência |
| `commitment_skips` | ocorrência dispensada | "a academia não cobrou dezembro" |
| `provisions` | reserva | dinheiro que existe e já tem destino |
| `scenarios`, `scenario_items` | simulação | hipóteses que não tocam no resto |
| `reconciliation_items` | conferência do mês | o incerto esperando confirmação |
| `transactions.commitment_id/_no` | a baixa | o lançamento que paga a ocorrência |
| `assets.include_in_planning` | conta do planejamento | "quanto tenho agora" |
| `asset_snapshots.observed_on` | dia do saldo | o que já está dentro do saldo |

## Enum, pela terceira vez

O `op.create_table` do Alembic dispara o `CREATE TYPE` dos enums nativos SEM
conferir se o tipo existe (ver `DefaultImpl.create_table`, `checkfirst=False`).
Duas consequências:

  - Os enums NOVOS (tipo de item de cenário, tipo e status da conferência) são
    VARCHAR, `native_enum=False`, no modelo e aqui. Sem tipo no Postgres, sem
    DDL a mais, e o banco grava o NOME do membro como os outros enums.
  - `commitments.finalidade` reaproveita o tipo `finalidade`, que a 0005 já
    criou. Por isso ele não vai no `create_table`: entra depois, por
    `add_column`, que não tenta criar o tipo — o mesmo caminho da 0005.

## Banco vazio

A 0001 monta tudo com `create_all`, que usa o modelo de HOJE — já com estas
tabelas e colunas. Então toda criação aqui confere antes se a tabela/coluna já
existe; sem isso, ambiente novo não sobe (foi o que quebrou a 0002).
"""

import sqlalchemy as sa
from alembic import op

from app.models import Finalidade, ReconciliationKind, ReconciliationStatus, ScenarioItemKind

revision = "0006_planejamento"
down_revision = "0005_finalidade"
branch_labels = None
depends_on = None


finalidade = sa.Enum(Finalidade, name="finalidade")


def enum_texto(classe):
    """O mesmo tipo do modelo (`app.models._enum_texto`): VARCHAR com o nome."""
    return sa.Enum(classe, native_enum=False, length=16)


def tem_tabela(nome: str) -> bool:
    return nome in sa.inspect(op.get_bind()).get_table_names()


def tem_coluna(tabela: str, coluna: str) -> bool:
    inspetor = sa.inspect(op.get_bind())
    if tabela not in inspetor.get_table_names():
        return False
    return coluna in {c["name"] for c in inspetor.get_columns(tabela)}


def _dono(tabela: str) -> list:
    return [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=f"fk_{tabela}_user_id"),
    ]


def _criado_em() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    conexao = op.get_bind()

    # ---------- Compromisso ----------
    if not tem_tabela("commitments"):
        op.create_table(
            "commitments",
            *_dono("commitments"),
            sa.Column("description", sa.String(), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=False),
            # O valor de CADA ocorrência. O cronograma não é gravado: sai de
            # primeira data + quantidade + intervalo toda vez que é pedido.
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("first_due", sa.Date(), nullable=False),
            sa.Column("installments", sa.Integer(), nullable=True),
            sa.Column("interval_months", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.true()),
            # Só informação — nenhum destes entra em conta.
            sa.Column("institution", sa.String(), nullable=True),
            sa.Column("total_amount", sa.Float(), nullable=True),
            sa.Column("down_payment", sa.Float(), nullable=True),
            sa.Column("payment_hint", sa.String(), nullable=True),
            sa.Column("note", sa.String(), nullable=True),
            sa.Column("cancelled_on", sa.Date(), nullable=True),
            _criado_em(),
            sa.ForeignKeyConstraint(
                ["category_id"], ["categories.id"], name="fk_commitments_category_id"
            ),
        )
        op.create_index("ix_commitments_user_id", "commitments", ["user_id"])

    if not tem_coluna("commitments", "finalidade"):
        # O tipo já existe desde a 0005; checkfirst cobre o banco que pulou ela.
        finalidade.create(conexao, checkfirst=True)
        op.add_column("commitments", sa.Column("finalidade", finalidade, nullable=True))

    if not tem_tabela("commitment_skips"):
        op.create_table(
            "commitment_skips",
            *_dono("commitment_skips"),
            sa.Column("commitment_id", sa.Integer(), nullable=False),
            sa.Column("number", sa.Integer(), nullable=False),
            sa.Column("note", sa.String(), nullable=True),
            sa.ForeignKeyConstraint(
                ["commitment_id"], ["commitments.id"], name="fk_commitment_skips_commitment_id"
            ),
            sa.UniqueConstraint("commitment_id", "number", name="uq_commitment_skip"),
        )
        op.create_index("ix_commitment_skips_user_id", "commitment_skips", ["user_id"])
        op.create_index("ix_commitment_skips_commitment_id", "commitment_skips", ["commitment_id"])

    # ---------- Reserva ----------
    if not tem_tabela("provisions"):
        op.create_table(
            "provisions",
            *_dono("provisions"),
            sa.Column("description", sa.String(), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("created_on", sa.Date(), nullable=False),
            sa.Column("commitment_id", sa.Integer(), nullable=True),
            sa.Column("commitment_no", sa.Integer(), nullable=True),
            sa.Column("target_date", sa.Date(), nullable=True),
            sa.Column("note", sa.String(), nullable=True),
            sa.Column("released_on", sa.Date(), nullable=True),
            _criado_em(),
            sa.ForeignKeyConstraint(
                ["commitment_id"], ["commitments.id"], name="fk_provisions_commitment_id"
            ),
        )
        op.create_index("ix_provisions_user_id", "provisions", ["user_id"])
        op.create_index("ix_provisions_commitment_id", "provisions", ["commitment_id"])

    # ---------- Cenário ----------
    if not tem_tabela("scenarios"):
        op.create_table(
            "scenarios",
            *_dono("scenarios"),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("note", sa.String(), nullable=True),
            _criado_em(),
        )
        op.create_index("ix_scenarios_user_id", "scenarios", ["user_id"])

    if not tem_tabela("scenario_items"):
        op.create_table(
            "scenario_items",
            *_dono("scenario_items"),
            sa.Column("scenario_id", sa.Integer(), nullable=False),
            sa.Column("kind", enum_texto(ScenarioItemKind), nullable=False),
            sa.Column("description", sa.String(), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("repeat_months", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("ref", sa.String(), nullable=True),
            sa.ForeignKeyConstraint(
                ["scenario_id"], ["scenarios.id"], name="fk_scenario_items_scenario_id"
            ),
        )
        op.create_index("ix_scenario_items_user_id", "scenario_items", ["user_id"])
        op.create_index("ix_scenario_items_scenario_id", "scenario_items", ["scenario_id"])

    # ---------- Conferência ----------
    if not tem_tabela("reconciliation_items"):
        op.create_table(
            "reconciliation_items",
            *_dono("reconciliation_items"),
            sa.Column("year", sa.Integer(), nullable=False),
            sa.Column("month", sa.Integer(), nullable=False),
            sa.Column("description", sa.String(), nullable=False),
            sa.Column("amount", sa.Float(), nullable=True),
            sa.Column("date", sa.Date(), nullable=True),
            sa.Column("kind", enum_texto(ReconciliationKind), nullable=False),
            sa.Column("status", enum_texto(ReconciliationStatus), nullable=False),
            sa.Column("suggestion", sa.String(), nullable=True),
            sa.Column("question", sa.String(), nullable=True),
            sa.Column("category_hint", sa.String(), nullable=True),
            sa.Column("prefill", sa.JSON(), nullable=True),
            sa.Column("note", sa.String(), nullable=True),
            # Sem chave estrangeira de propósito: a anotação não pode impedir
            # ninguém de apagar o lançamento que ela cita.
            sa.Column("transaction_id", sa.Integer(), nullable=True),
            sa.Column("commitment_id", sa.Integer(), nullable=True),
            sa.Column("provision_id", sa.Integer(), nullable=True),
            sa.Column("source", sa.String(), nullable=False, server_default="manual"),
            _criado_em(),
        )
        op.create_index("ix_reconciliation_items_user_id", "reconciliation_items", ["user_id"])

    # ---------- A baixa, no lançamento ----------
    # Em batch pelo mesmo motivo da 0004: no SQLite recria a tabela copiando os
    # dados (ADD CONSTRAINT não existe lá), no Postgres emite o ALTER normal. É
    # o que permite ensaiar numa cópia SQLite dos dados reais.
    faltando = [c for c in ("commitment_id", "commitment_no") if not tem_coluna("transactions", c)]
    if faltando:
        with op.batch_alter_table("transactions", recreate="auto") as batch:
            if "commitment_id" in faltando:
                batch.add_column(sa.Column("commitment_id", sa.Integer(), nullable=True))
                batch.create_foreign_key(
                    "fk_transactions_commitment_id", "commitments", ["commitment_id"], ["id"]
                )
            if "commitment_no" in faltando:
                batch.add_column(sa.Column("commitment_no", sa.Integer(), nullable=True))
        op.create_index("ix_transactions_commitment_id", "transactions", ["commitment_id"])
        # A trava contra baixa duplicada. Nulos não colidem entre si, então os
        # lançamentos comuns (todos, hoje) passam sem esbarrar nela.
        op.create_index(
            "uq_transactions_commitment_occurrence",
            "transactions",
            ["commitment_id", "commitment_no"],
            unique=True,
        )

    # ---------- Saldo de partida ----------
    if not tem_coluna("assets", "include_in_planning"):
        # Nulo = a escolha padrão (só a classe Conta). Nada é marcado aqui.
        op.add_column("assets", sa.Column("include_in_planning", sa.Boolean(), nullable=True))
    if not tem_coluna("asset_snapshots", "observed_on"):
        op.add_column("asset_snapshots", sa.Column("observed_on", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("asset_snapshots", recreate="auto") as batch:
        batch.drop_column("observed_on")
    with op.batch_alter_table("assets", recreate="auto") as batch:
        batch.drop_column("include_in_planning")

    op.drop_index("uq_transactions_commitment_occurrence", table_name="transactions")
    op.drop_index("ix_transactions_commitment_id", table_name="transactions")
    with op.batch_alter_table("transactions", recreate="auto") as batch:
        try:
            batch.drop_constraint("fk_transactions_commitment_id", type_="foreignkey")
        except Exception:
            # O nome pode variar conforme como a tabela nasceu (create_all).
            pass
        batch.drop_column("commitment_no")
        batch.drop_column("commitment_id")

    op.drop_table("reconciliation_items")
    op.drop_table("scenario_items")
    op.drop_table("scenarios")
    op.drop_table("provisions")
    op.drop_table("commitment_skips")
    # O tipo `finalidade` fica: é da 0005, e cards/purchases/transactions o usam.
    op.drop_table("commitments")
