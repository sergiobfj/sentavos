from contextlib import asynccontextmanager
import os
import re
import datetime as dt

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, SQLModel, and_, func, or_, select

from app.auth import ConfiguracaoIncompleta, autenticar, exigir_escrita, require_user
from app.cartao import limites_do_mes as month_bounds
from app.escopo import buscar, consulta, exigir
from app.faturas import enriquecer, resumo_de_caixa
from app.rendimento import rendimento_do_mes
from app.rotas_cartao import router_cartao
from app.rotas_relatorios import router_relatorios
from app.database import create_db_and_tables, get_session
from app.security import RateLimitMiddleware, SecurityHeadersMiddleware
from app.models import (
    Asset,
    AssetClass,
    AssetClassTotal,
    AssetCreate,
    AssetSnapshot,
    AssetSnapshotCreate,
    AssetSnapshotUpdate,
    AssetSummary,
    AssetSummaryItem,
    AssetUpdate,
    Budget,
    BudgetCreate,
    BudgetSummary,
    BudgetSummaryItem,
    BudgetSummaryTotals,
    BudgetUpdate,
    Category,
    CategoryCreate,
    CategoryRead,
    CategoryType,
    CategoryUpdate,
    Finalidade,
    PaymentMethod,
    Purchase,
    Transaction,
    TransactionCreate,
    TransactionUpdate,
    User,
    is_liability,
)



@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


# /docs e /openapi.json ficam desligados por padrão. Eles não expõem dado, mas
# entregam o mapa completo da API — toda rota, todo campo, todo formato — pra
# quem só tem a URL. Num app pessoal isso é só ajuda pra quem está sondando.
# Pra abrir num apuro: DOCS_ABERTOS=1 no host, e desligue depois.
DOCS_ABERTOS = os.getenv("DOCS_ABERTOS", "").lower() in {"1", "true", "yes"}

app = FastAPI(
    lifespan=lifespan,
    docs_url="/docs" if DOCS_ABERTOS else None,
    redoc_url="/redoc" if DOCS_ABERTOS else None,
    openapi_url="/openapi.json" if DOCS_ABERTOS else None,
)

# Ordem importa: o Starlette executa os middlewares na ordem inversa do
# add_middleware. Registrando rate limit por último, ele roda primeiro — e é o
# que se quer, porque quem estourou a cota deve ser recusado antes de gastar
# qualquer trabalho do servidor.
app.add_middleware(SecurityHeadersMiddleware)

# Origens liberadas pro front. Em produção, defina CORS_ORIGINS com o domínio da
# Vercel. O strip() não é firula: "a, b" com espaço depois da vírgula viraria a
# origem " b", que nunca casa com nada, e o navegador bloquearia tudo sem dizer
# por quê. É o tipo de erro que custa uma tarde.
cors_origins = [
    origem.strip()
    for origem in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000",
    ).split(",")
    if origem.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    # O front manda o token no cabeçalho Authorization, não em cookie. Sem
    # cookie, allow_credentials não serve pra nada aqui — e ligado ele afrouxa
    # o que o navegador permite a outra origem fazer. Fica desligado.
    allow_credentials=False,
    # Lista fechada em vez de "*": o que não está aqui é verbo que a API não
    # usa, e anunciar que aceita não ajuda ninguém além de quem sonda.
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)

app.add_middleware(RateLimitMiddleware)


# Toda rota de dados vive neste router, que exige token. Colar o Depends em cada
# endpoint seria pior: esquecer num deles abriria um buraco silencioso, e nenhum
# teste pegaria. Aqui, rota nova nasce protegida — dá trabalho expor sem querer.
router = APIRouter(dependencies=[Depends(require_user)])


def month_index(year: int, month: int) -> int:
    """Mês como número absoluto, pra comparar períodos sem cuidar de virada de ano."""
    return year * 12 + (month - 1)


def previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


# HEAD junto com GET: é a rota de healthcheck, e quem checa saúde costuma usar
# HEAD pra não baixar corpo à toa. O @app.get sozinho responderia 405 a eles —
# que o host lê como serviço caído, mesmo com tudo funcionando. Foi o que o
# Render fez na detecção de porta, e é o que um pinger externo faria depois.
@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    return {"message": "API do Sentavos no ar"}


# ---------- Login ----------
# Fora do `router` de propósito: é a única rota que não pode exigir token, já que
# é ela quem entrega o token. Continua protegida pelo rate limit, que conta as
# respostas 401 daqui na cota apertada de falhas.
class Credenciais(SQLModel):
    email: str
    senha: str


