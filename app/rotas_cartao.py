"""Rotas de cartão, compra, fatura e pagamento.

Ficam fora do `main.py` por tamanho — são quase quinhentas linhas, e o main já
tinha oitocentas. O que NÃO pode ficar fora é a proteção: este router nasce com
`Depends(require_user)` igual ao de lá, então rota nova aqui também nasce
fechada. Se um dia alguém criar um terceiro router sem essa linha, o
`test_isolamento.py` quebra — é ele, e não o comentário, que garante isto.

## As três recusas que este arquivo faz de propósito

Um app de dinheiro erra melhor recusando do que adivinhando. Aqui:

  - **parcela não se edita nem se apaga sozinha**. Apagar a 2 de 3 deixaria uma
    compra de R$ 900 valendo R$ 600 sem ninguém ter decidido isso. A operação é
    na compra inteira.
  - **compra com fatura paga não muda de valor, de parcelas nem de cartão**.
    Mudar reescreveria uma fatura que já foi cobrada e paga — o extrato do banco
    não se reescreve junto.
  - **pagamento maior que o restante é recusado**. Quase sempre é dedo errado, e
    o custo de recusar é digitar de novo.

A reconciliação (`/invoices/{id}/reconciliar`) é a exceção deliberada a essa
última: ali o valor vem de um lançamento antigo e não precisa bater com a fatura
reconstruída.
"""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, SQLModel, func, select

from app.auth import exigir_escrita, require_user
from app.cartao import avancar_meses, dividir_em_parcelas, competencia_da_parcela
from app.database import get_session
from app.escopo import buscar, consulta, exigir
from app.faturas import fatura_da_parcela, montar, totais
from app.models import (
    Card,
    CardCreate,
    CardInvoices,
    CardUpdate,
    Category,
    CategoryType,
    Invoice,
    InvoiceDetail,
    InvoiceItem,
    InvoicePayment,
    InvoicePaymentCreate,
    InvoicePaymentRead,
    InvoiceRead,
    InvoicesSummary,
    PaymentMethod,
    Purchase,
    PurchaseCreate,
    PurchaseRead,
    PurchaseUpdate,
    Transaction,
    User,
)

router_cartao = APIRouter(dependencies=[Depends(require_user)])


def hoje() -> dt.date:
    return dt.date.today()


# ---------- Cartões ----------


@router_cartao.post("/cards")
def criar_cartao(
    dados: CardCreate,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    exigir_escrita(dono)
    nome = dados.name.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="O cartão precisa de um nome.")

    cartao = Card.model_validate(dados, update={"user_id": dono.id, "name": nome})
    session.add(cartao)
    session.commit()
    session.refresh(cartao)
    return cartao


@router_cartao.get("/cards")
def listar_cartoes(
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
    incluir_arquivados: bool = Query(default=False),
):
    """Os cartões ativos. Arquivados só com `incluir_arquivados=1`.

    Mesmo arranjo das categorias: quem chama isto quase sempre é o formulário de
    lançamento, e cartão que você não usa mais não deve aparecer lá — mas
    continua existindo, porque as compras antigas apontam pra ele.
    """
    query = consulta(Card, dono)
    if not incluir_arquivados:
        query = query.where(Card.archived == False)  # noqa: E712
    return session.exec(query.order_by(Card.archived, Card.name)).all()


