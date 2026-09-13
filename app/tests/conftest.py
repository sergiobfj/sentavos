import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.auth import gerar_hash, require_user
from app.database import get_session
from app.main import app
from app.models import User
from app.security import zerar_limites

SEGREDO_DE_TESTE = "segredo-de-teste-com-tamanho-suficiente-pra-hs256"


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    """Config mínima pro app funcionar, igual em todo teste.

    O segredo entra por monkeypatch e não pelo .env da máquina: senão a suíte
    passaria ou falharia conforme o arquivo de quem rodou, que é pior do que
    falhar sempre.
    """
    monkeypatch.setenv("SENTAVOS_JWT_SECRET", SEGREDO_DE_TESTE)
    monkeypatch.delenv("SENTAVOS_TOKEN_EPOCH", raising=False)


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


@pytest.fixture(name="criar_usuario")
def criar_usuario_fixture(session):
    """Cria uma conta de verdade no banco de teste.

    Devolve o objeto User, que é o que as rotas recebem — assim o teste exercita
    o mesmo caminho da produção, incluindo o read_only.
    """
    def criar(email: str, nome: str, senha: str, read_only: bool = False) -> User:
        usuario = User(
            email=email.lower(), name=nome,
            password_hash=gerar_hash(senha), read_only=read_only,
        )
        session.add(usuario)
        session.commit()
        session.refresh(usuario)
        return usuario

    return criar


@pytest.fixture(name="cliente_de")
def cliente_de_fixture(session):
    """Cliente autenticado como um usuário específico.

    O override devolve o próprio objeto, pulando a verificação do token. O que
    se quer exercitar nos testes de isolamento é o filtro por dono, não a
    assinatura do JWT — essa tem arquivo próprio.
    """
    def para(usuario: User) -> TestClient:
        app.dependency_overrides[get_session] = lambda: session
        app.dependency_overrides[require_user] = lambda: usuario
        return TestClient(app)

    yield para
    app.dependency_overrides.clear()


@pytest.fixture(name="dono")
def dono_fixture(criar_usuario):
    """O usuário padrão dos testes de regra de negócio."""
    return criar_usuario("dono@exemplo.com", "Dono", "senha-do-dono-12345")


@pytest.fixture(name="client")
def client_fixture(session, cliente_de, dono):
    """Cliente já autenticado — é o que a maioria dos testes quer exercitar.

    A auth em si é testada pelo anon_client; aqui ela sai da frente pra o teste
    falar sobre a regra de negócio, não sobre token.
    """
    yield cliente_de(dono)
    app.dependency_overrides.clear()


@pytest.fixture(name="anon_client")
def anon_client_fixture(session):
    """Cliente sem token, com a auth de verdade ligada.

    Existe pra provar que as rotas estão fechadas. Sem ele, o override do
    client faria a suíte passar mesmo se a proteção caísse do router.
    """
    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
