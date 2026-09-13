import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.auth import require_user
from app.database import get_session
from app.main import app
from app.security import zerar_limites


@pytest.fixture(autouse=True)
def limites_zerados():
    """O rate limit conta por IP, e no TestClient todo teste vem do mesmo IP.

    Sem zerar, a suíte de auth — que provoca 401 de propósito — gastaria a cota
    de falhas e os testes seguintes receberiam 429 no lugar do status que estão
    verificando. Autouse porque a alternativa (lembrar de pedir a fixture) falha
    exatamente no teste novo que alguém escrever daqui a seis meses.
    """
    zerar_limites()
    yield
    zerar_limites()

@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
         "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # O SQLite ignora foreign key por padrão, o Postgres não. Sem este PRAGMA o
    # teste passa em delete que o banco de produção recusa — foi assim que um
    # delete na ordem errada passou batido.
    @event.listens_for(engine, "connect")
    def enforce_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

@pytest.fixture(name="client")
def client_fixture(session):
    """Cliente já autenticado — é o que a maioria dos testes quer exercitar."""
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    # A auth em si é testada pelo anon_client; aqui ela sai da frente pra o
    # teste falar sobre a regra de negócio, não sobre token.
    app.dependency_overrides[require_user] = lambda: "usuario-de-teste"
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture(name="anon_client")
def anon_client_fixture(session):
    """Cliente sem token, com a auth de verdade ligada.

    Existe pra provar que as rotas estão fechadas. Sem ele, o override do
    client faria a suíte passar mesmo se a proteção caísse do router.
    """
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()