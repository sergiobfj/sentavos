import datetime as dt
from sqlmodel import SQLModel, Field, UniqueConstraint
from enum import Enum


class CategoryType(str, Enum):
    EXPENSE = "expense"
    INCOME = "income"
    INVESTMENT = "investment"

class CategoryBase(SQLModel):
    name: str
    type: CategoryType
    color: str
    icon: str

class Category(CategoryBase, table=True):
    __tablename__ = "categories"
    id: int | None = Field(default=None, primary_key=True)

class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(SQLModel):
    name: str | None = None
    type: CategoryType | None = None
    color: str | None = None
    icon: str | None = None

class TransactionBase(SQLModel):
    date: dt.date
    description: str
    amount_planned: float | None = None
    amount_paid: float | None = None
    note: str | None = None
    category_id: int = Field(foreign_key="categories.id")

class Transaction(TransactionBase, table=True):
    __tablename__ = "transactions"
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
        UniqueConstraint("category_id", "year", "month", name="uq_budget_category_period"),
    )
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
    budget_id: int | None = None
    budgeted: float = 0
    planned: float = 0
    paid: float = 0

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

class Asset(AssetBase, table=True):
    __tablename__ = "assets"
    id: int | None = Field(default=None, primary_key=True)

class AssetCreate(AssetBase):
    pass

class AssetUpdate(SQLModel):
    name: str | None = None
    asset_class: AssetClass | None = None
    note: str | None = None


# O saldo de um ativo num mês. Preenchido à mão — sem cotação automática no v1.
class AssetSnapshotBase(SQLModel):
    asset_id: int = Field(foreign_key="assets.id")
    year: int = Field(ge=1900, le=2999)
    month: int = Field(ge=1, le=12)
    value: float

class AssetSnapshot(AssetSnapshotBase, table=True):
    __tablename__ = "asset_snapshots"
    __table_args__ = (
        UniqueConstraint("asset_id", "year", "month", name="uq_snapshot_asset_period"),
    )
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
