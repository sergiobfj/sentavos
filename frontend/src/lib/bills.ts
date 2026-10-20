import type { PlanoMes, PlanoResposta, PlanoItem, ReconciliationItem } from "./tiposPlanejamento";
import type { Transaction } from "./types";

const money = (n: number) => Math.round(n * 100) / 100;
const open = (i: PlanoItem) => i.direction === "saida" && i.remaining > 0 && i.status !== "pago";

/** O planejamento já conciliou faturas, parcelas e lançamentos previstos.
 * Esta leitura separa o confirmado do estimado; nunca soma outra fatura sobre
 * uma linha do planejamento. Conferências não são dinheiro nem vencimento. */
export function billView(plan: PlanoResposta | undefined, month: PlanoMes | undefined,
  checks: ReconciliationItem[], transactions: Transaction[]) {
  const due = (month?.items ?? []).filter(i => open(i) && i.certainty === "confirmado");
  const estimated = (month?.items ?? []).filter(i => open(i) && i.certainty !== "confirmado");
  const review = checks.filter(i => (i.kind === "obrigacao") &&
    (i.status === "pendente" || i.status === "confirmar" || i.link_missing)).sort((a,b) => {
      const rank = (i: ReconciliationItem) => i.prefill?.bill_visibility === "quote" || i.prefill?.confirmed === false ? 2
        : Number(i.prefill?.installments ?? 0) > 1 && !i.date ? 1 : 0;
      return rank(a)-rank(b) || a.description.localeCompare(b.description,"pt-BR");
    });
  const activeReview = review.filter(i => i.prefill?.bill_visibility !== "quote" && i.prefill?.confirmed !== false);
  // Parcelamento sem primeiro vencimento: mostrar o contrato, sem cobrar seu
  // valor integral no mês que a anotação foi criada.
  const reviewAmount = money(activeReview.reduce((sum, i) =>
    sum + (Number(i.prefill?.installments ?? 0) > 1 && !i.date ? 0 : i.amount ?? 0), 0));
  const estimatedAmount = money(estimated.reduce((sum, i) => sum + i.remaining, 0));
  const toPay = money(due.reduce((sum, i) => sum + i.remaining, 0));
  const paidPlanned = (month?.items ?? []).filter(i => i.direction === "saida" && i.status === "pago" &&
    i.commitment_id != null);
  const paidCash = transactions.filter(t => t.amount_paid != null && t.amount_paid > 0 &&
    t.date.slice(0, 7) === `${month?.year}-${String(month?.month).padStart(2, "0")}` &&
    t.payment_method !== "credit" && t.purchase_id == null && t.commitment_id == null &&
    t.effective_expense_class === "fixed");
  // O mês seguinte do Planning herda o saldo projetado do anterior, inclusive
  // estimativas. Retirá-las cumulativamente mantém a comparação coerente.
  const estimatesBefore = (plan?.months ?? []).filter(m => month && (m.year * 12 + m.month) <=
    (month.year * 12 + month.month)).reduce((sum, m) => sum + m.items.filter(i => open(i) &&
      i.certainty !== "confirmado").reduce((value, i) => value + i.remaining, 0), 0);
  const projected = month ? money(month.available + estimatesBefore) : null;
  return {
    due, estimated, review, paidPlanned, paidCash,
    toPay, toCheck: money(reviewAmount + estimatedAmount), projected,
    partial: review.length > 0 || estimated.length > 0,
  };
}
