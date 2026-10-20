"""Investimento: o movimento (aporte, resgate, ajuste) e a regra única do rendimento.

## Movimento

Aporte = dinheiro sai de uma conta e entra num ativo. Resgate = o contrário.
Nenhum dos dois é gasto, receita, perda ou rendimento. O lado CAIXA é o
lançamento de categoria investimento (positivo no aporte, negativo no resgate)
— é ele que o saldo do mês e a conta enxergam; o `InvestmentMovement` diz de
qual ativo e de qual conta. Ajuste é principal que entra no ativo sem passar
pelo caixa (saldo que já existia e não estava registrado).

## Rendimento (do mês, no total e por ativo)

    rendimento = (saldo final − saldo inicial) − aportes − ajustes + resgates

Só entra ativo de investimento ATUALIZADO no mês. É "não apurado", com o
motivo, quando falta uma parcela: ativo sem saldo do mês, saldo lançado por
conferência (resgate de valor desconhecido) — nunca um zero inventado, nunca
um prejuízo que é só resgate. "Sem base" no primeiro mês (sem saldo anterior).
Por ativo, só quando todo aporte/resgate do mês está ligado a um ativo.
"""

from collections import defaultdict

from fastapi import HTTPException
from sqlmodel import Session, SQLModel

from app.cartao import limites_do_mes
from app.dominio import patrimonio
from app.dominio.auditoria import registrar as auditar
from app.dominio.contas import conta_valida
from app.escopo import buscar, consulta, exigir
from app.models import (
    INVESTMENT_CLASSES,
    Asset,
    AssetClass,
    Category,
    CategoryType,
    InvestmentMovement,
    InvestmentMovementCreate,
    InvestmentMovementType,
    InvestmentPlan,
    PaymentMethod,
    Transaction,
    User,
)

TOLERANCIA = 0.005
APURADO = "apurado"
NAO_APURADO = "nao_apurado"
SEM_BASE = "sem_base"


def eh_investimento(ativo: Asset) -> bool:
    return AssetClass(ativo.asset_class) in INVESTMENT_CLASSES


def saldo_informado(session: Session, dono: User, ativo_id: int, observado_em) -> None:
    """O saldo observado substitui a pendência, sem inventar posição ou juros."""
    for p in session.exec(consulta(InvestmentPlan, dono).where(
        InvestmentPlan.asset_id == ativo_id, InvestmentPlan.balance_pending == True  # noqa: E712
    ).with_for_update()).all():
        mov = buscar(session, InvestmentMovement, p.movement_id, dono) if p.movement_id else None
        if mov and mov.date <= observado_em:
            p.balance_pending = False
            session.add(p)


# ---------------------------------------------------------------------------
# Movimentos
# ---------------------------------------------------------------------------


def movimento_do_lancamento(session: Session, dono: User, transacao_id: int) -> InvestmentMovement | None:
    return session.exec(
        consulta(InvestmentMovement, dono).where(InvestmentMovement.transaction_id == transacao_id)
    ).first()


