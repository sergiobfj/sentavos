"""Saldo de conta: o último saldo observado + os movimentos conhecidos depois dele.

Movimento de uma conta é tudo que tem `account_id` dela e mexe em dinheiro
(regra em `dominio/caixa.py`): receita, despesa à vista, aporte, resgate,
pagamento de fatura e transferência. Compra no cartão não é movimento — o
dinheiro sai no pagamento da fatura.

## Qualidade do número (derivada, nunca gravada)

  - **sem saldo**: a conta nunca teve saldo observado. Não entra em total.
  - **reconciliado**: saldo observado há até 31 dias, nada conhecido depois.
  - **calculado**: saldo observado há até 31 dias + movimentos posteriores.
  - **desatualizado**: o último saldo observado tem mais de 31 dias. Continua
    entrando nos totais (com os movimentos aplicados), marcado — a virada do
    mês não some com o dinheiro; o que avisa é a idade da observação.

E, à parte, **pode estar incompleto**: existe movimento realizado SEM conta
depois do saldo observado — o número pode não ter visto um gasto.

## O mesmo dia

O saldo observado tem hora (`observed_at`, com fuso). Lançamento com
`occurred_at` compara pela hora. Lançamento só com data (todo o histórico, e o
que for lançado sem hora): do mesmo dia conta como JÁ DENTRO do saldo
observado naquele dia; de um dia depois, conta como posterior. É a limitação de
`Transaction.date` não ter hora; a tela manda `occurred_at` quando o lançamento
é de hoje, que é o caso comum ("acabei de pagar").
"""

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from fastapi import HTTPException
from sqlmodel import Session

from app.dominio.auditoria import registrar
from app.dominio.caixa import efeito_no_caixa
from app.escopo import consulta, exigir
from app.models import (
    AccountBalanceSnapshot,
    AccountType,
    Category,
    CategoryType,
    FinancialAccount,
    InvoicePayment,
    PaymentMethod,
    SnapshotSource,
    Transaction,
    Transfer,
    User,
)

from app.dominio.tempo import FUSO, agora  # noqa: E402  (relógio único)

DESATUALIZA_EM = dt.timedelta(days=31)
TOLERANCIA = 0.005

RECONCILIADO = "reconciliado"
CALCULADO = "calculado"
DESATUALIZADO = "desatualizado"
SEM_SALDO = "sem_saldo"


def utc(d: dt.datetime) -> dt.datetime:
    """Datetime com fuso, em UTC. Sem fuso (o SQLite devolve assim) é UTC."""
    return d.replace(tzinfo=dt.timezone.utc) if d.tzinfo is None else d.astimezone(dt.timezone.utc)


def dia_local(instante: dt.datetime) -> dt.date:
    return utc(instante).astimezone(FUSO).date()


def fim_do_mes(ano: int, mes: int) -> dt.datetime:
    """Último instante do mês, no fuso local, em UTC."""
    a, m = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return dt.datetime(a, m, 1, tzinfo=FUSO).astimezone(dt.timezone.utc) - dt.timedelta(microseconds=1)


def depois(data: dt.date, ocorrido_em: dt.datetime | None, instante: dt.datetime) -> bool:
    """O movimento aconteceu depois do instante? (ver "O mesmo dia")."""
    if ocorrido_em is not None:
        return utc(ocorrido_em) > utc(instante)
    return data > dia_local(instante)


@dataclass
class Movimento:
    conta_id: int | None
    data: dt.date
    ocorrido_em: dt.datetime | None
    valor: float  # + entra, − sai
    tipo: str  # entrada | saida | aporte | resgate | fatura | transferencia
    descricao: str
    origem: str  # lancamento | fatura | transferencia
    origem_id: int


def _tipo_do_lancamento(tipo: CategoryType, valor: float) -> str:
    if tipo == CategoryType.INCOME:
        return "entrada"
    if tipo == CategoryType.INVESTMENT:
        return "aporte" if valor < 0 else "resgate"
    return "saida"