@router_cartao.patch("/cards/{card_id}")
def atualizar_cartao(
    card_id: int,
    dados: CardUpdate,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Muda o cartão daqui pra frente. As faturas já existentes não se mexem.

    Trocar o dia de fechamento não remonta fatura antiga de propósito: elas
    guardam as próprias datas justamente pra isso. Uma fatura que já foi cobrada
    com o ciclo velho continua sendo o que foi.
    """
    exigir_escrita(dono)
    cartao = exigir(session, Card, card_id, dono, "Cartão")

    for chave, valor in dados.model_dump(exclude_unset=True).items():
        if chave == "name":
            valor = (valor or "").strip()
            if not valor:
                raise HTTPException(status_code=400, detail="O cartão precisa de um nome.")
        setattr(cartao, chave, valor)

    session.add(cartao)
    session.commit()
    session.refresh(cartao)
    return cartao


@router_cartao.delete("/cards/{card_id}")
def excluir_cartao(
    card_id: int,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Só apaga cartão sem histórico. Com compra, a saída é arquivar.

    Mesma regra da categoria com lançamento: apagar levaria junto as compras, as
    faturas e os pagamentos — dado que o dono não pediu pra perder.
    """
    exigir_escrita(dono)
    cartao = exigir(session, Card, card_id, dono, "Cartão")

    compras = session.exec(
        select(func.count())
        .select_from(Purchase)
        .where(Purchase.user_id == dono.id, Purchase.card_id == card_id)
    ).one()

    if compras:
        raise HTTPException(
            status_code=409,
            detail=(
                f"'{cartao.name}' tem {compras} compra(s) registrada(s). "
                "Arquive o cartão em vez de apagá-lo — assim o histórico continua de pé."
            ),
        )

    # Faturas vazias podem ter sobrado de uma compra apagada; saem junto.
    for fatura in session.exec(consulta(Invoice, dono).where(Invoice.card_id == card_id)).all():
        session.delete(fatura)
    session.flush()

    session.delete(cartao)
    session.commit()
    return {"message": "Cartão excluído."}


# ---------- Compras ----------


def _categoria_de_despesa(session: Session, dono: User, category_id: int) -> Category:
    categoria = buscar(session, Category, category_id, dono)
    if not categoria:
        raise HTTPException(status_code=400, detail="Category not found")
    if categoria.type != CategoryType.EXPENSE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{categoria.name}' é {categoria.type.value}. "
                "Compra no cartão é despesa — receita e investimento não passam por fatura."
            ),
        )
    return categoria


def _faturas_da_compra(session: Session, dono: User, compra: Purchase) -> list[Invoice]:
    ids = {
        t.invoice_id
        for t in session.exec(
            consulta(Transaction, dono).where(Transaction.purchase_id == compra.id)
        ).all()
        if t.invoice_id
    }
    if not ids:
        return []
    return session.exec(consulta(Invoice, dono).where(Invoice.id.in_(ids))).all()


def _parcelas_pagas(session: Session, dono: User, compra: Purchase) -> int:
    """Quantas parcelas desta compra estão em fatura que já recebeu pagamento.

    É o que decide se a compra pode mudar de valor. Basta UMA fatura paga: o
    dinheiro daquela já saiu, e mexer no valor dela criaria uma diferença que o
    extrato do banco não tem."""
    faturas = _faturas_da_compra(session, dono, compra)
    if not faturas:
        return 0

    # `session.exec` com uma coluna só devolve o valor, não uma tupla de um.
    com_pagamento = {
        invoice_id
        for invoice_id in session.exec(
            select(InvoicePayment.invoice_id)
            .where(
                InvoicePayment.user_id == dono.id,
                InvoicePayment.invoice_id.in_([f.id for f in faturas]),
            )
            .distinct()
        ).all()
    }
    if not com_pagamento:
        return 0

    return session.exec(
        select(func.count())
        .select_from(Transaction)
        .where(
            Transaction.user_id == dono.id,
            Transaction.purchase_id == compra.id,
            Transaction.invoice_id.in_(com_pagamento),
        )
    ).one()


def _limpar_faturas_vazias(session: Session, dono: User, faturas: list[Invoice]) -> None:
    """Apaga fatura que ficou sem item nenhum e sem pagamento.

    Uma fatura existe porque uma compra caiu nela. Desfeita a compra, deixá-la
    no banco encheria a aba de Faturas de meses com R$ 0,00 — e "fatura de
    outubro: R$ 0,00" é diferente de "não teve fatura em outubro".
    """
    for fatura in faturas:
        itens = session.exec(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.user_id == dono.id, Transaction.invoice_id == fatura.id)
        ).one()
        pagamentos = session.exec(
            select(func.count())
            .select_from(InvoicePayment)
            .where(
                InvoicePayment.user_id == dono.id,
                InvoicePayment.invoice_id == fatura.id,
            )
        ).one()
        if not itens and not pagamentos:
            session.delete(fatura)
    session.flush()


def _gerar_parcelas(session: Session, dono: User, compra: Purchase, cartao: Card) -> None:
    """Cria as N parcelas da compra, cada uma na sua competência e na sua fatura.

    `amount_paid` recebe o valor da parcela e `amount_planned` fica vazio: a
    parcela é gasto REALIZADO no mês dela, mesmo que o mês ainda não tenha
    chegado. Foi decidido comprando — é isso que parcelar significa.
    """
    valores = dividir_em_parcelas(compra.total_amount, compra.installments)

    for numero, valor in enumerate(valores, start=1):
        fatura = fatura_da_parcela(session, dono, cartao, compra.purchase_date, numero)
        session.add(
            Transaction(
                user_id=dono.id,
                date=competencia_da_parcela(compra.purchase_date, numero),
                description=compra.description,
                amount_planned=None,
                amount_paid=valor,
                note=compra.note,
                category_id=compra.category_id,
                payment_method=PaymentMethod.CREDIT,
                purchase_id=compra.id,
                installment_no=numero,
                invoice_id=fatura.id,
            )
        )


