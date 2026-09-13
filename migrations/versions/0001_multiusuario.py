"""Introduz usuários e dá dono a todas as linhas existentes.

Revision ID: 0001_multiusuario
Revises:
Create Date: 2026-09-13

O app nasceu de uma conta só: e-mail e hash viviam em variável de ambiente, e as
cinco tabelas de dados não tinham a menor ideia de quem era o dono das linhas.
Esta migração é o que transforma isso em três contas com dados separados.

Ela NÃO pode ser autogerada, e a razão importa: `user_id` é obrigatório, mas o
banco já tem 330 linhas. Criar a coluna direto como NOT NULL falharia, porque
não existe valor pras linhas que já estão lá. A sequência correta tem três
passos e é o miolo deste arquivo:

    1. cria a coluna aceitando nulo
    2. preenche tudo com o dono original (lido do ambiente)
    3. só então torna a coluna obrigatória

O passo 2 é o que salva seu histórico. Sem ele, as 273 transações importadas da
planilha ficariam órfãs — tecnicamente no banco, invisíveis no app.
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "0001_multiusuario"
down_revision = None
branch_labels = None
depends_on = None

# As cinco tabelas que passam a ter dono.
TABELAS = ["categories", "transactions", "budgets", "assets", "asset_snapshots"]


def upgrade() -> None:
    # Este banco pode chegar aqui de dois jeitos, e a migração precisa dos dois:
    #
    #   - Já em uso, com as tabelas criadas pelo antigo `create_all` e cheias de
    #     dado. É o caso do banco de produção, com 330 linhas sem dono.
    #   - Vazio, num ambiente novo (uma cópia pra testar, outra máquina). Aqui
    #     não há o que alterar: as tabelas nascem já com `user_id`.
    #
    # Sem esta distinção, o caminho novo quebraria em `add_column` sobre tabela
    # que não existe — e só se descobriria ao montar o primeiro ambiente novo,
    # que é justamente quando ninguém está esperando problema de migração.
    inspetor = sa.inspect(op.get_bind())
    existentes = set(inspetor.get_table_names())
    banco_novo = "transactions" not in existentes

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("read_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # O dono original vem das variáveis que a API usava até agora. Ler daqui, e
    # não pedir na hora, é o que deixa a migração rodar sozinha no deploy.
    email = (os.getenv("SENTAVOS_EMAIL") or "").strip().lower()
    senha_hash = os.getenv("SENTAVOS_SENHA_HASH") or ""
    nome = os.getenv("SENTAVOS_NOME") or "Sergio"

    users = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("email", sa.String),
        sa.column("name", sa.String),
        sa.column("password_hash", sa.String),
        sa.column("read_only", sa.Boolean),
    )

    conexao = op.get_bind()
    tem_dados = (not banco_novo) and any(
        conexao.execute(sa.text(f"SELECT 1 FROM {t} LIMIT 1")).first() is not None
        for t in TABELAS
    )

    dono_id = None
    if email and senha_hash:
        conexao.execute(
            users.insert().values(
                email=email, name=nome, password_hash=senha_hash, read_only=False
            )
        )
        dono_id = conexao.execute(
            sa.text("SELECT id FROM users WHERE email = :e"), {"e": email}
        ).scalar_one()
    elif tem_dados:
        # Falhar aqui é de propósito. Se há linhas pra adotar e ninguém pra
        # adotá-las, seguir em frente apagaria o histórico no passo 3 — e o
        # erro só apareceria depois, com o dado já perdido.
        raise RuntimeError(
            "Existem dados no banco mas SENTAVOS_EMAIL/SENTAVOS_SENHA_HASH não "
            "estão definidas. Sem elas não há a quem atribuir as linhas "
            "existentes. Defina as duas e rode a migração de novo."
        )

    if banco_novo:
        # Nada a adotar: as tabelas são criadas pelo próprio SQLModel, já com a
        # coluna de dono, e a migração só precisa carimbar o estado.
        from app.models import SQLModel

        SQLModel.metadata.create_all(conexao, checkfirst=True)
        return

    for tabela in TABELAS:
        # Passo 1: nullable, porque as linhas existentes ainda não têm dono.
        op.add_column(tabela, sa.Column("user_id", sa.Integer(), nullable=True))

        # Passo 2: adota o que já existe.
        if dono_id is not None:
            conexao.execute(
                sa.text(f"UPDATE {tabela} SET user_id = :dono WHERE user_id IS NULL"),
                {"dono": dono_id},
            )

        # Passo 3: agora sim obrigatória, com a chave estrangeira.
        #
        # `batch_alter_table` e não `alter_column` direto: o SQLite não implementa
        # ALTER COLUMN nem ADD CONSTRAINT, então lá o Alembic recria a tabela e
        # copia os dados. No Postgres, que é a produção, ele emite o ALTER
        # normal. Isso é o que permite ensaiar a migração numa cópia SQLite
        # antes de rodá-la contra dado de verdade — e ensaiar é justamente o que
        # não se quer abrir mão numa migração que mexe em 330 linhas.
        with op.batch_alter_table(tabela, recreate="auto") as batch:
            batch.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
            batch.create_foreign_key(
                f"fk_{tabela}_user_id", "users", ["user_id"], ["id"]
            )
        op.create_index(f"ix_{tabela}_user_id", tabela, ["user_id"])

    # As restrições de unicidade passam a valer por dono: duas pessoas podem ter
    # meta pra a mesma categoria no mesmo mês sem uma barrar a outra.
    _refazer_unica(
        "budgets", "uq_budget_category_period", ["user_id", "category_id", "year", "month"]
    )
    _refazer_unica(
        "asset_snapshots", "uq_snapshot_asset_period", ["user_id", "asset_id", "year", "month"]
    )


def _refazer_unica(tabela: str, nome: str, colunas: list[str]) -> None:
    # Em batch pelo mesmo motivo do passo 3: no SQLite não existe DROP
    # CONSTRAINT. O drop é tolerante porque o nome pode variar conforme como a
    # tabela nasceu — `create_all` não nomeia igual em todo banco.
    with op.batch_alter_table(tabela, recreate="auto") as batch:
        try:
            batch.drop_constraint(nome, type_="unique")
        except Exception:
            pass
        batch.create_unique_constraint(nome, colunas)


def downgrade() -> None:
    # Volta ao schema de conta única. Perde o vínculo de dono, então só faz
    # sentido quando há um dono só — com três contas, as linhas viram uma
    # mistura sem como separar depois.
    _refazer_unica("asset_snapshots", "uq_snapshot_asset_period", ["asset_id", "year", "month"])
    _refazer_unica("budgets", "uq_budget_category_period", ["category_id", "year", "month"])

    for tabela in TABELAS:
        op.drop_index(f"ix_{tabela}_user_id", table_name=tabela)
        op.drop_constraint(f"fk_{tabela}_user_id", tabela, type_="foreignkey")
        op.drop_column(tabela, "user_id")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
