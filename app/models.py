import datetime as dt
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

class TransactionBase(SQLModel):
    date: dt.date
    description: str
    amount_planned: float | None = None
    amount_paid: float | None = None
    note: str | None = None
    category_id: int = Field(foreign_key="categories.id")

class Transaction(TransactionBase, table=True):
    __tablename__ = "transactions"
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)

class TransactionCreate(TransactionBase):
    pass

class TransactionUpdate(SQLModel):
    date: dt.date | None = None
    description: str | None = None
    amount_planned: float | None = None
    amount_paid: float | None = None
    note: str | None = None
    category_id: int | None = None


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

class BudgetSummary(SQLModel):
    year: int
    month: int
    items: list[BudgetSummaryItem]
    # Chaveado pelo tipo de categoria: expense, income, investment.
    totals: dict[str, BudgetSummaryTotals]


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

class Asset(AssetBase, table=True):
    __tablename__ = "assets"
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)

class AssetCreate(AssetBase):
    pass

class AssetUpdate(SQLModel):
    name: str | None = None
    asset_class: AssetClass | None = None
    note: str | None = None
    cdi_percent: float | None = None


# O saldo de um ativo num mês. Preenchido à mão — sem cotação automática no v1.
class AssetSnapshotBase(SQLModel):
    asset_id: int = Field(foreign_key="assets.id")
    year: int = Field(ge=1900, le=2999)
    month: int = Field(ge=1, le=12)
    value: float

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

class AssetClassTotal(SQLModel):
    value: float = 0
    previous: float = 0

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