class TokenDeAcesso(SQLModel):
    access_token: str
    token_type: str = "bearer"


@app.post("/auth/login", response_model=TokenDeAcesso)
def login(credenciais: Credenciais, session: Session = Depends(get_session)):
    try:
        token = autenticar(credenciais.email, credenciais.senha, session)
    except ConfiguracaoIncompleta:
        # 500 e não 401: o problema é o servidor, e mandar o usuário tentar de
        # novo seria mentira — nenhuma senha funcionaria.
        raise HTTPException(
            status_code=500, detail="Autenticação não configurada no servidor."
        )
    return TokenDeAcesso(access_token=token)


@router.post("/transactions")
def create_transaction(transaction: TransactionCreate, session: Session = Depends(get_session),
    dono: User = Depends(require_user)):
    exigir_escrita(dono)
    category = buscar(session, Category, transaction.category_id, dono)
    if not category:
        raise HTTPException(status_code=400, detail="Category not found")

    # Compra no cartão não entra por aqui. Ela precisa de cartão, de parcelas e
    # da fatura que vai cobrá-la — coisas que este endpoint não pede e não sabe
    # montar. Deixar passar criaria um lançamento "no cartão" que não está em
    # fatura nenhuma: contaria como gasto e nunca viraria saída de caixa.
    if transaction.payment_method == PaymentMethod.CREDIT:
        raise HTTPException(
            status_code=400,
            detail="Compra no cartão se registra em /purchases, que gera as parcelas e a fatura.",
        )

    db_transaction = Transaction.model_validate(
        transaction,
        update={
            "user_id": dono.id,
            "finalidade": finalidade_efetiva(category, transaction.finalidade, padrao=True),
        },
    )
    session.add(db_transaction)
    session.commit()
    session.refresh(db_transaction)
    return db_transaction


@router.get("/transactions")
def list_transactions(
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
    year: int | None = Query(default=None, ge=1900, le=2999),
    month: int | None = Query(default=None, ge=1, le=12),
):
    if month is not None and year is None:
        raise HTTPException(status_code=400, detail="Informe o ano junto com o mês.")

    query = consulta(Transaction, dono)

    if year is not None:
        if month is None:
            start, end = dt.date(year, 1, 1), dt.date(year + 1, 1, 1)
        else:
            start, end = month_bounds(year, month)
        query = query.where(Transaction.date >= start, Transaction.date < end)

    # `enriquecer` junta cartão e "2 de 10" em duas consultas para a lista
    # inteira. A alternativa seria o navegador buscar a compra de cada parcela.
    return enriquecer(
        session,
        dono,
        session.exec(query.order_by(Transaction.date.desc(), Transaction.id.desc())).all(),
    )


@router.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: int, session: Session = Depends(get_session),
    dono: User = Depends(require_user)):
    transaction = exigir(session, Transaction, transaction_id, dono, "Transação")

    return enriquecer(session, dono, [transaction])[0]


# Parcela não é um lançamento solto: ela é uma das N faces de uma compra, e as N
# somam o valor dela. Apagar a 2 de 3 deixaria uma compra de R$ 900 valendo
# R$ 600 sem ninguém ter decidido isso; mudar o valor de uma faria a fatura
# divergir do total. As duas operações existem — na compra, onde a decisão tem
# o escopo certo.
def _recusar_parcela(transaction: Transaction, acao: str) -> None:
    if transaction.purchase_id is None:
        return
    de = (
        f"{transaction.installment_no} de" if transaction.installment_no else "uma parcela de"
    )
    raise HTTPException(
        status_code=409,
        detail=(
            f"Este lançamento é a parcela {de} uma compra no cartão. "
            f"Para {acao}, abra a compra — assim todas as parcelas andam juntas."
        ),
    )


@router.delete("/transactions/{transaction_id}")
def delete_transaction(transaction_id: int, session: Session = Depends(get_session),
    dono: User = Depends(require_user)):
    exigir_escrita(dono)
    transaction = exigir(session, Transaction, transaction_id, dono, "Transação")
    _recusar_parcela(transaction, "excluir")

    session.delete(transaction)
    session.commit()

    return {"message": "Transação excluída."}


