import { Link } from "react-router-dom";
import { FinancialRow, LoadError, SectionTitle, Summary, type FinancialLine } from "../components/essencial/Common";
import HunterAdvance from "../components/essencial/HunterAdvance";
import { useCommitment, useCommitments, useInvoicesSummary, usePlanningHorizon, usePlanningMonth, useReconciliation, useTransactions } from "../lib/queries";
import { currentPeriod, formatPeriod, usePeriod } from "../lib/period";
import { formatDiaMes, formatMoney } from "../lib/format";
import type { PlanoItem } from "../lib/tiposPlanejamento";

const due = (item: PlanoItem) => item.direction === "saida" && item.remaining > 0 &&
  (item.source === "cartao" || item.source === "parcelado" || item.source === "recorrente" || item.expense_class === "fixed");

export default function ContasAPagar() {
  const { period } = usePeriod();
  const planning = usePlanningMonth(period, null);
  const invoices = useInvoicesSummary();
  const commitments = useCommitments();
  const transactions = useTransactions();
  const reconciliation = useReconciliation(period);
  const hunter = commitments.data?.find(c => /Hunter 350/i.test(c.description));
  const hunterDetail = useCommitment(hunter?.id ?? null);
  const now = currentPeriod();
  const distance = Math.max(0, (period.year-now.year)*12 + period.month-now.month);
  const horizon = usePlanningHorizon(Math.min(distance+4,24));
  const month = planning.data?.months.find(m => m.year === period.year && m.month === period.month);
  const obligations = (month?.items ?? []).filter(due);
  // O planejamento já deduplica faturas, compromissos e previstos. A lista
  // abaixo só mostra suas origens; o total nunca soma outra fonte por cima.
  const toPay = obligations.reduce((n,i)=>n+i.remaining,0);
  const paidCommitments = (month?.items ?? []).filter(i => i.direction === "saida" && i.status === "pago" && i.commitment_id != null).reduce((n,i)=>n+i.amount,0);
  const paidStandaloneFixed = (transactions.data ?? []).filter(t=>t.amount_paid != null && t.purchase_id == null && t.commitment_id == null && t.effective_expense_class === "fixed").reduce((n,t)=>n+(t.amount_paid??0),0);
  const alreadyPaid = (invoices.data?.paid_this_month ?? 0) + paidCommitments + paidStandaloneFixed;
  const cards = (invoices.data?.cards ?? []).filter(c=>c.current);
  const otherObligations = obligations.filter(i=>i.source!=="cartao");
  const abated = (hunterDetail.data?.schedule ?? []).filter(o=>o.status==="abatida" && o.due_date.slice(0,7)===`${period.year}-${String(period.month).padStart(2,"0")}`);
  const toCheck = (reconciliation.data?.items ?? []).filter(i=>i.status==="pendente"||i.status==="confirmar").length;
  const preview = (horizon.data?.months ?? []).filter(m=>(m.year-period.year)*12+m.month-period.month>0).slice(0,3);
  const line = (i:PlanoItem):FinancialLine => ({key:i.key,description:`${i.description}${i.label?` · ${i.label}`:""}`,date:i.date,value:i.remaining,status:i.certainty==="estimado"?"A confirmar":i.status==="vencido"?"Vencido":"A pagar",detail:i.detail??undefined});
  return <div className="e-page e-bills">
    <SectionTitle title="Contas"><Link to="/planejamento/compromissos">Cronogramas ›</Link></SectionTitle>
    <p className="e-page-sub">Faturas e pagamentos de {formatPeriod(period)}.</p>
    <LoadError error={planning.error||invoices.error||commitments.error||hunterDetail.error||reconciliation.error}/>
    <Summary items={[{label:"A pagar",value:month?toPay:null},{label:"Já paguei",value:month?alreadyPaid:null}]} />
    {toCheck>0&&<p className="e-bills-pending"><Link to="/organizar">{toCheck} informações a conferir neste mês ›</Link></p>}
    <SectionTitle title="Cartões"><Link to="/orcamento?aba=faturas">Ver faturas ›</Link></SectionTitle>
    <div className="e-list">{cards.map(c=><Link to="/orcamento?aba=faturas" className="e-bill-row" key={c.card_id}>
      <span><strong>{c.name}</strong><small>Fatura de {formatPeriod(period)} · vence {formatDiaMes(c.current!.due_date)}</small></span>
      <span className="e-bill-amount"><b className="tnum">{formatMoney(c.current!.remaining)}</b><small>{c.current!.status === "paga" ? "Paga" : c.current!.status === "atrasada" ? "Vencida" : c.current!.status === "parcial" ? "Parcial" : "A pagar"}</small></span>
    </Link>)}{!cards.length&&<p className="e-empty">Nenhuma fatura neste mês.</p>}</div>
    <SectionTitle title="Compromissos"><Link to="/planejamento/compromissos">Ver todos ›</Link></SectionTitle>
    <div className="e-list">{otherObligations.map(i=><Link to={i.commitment_id!=null?`/planejamento/compromissos?id=${i.commitment_id}`:"/planejamento"} className="e-linked-row" key={i.key}><FinancialRow line={line(i)}/></Link>)}
      {abated.map(o=><Link to={`/planejamento/compromissos?id=${hunter!.id}`} className="e-bill-row" key={`abatida-${o.number}`}><span><strong>{hunter!.description} · {o.label}</strong><small>Venceria {formatDiaMes(o.due_date)} · abatida pelo credor em {o.abated_on?formatDiaMes(o.abated_on):"data a confirmar"}</small></span><span className="e-bill-amount"><b>Abatida</b><small>{formatMoney(o.amount)} sem saída</small></span></Link>)}
      {!otherObligations.length&&!abated.length&&<p className="e-empty">Nenhum compromisso pendente neste mês.</p>}
    </div>
    <SectionTitle title="Próximos vencimentos"><Link to="/planejamento/proximos">Comparar meses ›</Link></SectionTitle>
    <div className="e-preview">{preview.map(m=><Link to="/planejamento/proximos" className="e-preview-month" key={`${m.year}-${m.month}`}><strong>{formatPeriod({year:m.year,month:m.month})}</strong><span>Faturas e compromissos</span><b className="tnum">{formatMoney(m.items.filter(due).reduce((n,i)=>n+i.remaining,0))}</b></Link>)}</div>
    {hunter&&<HunterAdvance/>}
    <p className="e-bills-footnote">Compras entram no gasto quando acontecem; a fatura entra aqui quando vence. Abatimentos não são pagamentos.</p>
  </div>;
}
