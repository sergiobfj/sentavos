"""Cartão de crédito: forma de pagamento, compras, faturas e pagamentos.

Revision ID: 0004_cartao
Revises: 0003_rendimento
Create Date: 2026-09-23

Separa "tive uma despesa" de "o dinheiro saiu da conta" — dois eventos que o app
tratava como um só. Quatro tabelas novas e quatro colunas em `transactions`.

## Por que nada é preenchido aqui

`payment_method` nasce NULO em todos os 269 lançamentos existentes, e continua
assim até o dono revisar pela tela. Marcar tudo como "à vista" seria inventar
informação financeira: parte desses lançamentos foi no cartão, e o próprio banco
mostra isso — existe uma categoria "Fatura do cartão" com 11 lançamentos, um por
mês, que é o jeito antigo de registrar a fatura inteira numa linha só.

A Carteira trata o nulo como saída de caixa, que é exatamente como esses
lançamentos já eram contados. O efeito prático é que **nenhum número de nenhum
mês anterior muda** no dia em que esta migração roda — o histórico continua
dizendo o que dizia, e o app passa a avisar quantos lançamentos ainda não têm
resposta.

Por isso também nada vira NOT NULL: uma coluna obrigatória exigiria um valor
para as linhas antigas, e o valor honesto é "não sei".

## Enum no Postgres, e a armadilha dele

`SQLModel` mapeia enum de string pra tipo nativo (`categorytype` e `assetclass`
já existem assim). O Alembic NÃO cria o tipo sozinho num `add_column`, então ele
é criado explicitamente antes. No SQLite vira VARCHAR com CHECK, que é o que
`create_all` produz nos testes.

O tipo vem de `PaymentMethod`, a classe, e **não** de uma lista de strings
escrita à mão aqui. O motivo custou um susto: o SQLAlchemy grava o NOME do
membro (`CASH`), não o valor (`cash`). Escrever `sa.Enum("cash", "credit")`
criaria no Postgres um tipo que recusa exatamente o que o ORM manda — e a suíte
de testes não pegaria, porque ela monta o banco com `create_all` e nunca executa
esta migração. Seria um erro que só aparece em produção, no primeiro lançamento
de cartão. Derivar do modelo torna a divergência impossível.
"""

import sqlalchemy as sa
from alembic import op

from app.models import PaymentMethod

revision = "0004_cartao"
down_revision = "0003_rendimento"
branch_labels = None
depends_on = None


metodo_de_pagamento = sa.Enum(PaymentMethod, name="paymentmethod")


def tem_tabela(nome: str) -> bool:
    return nome in sa.inspect(op.get_bind()).get_table_names()


def tem_coluna(tabela: str, coluna: str) -> bool:
    """Ver o comentário gêmeo na 0002.

    Num banco vazio a 0001 monta as tabelas com `create_all`, que usa o modelo
    de hoje — ou seja, já com tudo o que esta migração adicionaria. Sem esta
    checagem, ambiente novo não sobe.
    """
    inspetor = sa.inspect(op.get_bind())
    if tabela not in inspetor.get_table_names():
        return False
    return coluna in {c["name"] for c in inspetor.get_columns(tabela)}


