"""Rotas de contas, saldos observados e transferências.

Finas: validam, autorizam, chamam `app/dominio/contas.py` e serializam. A regra
do saldo (observado + movimentos, qualidade do número) não mora aqui.
"""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlmodel import Session, SQLModel, func, select

from app.auth import exigir_escrita, require_user
from app.database import get_session
from app.dominio import contas as dominio
from app.dominio.auditoria import ator_api, registrar
from app.escopo import consulta, exigir
from app.models import (
    AccountBalanceSnapshot,
    AccountType,
    FinancialAccount,
    FinancialAccountBase,
    FinancialAccountCreate,
    FinancialAccountUpdate,
    InvoicePayment,
    SnapshotSource,
    Transaction,
    Transfer,
    TransferCreate,
    User,
)

router_contas = APIRouter(dependencies=[Depends(require_user)])


class AccountRead(FinancialAccountBase):
    id: int
    archived: bool
    created_at: dt.datetime
    # Calculado: último saldo observado + movimentos conhecidos depois dele.
    balance: float | None = None
    quality: str  # reconciliado | calculado | desatualizado | sem_saldo
    observed_at: dt.datetime | None = None
    observed_balance: float | None = None
    movements_after: int = 0
    maybe_incomplete: bool = False


class AccountsSummary(SQLModel):
    accounts: list[AccountRead]
    total: float
    free: float
    restricted: float
    to_distribute: float
    stale_count: int
    without_balance_count: int
    maybe_incomplete: bool
    unassigned_movements: int


def _ler(s: dominio.SaldoDaConta) -> AccountRead:
    c = s.conta
    return AccountRead(
        **c.model_dump(include=set(FinancialAccountBase.model_fields) | {"id", "archived", "created_at"}),
        balance=s.saldo, quality=s.qualidade, observed_at=s.observado_em, observed_balance=s.saldo_observado,
        movements_after=s.movimentos_depois, maybe_incomplete=s.incompleto,
    )


def _uma(session: Session, dono: User, conta: FinancialAccount) -> AccountRead:
    return _ler(dominio.saldos(session, dono, contas=[conta])[0])


def _nome(bruto: str | None) -> str:
    nome = " ".join((bruto or "").split())
    if not nome:
        raise HTTPException(status_code=400, detail="Dê um nome à conta.")
    return nome[:60]


def _nome_livre(session: Session, dono: User, nome: str, ignorar: int | None = None) -> None:
    for c in session.exec(consulta(FinancialAccount, dono).where(FinancialAccount.archived == False)).all():  # noqa: E712
        if c.id != ignorar and c.name.casefold() == nome.casefold():
            raise HTTPException(status_code=409, detail=f"Já existe a conta {c.name}.")


@router_contas.get("/accounts")
def listar_contas(
    incluir_arquivadas: bool = Query(default=False),
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
) -> list[AccountRead]:
    q = consulta(FinancialAccount, dono)
    if not incluir_arquivadas:
        q = q.where(FinancialAccount.archived == False)  # noqa: E712
    contas = list(session.exec(q.order_by(FinancialAccount.id)).all())
    return [_ler(s) for s in dominio.saldos(session, dono, contas=contas)]


@router_contas.get("/accounts/summary")
def resumo_das_contas(session: Session = Depends(get_session), dono: User = Depends(require_user)) -> AccountsSummary:
    r = dominio.resumo(session, dono)
    return AccountsSummary(
        accounts=[_ler(s) for s in r.contas], total=r.total, free=r.livre, restricted=r.restrito,
        to_distribute=r.a_distribuir, stale_count=r.desatualizadas, without_balance_count=r.sem_saldo,
        maybe_incomplete=r.incompleto, unassigned_movements=r.movimentos_sem_conta,
    )


@router_contas.post("/accounts")
def criar_conta(
    dados: FinancialAccountCreate, session: Session = Depends(get_session), dono: User = Depends(require_user)
) -> AccountRead:
    exigir_escrita(dono)
    nome = _nome(dados.name)
    _nome_livre(session, dono, nome)
    restrita = dados.restricted if dados.restricted is not None else AccountType(dados.type) == AccountType.BENEFIT
    conta = FinancialAccount(
        user_id=dono.id, name=nome, institution=(dados.institution or "").strip() or None, type=dados.type,
        currency=(dados.currency or "BRL").upper()[:3],
        restricted=restrita,
        include_in_planning=dados.include_in_planning if dados.include_in_planning is not None else not restrita,
    )
    session.add(conta)
    session.commit()
    session.refresh(conta)
    return _uma(session, dono, conta)


