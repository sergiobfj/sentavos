from contextlib import asynccontextmanager
import os
import datetime as dt

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, func, select

from app.database import create_db_and_tables, get_session
from app.models import (
    Budget,
    BudgetCreate,
    BudgetSummary,
    BudgetSummaryItem,
    BudgetSummaryTotals,
    BudgetUpdate,
    Category,
    CategoryCreate,
    CategoryType,
    CategoryUpdate,
    Transaction,
    TransactionCreate,
    TransactionUpdate,
)



@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(lifespan=lifespan)

# Origens liberadas pro front. Em produção, sobrescreva via CORS_ORIGINS no .env.
cors_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def month_bounds(year: int, month: int) -> tuple[dt.date, dt.date]:
    """Intervalo semiaberto [start, end) do mês. Dezembro vira janeiro do ano seguinte."""
    start = dt.date(year, month, 1)
    end = dt.date(year + 1, 1, 1) if month == 12 else dt.date(year, month + 1, 1)
    return start, end


@app.get("/")
async def root():
    return {"message": "API do Sentavos no ar"}


@app.post("/transactions")
def create_transaction(transaction: TransactionCreate, session: Session = Depends(get_session)):
    category = session.get(Category, transaction.category_id)
    if not category:
        raise HTTPException(status_code=400, detail="Category not found")

    db_transaction = Transaction.model_validate(transaction)
    session.add(db_transaction)
    session.commit()
    session.refresh(db_transaction)
    return db_transaction


@app.get("/transactions")
def list_transactions(
    session: Session = Depends(get_session),
    year: int | None = Query(default=None, ge=1900, le=2999),
    month: int | None = Query(default=None, ge=1, le=12),
):
    if month is not None and year is None:
        raise HTTPException(status_code=400, detail="Informe o ano junto com o mês.")

    query = select(Transaction)

    if year is not None:
        if month is None:
            start, end = dt.date(year, 1, 1), dt.date(year + 1, 1, 1)
        else:
            start, end = month_bounds(year, month)
        query = query.where(Transaction.date >= start, Transaction.date < end)

    return session.exec(
        query.order_by(Transaction.date.desc(), Transaction.id.desc())
    ).all()


@app.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: int, session: Session = Depends(get_session)):
    transaction = session.get(Transaction, transaction_id)

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return transaction


@app.delete("/transactions/{transaction_id}")
def delete_transaction(transaction_id: int, session: Session = Depends(get_session)):
    transaction = session.get(Transaction, transaction_id)

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    session.delete(transaction)
    session.commit()

    return {"message": "Transação excluída."}


@app.patch("/transactions/{transaction_id}")
def update_transaction(
    transaction_id: int, transaction_data: TransactionUpdate, session: Session = Depends(get_session)
):
    transaction = session.get(Transaction, transaction_id)

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    update_data = transaction_data.model_dump(exclude_unset=True)

    if "category_id" in update_data:
        category = session.get(Category, update_data["category_id"])
        if not category:
            raise HTTPException(status_code=400, detail="Category not found")

    for key, value in update_data.items():
        setattr(transaction, key, value)

    session.add(transaction)
    session.commit()
    session.refresh(transaction)

    return transaction


@app.post("/categories")
def create_category(category: CategoryCreate, session: Session = Depends(get_session)):
    db_category = Category.model_validate(category)
    session.add(db_category)
    session.commit()
    session.refresh(db_category)
    return db_category


@app.get("/categories")
def list_categories(session: Session = Depends(get_session)):
    categories = session.exec(select(Category)).all()
    return categories


@app.get("/categories/{category_id}")
def get_category(category_id: int, session: Session = Depends(get_session)):
    category = session.get(Category, category_id)

    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    return category


@app.patch("/categories/{category_id}")
def update_category(
    category_id: int, category_data: CategoryUpdate, session: Session = Depends(get_session)
):
    category = session.get(Category, category_id)

    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    update_data = category_data.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        setattr(category, key, value)

    session.add(category)
    session.commit()
    session.refresh(category)

    return category


@app.delete("/categories/{category_id}")
def delete_category(category_id: int, session: Session = Depends(get_session)):
    category = session.get(Category, category_id)

    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    session.delete(category)
    session.commit()

    return {"message": "Categoria excluída."}