@router.patch("/transactions/{transaction_id}")
def update_transaction(
    transaction_id: int, transaction_data: TransactionUpdate, session: Session = Depends(get_session),
    dono: User = Depends(require_user)
):
    exigir_escrita(dono)
    transaction = exigir(session, Transaction, transaction_id, dono, "Transação")
    _recusar_parcela(transaction, "editar")

    update_data = transaction_data.model_dump(exclude_unset=True)

    if "category_id" in update_data:
        category = exigir(session, Category, update_data["category_id"], dono, "Categoria")
        if not category:
            raise HTTPException(status_code=400, detail="Category not found")

    # Marcar "cartão" aqui deixaria o lançamento fora de qualquer fatura. A
    # conversão de verdade é POST /transactions/{id}/forma-de-pagamento, que
    # cria a compra e as parcelas.
    if update_data.get("payment_method") == PaymentMethod.CREDIT:
        raise HTTPException(
            status_code=400,
            detail=(
                "Para passar este lançamento pro cartão use "
                "/transactions/{id}/forma-de-pagamento — é ela que cria a compra e a fatura."
            ),
        )

    categoria_antes = buscar(session, Category, transaction.category_id, dono)

    for key, value in update_data.items():
        setattr(transaction, key, value)

    # A finalidade segue o tipo da categoria que o lançamento tem DEPOIS da
    # edição. Virou receita: sai (finalidade é dimensão de consumo). Virou
    # despesa agora, sem escolha: PESSOAL, o mesmo padrão da criação. Despesa
    # antiga editada só na descrição continua nula — responder por ela uma
    # pergunta que ninguém fez é o que a migração também se recusou a fazer.
    categoria = buscar(session, Category, transaction.category_id, dono)
    virou_despesa = (
        categoria is not None
        and categoria.type == CategoryType.EXPENSE
        and (categoria_antes is None or categoria_antes.type != CategoryType.EXPENSE)
    )
    transaction.finalidade = finalidade_efetiva(
        categoria,
        transaction.finalidade,
        padrao=virou_despesa and "finalidade" not in update_data,
    )

    session.add(transaction)
    session.commit()
    session.refresh(transaction)

    return enriquecer(session, dono, [transaction])[0]


def finalidade_efetiva(
    categoria: Category | None, escolhida: Finalidade | None, padrao: bool
) -> Finalidade | None:
    """A finalidade que o lançamento à vista grava de fato.

    Só despesa tem finalidade. Com `padrao`, a despesa sem escolha vira PESSOAL
    — é o caso de quem lança um PIX sem pensar nisso, que é quase sempre gasto
    próprio. Sem `padrao`, o nulo fica nulo.
    """
    if categoria is None or categoria.type != CategoryType.EXPENSE:
        return None
    if escolhida is None and padrao:
        return Finalidade.PESSOAL
    return escolhida


# ---------- Categorias: o que a API recusa ----------
# A tela também valida, mas é daqui que vale: a conta demo tem senha pública e
# qualquer um manda o POST na mão.

NOME_MAX = 40
# Em unidades de código, não em caracteres: emoji composto (família, bandeira,
# tom de pele) passa de 4 fácil. O antigo maxLength=4 da tela cortava 👨‍👩‍👧 ao meio.
ICONE_MAX = 16
COR_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _nome_de_categoria(bruto: str | None) -> str:
    """Espaços colapsados e aparados. "  Mercado  " e "Mercado" são o mesmo nome."""
    nome = " ".join((bruto or "").split())
    if not nome:
        raise HTTPException(status_code=400, detail="A categoria precisa de um nome.")
    if len(nome) > NOME_MAX:
        raise HTTPException(
            status_code=400, detail=f"Nome de categoria tem no máximo {NOME_MAX} caracteres."
        )
    return nome


def _recusar_nome_repetido(
    session: Session, dono: User, nome: str, tipo: CategoryType, ignorar: int | None = None
) -> None:
    """Duas categorias de mesmo tipo e mesmo nome dividiriam o gasto em duas.

    Sem distinguir maiúscula ("mercado" = "Mercado") e contando as arquivadas: a
    saída pra quem quer o nome de volta é desarquivar, não criar uma gêmea.
    Tipos diferentes podem repetir — "Outros" de despesa e de receita são coisas
    distintas, e o seletor já separa por tipo.

    Só roda quando o nome (ou o tipo) muda: categoria antiga que já estivesse
    duplicada não passa a ser recusada numa edição de cor.
    """
    alvo = nome.casefold()
    for outra in session.exec(consulta(Category, dono).where(Category.type == tipo)).all():
        if outra.id != ignorar and " ".join(outra.name.split()).casefold() == alvo:
            estado = " (arquivada — desarquive-a em vez de criar outra)" if outra.archived else ""
            raise HTTPException(
                status_code=409,
                detail=f"Já existe a categoria '{outra.name}'{estado}.",
            )


