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
