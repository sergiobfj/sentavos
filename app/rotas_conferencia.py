"""Rotas da conferência do mês ("Organizar outubro").

Revisar e aplicar, item a item. Não existe "importar tudo": cada ação aqui é
uma decisão do dono sobre UM item, e a que cria dado (lançamento, compromisso,
reserva) cria e anota o vínculo numa transação só — sem o passo do meio em que
o lançamento existe mas a conferência ainda diz "pendente".

Router próprio com `Depends(require_user)`; o `test_isolamento.py` percorre
cada rota com o id de outra conta.
"""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, SQLModel

from app.auth import exigir_escrita, require_user
from app.conferencia import Candidato, candidatos
from app.database import get_session
from app.dominio.contas import conta_valida
from app.escopo import buscar, consulta, exigir
from app.models import (
    Category,
    CategoryType,
    Commitment,
    CommitmentCreate,
    Finalidade,
    PaymentMethod,
    Provision,
    ProvisionCreate,
    ReconciliationItem,
    ReconciliationItemBase,
    ReconciliationItemCreate,
    ReconciliationItemUpdate,
    ReconciliationStatus,
    Transaction,
    TransactionCreate,
    User,
)
from app.rotas_planejamento import _opcional, _texto, nova_reserva, novo_compromisso

router_conferencia = APIRouter(dependencies=[Depends(require_user)])


class Vinculo(SQLModel):
    kind: str  # lancamento | compromisso | reserva
    id: int
    description: str
    amount: float | None = None
    date: dt.date | None = None


class ReconciliationItemRead(ReconciliationItemBase):
    id: int
    status: ReconciliationStatus
    source: str
    transaction_id: int | None = None
    commitment_id: int | None = None
    provision_id: int | None = None
    linked: Vinculo | None = None
    # O vínculo aponta pra algo que foi apagado depois. A tela trata como
    # pendente de novo, em vez de dizer "resolvido" com base em nada.
    link_missing: bool = False
    candidates: list[Candidato] = []


def _ler(session: Session, dono: User, item: ReconciliationItem, com_candidatos: bool) -> ReconciliationItemRead:
    vinculo = None
    perdido = False
    if item.transaction_id is not None:
        t = buscar(session, Transaction, item.transaction_id, dono)
        if t is None:
            perdido = True
        else:
            vinculo = Vinculo(
                kind="lancamento",
                id=t.id,
                description=t.description,
                amount=t.amount_paid if t.amount_paid is not None else t.amount_planned,
                date=t.date,
            )
    elif item.commitment_id is not None:
        c = buscar(session, Commitment, item.commitment_id, dono)
        if c is None:
            perdido = True
        else:
            vinculo = Vinculo(kind="compromisso", id=c.id, description=c.description, amount=c.amount, date=c.first_due)
    elif item.provision_id is not None:
        p = buscar(session, Provision, item.provision_id, dono)
        if p is None:
            perdido = True
        else:
            vinculo = Vinculo(kind="reserva", id=p.id, description=p.description, amount=p.amount, date=p.created_on)

    aberto = item.status in (ReconciliationStatus.PENDENTE, ReconciliationStatus.CONFIRMAR) or perdido
    return ReconciliationItemRead(
        **item.model_dump(exclude={"user_id", "created_at"}),
        linked=vinculo,
        link_missing=perdido,
        candidates=candidatos(session, dono, item) if com_candidatos and aberto else [],
    )