@router_contas.get("/accounts/{account_id}")
def ver_conta(account_id: int, session: Session = Depends(get_session), dono: User = Depends(require_user)) -> AccountRead:
    return _uma(session, dono, exigir(session, FinancialAccount, account_id, dono, "Conta"))


@router_contas.patch("/accounts/{account_id}")
def atualizar_conta(
    account_id: int, dados: FinancialAccountUpdate,
    session: Session = Depends(get_session), dono: User = Depends(require_user),
) -> AccountRead:
    exigir_escrita(dono)
    conta = exigir(session, FinancialAccount, account_id, dono, "Conta")
    mudancas = dados.model_dump(exclude_unset=True)
    if "name" in mudancas:
        mudancas["name"] = _nome(mudancas["name"])
        _nome_livre(session, dono, mudancas["name"], ignorar=conta.id)
    for chave, valor in mudancas.items():
        if valor is None and chave in ("type", "include_in_planning", "restricted", "archived"):
            continue
        setattr(conta, chave, valor)
    session.add(conta)
    session.commit()
    session.refresh(conta)
    return _uma(session, dono, conta)


def _tem_movimento(session: Session, dono: User, conta_id: int) -> bool:
    perguntas = (
        consulta(Transaction, dono).where(Transaction.account_id == conta_id),
        consulta(InvoicePayment, dono).where(InvoicePayment.account_id == conta_id),
        consulta(Transfer, dono).where(or_(Transfer.from_account_id == conta_id, Transfer.to_account_id == conta_id)),
    )
    return any(session.exec(q.limit(1)).first() is not None for q in perguntas)


@router_contas.delete("/accounts/{account_id}")
def excluir_conta(account_id: int, session: Session = Depends(get_session), dono: User = Depends(require_user)):
    """Só conta sem movimento. Com movimento, arquive: o histórico é dela."""
    exigir_escrita(dono)
    conta = exigir(session, FinancialAccount, account_id, dono, "Conta")
    if _tem_movimento(session, dono, conta.id):
        raise HTTPException(status_code=409, detail="Esta conta tem lançamentos ou transferências. Arquive em vez de excluir.")
    for s in session.exec(consulta(AccountBalanceSnapshot, dono).where(AccountBalanceSnapshot.account_id == conta.id)).all():
        session.delete(s)
    session.delete(conta)
    session.commit()
    return {"message": "Conta excluída."}


# ---------------------------------------------------------------------------
# Saldo observado
# ---------------------------------------------------------------------------


class SaldoInformado(SQLModel):
    balance: float
    observed_at: dt.datetime | None = None
    note: str | None = None


class SnapshotRead(SQLModel):
    id: int
    account_id: int
    observed_at: dt.datetime
    balance: float
    source: SnapshotSource
    note: str | None = None
    # Observado − calculado (saldo anterior + movimentos). Nulo sem anterior.
    difference: float | None = None
    accepted_difference: float | None = None
    # O que da diferença ainda ninguém aceitou — é a pendência.
    pending_difference: float | None = None


def _ler_snapshot(session: Session, dono: User, s: AccountBalanceSnapshot) -> SnapshotRead:
    return SnapshotRead(
        id=s.id, account_id=s.account_id, observed_at=dominio.utc(s.observed_at), balance=s.balance,
        source=s.source, note=s.note, difference=dominio.diferenca(session, dono, s),
        accepted_difference=s.accepted_difference, pending_difference=dominio.diferenca_pendente(session, dono, s),
    )


@router_contas.get("/accounts/{account_id}/snapshots")
def listar_saldos(account_id: int, session: Session = Depends(get_session), dono: User = Depends(require_user)) -> list[SnapshotRead]:
    conta = exigir(session, FinancialAccount, account_id, dono, "Conta")
    lista = session.exec(
        consulta(AccountBalanceSnapshot, dono).where(AccountBalanceSnapshot.account_id == conta.id)
    ).all()
    return sorted((_ler_snapshot(session, dono, s) for s in lista), key=lambda x: (x.observed_at, x.id), reverse=True)