def _icone(bruto: str | None) -> str:
    icone = (bruto or "").strip()
    if not icone:
        raise HTTPException(status_code=400, detail="A categoria precisa de um ícone.")
    if len(icone) > ICONE_MAX:
        raise HTTPException(status_code=400, detail="O ícone é um emoji só.")
    return icone


def _cor(bruta: str | None) -> str:
    cor = (bruta or "").strip()
    if not COR_HEX.match(cor):
        raise HTTPException(status_code=400, detail="Cor inválida: use o formato #rrggbb.")
    return cor.lower()


def _uso_da_categoria(session: Session, dono: User) -> dict[int, tuple[int, int, int]]:
    """{category_id: (lançamentos, compras, metas)} em três consultas agregadas."""

    def contar(modelo) -> dict[int, int]:
        return {
            cid: int(n)
            for cid, n in session.exec(
                select(modelo.category_id, func.count(modelo.id))
                .where(modelo.user_id == dono.id)
                .group_by(modelo.category_id)
            ).all()
        }

    lanc, compras, metas = contar(Transaction), contar(Purchase), contar(Budget)
    return {
        cid: (lanc.get(cid, 0), compras.get(cid, 0), metas.get(cid, 0))
        for cid in set(lanc) | set(compras) | set(metas)
    }


@router.post("/categories")
def create_category(category: CategoryCreate, session: Session = Depends(get_session),
    dono: User = Depends(require_user)):
    exigir_escrita(dono)
    nome = _nome_de_categoria(category.name)
    _recusar_nome_repetido(session, dono, nome, category.type)
    db_category = Category.model_validate(
        category,
        update={
            "user_id": dono.id,
            "name": nome,
            "icon": _icone(category.icon),
            "color": _cor(category.color),
        },
    )
    session.add(db_category)
    session.commit()
    session.refresh(db_category)
    return db_category


@router.get("/categories")
def list_categories(
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
    incluir_arquivadas: bool = Query(default=False),
    incluir_uso: bool = Query(default=False),
):
    """As categorias ativas. Arquivadas só com `incluir_arquivadas=1`.

    O padrão exclui porque quem chama isto quase sempre é o formulário de
    lançamento, e oferecer 28 categorias herdadas de uma planilha é o que fazia
    escolher uma virar um exercício de paciência. Configurações passa o
    parâmetro pra poder desarquivar.
    """
    query = consulta(Category, dono)
    if not incluir_arquivadas:
        query = query.where(Category.archived == False)  # noqa: E712
    categorias = session.exec(query.order_by(Category.type, Category.name)).all()
    if not incluir_uso:
        return categorias

    uso = _uso_da_categoria(session, dono)
    return [
        CategoryRead(
            **c.model_dump(),
            transactions=uso.get(c.id, (0, 0, 0))[0],
            purchases=uso.get(c.id, (0, 0, 0))[1],
            budgets=uso.get(c.id, (0, 0, 0))[2],
        )
        for c in categorias
    ]


@router.get("/categories/{category_id}")
def get_category(category_id: int, session: Session = Depends(get_session),
    dono: User = Depends(require_user)):
    category = exigir(session, Category, category_id, dono, "Categoria")

    return category


@router.patch("/categories/{category_id}")
def update_category(
    category_id: int, category_data: CategoryUpdate, session: Session = Depends(get_session),
    dono: User = Depends(require_user)
):
    exigir_escrita(dono)
    category = exigir(session, Category, category_id, dono, "Categoria")

    update_data = category_data.model_dump(exclude_unset=True)

    # ---------- Trocar o tipo ----------
    # Despesa virar receita troca o sinal de todo o histórico dela de uma vez:
    # o mês em que se gastou 800 em Mercado passaria a ter "entrado" 800. Com
    # qualquer uso (lançamento, compra no cartão ou meta) a troca é recusada;
    # sem uso, ela é só a correção de um cadastro errado.
    novo_tipo = update_data.get("type")
    if "type" in update_data and novo_tipo is None:
        raise HTTPException(status_code=400, detail="O tipo não pode ficar vazio.")
    muda_tipo = novo_tipo is not None and CategoryType(novo_tipo) != CategoryType(category.type)
    if muda_tipo:
        lanc, compras, metas = _uso_da_categoria(session, dono).get(category.id, (0, 0, 0))
        if lanc or compras or metas:
            partes = [
                f"{n} {rotulo}"
                for n, rotulo in (
                    (lanc, "lançamento(s)"), (compras, "compra(s) no cartão"), (metas, "meta(s)")
                )
                if n
            ]
            raise HTTPException(
                status_code=409,
                detail=(
                    f"'{category.name}' já tem {', '.join(partes)}. Trocar o tipo "
                    "inverteria o sinal desse histórico. Crie uma categoria do tipo "
                    "certo e mova os lançamentos pra ela."
                ),
            )

    if "name" in update_data:
        update_data["name"] = _nome_de_categoria(update_data["name"])
    nome_final = update_data.get("name", category.name)
    if nome_final != category.name or muda_tipo:
        _recusar_nome_repetido(
            session, dono, nome_final, CategoryType(novo_tipo or category.type),
            ignorar=category.id,
        )
    if "icon" in update_data:
        update_data["icon"] = _icone(update_data["icon"])
    if "color" in update_data:
        update_data["color"] = _cor(update_data["color"])
    if "archived" in update_data and update_data["archived"] is None:
        del update_data["archived"]

    for key, value in update_data.items():
        setattr(category, key, value)

    session.add(category)
    session.commit()
    session.refresh(category)

    return category


