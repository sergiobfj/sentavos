from datetime import date
from sqlmodel import SQLModel, Field
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

class TransactionBase(SQLModel):
    date: date
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