def movimentos(
    session: Session, dono: User, contas_ids: set[int] | None, desde: dt.date | None = None
) -> list[Movimento]:
    """Movimentos realizados. `contas_ids=None` = os SEM conta (o que falta saber)."""
    tipos = {c.id: CategoryType(c.type) for c in session.exec(consulta(Category, dono)).all()}
    saida: list[Movimento] = []

    q = consulta(Transaction, dono).where(Transaction.amount_paid.is_not(None), Transaction.purchase_id.is_(None))
    if contas_ids is None:
        q = q.where(Transaction.account_id.is_(None))
    else:
        q = q.where(Transaction.account_id.in_(contas_ids or {-1}))
    if desde is not None:
        q = q.where(Transaction.date >= desde)
    for t in session.exec(q).all():
        tipo = tipos.get(t.category_id, CategoryType.EXPENSE)
        valor = efeito_no_caixa(tipo, t.payment_method, float(t.amount_paid or 0.0))
        if abs(valor) <= TOLERANCIA:
            continue
        saida.append(Movimento(t.account_id, t.date, t.occurred_at, valor, _tipo_do_lancamento(tipo, valor),
                               t.description, "lancamento", t.id))

    q = consulta(InvoicePayment, dono)
    if contas_ids is None:
        q = q.where(InvoicePayment.account_id.is_(None))
    else:
        q = q.where(InvoicePayment.account_id.in_(contas_ids or {-1}))
    if desde is not None:
        q = q.where(InvoicePayment.date >= desde)
    for p in session.exec(q).all():
        saida.append(Movimento(p.account_id, p.date, p.occurred_at, -p.amount, "fatura",
                               "Pagamento de fatura", "fatura", p.id))

    if contas_ids is not None:
        q = consulta(Transfer, dono)
        if desde is not None:
            q = q.where(Transfer.date >= desde)
        for tr in session.exec(q).all():
            desc = tr.description or "Transferência"
            if tr.from_account_id in contas_ids:
                saida.append(Movimento(tr.from_account_id, tr.date, tr.occurred_at, -tr.amount,
                                       "transferencia", desc, "transferencia", tr.id))
            if tr.to_account_id in contas_ids:
                saida.append(Movimento(tr.to_account_id, tr.date, tr.occurred_at, tr.amount,
                                       "transferencia", desc, "transferencia", tr.id))
    return saida


@dataclass
class SaldoDaConta:
    conta: FinancialAccount
    saldo: float | None
    qualidade: str
    observado_em: dt.datetime | None
    saldo_observado: float | None
    movimentos_depois: int
    incompleto: bool

    @property
    def conta_no_total(self) -> bool:
        return self.saldo is not None


def _snapshots(session: Session, dono: User, ids: set[int]) -> dict[int, list[AccountBalanceSnapshot]]:
    por_conta: dict[int, list[AccountBalanceSnapshot]] = defaultdict(list)
    if not ids:
        return por_conta
    for s in session.exec(
        consulta(AccountBalanceSnapshot, dono).where(AccountBalanceSnapshot.account_id.in_(ids))
    ).all():
        por_conta[s.account_id].append(s)
    for lista in por_conta.values():
        lista.sort(key=lambda s: (utc(s.observed_at), s.id))
    return por_conta


def ultimo_saldo(snaps: list[AccountBalanceSnapshot], instante: dt.datetime) -> AccountBalanceSnapshot | None:
    validos = [s for s in snaps if utc(s.observed_at) <= utc(instante)]
    return validos[-1] if validos else None