@router_contas.post("/accounts/{account_id}/snapshots")
def informar_saldo(
    account_id: int, dados: SaldoInformado, session: Session = Depends(get_session), dono: User = Depends(require_user)
):
    """"Atualizar saldo": registra o que a pessoa viu no banco. Não cria lançamento.

    Se o observado diverge do calculado, a resposta diz quanto — e a diferença
    fica como pendência até alguém revisar os movimentos ou aceitar o ajuste.
    """
    exigir_escrita(dono)
    conta = exigir(session, FinancialAccount, account_id, dono, "Conta")
    if conta.archived:
        raise HTTPException(status_code=400, detail="Conta arquivada não recebe saldo.")
    instante = dominio.utc(dados.observed_at) if dados.observed_at else dominio.agora()
    if instante > dominio.agora() + dt.timedelta(minutes=5):
        raise HTTPException(status_code=400, detail="O saldo observado não pode estar no futuro.")
    snap = AccountBalanceSnapshot(
        user_id=dono.id, account_id=conta.id, observed_at=instante, balance=round(dados.balance, 2),
        source=SnapshotSource.MANUAL, note=(dados.note or "").strip()[:200] or None,
    )
    session.add(snap)
    session.commit()
    session.refresh(snap)
    return {"snapshot": _ler_snapshot(session, dono, snap), "account": _uma(session, dono, conta)}


@router_contas.post("/accounts/{account_id}/snapshots/{snapshot_id}/aceitar")
def aceitar_diferenca(
    account_id: int, snapshot_id: int, session: Session = Depends(get_session), dono: User = Depends(require_user)
) -> SnapshotRead:
    """Aceita a diferença como ajuste de conferência. Nunca vira receita nem
    despesa — fica registrado que alguém olhou e decidiu que o banco está certo."""
    exigir_escrita(dono)
    conta = exigir(session, FinancialAccount, account_id, dono, "Conta")
    snap = exigir(session, AccountBalanceSnapshot, snapshot_id, dono, "Saldo")
    if snap.account_id != conta.id:
        raise HTTPException(status_code=404, detail="Saldo não encontrado.")
    d = dominio.diferenca(session, dono, snap)
    if d is None:
        raise HTTPException(status_code=400, detail="Este é o primeiro saldo da conta; não há diferença a aceitar.")
    snap.accepted_difference = d
    session.add(snap)
    registrar(session, acao="saldo.diferenca_aceita", ator=ator_api(dono.email), user_id=dono.id,
              entidade="account_balance_snapshot", entidade_id=snap.id,
              detalhes={"conta": conta.name, "diferenca": d, "saldo_observado": snap.balance})
    session.commit()
    session.refresh(snap)
    return _ler_snapshot(session, dono, snap)


@router_contas.delete("/accounts/{account_id}/snapshots/{snapshot_id}")
def excluir_saldo(
    account_id: int, snapshot_id: int, session: Session = Depends(get_session), dono: User = Depends(require_user)
):
    exigir_escrita(dono)
    conta = exigir(session, FinancialAccount, account_id, dono, "Conta")
    snap = exigir(session, AccountBalanceSnapshot, snapshot_id, dono, "Saldo")
    if snap.account_id != conta.id:
        raise HTTPException(status_code=404, detail="Saldo não encontrado.")
    session.delete(snap)
    session.commit()
    return {"message": "Saldo excluído."}


class MovimentoRead(SQLModel):
    date: dt.date
    occurred_at: dt.datetime | None = None
    amount: float
    kind: str
    description: str
    source: str
    source_id: int
    after_observation: bool


@router_contas.get("/accounts/{account_id}/movimentos")
def movimentos_da_conta(
    account_id: int, limite: int = Query(default=60, ge=1, le=500),
    session: Session = Depends(get_session), dono: User = Depends(require_user),
) -> list[MovimentoRead]:
    """Os movimentos da conta, do mais recente — o "Revisar movimentos"."""
    conta = exigir(session, FinancialAccount, account_id, dono, "Conta")
    atual = dominio.saldos(session, dono, contas=[conta])[0]
    lista = sorted(dominio.movimentos(session, dono, {conta.id}),
                   key=lambda m: (m.data, m.ocorrido_em or dt.datetime.min.replace(tzinfo=dt.timezone.utc)),
                   reverse=True)[:limite]
    return [
        MovimentoRead(
            date=m.data, occurred_at=m.ocorrido_em, amount=round(m.valor, 2), kind=m.tipo, description=m.descricao,
            source=m.origem, source_id=m.origem_id,
            after_observation=atual.observado_em is not None and dominio.depois(m.data, m.ocorrido_em, atual.observado_em),
        )
        for m in lista
    ]


# ---------------------------------------------------------------------------
# Saldo agregado
# ---------------------------------------------------------------------------


class Parte(SQLModel):
    account_id: int
    amount: float


class Distribuicao(SQLModel):
    destinos: list[Parte]
    note: str | None = None


