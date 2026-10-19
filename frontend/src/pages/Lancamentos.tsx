import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { EntryEditor, FinancialRow, LoadError, SectionTitle, Summary, transactionLine, type FinancialLine } from "../components/essencial/Common";
import { useBudgetSummary, useCategories, useInvoicesSummary, useTransactions } from "../lib/queries";
import { usePeriod } from "../lib/period";
import type { CategoryType, Transaction } from "../lib/types";

type Filter = "todos" | CategoryType;
const FILTERS: { key:Filter;label:string }[] = [{key:"todos",label:"Todos"},{key:"income",label:"Entradas"},{key:"expense",label:"Despesas"},{key:"investment",label:"Investimentos"}];

export default function Lancamentos() {
  const { label } = usePeriod();
  const navigate = useNavigate();
  const [filter,setFilter] = useState<Filter>("todos");
  const [editing,setEditing] = useState<Transaction|null>(null);
  const transactions = useTransactions();
  const categories = useCategories(true);
  const invoices = useInvoicesSummary();
  const budget = useBudgetSummary();
  const catMap = useMemo(()=>new Map((categories.data??[]).map(c=>[c.id,c])),[categories.data]);
  const lines = useMemo(()=>{
    const entries: FinancialLine[] = (transactions.data??[]).filter(t=>filter==="todos"||catMap.get(t.category_id)?.type===filter).map(t=>transactionLine(t,catMap.get(t.category_id),()=>setEditing(t)));
    if (filter==="todos") entries.push(...(invoices.data?.payments??[]).map(p=>({key:`payment-${p.id}`,description:`Pagamento da fatura · ${p.card_name}`,date:p.date,value:p.amount,detail:`Fatura ${p.invoice_month}/${p.invoice_year}`,status:"Pago · saída de caixa",onClick:()=>navigate("/orcamento?aba=faturas")})));
    return entries.sort((a,b)=>b.date.localeCompare(a.date)||a.key.localeCompare(b.key));
  },[transactions.data,invoices.data?.payments,filter,catMap,navigate]);
  const caixa = budget.data?.caixa;
  const unclassified = (transactions.data??[]).filter(t=>catMap.get(t.category_id)?.type==="expense"&&!t.effective_expense_class).length;
  return <div className="e-page">
    <SectionTitle title="Lançamentos"><Link to="/orcamento?aba=faturas">Faturas ›</Link></SectionTitle>
    <p className="e-page-sub">O que aconteceu em {label} e o que ainda está previsto.</p>
    <Summary items={[{label:"Entrou",value:caixa?.entrou},{label:"Saiu da conta",value:caixa ? caixa.saiu_a_vista+caixa.faturas_pagas : null},{label:"Investiu",value:caixa?.investido}]} />
    <div className="e-filter" role="group" aria-label="Filtrar lançamentos">{FILTERS.map(f=><button key={f.key} className={filter===f.key?"on":""} aria-pressed={filter===f.key} onClick={()=>setFilter(f.key)}>{f.label}</button>)}</div>
    <LoadError error={transactions.error || categories.error || invoices.error || budget.error}/>
    {unclassified>0&&<p className="e-note">{unclassified} {unclassified===1?"despesa ainda não foi classificada":"despesas ainda não foram classificadas"} como fixa ou variável. Você pode corrigir ao editar.</p>}
    <div className="e-list">{lines.map(line=><FinancialRow key={line.key} line={line}/>)}{!lines.length&&!transactions.isLoading&&<p className="e-empty">Nenhum lançamento {filter==="todos"?"neste mês":"neste filtro"}.</p>}</div>
    {transactions.isLoading&&<p className="e-empty">Carregando lançamentos…</p>}
    <div className="e-secondary-links"><Link to="/orcamento">Orçamento e metas</Link><Link to="/planejamento/compromissos">Compromissos</Link><Link to="/organizar">Conferir mês</Link></div>
    {editing&&<EntryEditor transaction={editing} categories={categories.data??[]} onClose={()=>setEditing(null)}/>}
  </div>;
}
