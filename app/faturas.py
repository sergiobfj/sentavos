"""A fatura montada a partir do banco: totais, status e o resumo de caixa do mês.

`app/cartao.py` responde "que fatura cobra esta compra" com aritmética de datas.
Aqui é o outro lado: dado o que está gravado, quanto cada fatura soma, quanto já
foi pago e quanto de dinheiro de verdade saiu da conta no mês.

## Nada aqui é gravado

Total, pago, restante e status são calculados toda vez. A alternativa — guardar
os números na linha da fatura — cria uma segunda fonte de verdade pro mesmo
dinheiro, e as duas começam iguais e terminam diferentes: basta apagar uma
parcela e esquecer de recalcular. É a mesma decisão que faz a aba de
Investimento não ter dados próprios.

O status tem ainda um segundo motivo pra ser derivado: "atrasada" depende da data
de hoje. Gravado, ele exigiria alguém passando todo dia só pra virar a chave na
data certa — e uma fatura vencida apareceria como aberta até esse alguém passar.

## O cuidado com NULL em SQL

`payment_method != 'credit'` **não** traz as linhas com `payment_method` nulo:
em SQL, `NULL != 'credit'` é NULL, que não é verdadeiro. E nulo é justamente o
estado dos 269 lançamentos anteriores ao cartão. Por isso a soma por forma de
pagamento é agrupada e resolvida em Python, onde nulo é uma chave como outra
qualquer.
"""

import datetime as dt

from sqlmodel import Session, func, select

from app.cartao import ciclo_da_parcela, referencia
from app.escopo import consulta
from app.models import (
    Caixa,
    Card,
    Category,
    CategoryType,
    Invoice,
    InvoicePayment,
    InvoiceRead,
    InvoiceStatus,
    PaymentMethod,
    Purchase,
    Transaction,
    TransactionRead,
    User,
)

# Abaixo disso, a diferença é resíduo de float e não dívida. Meio centavo.
TOLERANCIA = 0.005


def fatura_da_parcela(
    session: Session, dono: User, card: Card, compra: dt.date, numero: int
) -> Invoice:
    """A fatura que cobra a parcela `numero`, criando-a se ainda não existir.

    Find-or-create pelo mesmo motivo do PUT de metas e de saldos: quem chama
    conhece (cartão, período), nunca o id da fatura. A fatura passa a existir
    quando a primeira compra cai nela — não há gerador de faturas vazias.
    """
    fechamento, vencimento = ciclo_da_parcela(
        compra, card.closing_day, card.due_day, numero
    )
    ano, mes = referencia(vencimento)

    existente = session.exec(
        consulta(Invoice, dono).where(
            Invoice.card_id == card.id, Invoice.year == ano, Invoice.month == mes
        )
    ).first()
    if existente:
        return existente

    nova = Invoice(
        user_id=dono.id,
        card_id=card.id,
        year=ano,
        month=mes,
        closing_date=fechamento,
        due_date=vencimento,
    )
    session.add(nova)
    # Sem o flush a fatura não tem id, e é o id que vai na parcela.
    session.flush()
    return nova


def totais(session: Session, dono: User) -> dict[int, tuple[float, float, int]]:
    """{invoice_id: (total, pago, quantidade de itens)} para todas as faturas.

    Duas consultas agregadas para a conta inteira, em vez de duas por fatura.
    A tela de Faturas mostra todos os cartões de uma vez, e a de Início precisa
    do total em aberto — N+1 aqui viraria dezenas de idas ao banco por abertura.
    """
    itens = {
        invoice_id: (float(soma or 0.0), int(qtd))
        for invoice_id, soma, qtd in session.exec(
            select(
                Transaction.invoice_id,
                func.coalesce(func.sum(Transaction.amount_paid), 0.0),
                func.count(Transaction.id),
            )
            .where(Transaction.user_id == dono.id, Transaction.invoice_id.is_not(None))
            .group_by(Transaction.invoice_id)
        ).all()
    }

    pagos = {
        invoice_id: float(soma or 0.0)
        for invoice_id, soma in session.exec(
            select(
                InvoicePayment.invoice_id,
                func.coalesce(func.sum(InvoicePayment.amount), 0.0),
            )
            .where(InvoicePayment.user_id == dono.id)
            .group_by(InvoicePayment.invoice_id)
        ).all()
    }

    return {
        invoice_id: (itens.get(invoice_id, (0.0, 0))[0], pagos.get(invoice_id, 0.0),
                     itens.get(invoice_id, (0.0, 0))[1])
        for invoice_id in set(itens) | set(pagos)
    }


def status_de(total: float, pago: float, vencimento: dt.date, hoje: dt.date) -> InvoiceStatus:
    """Precedência: paga → atrasada → parcial → aberta.

    Vencida com saldo aparece como atrasada mesmo tendo recebido parte: é a
    informação que pede ação. Quanto já foi pago continua na tela ao lado.
    """
    if total - pago <= TOLERANCIA:
        return InvoiceStatus.PAGA
    if hoje > vencimento:
        return InvoiceStatus.ATRASADA
    if pago > TOLERANCIA:
        return InvoiceStatus.PARCIAL
    return InvoiceStatus.ABERTA


def montar(
    fatura: Invoice,
    nome_do_cartao: str,
    agregados: dict[int, tuple[float, float, int]],
    hoje: dt.date,
) -> InvoiceRead:
    total, pago, qtd = agregados.get(fatura.id, (0.0, 0.0, 0))
    return InvoiceRead(
        id=fatura.id,
        card_id=fatura.card_id,
        card_name=nome_do_cartao,
        year=fatura.year,
        month=fatura.month,
        closing_date=fatura.closing_date,
        due_date=fatura.due_date,
        total=round(total, 2),
        paid=round(pago, 2),
        remaining=round(max(total - pago, 0.0), 2),
        status=status_de(total, pago, fatura.due_date, hoje),
        item_count=qtd,
    )


