import datetime as dt
from typing import Any

import sqlalchemy as sa
from sqlmodel import SQLModel, Field, UniqueConstraint
from enum import Enum


# ---------- Usuário ----------
# O app nasceu de uma conta só, com e-mail e hash em variável de ambiente. Virou
# tabela quando apareceram três contas: a principal, uma de demonstração pública
# e a da namorada. O segredo que assina os tokens (SENTAVOS_JWT_SECRET) continua
# no ambiente — ele é do servidor, não de uma pessoa.

class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    # Guardado em minúsculas pra a comparação do login não depender de como a
    # pessoa digitou no teclado do celular.
    email: str = Field(unique=True, index=True)
    name: str
    # Hash Argon2id. A senha em si não existe em lugar nenhum do sistema.
    password_hash: str

    # Conta de demonstração: lê tudo, não escreve nada. A senha dela é pública
    # (vai no LinkedIn), então sem esta trava o primeiro visitante mal-
    # intencionado apagaria o demo inteiro — e só se descobriria depois.
    read_only: bool = Field(default=False)

    # A taxa CDI ao ano, em porcentagem (10.65 = 10,65% a.a.). Fica no usuário e
    # não no ativo porque é um número só pro país inteiro: repetido por
    # aplicação, atualizar a Selic viraria editar cinco lugares e esquecer o
    # sexto. Nulo = ainda não informado, e aí o app não projeta nada.
    cdi_annual: float | None = Field(default=None)

    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )


# Toda tabela de dados carrega o dono. Sem esta coluna as linhas seriam globais,
# que é exatamente o que eram quando só existia uma conta.
def dono() -> int:
    return Field(foreign_key="users.id", index=True)



class CategoryType(str, Enum):
    EXPENSE = "expense"
    INCOME = "income"
    INVESTMENT = "investment"


class ExpenseClass(str, Enum):
    FIXED = "fixed"
    VARIABLE = "variable"


def _classe_despesa():
    return sa.Enum(ExpenseClass, native_enum=False, length=8)

class TransactionNature(str, Enum):
    """Que evento econômico foi o gasto — não "com o quê" (isso é a categoria).

    Só despesa tem natureza, e o gasto total continua somando as três. A
    entrada da moto é Moto + aquisição; os equipamentos são Moto + consumo; a
    parcela do financiamento é financeiro. "Custo de vida" é só o consumo.
    Como os outros enums, o banco grava o NOME (`CONSUMPTION`).
    """

    CONSUMPTION = "consumption"
    ASSET_ACQUISITION = "asset_acquisition"
    FINANCIAL = "financial"


def _natureza():
    return sa.Enum(TransactionNature, native_enum=False, length=20)


class Finalidade(str, Enum):
    """Quem, ou qual contexto, consumiu o gasto.

    Responde "quanto EU gastei?" — pergunta que o filtro por cartão não
    responde, porque PIX e débito não têm cartão. Não confundir com a conta de
    onde o dinheiro saiu: a compra da família no meu cartão é FAMILIA e continua
    saindo do MEU caixa quando a fatura é paga. Por isso finalidade filtra gasto
    e nunca saldo, fatura ou patrimônio.

    Só existe em DESPESA. Receita e investimento ficam nulos de propósito: ainda
    não está decidido se reembolso da empresa é receita ou abatimento de gasto
    empresarial, e codificar uma das duas agora seria inventar regra contábil.

    Como em `PaymentMethod`, o banco grava o NOME (`PESSOAL`), não o valor.
    """

    PESSOAL = "pessoal"
    FAMILIA = "familia"
    EMPRESA = "empresa"


class CategoryBase(SQLModel):
    name: str
    type: CategoryType
    color: str
    icon: str

    # Categoria arquivada some do formulário de lançamento mas continua
    # existindo: os lançamentos antigos apontam pra ela, e apagá-la levaria o
    # histórico junto. É o caminho do meio entre "conviver com 28 categorias
    # herdadas da planilha" e "perder um ano de dados".
    archived: bool = False

    # Natureza padrão dos gastos desta categoria (nula = consumo). O lançamento
    # herda e pode sobrescrever: Moto é consumo, a entrada da moto não.
    default_nature: TransactionNature | None = Field(default=None, sa_type=_natureza())

class Category(CategoryBase, table=True):
    __tablename__ = "categories"
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)

class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(SQLModel):
    name: str | None = None
    type: CategoryType | None = None
    color: str | None = None
    icon: str | None = None
    archived: bool | None = None
    default_nature: TransactionNature | None = None


class CategoryRead(CategoryBase):
    """A categoria com o quanto ela já foi usada — só com `incluir_uso=1`.

    Serve à tela de Configurações, que precisa saber antes de oferecer a troca
    de tipo se ela vai ser recusada. A trava de verdade é no servidor; isto é só
    pra a tela não oferecer uma porta que dá em parede.
    """

    id: int
    user_id: int
    transactions: int = 0
    purchases: int = 0
    budgets: int = 0
    commitments: int = 0

class PaymentMethod(str, Enum):
    """Como o dinheiro sai (ou não sai) da conta neste lançamento.

    NULL é um terceiro estado, e é de propósito: os 269 lançamentos que já
    existiam quando o cartão entrou no app não têm essa informação, e inventá-la
    seria pior do que admitir que ela falta. Ver `TransactionBase.payment_method`.
    """

    # Saiu da conta na hora: PIX, débito, dinheiro, boleto.
    CASH = "cash"
    # Foi gasto agora, sai da conta quando a fatura for paga.
    CREDIT = "credit"


class TransactionBase(SQLModel):
    date: dt.date
    description: str
    amount_planned: float | None = None
    amount_paid: float | None = None
    note: str | None = None
    category_id: int = Field(foreign_key="categories.id")
    expense_class: ExpenseClass | None = Field(default=None, sa_type=_classe_despesa())

    # ---------- Gasto x saída de caixa ----------
    # Até aqui o app tratava os dois como o mesmo evento. É verdade pra PIX e
    # débito, e falso pro cartão: a compra é gasto hoje e só vira saída de caixa
    # quando a fatura é paga, semanas depois.
    #
    # Nulo = "ainda não sei", e só acontece em lançamento anterior a esta
    # funcionalidade. A Carteira conta esses como saída de caixa — não porque
    # sejam à vista, mas porque é assim que eles já eram contados, e mudar isso
    # sem o dono revisar reescreveria o histórico dele de um dia pro outro. A
    # tela de revisão existe pra transformar esse nulo em resposta.
    payment_method: PaymentMethod | None = None

    # ---------- Quem consumiu ----------
    # O valor EFETIVO, e é a única coluna que os relatórios consultam — à vista
    # e parcela de cartão passam pelo mesmo filtro, sem join com compra.
    #
    #   à vista sem escolha  -> PESSOAL (decidido na rota, não aqui)
    #   parcela de cartão    -> cópia de Purchase.finalidade
    #   receita/investimento -> sempre nulo
    #
    # Nulo também é o estado de todo lançamento anterior a esta funcionalidade.
    # Não se adivinha retroativamente: o filtro "Todos" os inclui, os outros
    # não, e a tela diz quanto ficou de fora.
    finalidade: Finalidade | None = None

    # De qual conta saiu (despesa, aporte) ou em qual entrou (receita, resgate).
    # Nulo = "conta não informada": todo o histórico anterior às contas, a
    # compra no cartão (quem diz de onde sai é o pagamento da fatura) e o
    # previsto. Não se deduz por descrição nem por banco.
    account_id: int | None = None
    # O instante, quando se sabe. `date` não tem hora, e o saldo observado
    # (AccountBalanceSnapshot) tem: sem isto, um Pix das 14h e um saldo lido às
    # 10h do mesmo dia seriam ambíguos. Nulo = só a data (ver app/dominio/contas.py).
    occurred_at: dt.datetime | None = Field(default=None, sa_type=sa.DateTime(timezone=True))
    # Sobrescreve a natureza da categoria só neste lançamento (nula = herda).
    # Só despesa; a baixa de compromisso copia a do compromisso.
    nature: TransactionNature | None = Field(default=None, sa_type=_natureza())


