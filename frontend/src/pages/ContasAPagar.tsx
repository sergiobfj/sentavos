import { useState } from "react";
import { Link } from "react-router-dom";
import { LoadError, SectionTitle, Summary } from "../components/essencial/Common";
import HunterAdvance from "../components/essencial/HunterAdvance";
import BillActions from "../components/essencial/BillActions";
import { billView } from "../lib/bills";
import { useCommitment, useCommitments, useInvoicesSummary, usePlanningHorizon, usePlanningMonth, useReconciliation, useTransactions } from "../lib/queries";
import { currentPeriod, formatPeriod, usePeriod } from "../lib/period";
import { formatDiaMes, formatMoney } from "../lib/format";
import type { PlanoItem, ReconciliationItem } from "../lib/tiposPlanejamento";

function BillRow({ name, value, detail, status, onClick, to }: { name: string; value: number; detail: string; status: string; onClick?: () => void; to?: string }) {
  const content = <><span><strong>{name}</strong><small>{detail}</small></span><span className="e-bill-amount"><b className="tnum">{formatMoney(value)}</b><small>{status}</small></span></>;
  return to ? <Link to={to} className="e-bill-row">{content}</Link> : <button type="button" className="e-bill-row e-bill-button" onClick={onClick}>{content}</button>;
}

