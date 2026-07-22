from fastapi import FastAPI, Depends, HTTPException
from sqlmodel import Session, select
from app.models import Category, CategoryCreate, Transaction, TransactionCreate, TransactionUpdate
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

@app.delete("/transaction/{transaction_id}")
def delete_transaction(transaction_id: int, session: Session = Depends(get_session)):
    transaction = session.get(Transaction, transaction_id)

    if not transaction:
        raise HTTPException(status_code = 404, detail="Transaction not found")

    session.delete(transaction)
    session.commit()

    return{
        "message": "Transação excluída."
    }

@app.patch("/transaction/{transaction_id}")
def update_transaction(transaction_id: int, transaction_data: TransactionUpdate, session: Session = Depends(get_session)):
    transaction = session.get(Transaction, transaction_id)

    if not transaction:
        raise HTTPException(status_code = 404, detail="Transaction not found")

    update_data = transaction_data.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        setattr(transaction, key, value)

    session.add(transaction)
    session.commit()
    session.refresh(transaction)

    return transaction


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

@app.delete("/category/{category_id}")
def delete_category(category_id: int, session: Session = Depends(get_session)):
    category = session.get(Category, category_id)

    if not category:
        raise HTTPException(status_code = 404, detail="Category not found")

    session.delete(category)
    session.commit()

    return{
        "message": "Categoria excluída."
    }