class Transaction(TransactionBase, table=True):
    __tablename__ = "transactions"
    __table_args__ = (
        # Uma ocorrência de compromisso tem no máximo UM lançamento que a paga.
        # É a trava contra a baixa duplicada: dois toques em "Pagar" na mesma
        # parcela da Hunter seriam R$ 618,08 saindo duas vezes. Nulos não
        # colidem entre si (Postgres e SQLite), então o lançamento comum passa.
        sa.Index(
            "uq_transactions_commitment_occurrence",
            "commitment_id",
            "commitment_no",
            unique=True,
        ),
        # A conta tem de ser do mesmo dono — garantido pelo banco, não só pela rota.
        sa.ForeignKeyConstraint(
            ["user_id", "account_id"],
            ["financial_accounts.user_id", "financial_accounts.id"],
            name="fk_transactions_account",
        ),
        sa.Index("ix_transactions_user_date", "user_id", "date"),
        sa.Index("ix_transactions_account_date", "account_id", "date"),
        # Alvo da chave composta do movimento de investimento (mesmo dono).
        sa.UniqueConstraint("user_id", "id", name="uq_transactions_user_id"),
    )
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)

    # ---------- Só para lançamento de cartão ----------
    # Os três andam juntos: ou são todos nulos (lançamento à vista), ou todos
    # preenchidos (uma parcela de uma compra, cobrada numa fatura).
    #
    # Não vêm em TransactionCreate de propósito: parcela não se cria solta, se
    # cria pela compra — senão dava pra plantar uma parcela "3 de 2", ou uma
    # parcela numa fatura que já foi paga.
    purchase_id: int | None = Field(default=None, foreign_key="purchases.id", index=True)
    installment_no: int | None = None
    invoice_id: int | None = Field(default=None, foreign_key="invoices.id", index=True)

    # ---------- Só para a baixa de um compromisso ----------
    # O lançamento que REALIZA a ocorrência `commitment_no` de um compromisso
    # (a parcela 3/48 do financiamento, a academia de novembro). O vínculo mora
    # aqui, e não numa tabela de pagamentos, por um motivo de integridade:
    # apagar o lançamento desfaz a baixa sozinho, sem deixar um "pago" órfão
    # apontando pra dinheiro que não saiu. Como `purchase_id`, não vem em
    # TransactionCreate — a baixa tem rota própria.
    commitment_id: int | None = Field(default=None, foreign_key="commitments.id", index=True)
    commitment_no: int | None = None


class TransactionCreate(TransactionBase):
    pass

class TransactionUpdate(SQLModel):
    date: dt.date | None = None
    description: str | None = None
    amount_planned: float | None = None
    amount_paid: float | None = None
    note: str | None = None
    category_id: int | None = None
    payment_method: PaymentMethod | None = None
    finalidade: Finalidade | None = None
    account_id: int | None = None
    occurred_at: dt.datetime | None = None
    nature: TransactionNature | None = None
    expense_class: ExpenseClass | None = None


class TransactionRead(TransactionBase):
    """O lançamento como a tela precisa dele.

    A lista mostra "Notebook · Compras · Nubank 2/10", e esses três últimos
    dados moram em duas tabelas diferentes. Resolver isso no navegador daria uma
    chamada por linha; resolver aqui custa duas consultas para a lista inteira.
    """

    id: int
    effective_expense_class: ExpenseClass | None = None
    purchase_id: int | None = None
    installment_no: int | None = None
    invoice_id: int | None = None
    # Vêm da compra e do cartão — nulos em lançamento à vista.
    installments: int | None = None
    purchase_total: float | None = None
    purchase_date: dt.date | None = None
    card_id: int | None = None
    card_name: str | None = None
    card_finalidade: Finalidade | None = None
    # Vêm do compromisso — nulos em lançamento que não é baixa de nenhum. A
    # lista mostra "Hunter 1/48" sem uma chamada por linha.
    commitment_id: int | None = None
    commitment_no: int | None = None
    commitment_description: str | None = None
    commitment_installments: int | None = None
    # Nome da conta, pra lista não precisar de uma chamada por linha.
    account_name: str | None = None
    # A natureza que vale: a do lançamento, senão a da categoria, senão
    # consumo. Nula em receita e investimento.
    effective_nature: TransactionNature | None = None


# ---------- Cartão de crédito ----------
# Três entidades e um princípio: a fatura não guarda dinheiro, ela guarda
# identidade. Total, pago, restante e status são derivados dos itens e dos
# pagamentos toda vez que a tela pede.
#
# É a mesma decisão da aba de Investimento, que não tem dados próprios: dois
# números para o mesmo dinheiro começam iguais e terminam diferentes. Um status
# gravado teria ainda um segundo defeito — precisaria de alguém passando de
# tempos em tempos só pra virar "aberta" em "atrasada" na data certa.


class CardBase(SQLModel):
    name: str
    # Dia do mês, 1 a 31. Mês curto é achatado na hora de calcular (ver
    # app/cartao.py): cartão que fecha 31 fecha 28 em fevereiro.
    closing_day: int = Field(ge=1, le=31)
    due_day: int = Field(ge=1, le=31)

    # Arquivado some do formulário de lançamento e continua no banco, igual à
    # categoria: as compras antigas apontam pra ele.
    archived: bool = False

    # O uso padrão do cartão ("o da família"). Compra nele herda isto quando a
    # pessoa não escolhe outra coisa.
    #
    # Nulo só nos cartões que existiam antes desta coluna: a migração não
    # adivinha pelo nome ("Nubank - Família" parece óbvio, e é justamente o tipo
    # de palpite que um dia erra calado). A tela pede a classificação.
    finalidade: Finalidade | None = None


class Card(CardBase, table=True):
    __tablename__ = "cards"
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )


class CardCreate(CardBase):
    # Cartão novo nasce com finalidade. A tela sempre manda a escolha; o padrão
    # só vale pra quem chama a API sem ela, e é o mesmo do lançamento à vista.
    finalidade: Finalidade | None = Finalidade.PESSOAL


class CardUpdate(SQLModel):
    name: str | None = None
    closing_day: int | None = Field(default=None, ge=1, le=31)
    due_day: int | None = Field(default=None, ge=1, le=31)
    archived: bool | None = None
    finalidade: Finalidade | None = None


# Teto de parcelas. Não é regra de cartão nenhum — é o que impede um dedo errado
# ("1200x") de plantar mil linhas no banco. A tela oferece até 24.
MAX_PARCELAS = 72


class PurchaseBase(SQLModel):
    card_id: int = Field(foreign_key="cards.id")
    category_id: int = Field(foreign_key="categories.id")
    description: str
    expense_class: ExpenseClass | None = Field(default=None, sa_type=_classe_despesa())
    # O valor CHEIO da compra. As parcelas saem daqui divididas em centavos
    # inteiros, e não o contrário: guardar o valor da parcela faria o total ser
    # uma multiplicação que não fecha (33,33 × 3 = 99,99).
    total_amount: float
    installments: int = Field(default=1, ge=1, le=MAX_PARCELAS)
    # Quando a compra aconteceu de verdade. Diferente da competência do gasto
    # (que é a data de cada parcela) e da fatura que a cobra.
    purchase_date: dt.date
    note: str | None = None

    # A finalidade LÓGICA da compra, que todas as parcelas copiam. Mora aqui, e
    # não só nas parcelas, pra uma compra em 10x não ter como ficar com parcelas
    # em finalidades diferentes: parcela não se edita sozinha, e editar a compra
    # reescreve as dez de uma vez.
    #
    # Na criação, nulo quer dizer "a do cartão". Depois de gravada ela vale por
    # si: trocar a finalidade do cartão em 2027 não reescreve pra que serviu uma
    # compra de 2026. A única herança posterior é a da transição — compra sem
    # finalidade nenhuma recebe a do cartão quando ele é classificado.
    finalidade: Finalidade | None = None


