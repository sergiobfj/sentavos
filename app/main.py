from contextlib import asynccontextmanager
import os
import datetime as dt

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

from app.database import create_db_and_tables, get_session
from app.models import (
    Category,
    CategoryCreate,
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
        elif month == 12:
            start, end = dt.date(year, 12, 1), dt.date(year + 1, 1, 1)
        else:
            start, end = dt.date(year, month, 1), dt.date(year, month + 1, 1)
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
