import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { EntryEditor, FinancialRow, LoadError, SectionTitle, Summary, transactionLine, type FinancialLine } from "../components/essencial/Common";
import { useBudgetSummary, useCategories, useInvoicesSummary, useTransactions } from "../lib/queries";
import type { CategoryType, Transaction } from "../lib/types";
import { formatDiaMes } from "../lib/format";

type Filter = "todos" | CategoryType;
const FILTERS: { key:Filter;label:string }[] = [{key:"todos",label:"Todos"},{key:"income",label:"Entradas"},{key:"expense",label:"Despesas"},{key:"investment",label:"Investimentos"}];

export default function Lancamentos() {
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
  const days = useMemo(()=>{
    const groups = new Map<string, FinancialLine[]>();
    for (const line of lines) {
      const day = groups.get(line.date);
      if (day) day.push(line);
      else groups.set(line.date,[line]);
    }
    return [...groups];
  },[lines]);
  const caixa = budget.data?.caixa;
  const unclassified = (transactions.data??[]).filter(t=>catMap.get(t.category_id)?.type==="expense"&&!t.effective_expense_class).length;
  return <div className="e-page e-journal">
    <SectionTitle title="Lançamentos"><Link to="/orcamento?aba=faturas">Faturas ›</Link></SectionTitle>
    <span className="sr-only">Resumo</span>
    <Summary items={[{label:"Entrou",value:caixa?.entrou},{label:"Saiu da conta",value:caixa ? caixa.saiu_a_vista+caixa.faturas_pagas : null},{label:"Investiu",value:caixa?.investido}]} />
    <div className="e-filter" role="group" aria-label="Filtrar lançamentos">{FILTERS.map(f=><button key={f.key} className={filter===f.key?"on":""} aria-pressed={filter===f.key} onClick={()=>setFilter(f.key)}>{f.label}</button>)}</div>
    <LoadError error={transactions.error || categories.error || invoices.error || budget.error}/>
    {unclassified>0&&<details className="e-journal-review"><summary>{unclassified} {unclassified===1?"despesa a classificar":"despesas a classificar"}</summary><p className="e-note">Classifique como fixa ou variável ao editar o lançamento.</p></details>}
    <div className="e-journal-list">{days.map(([date,entries])=><section className="e-day" key={date} aria-label={formatDiaMes(date)}><h3><time dateTime={date}>{new Date(`${date}T12:00:00`).toLocaleDateString("pt-BR",{weekday:"long"})}<span> · {formatDiaMes(date)}</span></time></h3><div className="e-list">{entries.map(line=><FinancialRow key={line.key} line={line} grouped/>)}</div></section>)}{!lines.length&&!transactions.isLoading&&<p className="e-empty">Nenhum lançamento {filter==="todos"?"neste mês":"neste filtro"}.</p>}</div>
    {transactions.isLoading&&<p className="e-empty">Carregando lançamentos…</p>}
    <details className="e-journal-tools"><summary>Mais opções</summary><div className="e-secondary-links"><Link to="/orcamento">Orçamento e metas</Link><Link to="/planejamento/compromissos">Compromissos</Link><Link to="/organizar">Conferir mês</Link></div></details>
    {editing&&<EntryEditor transaction={editing} categories={categories.data??[]} onClose={()=>setEditing(null)}/>}
  </div>;
}
