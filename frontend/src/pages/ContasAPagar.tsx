import { useState } from "react";
import { Link } from "react-router-dom";
import { LoadError, SectionTitle, Summary } from "../components/essencial/Common";
import { EntryEditor } from "../components/essencial/Common";
import type { Transaction } from "../lib/types";
import BillActions from "../components/essencial/BillActions";

import { useCommitment, useCommitments, useInvoicesSummary, useMonthSummary, useCategories, useTransactions } from "../lib/queries";
import { formatPeriod, usePeriod } from "../lib/period";
import { formatDiaMes, formatMoney } from "../lib/format";
import type { PlanoItem, ReconciliationItem } from "../lib/tiposPlanejamento";

function BillRow({ name, value, detail, status, onClick, to }: { name: string; value: number; detail: string; status: string; onClick?: () => void; to?: string }) {
  const content = <><span><strong>{name}</strong><small>{detail}</small></span><span className="e-bill-amount"><b className="tnum">{formatMoney(value)}</b><small>{status}</small></span></>;
  return to ? <Link to={to} className="e-bill-row">{content}</Link> : <button type="button" className="e-bill-row e-bill-button" onClick={onClick}>{content}</button>;
}

export default function ContasAPagar() {
  const { period } = usePeriod();
  const [selected, setSelected] = useState<{ due?: PlanoItem; review?: ReconciliationItem } | null>(null);
  const summary = useMonthSummary();
  const categories = useCategories(true);
  const [editing,setEditing] = useState<Transaction|null>(null);
  const transactions = useTransactions();
  const invoices = useInvoicesSummary();

  const commitments = useCommitments();
  const hunter = commitments.data?.find(c => /Hunter 350/i.test(c.description));
  const hunterDetail = useCommitment(hunter?.id ?? null);
  const month = summary.data?.month;
  const r = summary.data;
  const view = {due:r?.due??[], estimated:r?.estimated??[],review:r?.review??[],toPay:r?.to_pay,toCheck:r?.to_check,
    paidPlanned:[] as PlanoItem[],
    paidCash:(transactions.data??[]).filter(t=>r?.paid_cash_ids.includes(t.id))};
  const abated = (hunterDetail.data?.schedule ?? []).filter(o=>o.status==="abatida" && o.due_date.slice(0,7)===`${period.year}-${String(period.month).padStart(2,"0")}`);
  const invoicePayments = invoices.data?.payments ?? [];
  const paid = invoicePayments.reduce((n,p)=>n+p.amount,0)+view.paidPlanned.reduce((n,i)=>n+i.amount,0)+view.paidCash.reduce((n,t)=>n+(t.amount_paid??0),0);
  return <div className="e-page e-bills">
    <SectionTitle title="Contas"><Link to="/faturas">Faturas ›</Link></SectionTitle>
    <p className="e-page-sub">Fixas, variáveis e faturas · {formatPeriod(period)}</p>
    <LoadError error={summary.error || transactions.error || invoices.error || commitments.error || hunterDetail.error} />
    <Summary items={[{label:"A pagar",value:month?view.toPay:null},{label:"A conferir",value:month?view.toCheck:null},{label:"Já pagas",value:month?paid:null}]} />
    {view.review.some(i=>Number(i.prefill?.installments??0)>1 || i.prefill?.bill_visibility==="quote")&&<p className="e-bills-count-note">A conferir: valor deste mês. Parcelas sem data e cotações aparecem abaixo, fora do total.</p>}
    <SectionTitle title="A pagar" />
    <div className="e-list">{view.due.map(i=><BillRow key={i.key} name={`${i.description}${i.label?` · ${i.label}`:""}`} value={i.remaining} detail={`${i.source==="cartao"?"Fatura · ":""}vence ${formatDiaMes(i.date)}${i.source==="cartao"&&i.amount>i.remaining?` · pago ${formatMoney(i.amount-i.remaining)}`:""}`} status={i.status==="vencido"?"Vencida":"A pagar"} to={i.invoice_id!=null?"/faturas":undefined} onClick={()=>{const t=transactions.data?.find(t=>t.id===i.transaction_id);if(t)setEditing(t);else setSelected({due:i});}}/>)}{!view.due.length&&<p className="e-empty">Nenhuma obrigação confirmada pendente neste mês.</p>}</div>
    <SectionTitle title="A conferir"/>
    <div className="e-list">{view.review.map(i=>{const installments=Number(i.prefill?.installments??1);const parcel=Number(i.prefill?.amount??(i.amount&&installments>1?i.amount/installments:0));return <BillRow key={`review-${i.id}`} name={i.description} value={i.amount??0} detail={installments>1?`${installments} × ${formatMoney(parcel)} · datas a confirmar`:i.prefill?.bill_visibility==="quote"||i.prefill?.confirmed===false?"Cotação · contratação a confirmar":i.date?`Referência ${formatDiaMes(i.date)}`:"Vencimento não informado"} status="A conferir" onClick={()=>setSelected({review:i})}/>;})}{view.estimated.map(i=><BillRow key={i.key} name={i.description} value={i.remaining} detail={`Previsto para ${formatDiaMes(i.date)}`} status="Previsto" onClick={()=>setSelected({due:i})}/>)}{!view.review.length&&!view.estimated.length&&<p className="e-empty">Nada para conferir neste mês.</p>}</div>
    <SectionTitle title="Já pagas" />
    <div className="e-list">{invoicePayments.map(p=><BillRow key={`invoice-payment-${p.id}`} name={`Fatura ${p.card_name}`} value={p.amount} detail={`Pago em ${formatDiaMes(p.date)} · fatura ${String(p.invoice_month).padStart(2,"0")}/${p.invoice_year}`} status="Paga" to="/faturas"/>)}{view.paidPlanned.map(i=><BillRow key={i.key} name={i.description} value={i.amount} detail={`Vencia ${formatDiaMes(i.date)}`} status="Paga" onClick={()=>setSelected({due:i})}/>)}{view.paidCash.map(t=><BillRow key={`paid-${t.id}`} name={t.description} value={t.amount_paid??0} detail={`Pago em ${formatDiaMes(t.date)}${t.account_name?` · ${t.account_name}`:""}`} status="Paga" to="/lancamentos"/>)}{abated.map(o=><BillRow key={`abatida-${o.number}`} name={`${hunter!.description} · ${o.label}`} value={o.amount} detail={`Venceria ${formatDiaMes(o.due_date)} · sem saída de caixa`} status="Abatida" />)}{!invoicePayments.length&&!view.paidPlanned.length&&!view.paidCash.length&&!abated.length&&<p className="e-empty">Nenhum pagamento conhecido neste mês.</p>}</div>
    <p className="e-bills-footnote">Faturas contam uma vez, no vencimento. Valores a conferir não reduzem a previsão; abatimentos não saem da conta.</p>
    {editing&&<EntryEditor transaction={editing} categories={categories.data??[]} onClose={()=>setEditing(null)}/>}
    {selected&&<BillActions due={selected.due} review={selected.review} onClose={()=>setSelected(null)}/>}
  </div>;
}
