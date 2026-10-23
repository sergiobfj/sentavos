import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ContasSheet } from "../components/planejamento/Folhas";
import Modal from "../components/Modal";
import { EntryEditor, LoadError, MonthGroup, SectionTitle, Summary, transactionLine, type FinancialLine } from "../components/essencial/Common";
import { useCategories, useMonthSummary, useTransactions } from "../lib/queries";
import { useAuth } from "../lib/auth";
import { formatMoney } from "../lib/format";
import type { Transaction } from "../lib/types";
import type { PlanoItem } from "../lib/tiposPlanejamento";

export default function MeuMes() {
  const { sessao } = useAuth();
  const navigate = useNavigate();
  const [editing,setEditing] = useState<Transaction|null>(null);
  const [sheet,setSheet] = useState<"calculo"|"contas"|null>(null);
  const summary = useMonthSummary();
  const transactions = useTransactions();
  const categories = useCategories(true);
  const r = summary.data;
  const cats = useMemo(()=>new Map((categories.data??[]).map(c=>[c.id,c])),[categories.data]);
  const realized = (transactions.data??[]).filter(t=>t.amount_paid!=null);
  const paid = (type:string, fixed?:boolean)=>realized.filter(t=>cats.get(t.category_id)?.type===type &&
    (type!=="expense" || (t.effective_expense_class==="fixed")===fixed));
  const incomes=paid("income"), fixed=paid("expense",true), variable=paid("expense",false), invested=paid("investment");
  const pending=(r?.month.items??[]).filter(i=>i.remaining>0);
  const dueIncome=pending.filter(i=>i.direction==="entrada"&&i.category_type!=="investment");
  const dueFixed=pending.filter(i=>i.direction==="saida"&&i.expense_class==="fixed");
  const dueVariable=pending.filter(i=>i.direction==="saida"&&i.expense_class!=="fixed"&&i.category_type!=="investment");
  function itemLine(i:PlanoItem):FinancialLine {
    const t=transactions.data?.find(t=>t.id===i.transaction_id);
    return {key:i.key,description:i.description,date:i.date,value:i.remaining,income:i.direction==="entrada",
      status:i.certainty!=="confirmado"?"A conferir":i.direction==="entrada"?"A receber":"A pagar",
      onClick:t?()=>setEditing(t):()=>navigate("/contas-a-pagar")};
  }
  const lines=(ts:Transaction[],items:PlanoItem[])=>[...items.map(itemLine),...ts.map(t=>transactionLine(t,cats.get(t.category_id),()=>setEditing(t)))];
  const total=(ts:Transaction[])=>ts.reduce((n,t)=>n+(t.amount_paid??0),0);
  const due=(items:PlanoItem[])=>items.reduce((n,i)=>n+i.remaining,0);
  const day=r?.balance_date?`${r.balance_date.slice(8,10)}/${r.balance_date.slice(5,7)}`:null;
  const reserveLines:FinancialLine[]=(r?.month.reserves??[]).filter(i=>i.source==="aporte").map(i=>({key:i.key,description:i.description,date:`${r!.month.year}-${String(r!.month.month).padStart(2,"0")}-01`,value:i.amount,status:"A investir",onClick:()=>navigate("/investimentos")}));
  const error=summary.error||transactions.error||categories.error;
  if(error) return <LoadError error={error} retry={()=>{summary.refetch();transactions.refetch();categories.refetch();}}/>;
  if(!r||!transactions.data||!categories.data) return <div className="loading" role="status">Carregando mês…</div>;
  return <div className="e-month">
    <div className="e-lead">
      <section className="e-primary" aria-labelledby="e-money-label"><p id="e-money-label">{r.balance_kind==="calculado"?"Saldo calculado":"Saldo observado"}</p><strong className="tnum">{r.money_now==null?"—":formatMoney(r.money_now)}</strong><button className="e-subtle" onClick={()=>setSheet("contas")}>{day?`${r.balance_kind==="calculado"?"Calculado desde":"Saldo observado em"} ${day} · `:""}{r.balance_pending||r.balance_stale?"Atualização pendente":day?"ver contas":"Informar saldo das contas"} ›</button></section>
      <section className="e-projection" aria-labelledby="e-projection-label"><p id="e-projection-label">Vai sobrar</p><button onClick={()=>setSheet("calculo")} disabled={!r} className="e-projection-value tnum">{r?.projected==null?"—":formatMoney(r.projected)} <span>›</span></button><small>{r?.reasons.length?(r.projected==null?r.reasons[0]:"Previsão parcial · ver detalhes"):"Após receber, pagar e investir"}</small></section>
    </div>
    <Summary items={[{label:"A receber",value:r?.to_receive},{label:"A pagar",value:r?.to_pay,to:"/contas-a-pagar"},{label:"Investido no mês",value:r?.contributed,to:"/investimentos"}]}/>
    {!!r?.to_invest&&<Link className="e-to-invest" to="/investimentos"><span>A investir</span><b className="tnum">{formatMoney(r.to_invest)} ›</b></Link>}
    {!!r?.to_check&&<Link className="e-review-link" to="/contas-a-pagar">A conferir {formatMoney(r.to_check)} · previsão parcial ›</Link>}
    <LoadError error={summary.error||transactions.error||categories.error}/>
    <SectionTitle title="Resumo do mês"/>
    <div className="e-groups">
      <MonthGroup title="Entradas" mark="+" value={`${formatMoney(total(incomes))} recebido`} summary={`Recebido ${formatMoney(total(incomes))} · A receber ${formatMoney(due(dueIncome))}`} lines={lines(incomes,dueIncome)}/>
      <MonthGroup title="Despesas fixas" mark="−" value={`${formatMoney(total(fixed))} gasto`} summary={`Gasto ${formatMoney(total(fixed))} · A pagar ${formatMoney(due(dueFixed))}`} lines={lines(fixed,dueFixed)} note="Compras no cartão são gasto reconhecido; o caixa sai no pagamento da fatura."/>
      <MonthGroup title="Despesas variáveis" mark="−" value={`${formatMoney(total(variable))} gasto`} summary={`Gasto ${formatMoney(total(variable))} · A pagar ${formatMoney(due(dueVariable))}`} lines={lines(variable,dueVariable)}/>
      <MonthGroup title="Investimentos" mark="↗" value={`${formatMoney(r?.contributed??0)} aportado`} summary={`Aportado ${formatMoney(r?.contributed)} · Resgatado ${formatMoney(r?.redeemed)} · A investir ${formatMoney(r?.to_invest)}`} lines={[...reserveLines,...lines(invested,pending.filter(i=>i.category_type==="investment"))]}/>
    </div>
    {editing&&<EntryEditor transaction={editing} categories={categories.data??[]} onClose={()=>setEditing(null)}/>}
    {sheet==="calculo"&&r&&<Modal title="Previsão do mês" onClose={()=>setSheet(null)}><div className="m-body e-calculation"><p>Saldo conhecido <b>{r.money_now==null?"—":formatMoney(r.month.opening)}</b></p><p>+ A receber <b>{formatMoney(r.to_receive)}</b></p><p>+ Resgates previstos <b>{formatMoney(r.month.items.filter(i=>i.direction==="entrada"&&i.category_type==="investment").reduce((n,i)=>n+i.remaining,0))}</b></p><p>− A pagar <b>{formatMoney(r.to_pay)}</b></p><p>− A investir <b>{formatMoney(r.to_invest)}</b></p>{r.month.reserved-r.to_invest>0&&<p>− Reservas existentes <b>{formatMoney(r.month.reserved-r.to_invest)}</b></p>}<p>Vai sobrar <b>{r.projected==null?"—":formatMoney(r.projected)}</b></p>{r.reasons.map(reason=><p className="e-note" key={reason}>{reason}</p>)}</div></Modal>}
    {sheet==="contas"&&r&&<ContasSheet contas={r.plan.accounts} aviso={r.plan.balance_warning} period={{year:r.month.year,month:r.month.month}} podeEscrever={!sessao?.somenteLeitura} onClose={()=>setSheet(null)}/>}
  </div>;
}
