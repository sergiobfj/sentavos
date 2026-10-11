"""Conferência do mês: o que já existe no Sentavos que pode ser este item?

Responde com SUGESTÕES e os motivos de cada uma ("mesmo valor", "descrição
parecida", "2 dias de diferença"). Nunca vincula, nunca cria: quem decide é o
dono, na tela. Um casamento automático por valor parecido é exatamente o tipo
de palpite que acerta nove vezes e, na décima, faz uma entrada de R$ 7.000
"já existir" porque havia um aporte de R$ 7.000 na mesma semana.

## Onde procura

  - lançamentos (à vista, parcelas de cartão e previstos) perto da data;
  - faturas que vencem perto, pelo total e pelo restante — "Nubank R$ 302" é
    quase sempre uma fatura;
  - compromissos já cadastrados, pela descrição — pra não cadastrar a Hunter
    duas vezes.
"""

import datetime as dt
import re
import unicodedata

from sqlmodel import Session, SQLModel

from app.cartao import limites_do_mes
from app.escopo import consulta
from app.faturas import totais
from app.models import (
    Card,
    Category,
    CategoryType,
    Commitment,
    Invoice,
    Purchase,
    ReconciliationItem,
    ReconciliationKind,
    ReconciliationStatus,
    Transaction,
    User,
)

# Palavras que aparecem em tudo e não dizem nada sobre o que é o item.
VAZIAS = {
    "de", "da", "do", "das", "dos", "para", "pra", "com", "sem", "por", "the",
    "pago", "paga", "pagamento", "valor", "mes", "conta",
}

JANELA = dt.timedelta(days=10)


class Candidato(SQLModel):
    """Uma correspondência possível, com o porquê."""

    kind: str  # lancamento | parcela | previsto | fatura | compromisso
    id: int
    description: str
    amount: float | None = None
    date: dt.date | None = None
    detail: str | None = None
    score: float
    reasons: list[str] = []
    # Já está vinculado a outro item desta conferência.
    used: bool = False


def palavras(texto: str | None) -> set[str]:
    """Minúsculas, sem acento, sem as palavras vazias. "Salário" == "salario"."""
    if not texto:
        return set()
    sem_acento = "".join(
        ch for ch in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(ch) != "Mn"
    )
    return {p for p in re.split(r"[^a-z0-9]+", sem_acento) if len(p) >= 3 and p not in VAZIAS}


def _pontos_de_valor(alvo: float | None, valor: float | None) -> tuple[float, str | None]:
    if alvo is None or valor is None or alvo <= 0:
        return 0.0, None
    diferenca = abs(abs(valor) - alvo)
    relativa = diferenca / alvo
    if diferenca <= 0.01:
        return 3.0, "mesmo valor"
    if relativa <= 0.02:
        return 2.0, f"valor quase igual (diferença de R$ {diferenca:.2f})".replace(".", ",")
    if relativa <= 0.10:
        return 1.0, f"valor parecido (diferença de R$ {diferenca:.2f})".replace(".", ",")
    return 0.0, None


def _pontos_de_data(alvo: dt.date | None, data: dt.date | None) -> tuple[float, str | None]:
    if alvo is None or data is None:
        return 0.0, None
    dias = abs((data - alvo).days)
    if dias == 0:
        return 1.0, "mesma data"
    if dias <= 2:
        return 0.75, f"{dias} dia{'s' if dias > 1 else ''} de diferença"
    if dias <= 7:
        return 0.25, f"{dias} dias de diferença"
    return 0.0, None


def _combina_tipo(kind: ReconciliationKind, tipo: CategoryType) -> float:
    """Entrada procurando despesa (ou o contrário) quase nunca é a resposta."""
    if kind == ReconciliationKind.ENTRADA:
        return 0.5 if tipo == CategoryType.INCOME else -2.0
    if kind in (ReconciliationKind.SAIDA, ReconciliationKind.OBRIGACAO):
        return 0.5 if tipo == CategoryType.EXPENSE else -1.0
    if kind == ReconciliationKind.RESERVA:
        return 0.5 if tipo == CategoryType.INVESTMENT else 0.0
    return 0.0