def _ler_compra(session: Session, dono: User, compra: Purchase) -> PurchaseRead:
    cartao = buscar(session, Card, compra.card_id, dono)
    categoria = buscar(session, Category, compra.category_id, dono)
    pagas = _parcelas_pagas(session, dono, compra)

    return PurchaseRead(
        # `id`, `user_id` e `created_at` ficam de fora: os dois últimos não
        # existem no modelo de leitura, e o primeiro é passado logo abaixo.
        **compra.model_dump(exclude={"id", "user_id", "created_at"}),
        id=compra.id,
        card_name=cartao.name if cartao else "?",
        category_name=categoria.name if categoria else "?",
        color=categoria.color if categoria else "#666",
        icon=categoria.icon if categoria else "•",
        installment_amounts=dividir_em_parcelas(compra.total_amount, compra.installments),
        paid_installments=pagas,
        locked=pagas > 0,
    )


@router_cartao.post("/purchases")
def criar_compra(
    dados: PurchaseCreate,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Uma compra no cartão: vira N parcelas, cada uma na fatura do seu ciclo.

    É rota própria e não `POST /transactions` porque o que entra não é um
    lançamento — é uma compra que *gera* lançamentos, além de descobrir (ou
    criar) as faturas que vão cobrá-los.
    """
    exigir_escrita(dono)

    cartao = buscar(session, Card, dados.card_id, dono)
    if not cartao:
        raise HTTPException(status_code=400, detail="Card not found")
    _categoria_de_despesa(session, dono, dados.category_id)

    if dados.total_amount <= 0:
        raise HTTPException(
            status_code=400, detail="O valor da compra precisa ser maior que zero."
        )
    if not dados.description.strip():
        raise HTTPException(status_code=400, detail="A compra precisa de uma descrição.")

    compra = Purchase.model_validate(
        dados, update={"user_id": dono.id, "description": dados.description.strip()}
    )
    session.add(compra)
    # Flush pra a compra ter id antes das parcelas apontarem pra ela.
    session.flush()

    _gerar_parcelas(session, dono, compra, cartao)
    session.commit()
    session.refresh(compra)

    return _ler_compra(session, dono, compra)


@router_cartao.get("/purchases/{purchase_id}")
def ver_compra(
    purchase_id: int,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    compra = exigir(session, Purchase, purchase_id, dono, "Compra")
    return _ler_compra(session, dono, compra)


# Os três campos que mexem em dinheiro. Rótulo (descrição, categoria,
# observação) muda sempre; estes só enquanto nada foi pago.
CAMPOS_FINANCEIROS = {"total_amount", "installments", "card_id", "purchase_date"}


@router_cartao.patch("/purchases/{purchase_id}")
def atualizar_compra(
    purchase_id: int,
    dados: PurchaseUpdate,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Edita a compra. Rótulo sempre; dinheiro só antes de qualquer pagamento."""
    exigir_escrita(dono)
    compra = exigir(session, Purchase, purchase_id, dono, "Compra")
    mudancas = dados.model_dump(exclude_unset=True)

    mexe_em_dinheiro = {
        chave
        for chave in mudancas
        if chave in CAMPOS_FINANCEIROS and mudancas[chave] != getattr(compra, chave)
    }

    if mexe_em_dinheiro:
        pagas = _parcelas_pagas(session, dono, compra)
        if pagas:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"'{compra.description}' já tem {pagas} parcela(s) em fatura paga. "
                    "Valor, parcelas, cartão e data não mudam depois do pagamento — "
                    "mudar reescreveria uma fatura que já foi cobrada. "
                    "Dá pra alterar a descrição, a categoria e a observação."
                ),
            )

    if "category_id" in mudancas:
        _categoria_de_despesa(session, dono, mudancas["category_id"])
    if "card_id" in mudancas and not buscar(session, Card, mudancas["card_id"], dono):
        raise HTTPException(status_code=400, detail="Card not found")
    if "total_amount" in mudancas and mudancas["total_amount"] is not None and mudancas["total_amount"] <= 0:
        raise HTTPException(
            status_code=400, detail="O valor da compra precisa ser maior que zero."
        )

    for chave, valor in mudancas.items():
        if chave == "description":
            valor = (valor or "").strip()
            if not valor:
                raise HTTPException(status_code=400, detail="A compra precisa de uma descrição.")
        setattr(compra, chave, valor)
    session.add(compra)
    session.flush()

    if mexe_em_dinheiro:
        # Refazer, e não remendar: mudar o número de parcelas ou o cartão muda
        # quais faturas cobram o quê, e tentar ajustar linha a linha é onde
        # sobra parcela órfã de uma versão anterior da compra.
        antigas = _faturas_da_compra(session, dono, compra)
        for parcela in session.exec(
            consulta(Transaction, dono).where(Transaction.purchase_id == compra.id)
        ).all():
            session.delete(parcela)
        session.flush()

        cartao = buscar(session, Card, compra.card_id, dono)
        _gerar_parcelas(session, dono, compra, cartao)
        session.flush()
        _limpar_faturas_vazias(session, dono, antigas)
    else:
        # Rótulo desce pras parcelas: elas é que aparecem na lista do mês.
        for parcela in session.exec(
            consulta(Transaction, dono).where(Transaction.purchase_id == compra.id)
        ).all():
            parcela.description = compra.description
            parcela.category_id = compra.category_id
            parcela.note = compra.note
            session.add(parcela)

    session.commit()
    session.refresh(compra)
    return _ler_compra(session, dono, compra)


