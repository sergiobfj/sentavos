from contextlib import asynccontextmanager
import os
import datetime as dt

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, and_, func, or_, select

from app.database import create_db_and_tables, get_session
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
    CategoryType,
    CategoryUpdate,
    Transaction,
    TransactionCreate,
    TransactionUpdate,
    is_liability,
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


def month_index(year: int, month: int) -> int:
    """Mês como número absoluto, pra comparar períodos sem cuidar de virada de ano."""
    return year * 12 + (month - 1)


def previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


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

    # Lançamento é histórico: apagar a categoria junto seria destruir dado que
    # o usuário não pediu pra perder. Melhor recusar e deixar ele decidir.
    lancamentos = session.exec(
        select(func.count()).select_from(Transaction).where(Transaction.category_id == category_id)
    ).one()

    if lancamentos:
        raise HTTPException(
            status_code=409,
            detail=(
                f"A categoria tem {lancamentos} lançamento(s). "
                "Exclua ou mova esses lançamentos antes de apagar a categoria."
            ),
        )

    # Meta é planejamento, não histórico — pode sair junto. O flush garante que
    # ela vá embora antes da categoria, senão a FK barra no Postgres.
    for budget in session.exec(select(Budget).where(Budget.category_id == category_id)).all():
        session.delete(budget)
    session.flush()

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


# ---------- Patrimônio ----------
# Declarado antes de /assets/{asset_id} pra "summary" não ser lido como id.
@app.get("/assets/summary", response_model=AssetSummary)
def get_asset_summary(
    year: int = Query(ge=1900, le=2999),
    month: int = Query(ge=1, le=12),
    session: Session = Depends(get_session),
):
    """Saldo de cada ativo no mês, com variação e patrimônio líquido.

    Saldo é estoque, não movimento: quem não atualizou o mês continua valendo
    o último saldo lançado. Sem isso o patrimônio despencaria a zero em todo
    mês que ficou sem preencher, o que seria mentira e não ausência de dado.
    """
    target = month_index(year, month)
    prev_target = month_index(*previous_month(year, month))

    snapshots = session.exec(
        select(AssetSnapshot).where(
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

    assets = session.exec(select(Asset).order_by(Asset.asset_class, Asset.name)).all()

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

        items.append(
            AssetSummaryItem(
                asset_id=asset.id,
                name=asset.name,
                asset_class=asset.asset_class,
                liability=liability,
                note=asset.note,
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


@app.put("/assets/snapshots")
def set_asset_snapshot(
    snapshot: AssetSnapshotCreate, session: Session = Depends(get_session)
):
    """Lança o saldo do ativo no mês. Idempotente, pelo mesmo motivo do PUT de metas."""
    asset = session.get(Asset, snapshot.asset_id)
    if not asset:
        raise HTTPException(status_code=400, detail="Asset not found")

    db_snapshot = session.exec(
        select(AssetSnapshot).where(
            AssetSnapshot.asset_id == snapshot.asset_id,
            AssetSnapshot.year == snapshot.year,
            AssetSnapshot.month == snapshot.month,
        )
    ).first()

    if db_snapshot:
        db_snapshot.value = snapshot.value
    else:
        db_snapshot = AssetSnapshot.model_validate(snapshot)

    session.add(db_snapshot)
    session.commit()
    session.refresh(db_snapshot)

    return db_snapshot


@app.get("/assets/snapshots")
def list_asset_snapshots(
    session: Session = Depends(get_session),
    asset_id: int | None = None,
    year: int | None = Query(default=None, ge=1900, le=2999),
):
    query = select(AssetSnapshot)

    if asset_id is not None:
        query = query.where(AssetSnapshot.asset_id == asset_id)
    if year is not None:
        query = query.where(AssetSnapshot.year == year)

    return session.exec(
        query.order_by(AssetSnapshot.year, AssetSnapshot.month, AssetSnapshot.asset_id)
    ).all()


@app.patch("/assets/snapshots/{snapshot_id}")
def update_asset_snapshot(
    snapshot_id: int,
    snapshot_data: AssetSnapshotUpdate,
    session: Session = Depends(get_session),
):
    snapshot = session.get(AssetSnapshot, snapshot_id)

    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    for key, value in snapshot_data.model_dump(exclude_unset=True).items():
        setattr(snapshot, key, value)

    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)

    return snapshot


@app.delete("/assets/snapshots/{snapshot_id}")
def delete_asset_snapshot(snapshot_id: int, session: Session = Depends(get_session)):
    snapshot = session.get(AssetSnapshot, snapshot_id)

    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    session.delete(snapshot)
    session.commit()

    return {"message": "Saldo excluído."}


@app.post("/assets")
def create_asset(asset: AssetCreate, session: Session = Depends(get_session)):
    db_asset = Asset.model_validate(asset)
    session.add(db_asset)
    session.commit()
    session.refresh(db_asset)
    return db_asset


@app.get("/assets")
def list_assets(session: Session = Depends(get_session)):
    return session.exec(select(Asset).order_by(Asset.asset_class, Asset.name)).all()


@app.patch("/assets/{asset_id}")
def update_asset(asset_id: int, asset_data: AssetUpdate, session: Session = Depends(get_session)):
    asset = session.get(Asset, asset_id)

    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    for key, value in asset_data.model_dump(exclude_unset=True).items():
        setattr(asset, key, value)

    session.add(asset)
    session.commit()
    session.refresh(asset)

    return asset


@app.delete("/assets/{asset_id}")
def delete_asset(asset_id: int, session: Session = Depends(get_session)):
    asset = session.get(Asset, asset_id)

    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Os saldos saem junto: sem isso a FK barra o delete e sobraria histórico
    # órfão de um ativo que não existe mais.
    snapshots = session.exec(
        select(AssetSnapshot).where(AssetSnapshot.asset_id == asset_id)
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