class Purchase(PurchaseBase, table=True):
    """A compra no cartão, parcelada ou não.

    Existe mesmo em 1x. Poderia não existir — uma compra à vista no cartão é uma
    parcela só, e os dados caberiam na própria transação. Mas aí editar e
    apagar teriam dois caminhos diferentes conforme o número de parcelas, e o
    caminho menos usado é sempre o que quebra.
    """

    __tablename__ = "purchases"
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )


class PurchaseCreate(PurchaseBase):
    planned: bool = False


class PurchaseUpdate(SQLModel):
    planned: bool | None = None
    """O que dá pra mudar depois.

    Descrição, categoria e observação são rótulo: mudam sem mexer em dinheiro.
    Valor, parcelas e cartão mudam quanto cada fatura cobra — a rota recusa
    esses três quando alguma fatura da compra já recebeu pagamento.
    """

    description: str | None = None
    expense_class: ExpenseClass | None = None
    category_id: int | None = None
    note: str | None = None
    total_amount: float | None = None
    installments: int | None = Field(default=None, ge=1, le=MAX_PARCELAS)
    card_id: int | None = None
    purchase_date: dt.date | None = None
    finalidade: Finalidade | None = None


class Invoice(SQLModel, table=True):
    """Uma fatura de um cartão num período.

    `year`/`month` são a referência pela qual ela é conhecida — o mês do
    VENCIMENTO, que é como o banco a chama e como se fala dela ("a fatura de
    outubro"). O fechamento pode ser do mês anterior.

    As duas datas ficam CONGELADAS aqui, e não recalculadas a partir do cartão.
    Trocar o dia de fechamento em 2027 não pode remontar as faturas de 2026 —
    elas já foram cobradas e pagas com as datas que tinham.
    """

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("user_id", "card_id", "year", "month", name="uq_invoice_card_period"),
    )

    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)
    card_id: int = Field(foreign_key="cards.id", index=True)
    year: int = Field(ge=1900, le=2999)
    month: int = Field(ge=1, le=12)
    closing_date: dt.date
    due_date: dt.date


class InvoicePaymentBase(SQLModel):
    date: dt.date
    amount: float
    # Livre, e é o que guarda o rastro de uma reconciliação: quando um
    # lançamento antigo de "Fatura do cartão" vira pagamento, o que ele era
    # fica escrito aqui. Sem isso a operação apagaria a origem sem deixar marca.
    note: str | None = None
    # A compra no cartão não sabe de conta; o pagamento da fatura sabe — é aí
    # que o dinheiro sai. Nulo = não informada (todo pagamento anterior).
    account_id: int | None = None
    occurred_at: dt.datetime | None = Field(default=None, sa_type=sa.DateTime(timezone=True))


class InvoicePayment(InvoicePaymentBase, table=True):
    """O pagamento da fatura: saída de caixa que NÃO é gasto de categoria.

    É por isso que ele não é uma `Transaction`. O gasto já foi contado quando a
    compra foi lançada; contar de novo aqui somaria o mesmo dinheiro duas vezes,
    e o erro apareceria como "gastei 2.400 num mês em que gastei 1.200".

    Não ter `category_id` não é esquecimento: é a garantia estrutural de que
    isso nunca vai cair numa meta nem no "para onde foi".
    """

    __tablename__ = "invoice_payments"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["user_id", "account_id"],
            ["financial_accounts.user_id", "financial_accounts.id"],
            name="fk_invoice_payments_account",
        ),
    )
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)
    invoice_id: int = Field(foreign_key="invoices.id", index=True)


class InvoicePaymentCreate(InvoicePaymentBase):
    pass


class InvoiceStatus(str, Enum):
    """Calculado na hora, nunca gravado.

    A precedência é `paga` → `atrasada` → `parcial` → `aberta`: uma fatura
    vencida com saldo aparece como atrasada mesmo se já recebeu parte, porque é
    a informação que pede ação. Quanto já foi pago continua visível ao lado.
    """

    ABERTA = "aberta"
    PARCIAL = "parcial"
    PAGA = "paga"
    ATRASADA = "atrasada"


# Sem juros, multa, rotativo ou IOF — de propósito. Cobrança dessas entra como
# lançamento normal, feito pelo dono, com o valor que o banco cobrou de fato.


class InvoiceItem(SQLModel):
    planned: bool = False
    """Uma linha da fatura: a parcela, com o rastro até a compra que a gerou."""

    transaction_id: int
    # A competência do gasto — o mês em que esta parcela conta no orçamento.
    date: dt.date
    description: str
    amount: float
    category_id: int
    category_name: str
    color: str
    icon: str
    # "1/3". Nulo em compra de uma parcela só, pra a tela não escrever "1/1".
    installment_no: int | None = None
    installments: int | None = None
    purchase_id: int
    purchase_total: float
    purchase_date: dt.date
    finalidade: Finalidade | None = None


class InvoiceRead(SQLModel):
    id: int
    card_id: int
    card_name: str
    year: int
    month: int
    closing_date: dt.date
    due_date: dt.date
    total: float = 0
    paid: float = 0
    remaining: float = 0
    status: InvoiceStatus = InvoiceStatus.ABERTA
    item_count: int = 0


class InvoicePaymentRead(InvoicePaymentBase):
    id: int
    invoice_id: int
    card_id: int
    card_name: str
    # Pra a lista de lançamentos poder linkar de volta sem uma segunda consulta.
    invoice_year: int
    invoice_month: int


class InvoiceDetail(InvoiceRead):
    items: list[InvoiceItem] = []
    payments: list[InvoicePaymentRead] = []


class CardInvoices(SQLModel):
    """O que a aba de Faturas mostra por cartão."""

    card_id: int
    name: str
    closing_day: int
    due_day: int
    archived: bool
    # A fatura que vence no mês selecionado — a que se paga agora.
    current: InvoiceRead | None = None
    # A que está acumulando para o mês seguinte.
    next: InvoiceRead | None = None
    # Tudo que ainda não foi pago, deste cartão, somando todas as faturas.
    open_total: float = 0


class InvoicesSummary(SQLModel):
    year: int
    month: int
    cards: list[CardInvoices] = []
    # Os pagamentos feitos no mês — é o que a lista de lançamentos mescla, e o
    # que a Carteira desconta.
    payments: list[InvoicePaymentRead] = []
    # Faturas que vencem no mês selecionado.
    due_this_month: float = 0
    paid_this_month: float = 0
    # Restante de TODAS as faturas em aberto, de todos os cartões. É o número
    # que vira "após faturas" no Início.
    open_total: float = 0


class PurchaseRead(PurchaseBase):
    planned: bool = False
    """A compra com o contexto que a tela mostra ao abrir uma parcela."""

    id: int
    card_name: str
    category_name: str
    color: str
    icon: str
    # Valor de cada parcela, na ordem — a primeira leva os centavos que sobram.
    installment_amounts: list[float] = []
    # Quantas parcelas estão em fatura já paga: é o que decide se dá pra editar
    # valor, parcelas e cartão.
    paid_installments: int = 0
    locked: bool = False


# ---------- Orçamento ----------
# A meta de gasto de uma categoria num mês. Não confundir com o
# amount_planned da transação: "orçado" é o teto que você definiu pra
# categoria, "previsto" é a soma dos lançamentos que você já sabe que vêm.

