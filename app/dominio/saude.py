"""Saúde do mês: o que impede o mês de ser confiável, derivado — nada é gravado.

Cada pendência tem um código, uma gravidade e o agrupamento ("6 lançamentos
sem conta", não seis alertas iguais):

  - **revisar** (o número do mês pode estar errado): lançamento sem conta
    depois do saldo observado, diferença de saldo não aceita, resgate sem
    valor conciliado, compromisso vencido sem baixa, fatura atrasada, item da
    conferência esperando decisão;
  - **aviso** (o número está certo, mas incompleto): conta sem saldo ou
    desatualizada, saldo agregado esperando divisão, duplicidade suspeita,
    despesa sem forma de pagamento, aporte sem ativo.

Estado: sem pendência → conciliado; só aviso → parcial; algum revisar →
precisa_revisar. `saldo_do_mes_confiavel` é falso quando falta um resgate:
o "saldo do mês" vê o gasto pago com o dinheiro resgatado e não vê o resgate.
"""

from collections import Counter

from sqlmodel import Session, SQLModel

from app import planejamento
from app.cartao import limites_do_mes
from app.dominio import contas as dominio_contas
from app.dominio import patrimonio, investimentos
from app.escopo import consulta
from app.faturas import totais
from app.models import (
    INVESTMENT_CLASSES,
    AccountBalanceSnapshot,
    AccountType,
    AssetClass,
    Category,
    CategoryType,
    Commitment,
    FinancialAccount,
    Invoice,
    InvestmentMovement,
    OccurrenceStatus,
    ReconciliationItem,
    ReconciliationStatus,
    Transaction,
    User,
)

CONCILIADO = "conciliado"
PARCIAL = "parcial"
PRECISA_REVISAR = "precisa_revisar"
REVISAR = "revisar"
AVISO = "aviso"
TOLERANCIA = 0.005


class ItemDaPendencia(SQLModel):
    label: str
    date: str | None = None
    amount: float | None = None
    ref: int | None = None


class Pendencia(SQLModel):
    code: str
    severity: str  # revisar | aviso
    title: str
    detail: str | None = None
    count: int = 1
    amount: float | None = None
    # Onde se resolve (rota do front). A tela decide como abrir.
    where: str | None = None
    items: list[ItemDaPendencia] = []


class SaudeDoMes(SQLModel):
    year: int
    month: int
    state: str
    issues: list[Pendencia]
    to_review: int
    warnings: int
    # Falso quando um resgate não tem valor conciliado: o saldo do mês vê o
    # gasto e não vê de onde veio o dinheiro.
    trustworthy_balance: bool = True


def _plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


