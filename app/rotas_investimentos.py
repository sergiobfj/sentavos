"""Rotas de investimento: resumo do mês (com o rendimento) e movimentos.

Finas: a regra está em `app/dominio/investimentos.py`.
"""

import datetime as dt

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlmodel import Session, SQLModel, or_

from app.auth import exigir_escrita, require_user
from app.database import get_session
from app.dominio import investimentos
from app.dominio.auditoria import ator_api, registrar
from app.escopo import consulta, exigir
from app.models import (
    Asset,
    FinancialAccount,
    InvestmentMovement,
    InvestmentMovementCreate,
    InvestmentMovementType,
    InvestmentPlan,
    InvestmentPlanData,
    InvestmentPlanConfirm,
    Category,
    CategoryType,
    User,
)

router_investimentos = APIRouter(dependencies=[Depends(require_user)])


@router_investimentos.get("/months/summary")
def resumo_do_mes(year: int = Query(ge=1900, le=2999), month: int = Query(ge=1, le=12),
                  session: Session = Depends(get_session), dono: User = Depends(require_user)):
    from app.dominio.meu_mes import resumo
    return resumo(session, dono, year, month)

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
         "outubro", "novembro", "dezembro"]


def _plano(session: Session, dono: User, plan_id: int) -> InvestmentPlan:
    # Serializa confirmar/editar/cancelar entre clientes no Postgres.
    p = session.exec(consulta(InvestmentPlan, dono).where(InvestmentPlan.id == plan_id)
                     .with_for_update().execution_options(populate_existing=True)).first()
    if p is None:
        raise HTTPException(404, "Previsão não encontrada.")
    return p


def _validar_plano(session: Session, dono: User, dados: InvestmentPlanData):
    if dados.type == InvestmentMovementType.ADJUSTMENT:
        raise HTTPException(400, "Previsão aceita aporte ou resgate.")
    if dados.asset_id is not None:
        ativo = exigir(session, Asset, dados.asset_id, dono, "Ativo")
        if not investimentos.eh_investimento(ativo) or ativo.archived_on is not None:
            raise HTTPException(400, "Escolha um investimento ativo.")
    from app.dominio.contas import conta_valida
    conta_valida(session, dono, dados.account_id)
    if dados.category_id is not None:
        cat = exigir(session, Category, dados.category_id, dono, "Categoria")
        if cat.type != CategoryType.INVESTMENT or cat.archived:
            raise HTTPException(400, "Escolha uma categoria de investimento ativa.")


def _ler_plano(session: Session, dono: User, p: InvestmentPlan):
    from app.escopo import buscar
    from app.dominio.tempo import hoje_local
    ativo = buscar(session, Asset, p.asset_id, dono) if p.asset_id else None
    conta = buscar(session, FinancialAccount, p.account_id, dono) if p.account_id else None
    return {**p.model_dump(exclude={"user_id"}), "asset_name": ativo.name if ativo else None,
            "account_name": conta.name if conta else None,
            "overdue": p.status == "planned" and p.date < hoje_local()}


@router_investimentos.get("/investments/plans")
def listar_planos(year: int = Query(ge=1900, le=2999), month: int = Query(ge=1, le=12),
                  session: Session = Depends(get_session), dono: User = Depends(require_user)):
    from app.cartao import limites_do_mes
    from app.dominio.tempo import hoje_local
    inicio, fim = limites_do_mes(year, month)
    atual = (year, month) == (hoje_local().year, hoje_local().month)
    return [_ler_plano(session, dono, p) for p in session.exec(
        consulta(InvestmentPlan, dono).where(InvestmentPlan.date < fim,
            or_(InvestmentPlan.date >= inicio, InvestmentPlan.status == "planned") if atual else InvestmentPlan.date >= inicio)
        .order_by(InvestmentPlan.date, InvestmentPlan.id)).all()]


@router_investimentos.post("/investments/plans")
def criar_plano(dados: InvestmentPlanData, session: Session = Depends(get_session), dono: User = Depends(require_user)):
    exigir_escrita(dono)
    _validar_plano(session, dono, dados)
    p = InvestmentPlan(user_id=dono.id, **dados.model_dump())
    session.add(p)
    session.flush()
    registrar(session, acao="investimento.planejado", ator=ator_api(dono.email), user_id=dono.id,
              entidade="investment_plan", entidade_id=p.id, detalhes=dados.model_dump(mode="json"))
    session.commit()
    return _ler_plano(session, dono, p)


@router_investimentos.patch("/investments/plans/{plan_id}")
def editar_plano(plan_id: int, dados: InvestmentPlanData, session: Session = Depends(get_session), dono: User = Depends(require_user)):
    exigir_escrita(dono)
    p = _plano(session, dono, plan_id)
    if p.status != "planned":
        raise HTTPException(409, "Só uma previsão em aberto pode ser editada.")
    _validar_plano(session, dono, dados)
    p.sqlmodel_update(dados.model_dump())
    session.add(p)
    registrar(session, acao="investimento.plano_editado", ator=ator_api(dono.email), user_id=dono.id,
              entidade="investment_plan", entidade_id=p.id, detalhes=dados.model_dump(mode="json"))
    session.commit()
    return _ler_plano(session, dono, p)