# Declarado antes de /budgets/{budget_id} pra "summary" não ser lido como id.
@app.get("/budgets/summary", response_model=BudgetSummary)
def get_budget_summary(
    year: int = Query(ge=1900, le=2999),
    month: int = Query(ge=1, le=12),
    session: Session = Depends(get_session),
):
    """Orçado x previsto x pago por categoria no mês.

    Devolve todas as categorias, inclusive as sem meta e sem lançamento, pra
    aba de Orçamento poder oferecer o campo de meta em qualquer linha.
    """
    start, end = month_bounds(year, month)

    movement = {
        category_id: (planned, paid)
        for category_id, planned, paid in session.exec(
            select(
                Transaction.category_id,
                func.coalesce(func.sum(Transaction.amount_planned), 0.0),
                func.coalesce(func.sum(Transaction.amount_paid), 0.0),
            )
            .where(Transaction.date >= start, Transaction.date < end)
            .group_by(Transaction.category_id)
        ).all()
    }

    metas = {
        budget.category_id: budget
        for budget in session.exec(
            select(Budget).where(Budget.year == year, Budget.month == month)
        ).all()
    }

    categories = session.exec(select(Category).order_by(Category.type, Category.name)).all()

    # Os três tipos sempre vêm nos totais, mesmo zerados, pra o front não
    # precisar checar chave faltando.
    totals = {tipo.value: BudgetSummaryTotals() for tipo in CategoryType}
    items = []

    for category in categories:
        planned, paid = movement.get(category.id, (0.0, 0.0))
        meta = metas.get(category.id)
        item = BudgetSummaryItem(
            category_id=category.id,
            category_name=category.name,
            category_type=category.type,
            color=category.color,
            icon=category.icon,
            budget_id=meta.id if meta else None,
            budgeted=meta.amount if meta else 0.0,
            planned=planned,
            paid=paid,
        )
        items.append(item)

        total = totals[CategoryType(category.type).value]
        total.budgeted += item.budgeted
        total.planned += item.planned
        total.paid += item.paid

    return BudgetSummary(year=year, month=month, items=items, totals=totals)


@app.put("/budgets")
def set_budget(budget: BudgetCreate, session: Session = Depends(get_session)):
    """Define a meta da categoria no mês. Idempotente: cria ou sobrescreve.

    É PUT em vez de POST porque a tela de Orçamento só sabe "categoria + mês +
    valor" — ela não tem id de meta pra escolher entre criar e editar.
    """
    category = session.get(Category, budget.category_id)
    if not category:
        raise HTTPException(status_code=400, detail="Category not found")

    db_budget = session.exec(
        select(Budget).where(
            Budget.category_id == budget.category_id,
            Budget.year == budget.year,
            Budget.month == budget.month,
        )
    ).first()

    if db_budget:
        db_budget.amount = budget.amount
    else:
        db_budget = Budget.model_validate(budget)

    session.add(db_budget)
    session.commit()
    session.refresh(db_budget)

    return db_budget


@app.get("/budgets")
def list_budgets(
    session: Session = Depends(get_session),
    year: int | None = Query(default=None, ge=1900, le=2999),
    month: int | None = Query(default=None, ge=1, le=12),
):
    if month is not None and year is None:
        raise HTTPException(status_code=400, detail="Informe o ano junto com o mês.")

    query = select(Budget)

    if year is not None:
        query = query.where(Budget.year == year)
    if month is not None:
        query = query.where(Budget.month == month)

    return session.exec(query.order_by(Budget.year, Budget.month, Budget.category_id)).all()


@app.patch("/budgets/{budget_id}")
def update_budget(
    budget_id: int, budget_data: BudgetUpdate, session: Session = Depends(get_session)
):
    budget = session.get(Budget, budget_id)

    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    for key, value in budget_data.model_dump(exclude_unset=True).items():
        setattr(budget, key, value)

    session.add(budget)
    session.commit()
    session.refresh(budget)

    return budget


@app.delete("/budgets/{budget_id}")
def delete_budget(budget_id: int, session: Session = Depends(get_session)):
    budget = session.get(Budget, budget_id)

    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    session.delete(budget)
    session.commit()

    return {"message": "Meta excluída."}