def candidatos(
    session: Session, dono: User, item: ReconciliationItem, limite: int = 3
) -> list[Candidato]:
    """As melhores correspondências para o item, da mais forte pra mais fraca."""
    if item.kind == ReconciliationKind.SALDO:
        # Saldo observado não é lançamento — não há o que "já existir".
        return []

    inicio_mes, fim_mes = limites_do_mes(item.year, item.month)
    if item.date is not None:
        de, ate = item.date - JANELA, item.date + JANELA
    else:
        de, ate = inicio_mes - JANELA, fim_mes + JANELA

    tokens = palavras(item.description)
    categorias = {c.id: c for c in session.exec(consulta(Category, dono)).all()}

    # O que outro item desta conta já reivindicou aparece marcado — o mesmo
    # lançamento não deveria responder por dois itens da conferência.
    usados = {
        (r.transaction_id, r.commitment_id)
        for r in session.exec(
            consulta(ReconciliationItem, dono).where(
                ReconciliationItem.id != item.id,
                ReconciliationItem.status == ReconciliationStatus.RESOLVIDO,
            )
        ).all()
    }
    tx_usados = {t for t, _c in usados if t}
    compromissos_usados = {c for _t, c in usados if c}

    achados: list[Candidato] = []

    # ---------- Lançamentos ----------
    lancamentos = session.exec(
        consulta(Transaction, dono).where(Transaction.date >= de, Transaction.date <= ate)
    ).all()
    compras = {}
    ids_compra = {t.purchase_id for t in lancamentos if t.purchase_id}
    if ids_compra:
        compras = {
            p.id: p
            for p in session.exec(consulta(Purchase, dono).where(Purchase.id.in_(ids_compra))).all()
        }
    cartoes = {c.id: c.name for c in session.exec(consulta(Card, dono)).all()}

    for t in lancamentos:
        valor = t.amount_paid if t.amount_paid is not None else t.amount_planned
        pv, mv = _pontos_de_valor(item.amount, valor)
        comuns = tokens & palavras(t.description)
        pd = 2.0 if comuns else 0.0
        if pv == 0 and pd == 0:
            continue
        pdata, mdata = _pontos_de_data(item.date, t.date)
        if item.date is None and inicio_mes <= t.date < fim_mes:
            # Sem data, o que cai dentro do mês conferido ganha do vizinho da
            # borda: a parcela 2/5 de outubro, não a 1/5 de 23 de setembro.
            pdata, mdata = 0.5, "dentro do mês"
        # Valor parecido sozinho é coincidência demais pra ser sugestão — nos
        # dados reais, "Academia R$ 120" "parecia" uma assinatura de R$ 121,40
        # de outro mês. Sem descrição em comum, só vale o valor exato, ou o
        # quase igual numa data próxima.
        if not comuns and not (pv >= 3 or (pv >= 2 and pdata >= 0.5)):
            continue
        # E descrição em comum com valor muito diferente também não: o
        # "Salário" de R$ 944 não é o "Salário do dia 15" de R$ 720.
        if comuns and item.amount and valor and pv == 0:
            if abs(abs(valor) - item.amount) / item.amount > 0.30:
                continue
        cat = categorias.get(t.category_id)
        tipo = CategoryType(cat.type) if cat else CategoryType.EXPENSE
        pontos = pv + pd + pdata + _combina_tipo(item.kind, tipo)
        if pontos < 2.0:
            continue

        motivos = [m for m in (mv, "descrição parecida" if comuns else None, mdata) if m]
        if t.purchase_id:
            compra = compras.get(t.purchase_id)
            kind = "parcela"
            partes = [cartoes.get(compra.card_id, "cartão") if compra else "cartão"]
            if compra and compra.installments > 1:
                partes.insert(0, f"parcela {t.installment_no}/{compra.installments}")
            detalhe = " · ".join(partes)
        elif t.amount_paid is None:
            kind, detalhe = "previsto", "só previsto, sem valor pago"
        else:
            kind, detalhe = "lancamento", cat.name if cat else None
        if t.note:
            detalhe = f"{detalhe} · {t.note}" if detalhe else t.note
        achados.append(
            Candidato(
                kind=kind,
                id=t.id,
                description=t.description,
                amount=valor,
                date=t.date,
                detail=detalhe,
                score=round(pontos, 2),
                reasons=motivos,
                used=t.id in tx_usados,
            )
        )

    # ---------- Faturas ----------
    if item.amount and item.kind in (ReconciliationKind.SAIDA, ReconciliationKind.OBRIGACAO, ReconciliationKind.OUTRO):
        agregados = totais(session, dono)
        for f in session.exec(
            consulta(Invoice, dono).where(
                Invoice.due_date >= inicio_mes - dt.timedelta(days=31),
                Invoice.due_date <= fim_mes + dt.timedelta(days=31),
            )
        ).all():
            total, pago, _ = agregados.get(f.id, (0.0, 0.0, 0))
            melhor = max(
                (_pontos_de_valor(item.amount, total), _pontos_de_valor(item.amount, total - pago)),
                key=lambda x: x[0],
            )
            nome = cartoes.get(f.card_id, "cartão")
            comuns = tokens & palavras(nome + " fatura cartao")
            # Só com o cartão (ou "fatura") no item, ou com o valor exato: os
            # R$ 500,61 dos equipamentos "pareciam" uma fatura de R$ 500,63.
            if not comuns and melhor[0] < 3:
                continue
            pontos = melhor[0] + (1.0 if comuns else 0.0)
            if melhor[0] == 0 or pontos < 1.5:
                continue
            achados.append(
                Candidato(
                    kind="fatura",
                    id=f.id,
                    description=f"Fatura {nome}",
                    amount=round(total, 2),
                    date=f.due_date,
                    detail=f"vence {f.due_date.strftime('%d/%m')} · pago R$ {pago:.2f}".replace(".", ","),
                    score=round(pontos, 2),
                    reasons=[m for m in (melhor[1], "nome do cartão" if comuns else None) if m],
                )
            )

    # ---------- Compromissos já cadastrados ----------
    if tokens:
        for c in session.exec(consulta(Commitment, dono)).all():
            comuns = tokens & palavras(f"{c.description} {c.institution or ''}")
            if not comuns:
                continue
            pv, mv = _pontos_de_valor(item.amount, c.amount)
            pontos = 2.0 + pv
            achados.append(
                Candidato(
                    kind="compromisso",
                    id=c.id,
                    description=c.description,
                    amount=c.amount,
                    date=c.first_due,
                    detail=(f"{c.installments}x" if c.installments else "recorrente")
                    + (f" · {c.institution}" if c.institution else ""),
                    score=round(pontos, 2),
                    reasons=[m for m in ("compromisso com descrição parecida", mv) if m],
                    used=c.id in compromissos_usados,
                )
            )

    achados.sort(key=lambda a: (a.used, -a.score, a.date or dt.date.min))
    return achados[:limite]