def saude(session: Session, dono: User, ano: int, mes: int) -> SaudeDoMes:
    inicio, fim = limites_do_mes(ano, mes)
    hoje = planejamento.hoje()
    corrente = (ano, mes) == (hoje.year, hoje.month)
    pendencias: list[Pendencia] = []
    tipos = {c.id: CategoryType(c.type) for c in session.exec(consulta(Category, dono)).all()}
    lancamentos = list(session.exec(
        consulta(Transaction, dono).where(Transaction.date >= inicio, Transaction.date < fim)
    ).all())

    # ---------- Contas ----------
    contas = list(session.exec(
        consulta(FinancialAccount, dono).where(FinancialAccount.archived == False)  # noqa: E712
    ).all())
    if contas:
        saldos = dominio_contas.saldos(session, dono, contas=contas)
        observados = [s.observado_em for s in saldos if s.observado_em is not None]
        if observados:
            primeiro = min(observados)
            sem_conta = [
                m for m in dominio_contas.movimentos(session, dono, None, inicio)
                if m.data < fim and dominio_contas.depois(m.data, m.ocorrido_em, primeiro)
            ]
            if sem_conta:
                pendencias.append(Pendencia(
                    code="MISSING_ACCOUNT", severity=REVISAR,
                    title=_plural(len(sem_conta), "lançamento sem conta", "lançamentos sem conta"),
                    detail="Depois do saldo observado: o saldo das contas pode não ter visto estes movimentos.",
                    count=len(sem_conta), amount=round(sum(abs(m.valor) for m in sem_conta), 2),
                    where="/orcamento?aba=lancamentos",
                    items=[ItemDaPendencia(label=m.descricao, date=m.data.isoformat(), amount=round(m.valor, 2),
                                           ref=m.origem_id) for m in sem_conta[:12]],
                ))
        if corrente:
            ruins = [s for s in saldos if s.qualidade in (dominio_contas.SEM_SALDO, dominio_contas.DESATUALIZADO)
                     and AccountType(s.conta.type) != AccountType.RECONCILIATION]
            if ruins:
                pendencias.append(Pendencia(
                    code="STALE_BALANCE", severity=AVISO,
                    title=_plural(len(ruins), "conta sem saldo atualizado", "contas sem saldo atualizado"),
                    detail=", ".join(s.conta.name for s in ruins), count=len(ruins), where="/contas",
                ))
            agregados = [s for s in saldos if AccountType(s.conta.type) == AccountType.RECONCILIATION
                         and (s.saldo or 0) > TOLERANCIA]
            for s in agregados:
                pendencias.append(Pendencia(
                    code="TEMPORARY_AGGREGATE_BALANCE", severity=AVISO,
                    title=f"{s.conta.name} esperando divisão entre as contas", amount=s.saldo, where="/contas",
                ))
        diferencas = []
        for snap in session.exec(consulta(AccountBalanceSnapshot, dono)).all():
            dia = dominio_contas.dia_local(snap.observed_at)
            if inicio <= dia < fim:
                resto = dominio_contas.diferenca_pendente(session, dono, snap)
                if resto is not None:
                    diferencas.append((snap, resto))
        if diferencas:
            nomes = {c.id: c.name for c in contas}
            pendencias.append(Pendencia(
                code="BALANCE_DIFFERENCE", severity=REVISAR,
                title=_plural(len(diferencas), "diferença de saldo sem explicação", "diferenças de saldo sem explicação"),
                detail="Revise os movimentos da conta ou aceite o ajuste de conferência.",
                count=len(diferencas), amount=round(sum(abs(d) for _, d in diferencas), 2), where="/contas",
                items=[ItemDaPendencia(label=nomes.get(s.account_id, "?"), date=dominio_contas.dia_local(s.observed_at).isoformat(),
                                       amount=d, ref=s.account_id) for s, d in diferencas],
            ))

    # ---------- Investimento ----------
    posicoes = investimentos.resumo(session, dono, ano, mes)
    pendentes = [i for i in posicoes.items if i.position_pending]
    if pendentes:
        pendencias.append(Pendencia(
            code="INVESTMENT_BALANCE_PENDING", severity=AVISO,
            title="Posição de investimento a atualizar após movimento realizado",
            detail=", ".join(i.name for i in pendentes), count=len(pendentes), where="/investimentos",
        ))
    resumo_mes = patrimonio.resumo(session, dono, ano, mes)
    notas = [i for i in resumo_mes.items
             if i.reconciliation_note and AssetClass(i.asset_class) in INVESTMENT_CLASSES]
    for i in notas:
        pendencias.append(Pendencia(
            code="UNMATCHED_REDEMPTION", severity=REVISAR, title=f"Resgate sem valor conciliado — {i.name}",
            detail=i.reconciliation_note, where="/investimentos",
        ))
    if session.exec(consulta(InvestmentMovement, dono).limit(1)).first() is not None:
        ligados = {m.transaction_id for m in session.exec(
            consulta(InvestmentMovement, dono).where(InvestmentMovement.date >= inicio, InvestmentMovement.date < fim)
        ).all()}
        soltos = [t for t in lancamentos if tipos.get(t.category_id) == CategoryType.INVESTMENT
                  and t.amount_paid is not None and t.id not in ligados]
        if soltos:
            pendencias.append(Pendencia(
                code="UNLINKED_INVESTMENT", severity=AVISO,
                title=_plural(len(soltos), "aporte/resgate sem ativo", "aportes/resgates sem ativo"),
                count=len(soltos), where="/investimentos",
                items=[ItemDaPendencia(label=t.description, date=t.date.isoformat(), amount=t.amount_paid, ref=t.id)
                       for t in soltos[:12]],
            ))

    # ---------- Compromissos vencidos sem baixa ----------
    compromissos = list(session.exec(consulta(Commitment, dono)).all())
    if compromissos:
        estado = planejamento.carregar_estado(session, dono, [c.id for c in compromissos])
        vencidas = []
        for c in compromissos:
            for numero, venc in planejamento.ocorrencias_ate(c, min(fim, hoje)):
                if venc < inicio and not corrente:
                    continue
                if planejamento.status_da_ocorrencia(c, numero, venc, estado, hoje) == OccurrenceStatus.VENCIDA:
                    vencidas.append((c, numero, venc))
        if vencidas:
            pendencias.append(Pendencia(
                code="OVERDUE_COMMITMENT", severity=REVISAR,
                title=_plural(len(vencidas), "compromisso vencido sem baixa", "compromissos vencidos sem baixa"),
                count=len(vencidas), amount=round(sum(c.amount for c, _, _ in vencidas), 2),
                where="/planejamento/compromissos",
                items=[ItemDaPendencia(label=c.description, date=v.isoformat(), amount=c.amount, ref=c.id)
                       for c, _, v in vencidas[:12]],
            ))

    # ---------- Faturas atrasadas ----------
    agregados_fatura = totais(session, dono)
    atrasadas = []
    for f in session.exec(consulta(Invoice, dono).where(Invoice.due_date >= inicio, Invoice.due_date < fim)).all():
        total, pago, _ = agregados_fatura.get(f.id, (0.0, 0.0, 0))
        if total - pago > TOLERANCIA and f.due_date < hoje:
            atrasadas.append((f, total - pago))
    if atrasadas:
        pendencias.append(Pendencia(
            code="OVERDUE_INVOICE", severity=REVISAR,
            title=_plural(len(atrasadas), "fatura atrasada", "faturas atrasadas"),
            count=len(atrasadas), amount=round(sum(v for _, v in atrasadas), 2), where="/orcamento?aba=faturas",
        ))

    # ---------- Itens da conferência esperando decisão ----------
    itens = [i for i in session.exec(consulta(ReconciliationItem, dono).where(
        ReconciliationItem.year == ano, ReconciliationItem.month == mes)).all()
        if ReconciliationStatus(i.status) in (ReconciliationStatus.PENDENTE, ReconciliationStatus.CONFIRMAR)]
    if itens:
        pendencias.append(Pendencia(
            code="REVIEW_ITEMS", severity=REVISAR,
            title=_plural(len(itens), "item esperando decisão", "itens esperando decisão"),
            count=len(itens), where="/organizar",
        ))

    # ---------- Duplicidade suspeita ----------
    chaves = Counter(
        (t.date, round(t.amount_paid, 2), t.category_id, " ".join(t.description.casefold().split()))
        for t in lancamentos if t.amount_paid is not None and t.purchase_id is None and t.commitment_id is None
    )
    duplicados = [(k, n) for k, n in chaves.items() if n > 1]
    if duplicados:
        pendencias.append(Pendencia(
            code="DUPLICATE_SUSPECT", severity=AVISO,
            title=_plural(len(duplicados), "possível lançamento duplicado", "possíveis lançamentos duplicados"),
            detail="Mesmo dia, valor, categoria e descrição.", count=len(duplicados),
            where="/orcamento?aba=lancamentos",
            items=[ItemDaPendencia(label=k[3], date=k[0].isoformat(), amount=k[1]) for k, _ in duplicados[:12]],
        ))

    # ---------- Despesa sem forma de pagamento ----------
    sem_forma = [t for t in lancamentos if tipos.get(t.category_id) == CategoryType.EXPENSE
                 and t.amount_paid is not None and t.payment_method is None]
    if sem_forma:
        pendencias.append(Pendencia(
            code="NO_PAYMENT_METHOD", severity=AVISO,
            title=_plural(len(sem_forma), "despesa sem forma de pagamento", "despesas sem forma de pagamento"),
            count=len(sem_forma), amount=round(sum(t.amount_paid for t in sem_forma), 2), where="/rever",
        ))

    revisar = sum(1 for p in pendencias if p.severity == REVISAR)
    avisos = len(pendencias) - revisar
    estado = PRECISA_REVISAR if revisar else (PARCIAL if avisos else CONCILIADO)
    return SaudeDoMes(
        year=ano, month=mes, state=estado,
        issues=sorted(pendencias, key=lambda p: (p.severity != REVISAR,)),
        to_review=revisar, warnings=avisos, trustworthy_balance=not notas,
    )
