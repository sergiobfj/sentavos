from fastapi import FastAPI, Depends
from sqlmodel import Session, select
from app.models import Category, CategoryCreate, Transaction, TransactionCreate
from app.database import get_session


app = FastAPI()

@app.get("/")
async def root():
    return {
        "message": "API do Sentavos no ar"
    }

@app.post("/transactions")
def create_transaction(transaction: TransactionCreate, session: Session = Depends(get_session)):
    db_transaction = Transaction.model_validate(transaction)
    session.add(db_transaction)
    session.commit()
    session.refresh(db_transaction)
    return db_transaction

@app.get("/transactions")
def list_transactions(session: Session = Depends(get_session)):
    transactions = session.exec(select(Transaction)).all()
    return transactions

@app.post("/category")
def create_category(category: CategoryCreate, session: Session = Depends(get_session)):
    db_category = Category.model_validate(category)
    session.add(db_category)
    session.commit()
    session.refresh(db_category)
    return db_category

@app.get("/category")
def list_categorys(session: Session = Depends(get_session)):
    categorys = session.exec(select(Category)).all()
    return categorys