class BudgetBase(SQLModel):
    category_id: int = Field(foreign_key="categories.id")
    year: int = Field(ge=1900, le=2999)
    month: int = Field(ge=1, le=12)
    amount: float

class Budget(BudgetBase, table=True):
    __tablename__ = "budgets"
    # Uma meta por categoria por mês — o PUT depende disso pra decidir
    # entre criar e atualizar.
    __table_args__ = (
        UniqueConstraint("user_id", "category_id", "year", "month", name="uq_budget_category_period"),
    )
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)

class BudgetCreate(BudgetBase):
    pass

class BudgetUpdate(SQLModel):
    amount: float | None = None


# Resposta do /budgets/summary: uma linha por categoria com orçado,
# previsto e pago já cruzados, pra aba de Orçamento não precisar
# somar transação no navegador.

class BudgetSummaryItem(SQLModel):
    category_id: int
    category_name: str
    category_type: CategoryType
    color: str
    icon: str
    archived: bool = False
    budget_id: int | None = None
    # O teto do mês. Zero (ou sem meta) significa categoria sem teto, não
    # categoria proibida: gastar nela continua valendo, só não há régua.
    budgeted: float = 0
    planned: float = 0
    paid: float = 0

    # ---------- Por que não há acúmulo aqui ----------
    # Existiu uma versão com caixinha: o que sobrava num mês virava saldo do
    # mês seguinte (carried_in, available, has_envelope). A ideia é boa no
    # papel e ruim na prática — o número que a tela mostrava dependia de todo
    # o passado, então uma meta esquecida em janeiro reaparecia como dívida em
    # setembro, e a Fatura chegou a mostrar −R$ 5.443 de "disponível".
    #
    # O teto mensal não tem passado: gastei 480 de 750, faltam 270, e na virada
    # recomeça. É menos poderoso e é conferível de cabeça, que é o que importa
    # numa tela que se abre no meio do mercado.

class BudgetSummaryTotals(SQLModel):
    budgeted: float = 0
    planned: float = 0
    paid: float = 0

class Caixa(SQLModel):
    """Os dois eixos do mês, lado a lado: o que gastei e o que saiu da conta.

    Eles eram o mesmo número até o cartão entrar no app. Agora:

        gastei 1.200 no mês  (500 à vista + 700 no cartão)
        saiu da conta 500    (o cartão sai quando a fatura for paga)

    Mora no resumo do orçamento, e não numa rota própria, porque a tela de
    Início já pede este resumo — uma chamada a mais na tela que mais se abre
    seria meio segundo de espera por nada.
    """

    # ---------- Eixo caixa: dinheiro de verdade ----------
    entrou: float = 0
    saiu_a_vista: float = 0
    investido: float = 0
    faturas_pagas: float = 0
    # entrou − saiu à vista − investido − faturas pagas. Na tela é o "Saldo do
    # mês" — o nome do campo ficou pra não quebrar o front já publicado.
    carteira: float = 0

    # ---------- Eixo gasto: o que consumi ----------
    # gasto_total inclui o que foi no cartão; é o número das metas.
    gasto_total: float = 0
    no_cartao: float = 0
    # O mesmo gasto total pelas três naturezas (somam gasto_total). Custo de
    # vida é só o consumo: fora a entrada da moto e a parcela do financiamento.
    custo_de_vida: float = 0
    aquisicoes: float = 0
    financeiro: float = 0

    # ---------- Transição ----------
    # Despesa anterior ao cartão, ainda sem forma de pagamento definida. Conta
    # como saída de caixa (é como já era contada), mas a tela avisa que esses
    # lançamentos existem em vez de fingir que a resposta está completa.
    sem_forma_definida: float = 0
    sem_forma_definida_qtd: int = 0

    # ---------- Compromisso ----------
    # Faturas que vencem neste mês, e o que ainda falta pagar de todas elas.
    faturas_do_mes: float = 0
    faturas_em_aberto: float = 0
    # Carteira − faturas em aberto. Saiu da tela na V2: subtraía faturas de
    # meses futuros do fluxo de UM mês, misturando dois horizontes. Continua
    # aqui só pra o front antigo não quebrar durante o deploy.
    apos_faturas: float = 0


class BudgetSummary(SQLModel):
    year: int
    month: int
    items: list[BudgetSummaryItem]
    # Chaveado pelo tipo de categoria: expense, income, investment.
    #
    # Continua somando TODA despesa, à vista ou no cartão: meta mede gasto, e
    # uma compra parcelada no cartão consome o teto de Alimentação no mês da
    # parcela mesmo sem ter saído da conta ainda.
    totals: dict[str, BudgetSummaryTotals]
    caixa: Caixa = Caixa()


# ---------- Patrimônio ----------
# Enquanto Transaction é fluxo (o que entrou e saiu no mês), aqui é estoque:
# quanto cada coisa vale num ponto do tempo. Por isso não dá pra derivar
# patrimônio das transações — precisa de saldo lançado, não de movimento.

class AssetClass(str, Enum):
    CHECKING = "checking"
    FIXED_INCOME = "fixed_income"
    EQUITY = "equity"
    CRYPTO = "crypto"
    REAL_ESTATE = "real_estate"
    VEHICLE = "vehicle"
    DEBT = "debt"


# Dívida entra no mesmo lugar dos ativos e sai subtraindo — financiamento é
# patrimônio negativo, não uma entidade à parte.
LIABILITY_CLASSES = {AssetClass.DEBT}

# As classes que a aba de Investimento vai filtrar. Mora aqui pra as duas
# telas não discordarem sobre o que conta como investimento.
INVESTMENT_CLASSES = {AssetClass.FIXED_INCOME, AssetClass.EQUITY, AssetClass.CRYPTO}


def is_liability(asset_class: AssetClass) -> bool:
    return AssetClass(asset_class) in LIABILITY_CLASSES


class AssetBase(SQLModel):
    name: str
    asset_class: AssetClass
    note: str | None = None

    # Quanto do CDI a aplicação paga, em porcentagem (115.0 = 115% do CDI). É
    # como o banco apresenta renda fixa, então o número é copiado direto de lá.
    #
    # Nulo significa "não rende", que é o caso de conta corrente, imóvel e
    # carro — a maioria dos ativos. Zero diria a mesma coisa, mas tornaria
    # impossível distinguir "não sei a taxa" de "a taxa é zero".
    cdi_percent: float | None = None

    # Se o saldo deste ativo é dinheiro com que o planejamento conta ("quanto
    # tenho agora"). Não dá pra deduzir pela classe: o Mercado Pago e o Nubank
    # do dono são renda fixa (rendem 115% do CDI) e são justamente onde o
    # dinheiro do mês mora. Nulo = a escolha padrão, que é só a classe Conta —
    # o mesmo que a tela mostra marcado antes de alguém mexer.
    include_in_planning: bool | None = None

    # A partir de que mês o ativo deixa de contar (o dia é ignorado). O
    # histórico fica: setembro continua lendo o saldo de setembro. É como um
    # ativo que na verdade era conta (ou um quebra-galho, como o "Saldo
    # agregado" de out/2026) sai do patrimônio sem reescrever o passado.
    archived_on: dt.date | None = None

class Asset(AssetBase, table=True):
    __tablename__ = "assets"
    # Alvo da chave composta de investment_movements: movimento só aponta pra
    # ativo do mesmo dono.
    __table_args__ = (UniqueConstraint("user_id", "id", name="uq_assets_user_id"),)
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)

class AssetCreate(AssetBase):
    pass

class AssetUpdate(SQLModel):
    name: str | None = None
    asset_class: AssetClass | None = None
    note: str | None = None
    cdi_percent: float | None = None
    include_in_planning: bool | None = None
    archived_on: dt.date | None = None