@router.delete("/categories/{category_id}")
def delete_category(
    category_id: int,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
    mover_para: int | None = Query(
        default=None,
        description="Categoria que herda os lançamentos. Sem isso, categoria com lançamento não é apagada.",
    ),
):
    """Apaga a categoria. Com `mover_para`, os lançamentos mudam de dono antes.

    O `mover_para` é o que torna possível fundir categoria pela tela, que é a
    operação de verdade: ninguém quer "apagar Uber", quer "Uber virou
    Transporte". Sem ele só havia o caminho destrutivo — apagar um por um os 6
    lançamentos pra depois poder apagar a categoria.
    """
    exigir_escrita(dono)
    category = exigir(session, Category, category_id, dono, "Categoria")

    lancamentos = session.exec(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.user_id == dono.id, Transaction.category_id == category_id)
    ).one()

    if mover_para is not None:
        # Herdeira tem que existir, ser do dono e não ser ela mesma — senão o
        # UPDATE passaria e o DELETE em seguida levaria os lançamentos junto.
        if mover_para == category_id:
            raise HTTPException(
                status_code=400, detail="A categoria não pode herdar dela mesma."
            )
        destino = exigir(session, Category, mover_para, dono, "Categoria de destino")

        # Tipo diferente mudaria o sinal do lançamento: mover uma despesa pra
        # uma categoria de receita faria o gasto virar entrada, e o mês inteiro
        # passaria a mentir. Melhor recusar do que corromper calado.
        if destino.type != category.type:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"'{destino.name}' é {destino.type.value} e '{category.name}' é "
                    f"{category.type.value}. Mover trocaria o sinal dos lançamentos."
                ),
            )

        for t in session.exec(
            consulta(Transaction, dono).where(Transaction.category_id == category_id)
        ).all():
            t.category_id = mover_para
            session.add(t)

        # A compra no cartão também aponta pra categoria, e as parcelas dela são
        # justamente os lançamentos movidos acima. Sem mover a compra junto, a
        # chave estrangeira de `purchases` barra o DELETE lá embaixo — e no
        # Postgres isso é um 500, não um erro tratado. Mesma classe do bug de
        # ordem de delete que já mordeu em asset_snapshots.
        for compra in session.exec(
            consulta(Purchase, dono).where(Purchase.category_id == category_id)
        ).all():
            compra.category_id = mover_para
            session.add(compra)

        session.flush()

    elif lancamentos:
        # Lançamento é histórico: apagar a categoria junto seria destruir dado
        # que o usuário não pediu pra perder. Melhor recusar e deixar ele
        # decidir — agora com "mover_para" como saída não destrutiva.
        raise HTTPException(
            status_code=409,
            detail=(
                f"A categoria tem {lancamentos} lançamento(s). "
                "Mova esses lançamentos para outra categoria antes de apagá-la."
            ),
        )

    # Meta é planejamento, não histórico — pode sair junto. O flush garante que
    # ela vá embora antes da categoria, senão a FK barra no Postgres.
    for budget in session.exec(consulta(Budget, dono).where(Budget.category_id == category_id)).all():
        session.delete(budget)
    session.flush()

    session.delete(category)
    session.commit()

    if mover_para is not None and lancamentos:
        return {
            "message": f"Categoria excluída. {lancamentos} lançamento(s) movido(s).",
            "moved": lancamentos,
        }
    return {"message": "Categoria excluída.", "moved": 0}