export default function ContasAPagar() {
  const { period } = usePeriod();
  const [selected, setSelected] = useState<{ due?: PlanoItem; review?: ReconciliationItem } | null>(null);
  const planning = usePlanningMonth(period, null);
  const transactions = useTransactions();
  const invoices = useInvoicesSummary();
  const reconciliation = useReconciliation(period);
  const commitments = useCommitments();
  const hunter = commitments.data?.find(c => /Hunter 350/i.test(c.description));
  const hunterDetail = useCommitment(hunter?.id ?? null);
  const now = currentPeriod();
  const distance = Math.max(0, (period.year - now.year) * 12 + period.month - now.month);
  const horizon = usePlanningHorizon(Math.min(distance + 4, 24));
  const month = planning.data?.months.find(m => m.year === period.year && m.month === period.month);
  const view = billView(planning.data, month, reconciliation.data?.items ?? [], transactions.data ?? []);
  const abated = (hunterDetail.data?.schedule ?? []).filter(o=>o.status==="abatida" && o.due_date.slice(0,7)===`${period.year}-${String(period.month).padStart(2,"0")}`);
  const preview = (horizon.data?.months ?? []).filter(m=>(m.year-period.year)*12+m.month-period.month>0).slice(0,3);
  const invoicePayments = invoices.data?.payments ?? [];
  const paid = invoicePayments.reduce((n,p)=>n+p.amount,0)+view.paidPlanned.reduce((n,i)=>n+i.amount,0)+view.paidCash.reduce((n,t)=>n+(t.amount_paid??0),0);
  return <div className="e-page e-bills">
    <SectionTitle title="Contas"><Link to="/planejamento/compromissos">Cronogramas ›</Link></SectionTitle>
    <p className="e-page-sub">Faturas e pagamentos · {formatPeriod(period)}</p>
    <LoadError error={planning.error || transactions.error || invoices.error || reconciliation.error || commitments.error || hunterDetail.error} />
    <Summary items={[{label:"A pagar",value:month?view.toPay:null},{label:"A conferir",value:month?view.toCheck:null},{label:"Já pagas",value:month?paid:null}]} />
    {view.review.some(i=>Number(i.prefill?.installments??0)>1 || i.prefill?.bill_visibility==="quote")&&<p className="e-bills-count-note">A conferir: valor deste mês. Parcelas sem data e cotações aparecem abaixo, fora do total.</p>}
    <SectionTitle title="A pagar" />
    <div className="e-list">{view.due.map(i=><BillRow key={i.key} name={`${i.description}${i.label?` · ${i.label}`:""}`} value={i.remaining} detail={`${i.source==="cartao"?"Fatura · ":""}vence ${formatDiaMes(i.date)}${i.source==="cartao"&&i.amount>i.remaining?` · pago ${formatMoney(i.amount-i.remaining)}`:""}`} status={i.status==="vencido"?"Vencida":"A pagar"} to={i.invoice_id!=null?"/orcamento?aba=faturas":i.commitment_id==null?"/lancamentos":undefined} onClick={i.commitment_id!=null?()=>setSelected({due:i}):undefined}/>)}{!view.due.length&&<p className="e-empty">Nenhuma obrigação confirmada pendente neste mês.</p>}</div>
    <SectionTitle title="A conferir"><Link to="/organizar">Conferir mês ›</Link></SectionTitle>
    <div className="e-list">{view.review.map(i=>{const installments=Number(i.prefill?.installments??1);const parcel=Number(i.prefill?.amount??(i.amount&&installments>1?i.amount/installments:0));return <BillRow key={`review-${i.id}`} name={i.description} value={i.amount??0} detail={installments>1?`${installments} × ${formatMoney(parcel)} · datas a confirmar`:i.prefill?.bill_visibility==="quote"||i.prefill?.confirmed===false?"Cotação · contratação a confirmar":i.date?`Referência ${formatDiaMes(i.date)}`:"Vencimento não informado"} status="A conferir" onClick={()=>setSelected({review:i})}/>;})}{view.estimated.map(i=><BillRow key={i.key} name={i.description} value={i.remaining} detail={`Previsto para ${formatDiaMes(i.date)}`} status="Previsto" to={i.commitment_id!=null?`/planejamento/compromissos?id=${i.commitment_id}`:"/lancamentos"}/>)}{!view.review.length&&!view.estimated.length&&<p className="e-empty">Nada para conferir neste mês.</p>}</div>
    <SectionTitle title="Já pagas" />
    <div className="e-list">{invoicePayments.map(p=><BillRow key={`invoice-payment-${p.id}`} name={`Fatura ${p.card_name}`} value={p.amount} detail={`Pago em ${formatDiaMes(p.date)} · fatura ${String(p.invoice_month).padStart(2,"0")}/${p.invoice_year}`} status="Paga" to="/orcamento?aba=faturas"/>)}{view.paidPlanned.map(i=><BillRow key={i.key} name={i.description} value={i.amount} detail={`Vencia ${formatDiaMes(i.date)}`} status="Paga" to={`/planejamento/compromissos?id=${i.commitment_id}`}/>)}{view.paidCash.map(t=><BillRow key={`paid-${t.id}`} name={t.description} value={t.amount_paid??0} detail={`Pago em ${formatDiaMes(t.date)}${t.account_name?` · ${t.account_name}`:""}`} status="Paga" to="/lancamentos"/>)}{abated.map(o=><BillRow key={`abatida-${o.number}`} name={`${hunter!.description} · ${o.label}`} value={o.amount} detail={`Venceria ${formatDiaMes(o.due_date)} · sem saída de caixa`} status="Abatida" to={`/planejamento/compromissos?id=${hunter!.id}`}/>)}{!invoicePayments.length&&!view.paidPlanned.length&&!view.paidCash.length&&!abated.length&&<p className="e-empty">Nenhum pagamento conhecido neste mês.</p>}</div>
    <SectionTitle title="Próximos vencimentos"><Link to="/planejamento/proximos">Comparar meses ›</Link></SectionTitle>
    <div className="e-preview">{preview.map(m=><Link to="/planejamento/proximos" className="e-preview-month" key={`${m.year}-${m.month}`}><strong>{formatPeriod({year:m.year,month:m.month})}</strong><span>Faturas e compromissos confirmados</span><b className="tnum">{formatMoney(billView(horizon.data,m,[],[]).toPay)}</b></Link>)}</div>
    {hunter&&<HunterAdvance/>}
    <p className="e-bills-footnote">Faturas contam uma vez, no vencimento. Valores a conferir não reduzem a previsão; abatimentos não saem da conta.</p>
    {selected&&<BillActions due={selected.due} review={selected.review} onClose={()=>setSelected(null)}/>}
  </div>;
}