def saldos(
    session: Session,
    dono: User,
    instante: dt.datetime | None = None,
    contas: list[FinancialAccount] | None = None,
) -> list[SaldoDaConta]:
    """O saldo de cada conta no instante (padrão: agora)."""
    instante = instante or agora()
    if contas is None:
        contas = list(session.exec(
            consulta(FinancialAccount, dono).where(FinancialAccount.archived == False)  # noqa: E712
            .order_by(FinancialAccount.id)
        ).all())
    ids = {c.id for c in contas}
    snaps = _snapshots(session, dono, ids)
    ultimos = {cid: ultimo_saldo(snaps.get(cid, []), instante) for cid in ids}
    datas = [dia_local(s.observed_at) for s in ultimos.values() if s is not None]
    desde = min(datas) if datas else None

    por_conta: dict[int, list[Movimento]] = defaultdict(list)
    for m in movimentos(session, dono, ids, desde):
        por_conta[m.conta_id].append(m)
    sem_conta = movimentos(session, dono, None, desde) if desde else []

    resultado = []
    for c in contas:
        s = ultimos.get(c.id)
        if s is None:
            resultado.append(SaldoDaConta(c, None, SEM_SALDO, None, None, 0, False))
            continue
        posteriores = [
            m for m in por_conta.get(c.id, [])
            if depois(m.data, m.ocorrido_em, s.observed_at) and not depois(m.data, m.ocorrido_em, instante)
        ]
        idade = utc(instante) - utc(s.observed_at)
        if idade > DESATUALIZA_EM:
            qualidade = DESATUALIZADO
        else:
            qualidade = CALCULADO if posteriores else RECONCILIADO
        incompleto = any(
            depois(m.data, m.ocorrido_em, s.observed_at) and not depois(m.data, m.ocorrido_em, instante)
            for m in sem_conta
        )
        resultado.append(SaldoDaConta(
            c, round(s.balance + sum(m.valor for m in posteriores), 2), qualidade,
            utc(s.observed_at), s.balance, len(posteriores), incompleto,
        ))
    return resultado


@dataclass
class ResumoDeContas:
    contas: list[SaldoDaConta]
    total: float
    livre: float
    restrito: float
    a_distribuir: float
    desatualizadas: int
    sem_saldo: int
    incompleto: bool
    movimentos_sem_conta: int


def resumo(session: Session, dono: User, instante: dt.datetime | None = None) -> ResumoDeContas:
    """Tenho quanto, onde, e quanto disso é livre. Uma regra só pra todo mundo."""
    lista = saldos(session, dono, instante)
    com_saldo = [s for s in lista if s.saldo is not None]
    total = sum(s.saldo for s in com_saldo)
    restrito = sum(s.saldo for s in com_saldo if s.conta.restricted)
    a_distribuir = sum(s.saldo for s in com_saldo if AccountType(s.conta.type) == AccountType.RECONCILIATION)
    datas = [dia_local(s.observado_em) for s in com_saldo]
    sem_conta = 0
    if datas:
        sem_conta = sum(
            1 for m in movimentos(session, dono, None, min(datas))
            if any(depois(m.data, m.ocorrido_em, s.observado_em) for s in com_saldo)
        )
    return ResumoDeContas(
        contas=lista,
        total=round(total, 2),
        livre=round(total - restrito, 2),
        restrito=round(restrito, 2),
        a_distribuir=round(a_distribuir, 2),
        desatualizadas=sum(1 for s in lista if s.qualidade == DESATUALIZADO),
        sem_saldo=sum(1 for s in lista if s.qualidade == SEM_SALDO),
        incompleto=any(s.incompleto for s in lista),
        movimentos_sem_conta=sem_conta,
    )


# ---------------------------------------------------------------------------
# Diferença entre o observado e o calculado
# ---------------------------------------------------------------------------


def diferenca(session: Session, dono: User, snap: AccountBalanceSnapshot) -> float | None:
    """Observado − (saldo anterior + movimentos entre os dois). Nulo sem anterior.

    Derivada: lançar o gasto que faltava muda a diferença na hora, sem ninguém
    "atualizar" nada.
    """
    lista = _snapshots(session, dono, {snap.account_id}).get(snap.account_id, [])
    anteriores = [s for s in lista if (utc(s.observed_at), s.id) < (utc(snap.observed_at), snap.id)]
    if not anteriores:
        return None
    anterior = anteriores[-1]
    entre = [
        m for m in movimentos(session, dono, {snap.account_id}, dia_local(anterior.observed_at))
        if depois(m.data, m.ocorrido_em, anterior.observed_at) and not depois(m.data, m.ocorrido_em, snap.observed_at)
    ]
    return round(snap.balance - (anterior.balance + sum(m.valor for m in entre)), 2)


def diferenca_pendente(session: Session, dono: User, snap: AccountBalanceSnapshot) -> float | None:
    """A parte da diferença que ninguém aceitou ainda (nula se não há)."""
    d = diferenca(session, dono, snap)
    if d is None:
        return None
    resto = round(d - (snap.accepted_difference or 0.0), 2)
    return resto if abs(resto) > TOLERANCIA else None