def upgrade() -> None:
    conexao = op.get_bind()

    # checkfirst porque a 0001 pode ter criado o tipo junto com as tabelas.
    metodo_de_pagamento.create(conexao, checkfirst=True)

    if not tem_tabela("cards"):
        op.create_table(
            "cards",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            # Dia do mês. Mês curto é achatado no cálculo, não aqui: guardar 31
            # e resolver fevereiro na hora é o que mantém o dado fiel ao que o
            # banco informa.
            sa.Column("closing_day", sa.Integer(), nullable=False),
            sa.Column("due_day", sa.Integer(), nullable=False),
            sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_cards_user_id"),
        )
        op.create_index("ix_cards_user_id", "cards", ["user_id"])

    if not tem_tabela("purchases"):
        op.create_table(
            "purchases",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("card_id", sa.Integer(), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=False),
            sa.Column("description", sa.String(), nullable=False),
            # O valor cheio da compra. As parcelas são derivadas dele em
            # centavos inteiros — o caminho contrário não fecha (33,33 × 3).
            sa.Column("total_amount", sa.Float(), nullable=False),
            sa.Column("installments", sa.Integer(), nullable=False),
            sa.Column("purchase_date", sa.Date(), nullable=False),
            sa.Column("note", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_purchases_user_id"),
            sa.ForeignKeyConstraint(["card_id"], ["cards.id"], name="fk_purchases_card_id"),
            sa.ForeignKeyConstraint(
                ["category_id"], ["categories.id"], name="fk_purchases_category_id"
            ),
        )
        op.create_index("ix_purchases_user_id", "purchases", ["user_id"])

    if not tem_tabela("invoices"):
        op.create_table(
            "invoices",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("card_id", sa.Integer(), nullable=False),
            # Referência = mês do VENCIMENTO. O fechamento pode ser do anterior.
            sa.Column("year", sa.Integer(), nullable=False),
            sa.Column("month", sa.Integer(), nullable=False),
            # Congeladas: mudar o dia de fechamento do cartão não pode remontar
            # fatura que já foi cobrada.
            sa.Column("closing_date", sa.Date(), nullable=False),
            sa.Column("due_date", sa.Date(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "user_id", "card_id", "year", "month", name="uq_invoice_card_period"
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_invoices_user_id"),
            sa.ForeignKeyConstraint(["card_id"], ["cards.id"], name="fk_invoices_card_id"),
        )
        op.create_index("ix_invoices_user_id", "invoices", ["user_id"])
        op.create_index("ix_invoices_card_id", "invoices", ["card_id"])

    if not tem_tabela("invoice_payments"):
        op.create_table(
            "invoice_payments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("invoice_id", sa.Integer(), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False),
            # Guarda o rastro da reconciliação: qual lançamento antigo virou
            # este pagamento.
            sa.Column("note", sa.String(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["user_id"], ["users.id"], name="fk_invoice_payments_user_id"
            ),
            sa.ForeignKeyConstraint(
                ["invoice_id"], ["invoices.id"], name="fk_invoice_payments_invoice_id"
            ),
        )
        op.create_index("ix_invoice_payments_user_id", "invoice_payments", ["user_id"])
        op.create_index("ix_invoice_payments_invoice_id", "invoice_payments", ["invoice_id"])

    # ---------- As quatro colunas em transactions ----------
    #
    # Em batch porque o SQLite não implementa ADD CONSTRAINT: lá o Alembic
    # recria a tabela e copia os dados, no Postgres emite o ALTER normal. É o
    # que permite ensaiar esta migração numa cópia SQLite dos dados reais antes
    # de rodá-la em produção — e ensaiar não é opcional num banco em uso.
    faltando = [c for c in ("payment_method", "purchase_id", "installment_no", "invoice_id")
                if not tem_coluna("transactions", c)]

    if faltando:
        with op.batch_alter_table("transactions", recreate="auto") as batch:
            if "payment_method" in faltando:
                # Nullable e sem default: NULL é "ainda não sei", e é a resposta
                # certa para todo lançamento anterior ao cartão.
                batch.add_column(sa.Column("payment_method", metodo_de_pagamento, nullable=True))
            if "purchase_id" in faltando:
                batch.add_column(sa.Column("purchase_id", sa.Integer(), nullable=True))
                batch.create_foreign_key(
                    "fk_transactions_purchase_id", "purchases", ["purchase_id"], ["id"]
                )
            if "installment_no" in faltando:
                batch.add_column(sa.Column("installment_no", sa.Integer(), nullable=True))
            if "invoice_id" in faltando:
                batch.add_column(sa.Column("invoice_id", sa.Integer(), nullable=True))
                batch.create_foreign_key(
                    "fk_transactions_invoice_id", "invoices", ["invoice_id"], ["id"]
                )

        # Os dois índices servem à tela da fatura ("me dê os itens desta") e à
        # da compra ("me dê as parcelas desta"), que são as duas consultas que
        # esta funcionalidade faz o tempo todo.
        op.create_index("ix_transactions_invoice_id", "transactions", ["invoice_id"])
        op.create_index("ix_transactions_purchase_id", "transactions", ["purchase_id"])


def downgrade() -> None:
    op.drop_index("ix_transactions_purchase_id", table_name="transactions")
    op.drop_index("ix_transactions_invoice_id", table_name="transactions")

    with op.batch_alter_table("transactions", recreate="auto") as batch:
        for nome, tipo in (
            ("fk_transactions_invoice_id", "foreignkey"),
            ("fk_transactions_purchase_id", "foreignkey"),
        ):
            try:
                batch.drop_constraint(nome, type_=tipo)
            except Exception:
                # O nome pode variar conforme como a tabela nasceu — o mesmo
                # cuidado que a 0001 toma nas restrições de unicidade.
                pass
        batch.drop_column("invoice_id")
        batch.drop_column("installment_no")
        batch.drop_column("purchase_id")
        batch.drop_column("payment_method")

    op.drop_table("invoice_payments")
    op.drop_table("invoices")
    op.drop_table("purchases")
    op.drop_table("cards")

    metodo_de_pagamento.drop(op.get_bind(), checkfirst=True)