# Declarado antes de /budgets/{budget_id} pra "summary" não ser lido como id.
@router.get("/budgets/summary", response_model=BudgetSummary)
def get_budget_summary(
    year: int = Query(ge=1900, le=2999),
    month: int = Query(ge=1, le=12),
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Orçado x previsto x pago por categoria no mês.

    Devolve todas as categorias, inclusive as sem meta e sem lançamento, pra
    aba de Orçamento poder oferecer o campo de meta em qualquer linha.

    Cada mês é lido sozinho: o teto de setembro não sabe nada de agosto. Foi
    uma escolha de substituir a caixinha acumulativa, cujo número dependia de
    todo o histórico de metas — ver BudgetSummaryItem.
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
            .where(
                Transaction.user_id == dono.id,
                Transaction.date >= start,
                Transaction.date < end,
            )
            .group_by(Transaction.category_id)
        ).all()
    }

    metas = {
        budget.category_id: budget
        for budget in session.exec(
            consulta(Budget, dono).where(Budget.year == year, Budget.month == month)
        ).all()
    }

    categories = session.exec(
        consulta(Category, dono).order_by(Category.type, Category.name)
    ).all()

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
            archived=category.archived,
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

    # O bloco de caixa viaja junto com o de orçamento porque a tela de Início
    # já pede este resumo: uma rota separada seria uma ida a mais ao servidor
    # na tela que mais se abre, pra buscar números derivados dos mesmos
    # lançamentos. Os `totals` acima continuam medindo GASTO — meta não muda de
    # significado por causa do cartão.
    return BudgetSummary(
        year=year,
        month=month,
        items=items,
        totals=totals,
        caixa=resumo_de_caixa(session, dono, year, month, start, end),
    )


@router.put("/budgets")
def set_budget(budget: BudgetCreate, session: Session = Depends(get_session),
    dono: User = Depends(require_user)):
    """Define a meta da categoria no mês. Idempotente: cria ou sobrescreve.

    É PUT em vez de POST porque a tela de Orçamento só sabe "categoria + mês +
    valor" — ela não tem id de meta pra escolher entre criar e editar.
    """
    exigir_escrita(dono)
    category = buscar(session, Category, budget.category_id, dono)
    if not category:
        raise HTTPException(status_code=400, detail="Category not found")

    db_budget = session.exec(
        consulta(Budget, dono).where(
            Budget.category_id == budget.category_id,
            Budget.year == budget.year,
            Budget.month == budget.month,
        )
    ).first()

    if db_budget:
        db_budget.amount = budget.amount
    else:
        db_budget = Budget.model_validate(budget, update={"user_id": dono.id})

    session.add(db_budget)
    session.commit()
    session.refresh(db_budget)

    return db_budget


@router.get("/budgets")
def list_budgets(
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
    year: int | None = Query(default=None, ge=1900, le=2999),
    month: int | None = Query(default=None, ge=1, le=12),
):
    if month is not None and year is None:
        raise HTTPException(status_code=400, detail="Informe o ano junto com o mês.")

    query = consulta(Budget, dono)

    if year is not None:
        query = query.where(Budget.year == year)
    if month is not None:
        query = query.where(Budget.month == month)

    return session.exec(query.order_by(Budget.year, Budget.month, Budget.category_id)).all()


@router.patch("/budgets/{budget_id}")
def update_budget(
    budget_id: int, budget_data: BudgetUpdate, session: Session = Depends(get_session),
    dono: User = Depends(require_user)
):
    exigir_escrita(dono)
    budget = exigir(session, Budget, budget_id, dono, "Meta")

    for key, value in budget_data.model_dump(exclude_unset=True).items():
        setattr(budget, key, value)

    session.add(budget)
    session.commit()
    session.refresh(budget)

    return budget


@router.delete("/budgets/{budget_id}")
def delete_budget(budget_id: int, session: Session = Depends(get_session),
    dono: User = Depends(require_user)):
    exigir_escrita(dono)
    budget = exigir(session, Budget, budget_id, dono, "Meta")

    session.delete(budget)
    session.commit()

    return {"message": "Meta excluída."}