@router_cartao.delete("/purchases/{purchase_id}")
def excluir_compra(
    purchase_id: int,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Apaga a compra e todas as suas parcelas. Recusa se alguma já foi paga."""
    exigir_escrita(dono)
    compra = exigir(session, Purchase, purchase_id, dono, "Compra")

    pagas = _parcelas_pagas(session, dono, compra)
    if pagas:
        raise HTTPException(
            status_code=409,
            detail=(
                f"'{compra.description}' já tem {pagas} parcela(s) em fatura paga. "
                "Apagar mudaria o valor de uma fatura que já foi cobrada. "
                "Se a compra não existiu mesmo, desfaça o pagamento da fatura primeiro."
            ),
        )

    faturas = _faturas_da_compra(session, dono, compra)
    for parcela in session.exec(
        consulta(Transaction, dono).where(Transaction.purchase_id == compra.id)
    ).all():
        session.delete(parcela)
    # Sem Relationship declarado o SQLAlchemy não sabe a ordem; o flush garante
    # que as parcelas saiam antes da compra, senão a FK barra no Postgres.
    session.flush()

    session.delete(compra)
    session.flush()
    _limpar_faturas_vazias(session, dono, faturas)

    session.commit()
    return {"message": "Compra excluída.", "parcelas": len(faturas)}


# ---------- Faturas ----------


def _pagamentos_read(
    session: Session, dono: User, pagamentos: list[InvoicePayment]
) -> list[InvoicePaymentRead]:
    if not pagamentos:
        return []
    faturas = {
        f.id: f
        for f in session.exec(
            consulta(Invoice, dono).where(
                Invoice.id.in_({p.invoice_id for p in pagamentos})
            )
        ).all()
    }
    cartoes = {
        c.id: c
        for c in session.exec(
            consulta(Card, dono).where(
                Card.id.in_({f.card_id for f in faturas.values()})
            )
        ).all()
    }
    saida = []
    for p in pagamentos:
        fatura = faturas.get(p.invoice_id)
        cartao = cartoes.get(fatura.card_id) if fatura else None
        saida.append(
            InvoicePaymentRead(
                id=p.id,
                invoice_id=p.invoice_id,
                date=p.date,
                amount=p.amount,
                note=p.note,
                card_id=fatura.card_id if fatura else 0,
                card_name=cartao.name if cartao else "?",
                invoice_year=fatura.year if fatura else 0,
                invoice_month=fatura.month if fatura else 0,
            )
        )
    return saida


# Declarada antes de /invoices/{invoice_id} pra "summary" não virar id.
@router_cartao.get("/invoices/summary", response_model=InvoicesSummary)
def resumo_de_faturas(
    year: int = Query(ge=1900, le=2999),
    month: int = Query(ge=1, le=12),
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """O que a aba de Faturas mostra: um cartão por linha, com a fatura do mês.

    Traz junto os pagamentos do mês, porque a lista de lançamentos os mescla e o
    Início precisa deles pra Carteira — três telas, uma chamada.
    """
    agora = hoje()
    agregados = totais(session, dono)
    faturas = session.exec(consulta(Invoice, dono)).all()
    cartoes = session.exec(consulta(Card, dono).order_by(Card.name)).all()
    nomes = {c.id: c.name for c in cartoes}

    proximo_ano, proximo_mes = avancar_meses(year, month, 1)
    por_cartao: dict[int, list[Invoice]] = {}
    for f in faturas:
        por_cartao.setdefault(f.card_id, []).append(f)

    linhas: list[CardInvoices] = []
    for cartao in cartoes:
        minhas = por_cartao.get(cartao.id, [])
        atual = next((f for f in minhas if (f.year, f.month) == (year, month)), None)
        proxima = next(
            (f for f in minhas if (f.year, f.month) == (proximo_ano, proximo_mes)), None
        )
        em_aberto = 0.0
        for f in minhas:
            total, pago, _ = agregados.get(f.id, (0.0, 0.0, 0))
            em_aberto += max(total - pago, 0.0)

        # Cartão arquivado sem nenhuma fatura em aberto não precisa ocupar a
        # tela; com saldo em aberto, precisa — é dinheiro a pagar.
        if cartao.archived and em_aberto <= 0 and not atual:
            continue

        linhas.append(
            CardInvoices(
                card_id=cartao.id,
                name=cartao.name,
                closing_day=cartao.closing_day,
                due_day=cartao.due_day,
                archived=cartao.archived,
                current=montar(atual, nomes[cartao.id], agregados, agora) if atual else None,
                next=montar(proxima, nomes[cartao.id], agregados, agora) if proxima else None,
                open_total=round(em_aberto, 2),
            )
        )

    inicio = dt.date(year, month, 1)
    fim = dt.date(proximo_ano, proximo_mes, 1)
    pagamentos = session.exec(
        consulta(InvoicePayment, dono)
        .where(InvoicePayment.date >= inicio, InvoicePayment.date < fim)
        .order_by(InvoicePayment.date.desc())
    ).all()

    vence_no_mes = sum(
        agregados.get(f.id, (0.0, 0.0, 0))[0]
        for f in faturas
        if (f.year, f.month) == (year, month)
    )
    aberto_total = sum(
        max(agregados.get(f.id, (0.0, 0.0, 0))[0] - agregados.get(f.id, (0.0, 0.0, 0))[1], 0.0)
        for f in faturas
    )

    return InvoicesSummary(
        year=year,
        month=month,
        cards=linhas,
        payments=_pagamentos_read(session, dono, pagamentos),
        due_this_month=round(vence_no_mes, 2),
        paid_this_month=round(sum(p.amount for p in pagamentos), 2),
        open_total=round(aberto_total, 2),
    )


@router_cartao.get("/invoices", response_model=list[InvoiceRead])
def listar_faturas(
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
    card_id: int | None = Query(default=None),
    limite: int = Query(default=24, ge=1, le=120),
):
    """Histórico de faturas, da mais nova pra mais antiga."""
    agregados = totais(session, dono)
    query = consulta(Invoice, dono)
    if card_id is not None:
        query = query.where(Invoice.card_id == card_id)

    faturas = session.exec(
        query.order_by(Invoice.year.desc(), Invoice.month.desc()).limit(limite)
    ).all()
    nomes = {
        c.id: c.name
        for c in session.exec(
            consulta(Card, dono).where(Card.id.in_({f.card_id for f in faturas}))
        ).all()
    } if faturas else {}

    agora = hoje()
    return [montar(f, nomes.get(f.card_id, "?"), agregados, agora) for f in faturas]


@router_cartao.get("/invoices/{invoice_id}", response_model=InvoiceDetail)
def ver_fatura(
    invoice_id: int,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    fatura = exigir(session, Invoice, invoice_id, dono, "Fatura")
    cartao = buscar(session, Card, fatura.card_id, dono)
    agregados = totais(session, dono)
    base = montar(fatura, cartao.name if cartao else "?", agregados, hoje())

    parcelas = session.exec(
        consulta(Transaction, dono)
        .where(Transaction.invoice_id == invoice_id)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
    ).all()

    compras = {
        c.id: c
        for c in session.exec(
            consulta(Purchase, dono).where(
                Purchase.id.in_({t.purchase_id for t in parcelas if t.purchase_id})
            )
        ).all()
    } if parcelas else {}
    categorias = {
        c.id: c
        for c in session.exec(
            consulta(Category, dono).where(
                Category.id.in_({t.category_id for t in parcelas})
            )
        ).all()
    } if parcelas else {}

    itens: list[InvoiceItem] = []
    for t in parcelas:
        compra = compras.get(t.purchase_id)
        categoria = categorias.get(t.category_id)
        if compra is None:
            # Parcela sem compra não deveria existir; se existir, é dado
            # inconsistente e some da fatura em silêncio — pior seria estourar
            # 500 e a tela inteira sumir por causa de uma linha.
            continue
        itens.append(
            InvoiceItem(
                transaction_id=t.id,
                date=t.date,
                description=t.description,
                amount=t.amount_paid or 0.0,
                category_id=t.category_id,
                category_name=categoria.name if categoria else "?",
                color=categoria.color if categoria else "#666",
                icon=categoria.icon if categoria else "•",
                # "1/1" não informa nada; em compra de uma parcela só, some.
                installment_no=t.installment_no if compra.installments > 1 else None,
                installments=compra.installments if compra.installments > 1 else None,
                purchase_id=compra.id,
                purchase_total=compra.total_amount,
                purchase_date=compra.purchase_date,
            )
        )

    pagamentos = session.exec(
        consulta(InvoicePayment, dono)
        .where(InvoicePayment.invoice_id == invoice_id)
        .order_by(InvoicePayment.date)
    ).all()

    return InvoiceDetail(
        **base.model_dump(),
        items=itens,
        payments=_pagamentos_read(session, dono, pagamentos),
    )


def _restante(session: Session, dono: User, fatura: Invoice) -> float:
    total, pago, _ = totais(session, dono).get(fatura.id, (0.0, 0.0, 0))
    return round(total - pago, 2)


@router_cartao.post("/invoices/{invoice_id}/payments")
def pagar_fatura(
    invoice_id: int,
    dados: InvoicePaymentCreate,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Registra o pagamento. Sai da Carteira, NÃO entra em nenhuma categoria.

    O gasto já foi contado quando a compra foi lançada. Contar de novo aqui
    somaria o mesmo dinheiro duas vezes — é justamente o erro que esta
    funcionalidade inteira existe pra evitar.
    """
    exigir_escrita(dono)
    fatura = exigir(session, Invoice, invoice_id, dono, "Fatura")

    if dados.amount <= 0:
        raise HTTPException(status_code=400, detail="O pagamento precisa ser maior que zero.")

    falta = _restante(session, dono, fatura)
    if dados.amount > falta + 0.005:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Esta fatura tem R$ {falta:.2f} a pagar, e o valor informado é maior. "
                "Pagamento parcial pode ser menor; maior costuma ser dígito a mais."
            ),
        )

    pagamento = InvoicePayment.model_validate(dados, update={
        "user_id": dono.id, "invoice_id": invoice_id
    })
    session.add(pagamento)
    session.commit()
    session.refresh(pagamento)

    cartao = buscar(session, Card, fatura.card_id, dono)
    return montar(fatura, cartao.name if cartao else "?", totais(session, dono), hoje())