# ---------------------------------------------------------------------------
# Validação de conta nos lançamentos
# ---------------------------------------------------------------------------


def conta_valida(
    session: Session, dono: User, account_id: int | None, forma: PaymentMethod | str | None = None
) -> int | None:
    """A conta informada num lançamento, pagamento ou baixa: do dono, ativa, e
    nunca numa compra no cartão (ali quem diz de onde sai é a fatura)."""
    if account_id is None:
        return None
    conta = exigir(session, FinancialAccount, account_id, dono, "Conta")
    if conta.archived:
        raise HTTPException(status_code=400, detail=f"A conta {conta.name} está arquivada.")
    if forma is not None and PaymentMethod(forma) == PaymentMethod.CREDIT:
        raise HTTPException(
            status_code=400,
            detail="Compra no cartão não tem conta: o dinheiro sai no pagamento da fatura.",
        )
    return conta.id


# ---------------------------------------------------------------------------
# Resolver o saldo agregado
# ---------------------------------------------------------------------------


def distribuir(
    session: Session,
    dono: User,
    agregado: FinancialAccount,
    destinos: list[tuple[FinancialAccount, float]],
    ator: str,
    nota: str | None = None,
) -> dict:
    """Diz em quais contas estava o dinheiro do saldo agregado.

    Não é receita, despesa, transferência nem rendimento: é a LOCALIZAÇÃO do
    dinheiro. No mesmo instante, o agregado passa a 0 e cada conta passa a ter
    o que tinha + a parte dela. O total não muda — é a invariante.
    """
    if AccountType(agregado.type) != AccountType.RECONCILIATION:
        raise HTTPException(status_code=400, detail="Só conta de reconciliação (saldo agregado) se distribui.")
    if not destinos:
        raise HTTPException(status_code=400, detail="Informe pelo menos uma conta de destino.")
    ids = [d.id for d, _ in destinos]
    if len(set(ids)) != len(ids) or agregado.id in ids:
        raise HTTPException(status_code=400, detail="Cada conta de destino aparece uma vez, e nunca o próprio agregado.")
    if any(v <= 0 for _, v in destinos):
        raise HTTPException(status_code=400, detail="Cada parte precisa ser maior que zero.")
    if any(d.archived for d, _ in destinos):
        raise HTTPException(status_code=400, detail="Conta arquivada não recebe distribuição.")

    instante = agora()
    atuais = {s.conta.id: s for s in saldos(session, dono, instante, [agregado] + [d for d, _ in destinos])}
    total_agregado = atuais[agregado.id].saldo
    if total_agregado is None:
        raise HTTPException(status_code=400, detail="O saldo agregado não tem saldo observado.")
    soma = round(sum(v for _, v in destinos), 2)
    if abs(soma - total_agregado) > TOLERANCIA:
        raise HTTPException(
            status_code=400,
            detail=f"A distribuição soma R$ {soma:.2f}; o saldo agregado é R$ {total_agregado:.2f}.",
        )

    texto = nota or "Distribuição do saldo agregado"
    partes = []
    for destino, valor in destinos:
        antes = atuais[destino.id].saldo or 0.0
        session.add(AccountBalanceSnapshot(
            user_id=dono.id, account_id=destino.id, observed_at=instante, balance=round(antes + valor, 2),
            source=SnapshotSource.RECONCILIATION, note=texto,
        ))
        partes.append({"conta": destino.name, "conta_id": destino.id, "valor": valor, "antes": antes})
    session.add(AccountBalanceSnapshot(
        user_id=dono.id, account_id=agregado.id, observed_at=instante, balance=0.0,
        source=SnapshotSource.RECONCILIATION, note=texto,
    ))
    registrar(session, acao="saldo_agregado.distribuido", ator=ator, user_id=dono.id,
              entidade="financial_account", entidade_id=agregado.id,
              detalhes={"total": total_agregado, "partes": partes, "nota": nota})
    return {"total": total_agregado, "partes": partes, "instante": instante}