# ---------- Patrimônio ----------
# Declarado antes de /assets/{asset_id} pra "summary" não ser lido como id.
@router.get("/assets/summary", response_model=AssetSummary)
def get_asset_summary(
    year: int = Query(ge=1900, le=2999),
    month: int = Query(ge=1, le=12),
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Saldo de cada ativo no mês, com variação e patrimônio líquido.

    Saldo é estoque, não movimento: quem não atualizou o mês continua valendo
    o último saldo lançado. Sem isso o patrimônio despencaria a zero em todo
    mês que ficou sem preencher, o que seria mentira e não ausência de dado.
    """
    target = month_index(year, month)
    prev_target = month_index(*previous_month(year, month))

    snapshots = session.exec(
        consulta(AssetSnapshot, dono).where(
            or_(
                AssetSnapshot.year < year,
                and_(AssetSnapshot.year == year, AssetSnapshot.month <= month),
            )
        )
    ).all()

    # Último snapshot de cada ativo até o mês pedido, e até o mês anterior.
    latest: dict[int, AssetSnapshot] = {}
    latest_prev: dict[int, AssetSnapshot] = {}

    def keep_latest(bucket: dict[int, AssetSnapshot], snap: AssetSnapshot, idx: int):
        current = bucket.get(snap.asset_id)
        if current is None or month_index(current.year, current.month) < idx:
            bucket[snap.asset_id] = snap

    for snap in snapshots:
        idx = month_index(snap.year, snap.month)
        if idx <= target:
            keep_latest(latest, snap, idx)
        if idx <= prev_target:
            keep_latest(latest_prev, snap, idx)

    assets = session.exec(consulta(Asset, dono).order_by(Asset.asset_class, Asset.name)).all()

    items: list[AssetSummaryItem] = []
    by_class = {classe.value: AssetClassTotal() for classe in AssetClass}
    total_assets = total_liabilities = 0.0
    prev_assets = prev_liabilities = 0.0

    for asset in assets:
        snap = latest.get(asset.id)
        prev_snap = latest_prev.get(asset.id)
        value = snap.value if snap else 0.0
        previous = prev_snap.value if prev_snap else 0.0
        liability = is_liability(asset.asset_class)

        # O rendimento esperado parte do saldo do mês ANTERIOR: é sobre ele que
        # os juros do mês incidiram. Usar o saldo atual contaria juros sobre o
        # aporte que acabou de entrar, inflando o resultado.
        esperado = None
        if asset.cdi_percent and dono.cdi_annual and previous > 0:
            esperado = rendimento_do_mes(
                previous, dono.cdi_annual, asset.cdi_percent, year, month
            )

        items.append(
            AssetSummaryItem(
                asset_id=asset.id,
                name=asset.name,
                asset_class=asset.asset_class,
                liability=liability,
                note=asset.note,
                cdi_percent=asset.cdi_percent,
                expected_yield=esperado,
                # Só conta como "deste mês" se o snapshot for do período pedido;
                # valor herdado de mês anterior não tem id pra editar aqui.
                snapshot_id=(
                    snap.id if snap and month_index(snap.year, snap.month) == target else None
                ),
                value=value,
                previous=previous,
                change=value - previous,
                as_of=f"{snap.year}-{snap.month:02d}" if snap else None,
            )
        )

        total = by_class[AssetClass(asset.asset_class).value]
        total.value += value
        total.previous += previous

        if liability:
            total_liabilities += value
            prev_liabilities += previous
        else:
            total_assets += value
            prev_assets += previous

    return AssetSummary(
        year=year,
        month=month,
        items=items,
        by_class=by_class,
        assets=total_assets,
        liabilities=total_liabilities,
        net_worth=total_assets - total_liabilities,
        previous_net_worth=prev_assets - prev_liabilities,
    )


@router.put("/assets/snapshots")
def set_asset_snapshot(
    snapshot: AssetSnapshotCreate, session: Session = Depends(get_session),
    dono: User = Depends(require_user)
):
    """Lança o saldo do ativo no mês. Idempotente, pelo mesmo motivo do PUT de metas."""
    exigir_escrita(dono)
    asset = buscar(session, Asset, snapshot.asset_id, dono)
    if not asset:
        raise HTTPException(status_code=400, detail="Asset not found")

    db_snapshot = session.exec(
        consulta(AssetSnapshot, dono).where(
            AssetSnapshot.asset_id == snapshot.asset_id,
            AssetSnapshot.year == snapshot.year,
            AssetSnapshot.month == snapshot.month,
        )
    ).first()

    if db_snapshot:
        db_snapshot.value = snapshot.value
    else:
        db_snapshot = AssetSnapshot.model_validate(snapshot, update={"user_id": dono.id})

    session.add(db_snapshot)
    session.commit()
    session.refresh(db_snapshot)

    return db_snapshot


@router.get("/assets/snapshots")
def list_asset_snapshots(
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
    asset_id: int | None = None,
    year: int | None = Query(default=None, ge=1900, le=2999),
):
    query = consulta(AssetSnapshot, dono)

    if asset_id is not None:
        query = query.where(AssetSnapshot.asset_id == asset_id)
    if year is not None:
        query = query.where(AssetSnapshot.year == year)

    return session.exec(
        query.order_by(AssetSnapshot.year, AssetSnapshot.month, AssetSnapshot.asset_id)
    ).all()


@router.patch("/assets/snapshots/{snapshot_id}")
def update_asset_snapshot(
    snapshot_id: int,
    snapshot_data: AssetSnapshotUpdate,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    exigir_escrita(dono)
    snapshot = exigir(session, AssetSnapshot, snapshot_id, dono, "Saldo")

    for key, value in snapshot_data.model_dump(exclude_unset=True).items():
        setattr(snapshot, key, value)

    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)

    return snapshot


@router.delete("/assets/snapshots/{snapshot_id}")
def delete_asset_snapshot(snapshot_id: int, session: Session = Depends(get_session),
    dono: User = Depends(require_user)):
    exigir_escrita(dono)
    snapshot = exigir(session, AssetSnapshot, snapshot_id, dono, "Saldo")

    session.delete(snapshot)
    session.commit()

    return {"message": "Saldo excluído."}


class PerfilUpdate(SQLModel):
    cdi_annual: float | None = None


@router.get("/perfil")
def get_perfil(dono: User = Depends(require_user)):
    """Os ajustes da conta. Hoje só o CDI, que alimenta a projeção."""
    return {"nome": dono.name, "email": dono.email, "cdi_annual": dono.cdi_annual}


@router.patch("/perfil")
def update_perfil(
    dados: PerfilUpdate,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    exigir_escrita(dono)
    # O objeto do dono vem da mesma sessão da requisição, então basta alterar.
    dono.cdi_annual = dados.cdi_annual
    session.add(dono)
    session.commit()
    return {"cdi_annual": dono.cdi_annual}


@router.post("/assets")
def create_asset(asset: AssetCreate, session: Session = Depends(get_session),
    dono: User = Depends(require_user)):
    exigir_escrita(dono)
    db_asset = Asset.model_validate(asset, update={"user_id": dono.id})
    session.add(db_asset)
    session.commit()
    session.refresh(db_asset)
    return db_asset


@router.get("/assets")
def list_assets(session: Session = Depends(get_session),
    dono: User = Depends(require_user)):
    return session.exec(consulta(Asset, dono).order_by(Asset.asset_class, Asset.name)).all()


@router.patch("/assets/{asset_id}")
def update_asset(asset_id: int, asset_data: AssetUpdate, session: Session = Depends(get_session),
    dono: User = Depends(require_user)):
    exigir_escrita(dono)
    asset = exigir(session, Asset, asset_id, dono, "Ativo")

    for key, value in asset_data.model_dump(exclude_unset=True).items():
        setattr(asset, key, value)

    session.add(asset)
    session.commit()
    session.refresh(asset)

    return asset


@router.delete("/assets/{asset_id}")
def delete_asset(asset_id: int, session: Session = Depends(get_session),
    dono: User = Depends(require_user)):
    exigir_escrita(dono)
    asset = exigir(session, Asset, asset_id, dono, "Ativo")

    # Os saldos saem junto: sem isso a FK barra o delete e sobraria histórico
    # órfão de um ativo que não existe mais.
    snapshots = session.exec(
        consulta(AssetSnapshot, dono).where(AssetSnapshot.asset_id == asset_id)
    ).all()
    for snapshot in snapshots:
        session.delete(snapshot)

    # O flush é obrigatório: sem Relationship declarado o SQLAlchemy não sabe
    # que asset_snapshots depende de assets e pode mandar o DELETE do ativo
    # primeiro, o que o Postgres recusa por violação de FK.
    session.flush()

    session.delete(asset)
    session.commit()

    return {"message": "Ativo excluído."}


# No fim de propósito: o router só é registrado depois de todas as rotas serem
# declaradas nele.
app.include_router(router)

# As rotas de cartão moram em app/rotas_cartao.py por tamanho, num router
# próprio que também exige token. É o test_isolamento.py que garante isso —
# ele percorre as rotas de lá com o id da outra conta e exige 404.
app.include_router(router_cartao)

# Relatórios (app/rotas_relatorios.py): séries e distribuição já agregadas no
# servidor, no mesmo arranjo — router próprio que também exige token.
app.include_router(router_relatorios)