# O saldo de um ativo num mês. Preenchido à mão — sem cotação automática no v1.
class AssetSnapshotBase(SQLModel):
    asset_id: int = Field(foreign_key="assets.id")
    year: int = Field(ge=1900, le=2999)
    month: int = Field(ge=1, le=12)
    value: float
    # O dia em que o saldo foi lido no banco. O saldo continua sendo do MÊS
    # (Patrimônio não muda); o dia serve ao planejamento, que precisa saber se
    # um lançamento de 10/10 já está ou não dentro de um saldo "de outubro".
    # Nulo nos saldos antigos e nos de meses passados, onde vale "fim do mês".
    observed_on: dt.date | None = None
    # Saldo lançado por CONFERÊNCIA: o dono sabe o valor de hoje, mas no mês
    # houve movimento cujo valor exato não está registrado (o resgate da
    # caixinha usado na moto, sem o extrato). O texto diz o que aconteceu.
    #
    # Com ele, o rendimento do mês desse ativo é "não apurado": a conta
    # variação − aportes + resgates daria um número falso, porque falta uma
    # das parcelas. Melhor um traço com o motivo do que um prejuízo inventado.
    # Não muda nenhum valor — saldo, patrimônio e caixa continuam iguais.
    reconciliation_note: str | None = None

class AssetSnapshot(AssetSnapshotBase, table=True):
    __tablename__ = "asset_snapshots"
    __table_args__ = (
        UniqueConstraint("user_id", "asset_id", "year", "month", name="uq_snapshot_asset_period"),
    )
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)

class AssetSnapshotCreate(AssetSnapshotBase):
    pass

class AssetSnapshotUpdate(SQLModel):
    value: float | None = None


class AssetSummaryItem(SQLModel):
    asset_id: int
    name: str
    asset_class: AssetClass
    liability: bool
    note: str | None = None
    cdi_percent: float | None = None
    # Quanto a aplicação DEVERIA render no mês, pela taxa declarada. É bruto:
    # não desconta imposto de renda nem IOF. Nulo quando não há taxa ou o
    # usuário ainda não informou o CDI.
    expected_yield: float | None = None
    # id do snapshot deste mês exato; None quando o valor veio de mês anterior.
    snapshot_id: int | None = None
    value: float = 0
    previous: float = 0
    change: float = 0
    # "YYYY-MM" de onde o valor saiu, ou None se o ativo nunca teve saldo.
    # Deixa a tela avisar que o número é herdado em vez de fingir que é atual.
    as_of: str | None = None
    # Só quando o saldo DESTE mês foi lançado por conferência: o rendimento do
    # mês desse ativo não é apurável (ver AssetSnapshotBase).
    reconciliation_note: str | None = None
    # Do mês corrente em diante, um saldo herdado de mês anterior é só o
    # último conhecido: `value` mostra qual era, mas ele NÃO soma em total
    # nenhum (classe, ativos, patrimônio). Ver `planejamento.saldo_desatualizado`.
    stale: bool = False

class AssetClassTotal(SQLModel):
    value: float = 0
    previous: float = 0

class AccountPatrimonyItem(SQLModel):
    """Uma conta no patrimônio do mês (saldo calculado, ver dominio/contas.py)."""

    account_id: int
    name: str
    type: str
    restricted: bool
    archived: bool = False
    balance: float | None = None
    quality: str
    observed_at: dt.datetime | None = None


class AssetSummary(SQLModel):
    year: int
    month: int
    items: list[AssetSummaryItem]
    # Chaveado pela classe: checking, fixed_income, equity, cripto...
    by_class: dict[str, AssetClassTotal]
    assets: float = 0
    liabilities: float = 0
    net_worth: float = 0
    previous_net_worth: float = 0
    # O que ficou FORA dos totais por estar desatualizado (último saldo
    # conhecido de cada um), pra tela dizer quanto e quantos.
    stale_count: int = 0
    stale_assets: float = 0
    stale_liabilities: float = 0
    # Contas financeiras: entram no patrimônio líquido (net_worth), não em
    # `assets` — que continua sendo a soma dos ativos, como sempre foi.
    accounts: list[AccountPatrimonyItem] = []
    accounts_total: float = 0
    previous_accounts_total: float = 0
    # Variação do mês sem cadastro (`new_total`); nula com ativo desatualizado.
    variation: float | None = None
    new_total: float = 0


# ===========================================================================
# Planejamento
# ===========================================================================
#
# Quatro coisas diferentes, que este bloco existe para não misturar:
#
#   realizado   o dinheiro que entrou ou saiu — continua sendo `Transaction`
#               (com `amount_paid`), parcela de cartão e `InvoicePayment`.
#   compromisso o que vai ser pago (ou recebido): `Commitment`. Não é
#               lançamento; vira um quando recebe baixa.
#   reserva     dinheiro que existe e já tem destino: `Provision`. Não sai do
#               patrimônio — só deixa de estar livre.
#   simulação   o que aconteceria SE: `Scenario`. Nunca toca no resto.
#
# O cartão não ganha nada aqui: as parcelas futuras já estão nas faturas, e o
# planejamento as lê de lá. Um compromisso por parcela de cartão seria o mesmo
# dinheiro em dois lugares.


# Teto de ocorrências de um compromisso parcelado. Não é regra de banco nenhum:
# 480 meses cobrem um financiamento imobiliário de 40 anos, e o teto impede que
# um dedo errado gere um cronograma de dez mil linhas na tela.
MAX_OCORRENCIAS = 480


class CommitmentBase(SQLModel):
    expense_class: ExpenseClass | None = Field(default=None, sa_type=_classe_despesa())
    """O que define um compromisso. O cronograma sai daqui, calculado."""

    description: str
    # A categoria decide a DIREÇÃO: despesa é algo a pagar (financiamento,
    # academia), receita é algo a receber (o salário que cai todo dia 5).
    # Investimento não entra — guardar dinheiro é reserva, não compromisso.
    category_id: int = Field(foreign_key="categories.id")
    # O valor de CADA ocorrência. O total é consequência, não entrada: no
    # financiamento, 48 × 618,08 não é o principal (há juros, tarifa, seguro),
    # então "valor total" só existe como informação separada, abaixo.
    amount: float
    # A primeira ocorrência. As seguintes andam `interval_months` por vez, no
    # mesmo dia — achatado no fim do mês curto, como o cartão.
    first_due: dt.date
    # Quantas ocorrências. Nulo = recorrente, sem número fechado (academia):
    # ela vai até `end_date`, ou até alguém encerrar.
    installments: int | None = Field(default=None, ge=1, le=MAX_OCORRENCIAS)
    interval_months: int = Field(default=1, ge=1, le=12)
    end_date: dt.date | None = None
    # Confirmado (contrato assinado, valor certo) ou estimado (proteção ainda
    # não contratada, conta que varia). A tela não soma os dois como se
    # tivessem o mesmo grau de certeza sem dizer isso.
    confirmed: bool = True
    # Só em despesa, como no lançamento. Copiada pra cada baixa.
    finalidade: Finalidade | None = None
    # Idem: a parcela do financiamento é FINANCIAL, e cada baixa nasce assim.
    nature: TransactionNature | None = Field(default=None, sa_type=_natureza())

    # ---------- Só informação ----------
    # Nenhum destes entra em conta nenhuma. "Valor financiado R$ 13.990" e
    # "entrada R$ 7.000" ajudam a reconhecer o contrato; somá-los a qualquer
    # coisa duplicaria o que já está nas parcelas e no lançamento da entrada.
    institution: str | None = None
    total_amount: float | None = None
    down_payment: float | None = None
    # "Pix", "boleto", "débito automático". Texto e não enum: a pergunta é só
    # "como você costuma pagar isso", e a baixa sempre vira saída à vista.
    payment_hint: str | None = None
    note: str | None = None