def registrar(session: Session, dono: User, dados: InvestmentMovementCreate, ator: str) -> InvestmentMovement:
    """Cria o movimento — ligando um lançamento existente ou criando o lado caixa."""
    ativo = exigir(session, Asset, dados.asset_id, dono, "Ativo")
    if not eh_investimento(ativo):
        raise HTTPException(status_code=400, detail=f"{ativo.name} não é investimento (renda fixa, variável ou cripto).")
    if dados.amount is None or dados.amount <= TOLERANCIA:
        raise HTTPException(status_code=400, detail="O valor do movimento precisa ser maior que zero.")
    valor = round(dados.amount, 2)
    tipo = InvestmentMovementType(dados.type)
    conta_id = conta_valida(session, dono, dados.account_id)
    transacao: Transaction | None = None

    if tipo == InvestmentMovementType.ADJUSTMENT:
        if dados.transaction_id is not None or dados.category_id is not None:
            raise HTTPException(status_code=400, detail="Ajuste não passa pelo caixa: sem lançamento.")
    elif dados.transaction_id is not None:
        transacao = exigir(session, Transaction, dados.transaction_id, dono, "Lançamento")
        categoria = buscar(session, Category, transacao.category_id, dono)
        if categoria is None or CategoryType(categoria.type) != CategoryType.INVESTMENT:
            raise HTTPException(status_code=400, detail="Só lançamento de categoria de investimento vira aporte ou resgate.")
        if transacao.amount_paid is None:
            raise HTTPException(status_code=400, detail="Lançamento só previsto: o dinheiro ainda não se moveu.")
        aporte = transacao.amount_paid > 0
        if aporte != (tipo == InvestmentMovementType.CONTRIBUTION):
            raise HTTPException(
                status_code=400,
                detail="O sinal do lançamento não bate: aporte é valor positivo, resgate é negativo.",
            )
        if abs(abs(transacao.amount_paid) - valor) > TOLERANCIA:
            raise HTTPException(status_code=400, detail=f"O lançamento é de R$ {abs(transacao.amount_paid):.2f}, não de R$ {valor:.2f}.")
        if movimento_do_lancamento(session, dono, transacao.id) is not None:
            raise HTTPException(status_code=409, detail="Esse lançamento já é o movimento de um ativo.")
        if conta_id is not None and transacao.account_id not in (None, conta_id):
            raise HTTPException(status_code=400, detail="O lançamento já tem outra conta.")
        if conta_id is not None and transacao.account_id is None:
            transacao.account_id = conta_id
            session.add(transacao)
        conta_id = conta_id or transacao.account_id
    else:
        if dados.category_id is None:
            raise HTTPException(status_code=400, detail="Escolha a categoria de investimento do lançamento.")
        categoria = exigir(session, Category, dados.category_id, dono, "Categoria")
        if CategoryType(categoria.type) != CategoryType.INVESTMENT:
            raise HTTPException(status_code=400, detail="A categoria precisa ser de investimento.")
        rotulo = "Aporte" if tipo == InvestmentMovementType.CONTRIBUTION else "Resgate"
        transacao = Transaction(
            user_id=dono.id, date=dados.date,
            description=(dados.description or "").strip()[:120] or f"{rotulo} — {ativo.name}",
            amount_paid=valor if tipo == InvestmentMovementType.CONTRIBUTION else -valor,
            category_id=categoria.id, payment_method=PaymentMethod.CASH, account_id=conta_id,
            occurred_at=dados.occurred_at, note=(dados.note or None),
        )
        session.add(transacao)
        session.flush()

    mov = InvestmentMovement(
        user_id=dono.id, asset_id=ativo.id, type=tipo, amount=valor, date=transacao.date if transacao else dados.date,
        account_id=conta_id, note=(dados.note or "").strip()[:200] or None,
        transaction_id=transacao.id if transacao else None,
    )
    session.add(mov)
    session.flush()
    auditar(session, acao="investimento.movimento_criado", ator=ator, user_id=dono.id,
            entidade="investment_movement", entidade_id=mov.id,
            detalhes={"ativo": ativo.name, "tipo": tipo.value, "valor": valor,
                      "lancamento": mov.transaction_id, "conta": conta_id})
    return mov


def sincronizar_lancamento(session: Session, dono: User, transacao: Transaction) -> None:
    """Depois de editar um lançamento que é movimento: mantém o par coerente,
    ou recusa a edição que o desfiguraria (virar despesa, trocar o sinal)."""
    mov = movimento_do_lancamento(session, dono, transacao.id)
    if mov is None:
        return
    categoria = buscar(session, Category, transacao.category_id, dono)
    if categoria is None or CategoryType(categoria.type) != CategoryType.INVESTMENT or transacao.amount_paid is None:
        raise HTTPException(
            status_code=409,
            detail="Este lançamento é um aporte/resgate de um ativo. Desvincule no Investir antes de mudar o tipo.",
        )
    aporte = transacao.amount_paid > 0
    if aporte != (InvestmentMovementType(mov.type) == InvestmentMovementType.CONTRIBUTION):
        raise HTTPException(status_code=409, detail="Trocar o sinal transformaria aporte em resgate (ou o contrário).")
    mov.amount = round(abs(transacao.amount_paid), 2)
    mov.date = transacao.date
    mov.account_id = transacao.account_id
    session.add(mov)


# ---------------------------------------------------------------------------
# Rendimento
# ---------------------------------------------------------------------------


class InvestmentAssetItem(SQLModel):
    asset_id: int
    name: str
    asset_class: AssetClass
    value: float
    previous: float
    stale: bool = False
    as_of: str | None = None
    reconciliation_note: str | None = None
    cdi_percent: float | None = None
    expected_yield: float | None = None
    share: float | None = None  # fração do total atualizado
    contributed: float = 0
    redeemed: float = 0
    adjusted: float = 0
    yield_amount: float | None = None
    yield_status: str = NAO_APURADO


class InvestmentSummary(SQLModel):
    year: int
    month: int
    items: list[InvestmentAssetItem]
    total: float  # só ativos atualizados
    previous_total: float
    variation: float | None = None  # nula com ativo desatualizado
    contributed: float = 0
    redeemed: float = 0
    adjusted: float = 0
    yield_amount: float | None = None
    yield_status: str = NAO_APURADO
    reasons: list[str] = []
    expected_yield: float | None = None
    # Aporte/resgate do mês sem ativo ligado: o rendimento POR ATIVO fica sem conta.
    unlinked: int = 0
    stale_names: list[str] = []
    stale_total: float = 0