@router_conferencia.get("/reconciliation")
def listar(
    year: int = Query(ge=1900, le=2999),
    month: int = Query(ge=1, le=12),
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Os itens do mês, cada um com as correspondências possíveis."""
    itens = session.exec(
        consulta(ReconciliationItem, dono)
        .where(ReconciliationItem.year == year, ReconciliationItem.month == month)
        .order_by(ReconciliationItem.id)
    ).all()
    lidos = [_ler(session, dono, i, com_candidatos=True) for i in itens]
    contagem = {s.value: 0 for s in ReconciliationStatus}
    for i in lidos:
        status = ReconciliationStatus.PENDENTE if i.link_missing else i.status
        contagem[ReconciliationStatus(status).value] += 1
    return {"year": year, "month": month, "counts": contagem, "items": lidos}


@router_conferencia.post("/reconciliation")
def adicionar(
    dados: ReconciliationItemCreate,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Um item digitado na tela — "lembrei de um gasto que não lancei"."""
    exigir_escrita(dono)
    item = ReconciliationItem.model_validate(
        dados,
        update={
            "user_id": dono.id,
            "description": _texto(dados.description, "A descrição"),
            "source": "manual",
        },
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return _ler(session, dono, item, com_candidatos=True)


@router_conferencia.patch("/reconciliation/{item_id}")
def atualizar(
    item_id: int,
    dados: ReconciliationItemUpdate,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Edita, marca "precisa confirmar", ignora ou reabre.

    Reabrir (status pendente) solta o vínculo, mas NÃO apaga o que foi criado:
    o lançamento continua sendo dinheiro que saiu. Apagá-lo é na tela dele.
    """
    exigir_escrita(dono)
    item = exigir(session, ReconciliationItem, item_id, dono, "Item")
    mudancas = dados.model_dump(exclude_unset=True)
    try:
        for chave, valor in mudancas.items():
            if chave == "description":
                valor = _texto(valor, "A descrição")
            elif chave in ("suggestion", "question", "category_hint", "note"):
                valor = _opcional(valor, 500)
            elif chave in ("status", "kind") and valor is None:
                continue
            setattr(item, chave, valor)
    except HTTPException:
        session.rollback()
        raise
    if mudancas.get("status") == ReconciliationStatus.PENDENTE:
        item.transaction_id = item.commitment_id = item.provision_id = None
    session.add(item)
    session.commit()
    session.refresh(item)
    return _ler(session, dono, item, com_candidatos=True)


@router_conferencia.delete("/reconciliation/{item_id}")
def excluir(
    item_id: int,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Tira o item da lista. Nada do que ele vinculou é tocado."""
    exigir_escrita(dono)
    session.delete(exigir(session, ReconciliationItem, item_id, dono, "Item"))
    session.commit()
    return {"message": "Item excluído."}


class PedidoDeVinculo(SQLModel):
    transaction_id: int | None = None
    commitment_id: int | None = None
    note: str | None = None


@router_conferencia.post("/reconciliation/{item_id}/vincular")
def ja_existe(
    item_id: int,
    pedido: PedidoDeVinculo,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """"Já existe": o item é este lançamento (ou este compromisso). Nada é criado."""
    exigir_escrita(dono)
    item = exigir(session, ReconciliationItem, item_id, dono, "Item")
    if (pedido.transaction_id is None) == (pedido.commitment_id is None):
        raise HTTPException(status_code=400, detail="Informe um lançamento OU um compromisso.")
    if pedido.transaction_id is not None:
        exigir(session, Transaction, pedido.transaction_id, dono, "Lançamento")
    else:
        exigir(session, Commitment, pedido.commitment_id, dono, "Compromisso")

    item.transaction_id = pedido.transaction_id
    item.commitment_id = pedido.commitment_id
    item.provision_id = None
    item.status = ReconciliationStatus.RESOLVIDO
    if pedido.note is not None:
        item.note = _opcional(pedido.note, 500)
    session.add(item)
    session.commit()
    session.refresh(item)
    return _ler(session, dono, item, com_candidatos=False)


@router_conferencia.post("/reconciliation/{item_id}/lancamento")
def criar_lancamento(
    item_id: int,
    dados: TransactionCreate,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Cria o lançamento revisado na tela e resolve o item — realizado ou previsto.

    As regras são as do `POST /transactions`: categoria do dono, nada de cartão
    por aqui (compra no cartão é em /purchases), e despesa sem finalidade
    escolhida é pessoal.
    """
    exigir_escrita(dono)
    item = exigir(session, ReconciliationItem, item_id, dono, "Item")
    categoria = buscar(session, Category, dados.category_id, dono)
    if categoria is None:
        raise HTTPException(status_code=400, detail="Category not found")
    if dados.payment_method == PaymentMethod.CREDIT:
        raise HTTPException(
            status_code=400,
            detail="Compra no cartão se registra pelo formulário de compra; depois use 'Já existe'.",
        )
    if dados.amount_paid is None and dados.amount_planned is None:
        raise HTTPException(status_code=400, detail="Informe o valor pago ou o previsto.")

    finalidade = None
    if CategoryType(categoria.type) == CategoryType.EXPENSE:
        finalidade = dados.finalidade or Finalidade.PESSOAL

    lancamento = Transaction.model_validate(
        dados,
        update={
            "user_id": dono.id,
            "description": _texto(dados.description, "A descrição"),
            "finalidade": finalidade,
            "payment_method": dados.payment_method or PaymentMethod.CASH,
            "account_id": conta_valida(session, dono, dados.account_id),
        },
    )
    session.add(lancamento)
    session.flush()

    item.transaction_id = lancamento.id
    item.commitment_id = item.provision_id = None
    item.status = ReconciliationStatus.RESOLVIDO
    session.add(item)
    session.commit()
    session.refresh(item)
    return _ler(session, dono, item, com_candidatos=False)


@router_conferencia.post("/reconciliation/{item_id}/compromisso")
def criar_compromisso(
    item_id: int,
    dados: CommitmentCreate,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Cria o compromisso (a Hunter, o emplacamento) e resolve o item."""
    exigir_escrita(dono)
    item = exigir(session, ReconciliationItem, item_id, dono, "Item")
    c = novo_compromisso(session, dono, dados)
    item.commitment_id = c.id
    item.transaction_id = item.provision_id = None
    item.status = ReconciliationStatus.RESOLVIDO
    session.add(item)
    session.commit()
    session.refresh(item)
    return _ler(session, dono, item, com_candidatos=False)


@router_conferencia.post("/reconciliation/{item_id}/reserva")
def criar_reserva(
    item_id: int,
    dados: ProvisionCreate,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Planejamento que não é gasto ("R$ 688,31 pra reserva") vira reserva."""
    exigir_escrita(dono)
    item = exigir(session, ReconciliationItem, item_id, dono, "Item")
    p = nova_reserva(session, dono, dados)
    item.provision_id = p.id
    item.transaction_id = item.commitment_id = None
    item.status = ReconciliationStatus.RESOLVIDO
    session.add(item)
    session.commit()
    session.refresh(item)
    return _ler(session, dono, item, com_candidatos=False)