@router_investimentos.post("/investments/plans/{plan_id}/cancel")
def cancelar_plano(plan_id: int, session: Session = Depends(get_session), dono: User = Depends(require_user)):
    exigir_escrita(dono)
    p = _plano(session, dono, plan_id)
    if p.status == "completed":
        raise HTTPException(409, "O plano já foi realizado.")
    p.status = "cancelled"
    session.add(p)
    registrar(session, acao="investimento.plano_cancelado", ator=ator_api(dono.email), user_id=dono.id,
              entidade="investment_plan", entidade_id=p.id)
    session.commit()
    return _ler_plano(session, dono, p)


@router_investimentos.post("/investments/plans/{plan_id}/confirm")
def confirmar_plano(plan_id: int, dados: InvestmentPlanConfirm, session: Session = Depends(get_session), dono: User = Depends(require_user)):
    exigir_escrita(dono)
    p = _plano(session, dono, plan_id)
    if p.status == "completed":
        return _ler_plano(session, dono, p)
    if p.status == "cancelled":
        raise HTTPException(409, "A previsão foi cancelada.")
    from app.dominio.tempo import hoje_local, agora
    if dados.date > hoje_local():
        raise HTTPException(400, "A realização não pode ter data futura.")
    if p.account_id is None or p.asset_id is None or p.category_id is None:
        raise HTTPException(400, "Complete conta, investimento e categoria antes de confirmar.")
    _validar_plano(session, dono, InvestmentPlanData(**p.model_dump()))
    mov = investimentos.registrar(session, dono, InvestmentMovementCreate(
        type=p.type, amount=p.amount, date=dados.date, account_id=p.account_id, asset_id=p.asset_id,
        category_id=p.category_id, description=p.description,
        occurred_at=agora() if dados.date == hoje_local() else None), ator_api(dono.email))
    p.movement_id, p.status = mov.id, "completed"
    p.balance_pending = True
    session.add(p)
    registrar(session, acao="investimento.plano_realizado", ator=ator_api(dono.email), user_id=dono.id,
              entidade="investment_plan", entidade_id=p.id, detalhes={"movement_id": mov.id})
    session.commit()
    return _ler_plano(session, dono, p)


class MovementRead(SQLModel):
    id: int
    asset_id: int
    asset_name: str
    type: InvestmentMovementType
    amount: float
    date: dt.date
    account_id: int | None = None
    account_name: str | None = None
    note: str | None = None
    transaction_id: int | None = None


def _ler(session: Session, dono: User, movs: list[InvestmentMovement]) -> list[MovementRead]:
    ativos = {a.id: a.name for a in session.exec(consulta(Asset, dono)).all()}
    contas = {c.id: c.name for c in session.exec(consulta(FinancialAccount, dono)).all()}
    return [
        MovementRead(**m.model_dump(include={"id", "asset_id", "type", "amount", "date", "account_id", "note",
                                              "transaction_id"}),
                     asset_name=ativos.get(m.asset_id, "?"),
                     account_name=contas.get(m.account_id) if m.account_id else None)
        for m in movs
    ]


@router_investimentos.get("/investments/summary")
def resumo_de_investimentos(
    year: int = Query(ge=1900, le=2999), month: int = Query(ge=1, le=12),
    session: Session = Depends(get_session), dono: User = Depends(require_user),
) -> investimentos.InvestmentSummary:
    return investimentos.resumo(session, dono, year, month, f"{MESES[month - 1]} de {year}")


@router_investimentos.get("/investments/movements")
def listar_movimentos(
    year: int | None = Query(default=None, ge=1900, le=2999), month: int | None = Query(default=None, ge=1, le=12),
    asset_id: int | None = Query(default=None),
    session: Session = Depends(get_session), dono: User = Depends(require_user),
) -> list[MovementRead]:
    if asset_id is not None:
        exigir(session, Asset, asset_id, dono, "Ativo")
    return _ler(session, dono, investimentos.lista_de_movimentos(session, dono, year, month, asset_id))


@router_investimentos.post("/investments/movements")
def criar_movimento(
    dados: InvestmentMovementCreate, session: Session = Depends(get_session), dono: User = Depends(require_user)
) -> MovementRead:
    """Aporte, resgate ou ajuste. Liga um lançamento existente ou cria o lado caixa."""
    exigir_escrita(dono)
    mov = investimentos.registrar(session, dono, dados, ator_api(dono.email))
    session.commit()
    session.refresh(mov)
    return _ler(session, dono, [mov])[0]


@router_investimentos.delete("/investments/movements/{movement_id}")
def desvincular_movimento(
    movement_id: int, session: Session = Depends(get_session), dono: User = Depends(require_user)
):
    """Tira a semântica de ativo; o lançamento (o lado caixa) fica. Pra apagar
    o aporte inteiro, apague o lançamento — o movimento vai junto."""
    exigir_escrita(dono)
    mov = exigir(session, InvestmentMovement, movement_id, dono, "Movimento")
    registrar(session, acao="investimento.movimento_removido", ator=ator_api(dono.email), user_id=dono.id,
              entidade="investment_movement", entidade_id=mov.id,
              detalhes={"ativo": mov.asset_id, "tipo": InvestmentMovementType(mov.type).value,
                        "valor": mov.amount, "lancamento": mov.transaction_id})
    session.delete(mov)
    session.commit()
    return {"message": "Movimento desvinculado. O lançamento continua."}
