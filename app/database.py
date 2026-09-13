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

# pool_pre_ping testa a conexão antes de entregá-la. Não é zelo genérico: o Neon
# suspende o compute quando o banco fica ocioso, e o Render free derruba o
# serviço no mesmo caso. Quando qualquer um dos dois volta, as conexões guardadas
# no pool já morreram — sem o ping, a primeira requisição depois da ociosidade
# estouraria com "server closed the connection unexpectedly" em vez de só
# reconectar. Com hospedagem que hiberna, isto deixa de ser opcional.
#
# O pool_recycle é a segunda linha: descarta conexão com mais de 5 minutos mesmo
# que ela pareça viva, porque nem toda queda é detectável pelo ping.
engine_options = {
    "echo": SQL_ECHO,
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

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
