"""Rotas de investimento: resumo do mês (com o rendimento) e movimentos.

Finas: a regra está em `app/dominio/investimentos.py`.
"""

import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, SQLModel

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
    User,
)

router_investimentos = APIRouter(dependencies=[Depends(require_user)])

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
         "outubro", "novembro", "dezembro"]


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