@router_contas.post("/accounts/{account_id}/distribuir")
def distribuir_saldo_agregado(
    account_id: int, dados: Distribuicao, session: Session = Depends(get_session), dono: User = Depends(require_user)
) -> AccountsSummary:
    exigir_escrita(dono)
    agregado = exigir(session, FinancialAccount, account_id, dono, "Conta")
    destinos = [(exigir(session, FinancialAccount, p.account_id, dono, "Conta"), round(p.amount, 2)) for p in dados.destinos]
    dominio.distribuir(session, dono, agregado, destinos, ator_api(dono.email), dados.note)
    session.commit()
    return resumo_das_contas(session, dono)


# ---------------------------------------------------------------------------
# Transferências
# ---------------------------------------------------------------------------


class TransferRead(SQLModel):
    id: int
    from_account_id: int
    to_account_id: int
    from_name: str
    to_name: str
    amount: float
    date: dt.date
    occurred_at: dt.datetime | None = None
    description: str | None = None
    note: str | None = None


def _ler_transferencia(session: Session, dono: User, t: Transfer) -> TransferRead:
    nomes = {c.id: c.name for c in session.exec(consulta(FinancialAccount, dono)).all()}
    return TransferRead(**t.model_dump(exclude={"user_id", "created_at"}),
                        from_name=nomes.get(t.from_account_id, "?"), to_name=nomes.get(t.to_account_id, "?"))


@router_contas.get("/transfers")
def listar_transferencias(
    year: int | None = Query(default=None, ge=1900, le=2999),
    month: int | None = Query(default=None, ge=1, le=12),
    session: Session = Depends(get_session), dono: User = Depends(require_user),
) -> list[TransferRead]:
    q = consulta(Transfer, dono)
    if year is not None and month is not None:
        inicio = dt.date(year, month, 1)
        fim = dt.date(year + (month == 12), month % 12 + 1, 1)
        q = q.where(Transfer.date >= inicio, Transfer.date < fim)
    return [_ler_transferencia(session, dono, t) for t in session.exec(q.order_by(Transfer.date.desc(), Transfer.id.desc())).all()]


@router_contas.post("/transfers")
def criar_transferencia(
    dados: TransferCreate, session: Session = Depends(get_session), dono: User = Depends(require_user)
) -> TransferRead:
    """Dinheiro mudando de conta: sem gasto, sem receita, patrimônio igual."""
    exigir_escrita(dono)
    origem = exigir(session, FinancialAccount, dados.from_account_id, dono, "Conta")
    destino = exigir(session, FinancialAccount, dados.to_account_id, dono, "Conta")
    if origem.id == destino.id:
        raise HTTPException(status_code=400, detail="Origem e destino são a mesma conta.")
    if dados.amount <= 0:
        raise HTTPException(status_code=400, detail="O valor da transferência precisa ser maior que zero.")
    if origem.archived or destino.archived:
        raise HTTPException(status_code=400, detail="Conta arquivada não transfere nem recebe.")
    t = Transfer(
        user_id=dono.id, from_account_id=origem.id, to_account_id=destino.id, amount=round(dados.amount, 2),
        date=dados.date, occurred_at=dominio.utc(dados.occurred_at) if dados.occurred_at else None,
        description=(dados.description or "").strip()[:120] or None, note=(dados.note or "").strip()[:200] or None,
    )
    session.add(t)
    session.flush()
    registrar(session, acao="transferencia.criada", ator=ator_api(dono.email), user_id=dono.id,
              entidade="transfer", entidade_id=t.id,
              detalhes={"de": origem.name, "para": destino.name, "valor": t.amount, "data": t.date.isoformat()})
    session.commit()
    session.refresh(t)
    return _ler_transferencia(session, dono, t)


@router_contas.delete("/transfers/{transfer_id}")
def excluir_transferencia(transfer_id: int, session: Session = Depends(get_session), dono: User = Depends(require_user)):
    exigir_escrita(dono)
    t = exigir(session, Transfer, transfer_id, dono, "Transferência")
    registrar(session, acao="transferencia.excluida", ator=ator_api(dono.email), user_id=dono.id,
              entidade="transfer", entidade_id=t.id,
              detalhes={"de": t.from_account_id, "para": t.to_account_id, "valor": t.amount, "data": t.date.isoformat()})
    session.delete(t)
    session.commit()
    return {"message": "Transferência excluída."}


def contas_existem(session: Session, dono: User) -> bool:
    return (session.exec(
        select(func.count(FinancialAccount.id)).where(
            FinancialAccount.user_id == dono.id, FinancialAccount.archived == False  # noqa: E712
        )
    ).one() or 0) > 0