def resumo(session: Session, dono: User, ano: int, mes: int, nome_do_mes: str | None = None) -> InvestmentSummary:
    base = patrimonio.resumo(session, dono, ano, mes)
    itens = [i for i in base.items if AssetClass(i.asset_class) in INVESTMENT_CLASSES]
    atuais = [i for i in itens if not i.stale]
    desatualizados = [i for i in itens if i.stale]
    total = sum(i.value for i in atuais)
    anterior = sum(i.previous for i in atuais)

    inicio, fim = limites_do_mes(ano, mes)
    tipos = {c.id: CategoryType(c.type) for c in session.exec(consulta(Category, dono)).all()}
    lancamentos = [
        t for t in session.exec(
            consulta(Transaction, dono).where(Transaction.date >= inicio, Transaction.date < fim,
                                              Transaction.amount_paid.is_not(None))
        ).all()
        if tipos.get(t.category_id) == CategoryType.INVESTMENT
    ]
    aportado = sum(t.amount_paid for t in lancamentos if t.amount_paid > 0)
    resgatado = sum(-t.amount_paid for t in lancamentos if t.amount_paid < 0)
    movimentos = list(session.exec(
        consulta(InvestmentMovement, dono).where(InvestmentMovement.date >= inicio, InvestmentMovement.date < fim)
    ).all())
    movimentos_ids = {m.id for m in movimentos}
    pendentes_saldo = {p.asset_id for p in session.exec(consulta(InvestmentPlan, dono).where(
        InvestmentPlan.status == "completed", InvestmentPlan.balance_pending == True  # noqa: E712
    )).all() if p.movement_id in movimentos_ids}
    ligados = {m.transaction_id for m in movimentos if m.transaction_id}
    sem_ativo = sum(1 for t in lancamentos if t.id not in ligados)
    ajustado = sum(m.amount for m in movimentos if InvestmentMovementType(m.type) == InvestmentMovementType.ADJUSTMENT)

    por_ativo: dict[int, dict[str, float]] = defaultdict(lambda: {"c": 0.0, "r": 0.0, "a": 0.0})
    for m in movimentos:
        chave = {"contribution": "c", "redemption": "r", "adjustment": "a"}[InvestmentMovementType(m.type).value]
        por_ativo[m.asset_id][chave] += m.amount

    mes_txt = nome_do_mes or f"{mes:02d}/{ano}"
    motivos = [f"{i.name} — {i.reconciliation_note}" for i in itens if i.reconciliation_note]
    motivos.extend(f"Atualize o saldo de {i.name} após o movimento realizado." for i in itens if i.asset_id in pendentes_saldo)
    if desatualizados:
        motivos.append(f"Falta o saldo de {mes_txt} de {', '.join(i.name for i in desatualizados)}.")
    if motivos:
        status, rendeu = NAO_APURADO, None
    elif anterior <= TOLERANCIA:
        status, rendeu = SEM_BASE, None
        motivos = ["Sem saldo no mês anterior pra comparar."]
    else:
        status = APURADO
        rendeu = round(total - anterior - aportado - ajustado + resgatado, 2)

    saida_itens = []
    for i in sorted(itens, key=lambda x: (x.stale, -x.value)):
        mv = por_ativo.get(i.asset_id, {"c": 0.0, "r": 0.0, "a": 0.0})
        if i.stale or i.reconciliation_note or sem_ativo or i.asset_id in pendentes_saldo:
            st, r = NAO_APURADO, None
        elif i.previous <= TOLERANCIA:
            st, r = SEM_BASE, None
        else:
            st, r = APURADO, round(i.value - i.previous - mv["c"] - mv["a"] + mv["r"], 2)
        saida_itens.append(InvestmentAssetItem(
            asset_id=i.asset_id, name=i.name, asset_class=i.asset_class, value=i.value, previous=i.previous,
            stale=i.stale, as_of=i.as_of, reconciliation_note=i.reconciliation_note or (
                "Saldo a atualizar após o movimento" if i.asset_id in pendentes_saldo else None), cdi_percent=i.cdi_percent,
            expected_yield=i.expected_yield,
            share=(i.value / total) if total > TOLERANCIA and not i.stale else None,
            contributed=round(mv["c"], 2), redeemed=round(mv["r"], 2), adjusted=round(mv["a"], 2),
            yield_amount=r, yield_status=st,
        ))

    esperados = [i.expected_yield for i in atuais if i.expected_yield is not None]
    return InvestmentSummary(
        year=ano, month=mes, items=saida_itens, total=round(total, 2), previous_total=round(anterior, 2),
        variation=None if desatualizados else round(total - anterior, 2),
        contributed=round(aportado, 2), redeemed=round(resgatado, 2), adjusted=round(ajustado, 2),
        yield_amount=rendeu, yield_status=status, reasons=motivos,
        expected_yield=round(sum(esperados), 2) if esperados and status == APURADO else None,
        unlinked=sem_ativo, stale_names=[i.name for i in desatualizados],
        stale_total=round(sum(i.value for i in desatualizados), 2),
    )


def lista_de_movimentos(session: Session, dono: User, ano: int | None, mes: int | None,
                        ativo_id: int | None) -> list[InvestmentMovement]:
    q = consulta(InvestmentMovement, dono)
    if ano is not None and mes is not None:
        inicio, fim = limites_do_mes(ano, mes)
        q = q.where(InvestmentMovement.date >= inicio, InvestmentMovement.date < fim)
    if ativo_id is not None:
        q = q.where(InvestmentMovement.asset_id == ativo_id)
    return list(session.exec(q.order_by(InvestmentMovement.date.desc(), InvestmentMovement.id.desc())).all())

