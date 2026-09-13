import os

from dotenv import load_dotenv
from sqlalchemy.pool import NullPool
from sqlmodel import Session, SQLModel, create_engine

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Em produção a variável vem do host. Falhar aqui com mensagem clara é melhor
    # que deixar o create_engine estourar um erro que não diz o que faltou.
    raise RuntimeError("DATABASE_URL não configurada. Veja o .env.example.")

# echo=True loga todo SQL com os valores. Ótimo pra depurar, ruim em produção:
# enche o log do host e joga dado do usuário nele.
SQL_ECHO = os.getenv("SQL_ECHO", "").lower() in {"1", "true", "yes"}

engine_options = {"echo": SQL_ECHO, "pool_pre_ping": True}

# A porta 6543 é a convenção de pooler (pgBouncer em modo transaction). Manter um
# pool do SQLAlchemy em cima de outro pooler dá erro intermitente de conexão: o
# pgBouncer recicla a conexão por baixo e a que está guardada aqui já morreu.
# NullPool deixa o pooler cuidar disso, que é o trabalho dele.
#
# O Postgres do Railway atende na 5432 e não tem pooler na frente, então o
# caminho normal (pool do SQLAlchemy) é o que roda. A regra fica porque não custa
# nada e evita um bug obscuro se um dia entrar um pooler na jogada.
if ":6543" in DATABASE_URL:
    engine_options["poolclass"] = NullPool

engine = create_engine(DATABASE_URL, **engine_options)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session




if __name__ == "__main__":
    create_db_and_tables()