def enriquecer(
    session: Session, dono: User, lancamentos: list[Transaction]
) -> list[TransactionRead]:
    """Junta a cada lançamento o que a tela mostra: cartão e "2 de 10".

    Esses dados moram em `purchases` e `cards`. Resolvê-los linha a linha daria
    uma consulta por parcela; aqui são duas consultas para a lista inteira,
    independentemente do tamanho dela.
    """
    ids_de_compra = {t.purchase_id for t in lancamentos if t.purchase_id}
    if not ids_de_compra:
        return [TransactionRead.model_validate(t, from_attributes=True) for t in lancamentos]

    compras = {
        c.id: c
        for c in session.exec(
            consulta(Purchase, dono).where(Purchase.id.in_(ids_de_compra))
        ).all()
    }
    cartoes = {
        c.id: c
        for c in session.exec(
            consulta(Card, dono).where(
                Card.id.in_({p.card_id for p in compras.values()})
            )
        ).all()
    }

    saida = []
    for t in lancamentos:
        linha = TransactionRead.model_validate(t, from_attributes=True)
        compra = compras.get(t.purchase_id) if t.purchase_id else None
        if compra:
            linha.installments = compra.installments
            linha.purchase_total = compra.total_amount
            linha.purchase_date = compra.purchase_date
            linha.card_id = compra.card_id
            cartao = cartoes.get(compra.card_id)
            linha.card_name = cartao.name if cartao else None
        saida.append(linha)
    return saida


def resumo_de_caixa(
    session: Session, dono: User, ano: int, mes: int, inicio: dt.date, fim: dt.date
) -> Caixa:
    """Os dois eixos do mês: o que foi gasto e o que saiu da conta.

    Eram o mesmo número até o cartão existir. A diferença entre eles é
    exatamente o que foi comprado no cartão e ainda não foi pago.
    """
    # Soma por (tipo de categoria, forma de pagamento). O agrupamento é o que
    # permite tratar NULL como um caso explícito em vez de deixá-lo cair fora
    # de um `!=` em SQL.
    por_forma: dict[tuple[str, str | None], float] = {}
    for tipo, forma, soma in session.exec(
        select(
            Category.type,
            Transaction.payment_method,
            func.coalesce(func.sum(Transaction.amount_paid), 0.0),
        )
        .join(
            Category,
            Transaction.category_id
            == Category.id,
        )
        .where(
            Transaction.user_id == dono.id,
            Transaction.date >= inicio,
            Transaction.date < fim,
        )
        .group_by(
            Category.type,
            Transaction.payment_method,
        )
    ).all():
        chave = (CategoryType(tipo).value, PaymentMethod(forma).value if forma else None)
        por_forma[chave] = por_forma.get(chave, 0.0) + float(soma or 0.0)

    def somar(tipo: str, formas: tuple[str | None, ...]) -> float:
        return sum(por_forma.get((tipo, f), 0.0) for f in formas)

    entrou = somar("income", (None, "cash", "credit"))
    investido = somar("investment", (None, "cash", "credit"))
    no_cartao = somar("expense", ("credit",))
    # Nulo entra no caixa junto com "à vista": é como esses lançamentos já eram
    # contados antes do cartão existir, e mudar isso sem o dono revisar faria a
    # Carteira de todo mês passado trocar de valor da noite pro dia.
    sem_forma = somar("expense", (None,))
    a_vista = somar("expense", ("cash",)) + sem_forma
    gasto_total = a_vista + no_cartao

    sem_forma_qtd = session.exec(
        select(func.count(Transaction.id))
        .join(
            Category,
            Transaction.category_id
            == Category.id,
        )
        .where(
            Transaction.user_id == dono.id,
            Transaction.date >= inicio,
            Transaction.date < fim,
            Transaction.payment_method.is_(None),
            Category.type
            == CategoryType.EXPENSE,
        )
    ).one()

    faturas_pagas = float(
        session.exec(
            select(func.coalesce(func.sum(InvoicePayment.amount), 0.0)).where(
                InvoicePayment.user_id == dono.id,
                InvoicePayment.date >= inicio,
                InvoicePayment.date < fim,
            )
        ).one()
        or 0.0
    )

    agregados = totais(session, dono)
    faturas = session.exec(consulta(Invoice, dono)).all()

    faturas_do_mes = sum(
        agregados.get(f.id, (0.0, 0.0, 0))[0]
        for f in faturas
        if (f.year, f.month) == (ano, mes)
    )
    # Tudo que já está comprometido, de qualquer mês — inclusive as parcelas de
    # meses futuros. É esse o sentido de "após faturas": o dinheiro que ainda
    # está na conta mas já tem destino.
    em_aberto = 0.0
    for f in faturas:
        total, pago, _ = agregados.get(f.id, (0.0, 0.0, 0))
        em_aberto += max(total - pago, 0.0)

    carteira = entrou - a_vista - investido - faturas_pagas

    return Caixa(
        entrou=round(entrou, 2),
        saiu_a_vista=round(a_vista, 2),
        investido=round(investido, 2),
        faturas_pagas=round(faturas_pagas, 2),
        carteira=round(carteira, 2),
        gasto_total=round(gasto_total, 2),
        no_cartao=round(no_cartao, 2),
        sem_forma_definida=round(sem_forma, 2),
        sem_forma_definida_qtd=int(sem_forma_qtd or 0),
        faturas_do_mes=round(faturas_do_mes, 2),
        faturas_em_aberto=round(em_aberto, 2),
        apos_faturas=round(carteira - em_aberto, 2),
    )