class Commitment(CommitmentBase, table=True):
    """Compromisso fora do cartão: financiamento, parcelado direto, recorrência.

    Uma tabela só pros três porque são a mesma coisa vista de perto — uma
    sequência de vencimentos com um valor. O que muda é se a sequência tem fim
    (`installments`) ou não.

    O cronograma NÃO é gravado. As 48 parcelas da Hunter saem de (primeira
    data, quantidade, intervalo) toda vez que alguém pede, pelo mesmo motivo da
    fatura não guardar total: duas fontes pro mesmo número começam iguais e
    terminam diferentes. O que se grava é só o que é decisão de alguém: a baixa
    (no lançamento), a dispensa (`CommitmentSkip`) e o cancelamento.
    """

    __tablename__ = "commitments"
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)
    # A partir desta data, o que não foi pago está cancelado. O que venceu
    # ANTES continua devido: cancelar o contrato em dezembro não apaga a
    # mensalidade de novembro que ficou em aberto.
    cancelled_on: dt.date | None = None
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )


class CommitmentCreate(CommitmentBase):
    pass


class CommitmentUpdate(SQLModel):
    expense_class: ExpenseClass | None = None
    description: str | None = None
    category_id: int | None = None
    amount: float | None = None
    first_due: dt.date | None = None
    installments: int | None = Field(default=None, ge=1, le=MAX_OCORRENCIAS)
    interval_months: int | None = Field(default=None, ge=1, le=12)
    end_date: dt.date | None = None
    confirmed: bool | None = None
    finalidade: Finalidade | None = None
    nature: TransactionNature | None = None
    institution: str | None = None
    total_amount: float | None = None
    down_payment: float | None = None
    payment_hint: str | None = None
    note: str | None = None
    cancelled_on: dt.date | None = None


class CommitmentSkip(SQLModel, table=True):
    """Uma ocorrência que não vai ser paga — e não porque foi esquecida.

    A academia que não cobrou dezembro, a parcela renegociada. Sem isto, o mês
    que passou sem baixa viraria "vencido" pra sempre, e a única saída seria
    inventar um lançamento de R$ 0. Dispensar é dizer, explicitamente, que
    aquela não conta.
    """

    __tablename__ = "commitment_skips"
    __table_args__ = (
        UniqueConstraint("commitment_id", "number", name="uq_commitment_skip"),
    )
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)
    commitment_id: int = Field(foreign_key="commitments.id", index=True)
    number: int = Field(ge=1)
    note: str | None = None
    # Abatimento contratual encerra a obrigação sem dinheiro sair da conta.
    # Nulo nas dispensas comuns e pausas antigas; não cria Transaction.
    abated_on: dt.date | None = None


class OccurrenceStatus(str, Enum):
    """Calculado, nunca gravado. A passagem do tempo não paga nada."""

    PENDENTE = "pendente"
    VENCIDA = "vencida"
    PAGA = "paga"
    DISPENSADA = "dispensada"
    ABATIDA = "abatida"
    CANCELADA = "cancelada"
    # Entrada recorrente que já está num lançamento só PREVISTO (o "720 em
    # 15/10" lançado à mão): não conta de novo — quem conta é o lançamento.
    PREVISTA = "prevista"


class OccurrenceRead(SQLModel):
    number: int
    due_date: dt.date
    amount: float
    status: OccurrenceStatus
    # "3/48" em parcelado; nulo em recorrência, que se lê pelo mês.
    label: str | None = None
    transaction_id: int | None = None
    paid_amount: float | None = None
    paid_date: dt.date | None = None
    # Quanto das reservas está apontado pra esta ocorrência.
    provisioned: float = 0
    skip_note: str | None = None
    abated_on: dt.date | None = None
    # O lançamento foi reconhecido (entrada da mesma categoria perto do
    # vencimento), não vinculado à mão. Ver `planejamento.casar_entradas`.
    matched: bool = False


class CommitmentRead(CommitmentBase):
    id: int
    cancelled_on: dt.date | None = None
    kind: str  # "parcelado" | "recorrente"
    direction: str  # "saida" | "entrada"
    category_name: str
    color: str
    icon: str
    status: str  # "ativo" | "quitado" | "encerrado" | "cancelado"
    paid_count: int = 0
    skipped_count: int = 0
    abated_count: int = 0
    overdue_count: int = 0
    overdue_amount: float = 0
    # Nulos em recorrência sem fim: não existe "faltam" pra o que não acaba.
    total_count: int | None = None
    remaining_count: int | None = None
    # Soma NOMINAL das ocorrências que faltam. Não é saldo devedor: o banco
    # desconta juros na quitação antecipada, e o app não sabe quanto.
    remaining_nominal: float | None = None
    next: OccurrenceRead | None = None
    # Última ocorrência futura dispensada por pausa ("pausada até dez/2026").
    paused_until: dt.date | None = None


class CommitmentDetail(CommitmentRead):
    schedule: list[OccurrenceRead] = []


class PagarOcorrencia(SQLModel):
    """A baixa: vira um lançamento realizado, já vinculado."""

    date: dt.date | None = None
    # Sem valor, o previsto. Pode ser diferente — juros de atraso, desconto.
    amount: float | None = None
    note: str | None = None
    # De onde saiu ("Paguei") ou onde entrou ("Recebi"). Nulo = não informada.
    account_id: int | None = None
    occurred_at: dt.datetime | None = None


class VincularLancamento(SQLModel):
    transaction_id: int


class DispensarOcorrencia(SQLModel):
    note: str | None = None


class AbaterOcorrencia(SQLModel):
    date: dt.date
    note: str | None = None


class PausarRecorrencia(SQLModel):
    """Pausa até o fim do mês de `ate`: as ocorrências em aberto de hoje até lá
    viram dispensas com a nota "Pausa". Retomar desfaz só as futuras."""

    ate: dt.date


# ---------- Reserva ----------


class ProvisionBase(SQLModel):
    description: str
    amount: float
    # Desde quando o dinheiro está separado. Antes disso ele era livre.
    created_on: dt.date
    # Opcional: a ocorrência pra qual o dinheiro foi separado ("a parcela de
    # novembro da Hunter"). Quando ela é paga, a reserva se cumpre sozinha.
    commitment_id: int | None = Field(default=None, foreign_key="commitments.id", index=True)
    commitment_no: int | None = None
    # Pra objetivo sem compromisso ("documentação em dezembro"): só
    # informação, a reserva continua até ser liberada.
    target_date: dt.date | None = None
    note: str | None = None


class Provision(ProvisionBase, table=True):
    """Dinheiro que existe e já tem destino.

    Não é despesa e não sai do patrimônio: o R$ 618,08 separado em outubro pra
    parcela de novembro continua na conta até novembro. O que ele muda é o
    "disponível pra decidir". Por isso reserva nunca vira lançamento — quem tira
    dinheiro da conta é a baixa do compromisso, uma vez só.

    Ativa, cumprida e liberada são derivadas. Gravado só `released_on`: o dia em
    que o dono disse "não preciso mais separar isso".
    """

    __tablename__ = "provisions"
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)
    released_on: dt.date | None = None
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )


class ProvisionCreate(SQLModel):
    description: str | None = None
    amount: float
    # Sem data, hoje.
    created_on: dt.date | None = None
    commitment_id: int | None = None
    commitment_no: int | None = None
    target_date: dt.date | None = None
    note: str | None = None


class ProvisionUpdate(SQLModel):
    description: str | None = None
    amount: float | None = None
    created_on: dt.date | None = None
    target_date: dt.date | None = None
    note: str | None = None
    released_on: dt.date | None = None


class ProvisionRead(ProvisionBase):
    id: int
    released_on: dt.date | None = None
    status: str  # "ativa" | "cumprida" | "liberada"
    commitment_description: str | None = None
    occurrence_label: str | None = None
    occurrence_due: dt.date | None = None


