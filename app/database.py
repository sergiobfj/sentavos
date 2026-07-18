from dotenv import load_dotenv
import os
from app.models import Category, Transaction
from sqlmodel import create_engine, SQLModel

load_dotenv()

DATABASE_URL =  os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL, echo=True)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


if __name__ == "__main__":
    create_db_and_tables()