@router_cartao.delete("/invoice_payments/{payment_id}")
def desfazer_pagamento(
    payment_id: int,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Desfaz um pagamento. A fatura volta ao que era e a Carteira também."""
    exigir_escrita(dono)
    pagamento = exigir(session, InvoicePayment, payment_id, dono, "Pagamento")

    session.delete(pagamento)
    session.commit()
    return {"message": "Pagamento desfeito."}


# ---------- Reconciliação com o jeito antigo ----------
#
# Antes do cartão existir no app, a fatura era lançada como UMA despesa numa
# categoria chamada "Fatura do cartão" — uma linha por mês, sem as compras. É um
# registro correto do CAIXA (o dinheiro saiu mesmo) e mudo sobre o GASTO (não diz
# em quê).
#
# Enquanto o mês não for reconstruído, esse lançamento pode ficar como está: ele
# é a melhor informação que existe daquele mês. O problema aparece quando o mês É
# reconstruído — aí as compras individuais passam a contar o gasto, e o
# lançamento antigo passa a contar o mesmo dinheiro uma segunda vez, nos dois
# eixos: some no gasto do mês e some na saída de caixa.
#
# A saída não pode ser automática. "Categoria chamada Fatura" é palpite sobre
# dinheiro de outra pessoa, e o dono pode ter lançado a fatura em qualquer
# categoria, ou ter uma despesa legítima chamada "Fatura". Por isso é uma
# operação explícita, item a item, pedida por quem sabe o que aquele lançamento
# era.


class ReconciliarPedido(SQLModel):
    transaction_id: int


@router_cartao.get("/invoices/{invoice_id}/candidatos-a-pagamento")
def candidatos_a_pagamento(
    invoice_id: int,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Lançamentos que PODEM ser o pagamento desta fatura, pro dono escolher.

    O filtro é por forma, não por significado: despesa, já paga, que não seja
    parcela de compra nenhuma, com data perto do vencimento. Nenhum palpite por
    nome de categoria ou descrição — a lista é candidata, e quem decide é quem
    lançou.
    """
    fatura = exigir(session, Invoice, invoice_id, dono, "Fatura")

    janela = dt.timedelta(days=60)
    despesas = {
        c.id
        for c in session.exec(
            consulta(Category, dono).where(Category.type == CategoryType.EXPENSE)
        ).all()
    }
    if not despesas:
        return []

    candidatos = session.exec(
        consulta(Transaction, dono)
        .where(
            Transaction.purchase_id.is_(None),
            Transaction.amount_paid.is_not(None),
            Transaction.amount_paid > 0,
            Transaction.category_id.in_(despesas),
            Transaction.date >= fatura.due_date - janela,
            Transaction.date <= fatura.due_date + janela,
        )
        .order_by(Transaction.date.desc())
    ).all()

    nomes = {
        c.id: c.name
        for c in session.exec(
            consulta(Category, dono).where(
                Category.id.in_({t.category_id for t in candidatos})
            )
        ).all()
    } if candidatos else {}

    falta = _restante(session, dono, fatura)
    # O mais parecido com o restante primeiro: é quase sempre o certo, e poupa
    # rolagem numa lista que pode ter trinta linhas.
    candidatos.sort(key=lambda t: (abs((t.amount_paid or 0) - falta), -t.date.toordinal()))

    return [
        {
            "id": t.id,
            "date": t.date.isoformat(),
            "description": t.description,
            "amount": t.amount_paid,
            "category_name": nomes.get(t.category_id, "?"),
            "payment_method": t.payment_method.value if t.payment_method else None,
        }
        for t in candidatos[:30]
    ]


@router_cartao.post("/invoices/{invoice_id}/reconciliar")
def reconciliar(
    invoice_id: int,
    pedido: ReconciliarPedido,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Transforma um lançamento antigo no pagamento desta fatura.

    O lançamento some e vira `InvoicePayment` com o mesmo valor e a mesma data.
    Os dois eixos ficam certos de uma vez:

      - GASTO: a despesa agregada some, e sobram só as compras individuais, que
        contam uma vez cada.
      - CAIXA: o dinheiro continua saindo uma vez só, agora como pagamento de
        fatura — que é o que ele sempre foi.

    O valor NÃO precisa bater com a fatura. Reconstruir um mês raramente
    itemiza tudo, e recusar por diferença de centavos só empurraria o dono a
    apagar o lançamento na mão, que é pior: aí some o registro de que o dinheiro
    saiu.

    Não dá pra desfazer: o lançamento é apagado. O que ele era fica escrito na
    observação do pagamento, e a tela avisa antes.
    """
    exigir_escrita(dono)
    fatura = exigir(session, Invoice, invoice_id, dono, "Fatura")
    lancamento = exigir(session, Transaction, pedido.transaction_id, dono, "Lançamento")

    if lancamento.purchase_id is not None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Esse lançamento é uma parcela de compra no cartão — ele é um item "
                "da fatura, não o pagamento dela."
            ),
        )

    if lancamento.amount_paid is None or lancamento.amount_paid <= 0:
        raise HTTPException(
            status_code=400,
            detail=(
                "Esse lançamento não tem valor pago: ele é só uma previsão, e "
                "previsão não tirou dinheiro da conta. Apague-o e registre o "
                "pagamento pelo botão 'Pagar fatura'."
            ),
        )

    categoria = buscar(session, Category, lancamento.category_id, dono)
    if categoria and categoria.type != CategoryType.EXPENSE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{lancamento.description}' está em {categoria.name}, que é "
                f"{categoria.type.value}. Pagamento de fatura é saída de dinheiro."
            ),
        )

    rastro = (
        f"Reconciliado do lançamento «{lancamento.description}» de "
        f"{lancamento.date.strftime('%d/%m/%Y')}"
        + (f" em {categoria.name}" if categoria else "")
    )

    pagamento = InvoicePayment(
        user_id=dono.id,
        invoice_id=invoice_id,
        date=lancamento.date,
        amount=lancamento.amount_paid,
        note=rastro,
    )
    session.add(pagamento)
    session.delete(lancamento)
    session.commit()

    cartao = buscar(session, Card, fatura.card_id, dono)
    return montar(fatura, cartao.name if cartao else "?", totais(session, dono), hoje())


# ---------- Forma de pagamento dos lançamentos que já existiam ----------


class FormaDePagamentoPedido(SQLModel):
    metodo: PaymentMethod
    card_id: int | None = None
    installments: int = 1


class FormaEmLotePedido(FormaDePagamentoPedido):
    ids: list[int]


def _classificar(
    session: Session,
    dono: User,
    lancamento: Transaction,
    pedido: FormaDePagamentoPedido,
) -> str | None:
    """Classifica um lançamento. Devolve o motivo quando não dá, ou None."""
    if lancamento.purchase_id is not None:
        return "já é parcela de uma compra no cartão"

    if pedido.metodo == PaymentMethod.CASH:
        lancamento.payment_method = PaymentMethod.CASH
        session.add(lancamento)
        return None

    categoria = buscar(session, Category, lancamento.category_id, dono)
    if categoria is None or categoria.type != CategoryType.EXPENSE:
        return "não é despesa — só despesa vai pra fatura"
    if lancamento.amount_paid is None or lancamento.amount_paid <= 0:
        return "não tem valor pago, então não há o que cobrar numa fatura"

    cartao = buscar(session, Card, pedido.card_id, dono) if pedido.card_id else None
    if cartao is None:
        return "cartão não encontrado"

    # Vira compra de verdade: o lançamento antigo sai e as parcelas entram no
    # lugar. Reaproveitar a linha existente como parcela 1 pareceria mais
    # gentil, mas deixaria a compra meio criada se algo falhasse no meio.
    compra = Purchase(
        user_id=dono.id,
        card_id=cartao.id,
        category_id=lancamento.category_id,
        description=lancamento.description,
        total_amount=lancamento.amount_paid,
        installments=max(1, pedido.installments),
        purchase_date=lancamento.date,
        note=lancamento.note,
    )
    session.add(compra)
    session.flush()

    _gerar_parcelas(session, dono, compra, cartao)
    session.delete(lancamento)
    return None


@router_cartao.post("/transactions/forma-de-pagamento")
def classificar_em_lote(
    pedido: FormaEmLotePedido,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Marca vários lançamentos de uma vez — a tela de revisão do histórico.

    Em lote o parcelamento é sempre 1x de propósito: parcelar é decisão por
    compra, e aplicar "3x" a dez lançamentos selecionados juntos inventaria
    dado. Compra parcelada se resolve uma a uma.
    """
    exigir_escrita(dono)
    if not pedido.ids:
        raise HTTPException(status_code=400, detail="Nenhum lançamento selecionado.")
    if len(pedido.ids) > 200:
        raise HTTPException(status_code=400, detail="No máximo 200 lançamentos por vez.")

    em_lote = FormaDePagamentoPedido(
        metodo=pedido.metodo, card_id=pedido.card_id, installments=1
    )

    atualizados = 0
    ignorados = []
    for id_ in pedido.ids:
        lancamento = buscar(session, Transaction, id_, dono)
        if lancamento is None:
            ignorados.append({"id": id_, "motivo": "não encontrado"})
            continue
        motivo = _classificar(session, dono, lancamento, em_lote)
        if motivo:
            ignorados.append({"id": id_, "motivo": motivo})
        else:
            atualizados += 1

    session.commit()
    return {"atualizados": atualizados, "ignorados": ignorados}


@router_cartao.post("/transactions/{transaction_id}/forma-de-pagamento")
def classificar_um(
    transaction_id: int,
    pedido: FormaDePagamentoPedido,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Classifica um lançamento só — e é aqui que o parcelamento é aceito."""
    exigir_escrita(dono)
    lancamento = exigir(session, Transaction, transaction_id, dono, "Lançamento")

    motivo = _classificar(session, dono, lancamento, pedido)
    if motivo:
        raise HTTPException(
            status_code=409, detail=f"Não dá pra classificar: {motivo}."
        )

    session.commit()
    return {"message": "Forma de pagamento definida."}