# ---------- Cenário ----------
#
# Os enums daqui pra baixo vão pro banco como VARCHAR, não como tipo nativo do
# Postgres. Tipo nativo novo é um `CREATE TYPE` que o `op.create_table` do
# Alembic dispara sem conferir se já existe — e enum já quase quebrou produção
# duas vezes sem a suíte perceber (ver 0004). Texto com o NOME do membro, como
# os outros enums, e nenhuma DDL a mais.


def _enum_texto(classe: type[Enum], tamanho: int = 16):
    return sa.Enum(classe, native_enum=False, length=tamanho)


class ScenarioItemKind(str, Enum):
    ENTRADA = "entrada"
    SAIDA = "saida"
    RESERVA = "reserva"


class Scenario(SQLModel, table=True):
    """Uma hipótese com nome: "Viagem", "Amortizar Hunter", "Outubro apertado".

    Mora em tabela própria e não toca em nenhuma outra. Apagar um cenário
    apaga os itens dele e mais nada — é a garantia de que simular não mexe no
    dinheiro de verdade.
    """

    __tablename__ = "scenarios"
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)
    name: str
    note: str | None = None
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )


class ScenarioItemBase(SQLModel):
    kind: ScenarioItemKind = Field(sa_type=_enum_texto(ScenarioItemKind))
    description: str
    amount: float
    # O dia em que a hipótese acontece. O mês dela é o que importa.
    date: dt.date
    # "Assumir uma parcela nova de 10x" = a mesma saída por 10 meses.
    repeat_months: int = Field(default=1, ge=1, le=60)
    # Nulo: um item novo, que só existe no cenário. Preenchido: muda um item
    # REAL só dentro do cenário — "compromisso:12:3", "fatura:29",
    # "lancamento:701", "reserva:4" —, e `amount` passa a ser o valor dele
    # aqui (zero = some do cenário). É assim que se simula cancelar um gasto
    # sem cancelar nada.
    ref: str | None = None


class ScenarioItem(ScenarioItemBase, table=True):
    __tablename__ = "scenario_items"
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)
    scenario_id: int = Field(foreign_key="scenarios.id", index=True)


class ScenarioItemCreate(ScenarioItemBase):
    pass


class ScenarioItemUpdate(SQLModel):
    kind: ScenarioItemKind | None = None
    description: str | None = None
    amount: float | None = None
    date: dt.date | None = None
    repeat_months: int | None = Field(default=None, ge=1, le=60)


class ScenarioCreate(SQLModel):
    name: str
    note: str | None = None


class ScenarioUpdate(SQLModel):
    name: str | None = None
    note: str | None = None


class ScenarioRead(SQLModel):
    id: int
    name: str
    note: str | None = None
    created_at: dt.datetime
    items: list[ScenarioItem] = []


# ---------- Conferência ----------


class ReconciliationKind(str, Enum):
    """O que o candidato parece ser — decide as ações que a tela oferece."""

    ENTRADA = "entrada"
    SAIDA = "saida"
    OBRIGACAO = "obrigacao"
    RESERVA = "reserva"
    # Um saldo observado ("R$ 8.393 em 08/10"). Nunca vira lançamento.
    SALDO = "saldo"
    OUTRO = "outro"


class ReconciliationStatus(str, Enum):
    PENDENTE = "pendente"
    CONFIRMAR = "confirmar"
    RESOLVIDO = "resolvido"
    IGNORADO = "ignorado"


class ReconciliationItemBase(SQLModel):
    year: int = Field(ge=1900, le=2999)
    month: int = Field(ge=1, le=12)
    description: str
    amount: float | None = None
    date: dt.date | None = None
    kind: ReconciliationKind = Field(
        default=ReconciliationKind.OUTRO, sa_type=_enum_texto(ReconciliationKind)
    )
    # O que se sabe e o que falta saber, em texto de gente: "Pago, Pix
    # 10/10 15:23" e "de qual conta saiu?".
    suggestion: str | None = None
    question: str | None = None
    category_hint: str | None = None
    # Dados pra pré-preencher o formulário de criação (parcelas, 1ª data,
    # instituição). Só sugestão: quem cria é o dono, revisando.
    prefill: dict[str, Any] | None = Field(default=None, sa_type=sa.JSON)
    note: str | None = None


class ReconciliationItem(ReconciliationItemBase, table=True):
    """Um item da conferência de um mês: algo que talvez precise virar dado.

    É lista de tarefas, não dinheiro. Nenhum número daqui entra em saldo,
    gasto ou planejamento — é justamente o lugar onde o incerto espera a
    confirmação, em vez de entrar no mês como se fosse fato.

    Os vínculos (`transaction_id`, `commitment_id`, `provision_id`) são de
    propósito SEM chave estrangeira: a anotação "isto é aquele lançamento" não
    pode impedir alguém de apagar o lançamento. Se ele sumir, a tela mostra o
    item como pendente de novo.
    """

    __tablename__ = "reconciliation_items"
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)
    status: ReconciliationStatus = Field(
        default=ReconciliationStatus.PENDENTE, sa_type=_enum_texto(ReconciliationStatus)
    )
    transaction_id: int | None = None
    commitment_id: int | None = None
    provision_id: int | None = None
    # "arquivo" quando veio de um arquivo importado, "manual" quando foi
    # digitado na tela. Só pra a tela saber de onde a pergunta veio.
    source: str = "manual"
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )


class ReconciliationItemCreate(ReconciliationItemBase):
    pass


class ReconciliationItemUpdate(SQLModel):
    description: str | None = None
    amount: float | None = None
    date: dt.date | None = None
    kind: ReconciliationKind | None = None
    status: ReconciliationStatus | None = None
    suggestion: str | None = None
    question: str | None = None
    category_hint: str | None = None
    note: str | None = None


# ---------------------------------------------------------------------------
# Contas financeiras (Foundation V3)
# ---------------------------------------------------------------------------
#
# Conta = onde existe dinheiro líquido (Nubank, Mercado Pago, carteira, vale).
# Ativo = investimento ou patrimônio (caixinha, CDB, ações, moto). Um não finge
# ser o outro: o saldo da conta é o último saldo observado + os movimentos
# conhecidos daquela conta depois dele (app/dominio/contas.py).


class AccountType(str, Enum):
    CHECKING = "checking"  # conta corrente
    PAYMENT = "payment"  # conta de pagamento (carteira digital)
    CASH = "cash"  # dinheiro em espécie
    BENEFIT = "benefit"  # benefício de uso restrito (vale-transporte)
    # Quebra-galho temporário: o total é conhecido, a divisão por conta não.
    # Existe até alguém distribuir (POST /accounts/{id}/distribuir).
    RECONCILIATION = "reconciliation"


class SnapshotSource(str, Enum):
    MANUAL = "manual"  # alguém olhou o app do banco e digitou
    MIGRATION = "migration"  # veio de um dado anterior às contas
    RECONCILIATION = "reconciliation"  # distribuição do saldo agregado


class FinancialAccountBase(SQLModel):
    name: str
    institution: str | None = None
    type: AccountType = Field(sa_type=_enum_texto(AccountType))
    currency: str = "BRL"
    # Entra no "quanto tenho agora" do planejamento.
    include_in_planning: bool = True
    # Dinheiro com destino fixo (vale-transporte): conta no patrimônio, nunca
    # no dinheiro livre.
    restricted: bool = False


class FinancialAccount(FinancialAccountBase, table=True):
    __tablename__ = "financial_accounts"
    # (user_id, id) único: é o alvo das chaves estrangeiras compostas que
    # garantem, no banco, que saldo, transferência e lançamento apontam pra uma
    # conta do MESMO dono.
    __table_args__ = (sa.UniqueConstraint("user_id", "id", name="uq_financial_accounts_user_id"),)
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)
    archived: bool = False
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))


