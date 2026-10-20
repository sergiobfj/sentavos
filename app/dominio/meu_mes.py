"""Resumo canônico de caixa livre. A UI apenas formata estes totais.

Saldo calculado já contém movimentos realizados posteriores à observação.
Somente obrigações ainda abertas entram no futuro; cartão entra por fatura.
Estimativas incertas ficam fora do total confirmado e tornam a previsão parcial.
"""
from app import planejamento
from app.cartao import limites_do_mes
from app.dominio import investimentos
from app.escopo import consulta
from app.models import Category, CategoryType, Transaction, ReconciliationItem, InvestmentPlan


def resumo(session, dono, year, month):
    from app.rotas_conferencia import _ler
    hoje = planejamento.hoje()
    passado = (year, month) < (hoje.year, hoje.month)
    inicio, fim = limites_do_mes(year, month)
    plano = planejamento.planejar(session, dono, (year, month), agora=inicio if passado else hoje)
    mes = plano.months[-1]
    abertas = [i for i in mes.items if i.direction == "saida" and i.remaining > 0 and i.category_type != CategoryType.INVESTMENT]
    devidas = [i for i in abertas if i.certainty == "confirmado"]
    estimadas = [i for i in abertas if i.certainty != "confirmado"]
    revisoes = [_ler(session, dono, r, False) for r in session.exec(consulta(ReconciliationItem, dono).where(
        ReconciliationItem.year == year, ReconciliationItem.month == month)).all()]
    revisar = [r for r in revisoes if r.kind == "obrigacao" and
               (r.status in ("pendente", "confirmar") or r.link_missing)]
    def valor_revisao(r):
        p = r.prefill or {}
        if p.get("bill_visibility") == "quote" or p.get("confirmed") is False:
            return 0
        if int(p.get("installments", 0) or 0) > 1 and r.date is None:
            return 0
        return r.amount or 0
    tipos = {c.id: c.type for c in session.exec(consulta(Category, dono)).all()}
    pagos = [t for t in session.exec(consulta(Transaction, dono).where(Transaction.date >= inicio,
             Transaction.date < fim, Transaction.amount_paid.is_not(None))).all()
             if tipos.get(t.category_id) == CategoryType.EXPENSE and t.payment_method != "credit"
             and t.purchase_id is None]
    contas = [c for c in plano.accounts if c.included]
    conhecidas = [c for c in contas if c.as_of is not None]
    base_conhecida = [c for c in conhecidas if not c.stale]
    aviso = plano.balance_warning
    motivos = []
    if not conhecidas:
        motivos.append("Informe o saldo das contas")
    if aviso.contas_sem_saldo or aviso.sem_dia or aviso.sem_contas:
        motivos.append("Saldo incompleto")
    if aviso.desatualizado:
        motivos.append("Atualize os saldos antigos")
    if aviso.quantidade:
        motivos.append("Há movimentos sem conta após o saldo")
    if revisar or estimadas:
        motivos.append("Há contas a conferir")
    planos = list(session.exec(consulta(InvestmentPlan, dono).where(InvestmentPlan.status == "planned",
                  InvestmentPlan.date < fim)).all())
    if any(p.type == "redemption" for p in planos):
        motivos.append("Depende de resgate previsto")
    if any(p.asset_id is None or p.account_id is None or p.category_id is None for p in planos):
        motivos.append("Complete os planos de investimento")
    # Retira estimativas incertas cumulativamente do cálculo confirmado.
    incertas = sum(i.remaining for m in plano.months for i in m.items
                   if i.direction == "saida" and i.certainty != "confirmado")
    base_invalida = not base_conhecida or aviso.sem_dia or aviso.sem_contas or bool(aviso.contas_sem_saldo) or bool(aviso.quantidade)
    fluxo = investimentos.resumo(session, dono, year, month)
    return {
        "plan": plano, "month": mes,
        "money_now": round(sum(c.value for c in conhecidas), 2) if conhecidas else None,
        "balance_date": min((c.observed_on for c in conhecidas if c.observed_on), default=None),
        "balance_stale": aviso.desatualizado,
        "to_receive": round(sum(i.remaining for i in mes.items if i.direction == "entrada" and i.category_type != CategoryType.INVESTMENT), 2),
        "to_pay": round(sum(i.remaining for i in devidas), 2),
        "to_check": round(sum(valor_revisao(r) for r in revisar) + sum(i.remaining for i in estimadas), 2),
        "contributed": fluxo.contributed, "redeemed": fluxo.redeemed,
        "to_invest": round(sum(r.amount for r in mes.reserves if r.source == "aporte"), 2),
        "projected": None if base_invalida or passado else round(mes.available + incertas, 2),
        "partial": bool(motivos), "reasons": ["Mês encerrado"] if passado else motivos,
        "due": devidas, "estimated": estimadas, "review": revisar,
        "paid_cash_ids": [t.id for t in pagos],
    }