class FinancialAccountCreate(FinancialAccountBase):
    include_in_planning: bool | None = None  # nulo = padrão do tipo
    restricted: bool | None = None


class FinancialAccountUpdate(SQLModel):
    name: str | None = None
    institution: str | None = None
    type: AccountType | None = None
    include_in_planning: bool | None = None
    restricted: bool | None = None
    archived: bool | None = None


class AccountBalanceSnapshot(SQLModel, table=True):
    """"Observei este saldo neste instante." Não é lançamento.

    Com hora (`observed_at`, com fuso): um Pix das 14h é claramente posterior a
    um saldo lido às 10h do mesmo dia.
    """

    __tablename__ = "account_balance_snapshots"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["user_id", "account_id"],
            ["financial_accounts.user_id", "financial_accounts.id"],
            name="fk_account_balance_snapshots_account",
            ondelete="CASCADE",
        ),
        sa.Index("ix_account_balance_snapshots_account", "account_id", "observed_at"),
    )
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)
    account_id: int
    observed_at: dt.datetime = Field(sa_type=sa.DateTime(timezone=True))
    balance: float
    source: SnapshotSource = Field(default=SnapshotSource.MANUAL, sa_type=_enum_texto(SnapshotSource))
    note: str | None = None
    # A diferença entre o observado e o calculado que alguém ACEITOU como
    # ajuste de conferência. Nunca vira receita nem despesa; sem aceite, a
    # diferença é pendência do mês.
    accepted_difference: float | None = None
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))


class Transfer(SQLModel, table=True):
    """Dinheiro mudando de conta. Não é receita, não é despesa, não mexe no
    patrimônio — uma linha só, pra ida e volta nunca se perderem uma da outra."""

    __tablename__ = "transfers"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["user_id", "from_account_id"],
            ["financial_accounts.user_id", "financial_accounts.id"],
            name="fk_transfers_from_account",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "to_account_id"],
            ["financial_accounts.user_id", "financial_accounts.id"],
            name="fk_transfers_to_account",
        ),
        sa.CheckConstraint("from_account_id <> to_account_id", name="ck_transfers_contas_diferentes"),
        sa.CheckConstraint("amount > 0", name="ck_transfers_valor_positivo"),
        sa.Index("ix_transfers_user_date", "user_id", "date"),
    )
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)
    from_account_id: int
    to_account_id: int
    amount: float
    date: dt.date
    occurred_at: dt.datetime | None = Field(default=None, sa_type=sa.DateTime(timezone=True))
    description: str | None = None
    note: str | None = None
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))


class TransferCreate(SQLModel):
    from_account_id: int
    to_account_id: int
    amount: float
    date: dt.date
    occurred_at: dt.datetime | None = None
    description: str | None = None
    note: str | None = None


class AuditEvent(SQLModel, table=True):
    """Rastro mínimo do que mexeu em dinheiro fora do fluxo comum.

    Conferência (aceitar diferença, distribuir saldo agregado), transferências,
    movimentos de investimento, scripts administrativos e migração de dados.
    Não registra navegação nem edição de texto, e `details` nunca leva senha,
    token ou segredo (app/dominio/auditoria.py filtra).
    """

    __tablename__ = "audit_events"
    __table_args__ = (sa.Index("ix_audit_events_user_created", "user_id", "created_at"),)
    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None = Field(default=None, foreign_key="users.id")
    # "api:<email>", "script:<nome>", "migracao:<revisão>".
    actor: str
    action: str
    entity_type: str | None = None
    entity_id: int | None = None
    details: dict[str, Any] | None = Field(default=None, sa_type=sa.JSON)
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))


# ---------------------------------------------------------------------------
# Movimentos de investimento (Foundation V3)
# ---------------------------------------------------------------------------


class InvestmentMovementType(str, Enum):
    # Dinheiro sai da conta e entra no ativo. Não é gasto nem perda: é alocação.
    CONTRIBUTION = "contribution"
    # Dinheiro sai do ativo e volta pra conta. Não é receita nem rendimento.
    REDEMPTION = "redemption"
    # Principal que entra no ativo SEM passar pelo caixa (ex.: saldo que já
    # existia e não estava registrado). Conta como aporte no rendimento.
    ADJUSTMENT = "adjustment"


class InvestmentMovementBase(SQLModel):
    asset_id: int
    type: InvestmentMovementType = Field(sa_type=_enum_texto(InvestmentMovementType))
    amount: float
    date: dt.date
    account_id: int | None = None
    note: str | None = None


class InvestmentMovement(InvestmentMovementBase, table=True):
    """A semântica de um aporte, resgate ou ajuste: qual ativo, qual conta.

    O lado CAIXA continua sendo o lançamento de categoria investimento
    (`transaction_id`): é ele que entra no "investido" e no saldo do mês, como
    sempre. Um lançamento representa no máximo um movimento (índice único), e
    apagar o lançamento leva o movimento junto (cascade).
    """

    __tablename__ = "investment_movements"
    __table_args__ = (
        sa.ForeignKeyConstraint(["user_id", "asset_id"], ["assets.user_id", "assets.id"],
                                name="fk_investment_movements_asset"),
        sa.ForeignKeyConstraint(["user_id", "account_id"],
                                ["financial_accounts.user_id", "financial_accounts.id"],
                                name="fk_investment_movements_account"),
        sa.ForeignKeyConstraint(["user_id", "transaction_id"], ["transactions.user_id", "transactions.id"],
                                name="fk_investment_movements_transaction", ondelete="CASCADE"),
        sa.CheckConstraint("amount > 0", name="ck_investment_movements_valor_positivo"),
        sa.Index("uq_investment_movements_transaction", "transaction_id", unique=True),
        sa.Index("ix_investment_movements_asset_date", "asset_id", "date"),
    )
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)
    transaction_id: int | None = None
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))


class InvestmentMovementCreate(InvestmentMovementBase):
    # Ligar a um lançamento que já existe (o aporte de 06/10, por exemplo)...
    transaction_id: int | None = None
    # ...ou criar o lado caixa agora: categoria de investimento obrigatória.
    category_id: int | None = None
    description: str | None = None
    occurred_at: dt.datetime | None = None


class InvestmentPlanData(SQLModel):
    type: InvestmentMovementType
    amount: float = Field(gt=0, le=999999999)
    date: dt.date
    asset_id: int | None = None
    account_id: int | None = None
    category_id: int | None = None
    description: str = Field(default="", max_length=120)


class InvestmentPlan(SQLModel, table=True):
    """Intenção sem efeito financeiro. Só confirmar cria movimento real."""
    __tablename__ = "investment_plans"
    __table_args__ = (
        sa.ForeignKeyConstraint(["user_id", "asset_id"], ["assets.user_id", "assets.id"]),
        sa.ForeignKeyConstraint(["user_id", "account_id"], ["financial_accounts.user_id", "financial_accounts.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.CheckConstraint("amount > 0", name="ck_investment_plans_amount"),
        sa.CheckConstraint("status IN ('planned', 'completed', 'cancelled')", name="ck_investment_plans_status"),
        sa.CheckConstraint("type IN ('CONTRIBUTION', 'REDEMPTION')", name="ck_investment_plans_type"),
        sa.Index("ix_investment_plans_user_date", "user_id", "date"),
        sa.Index("uq_investment_plans_movement", "movement_id", unique=True),
    )
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = dono()
    type: InvestmentMovementType = Field(sa_type=_enum_texto(InvestmentMovementType))
    amount: float
    date: dt.date
    asset_id: int | None = None
    account_id: int | None = None
    category_id: int | None = None
    description: str = ""
    status: str = "planned"
    # Identificador de auditoria preservado mesmo se o lançamento for excluído.
    movement_id: int | None = None
    balance_pending: bool = False
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))


class InvestmentPlanConfirm(SQLModel):
    date: dt.date
