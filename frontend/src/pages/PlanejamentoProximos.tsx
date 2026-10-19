import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { LoadError } from "../components/essencial/Common";
import { usePlanningHorizon } from "../lib/queries";
import { currentPeriod, formatPeriod, usePeriod } from "../lib/period";
import { formatMoney } from "../lib/format";
import type { PlanoMes } from "../lib/tiposPlanejamento";

function row(m: PlanoMes) {
  const groups = m.expense_groups;
  return {
    income:m.income,
    fixed:(groups?.fixed??0)+(groups?.invoices??0),
    variable:(groups?.variable??0)+(groups?.unclassified??0),
    investment:m.reserves.filter(r=>r.source==="aporte").reduce((v,r)=>v+r.amount,0),
    available:m.available,
  };
}

export default function PlanejamentoProximos() {
  const {period,setPeriod} = usePeriod();
  const navigate = useNavigate();
  const [count,setCount] = useState<3|6|12>(3);
  const now = currentPeriod();
  const offset = Math.max(0,(period.year-now.year)*12+period.month-now.month);
  const horizon = usePlanningHorizon(Math.min(offset+count,24));
  const months = (horizon.data?.months??[]).filter(m=>(m.year-period.year)*12+m.month-period.month>=0).slice(0,count);
  const hasOpening = !!horizon.data?.accounts.some(a=>a.included&&!a.stale&&a.as_of!=null);
  const labels = [{name:"Entradas a receber",key:"income"},{name:"Despesas fixas e faturas",key:"fixed"},{name:"Despesas variáveis e a confirmar",key:"variable"},{name:"Investimentos planejados",key:"investment"},{name:"Saldo após contas e reservas",key:"available"}] as const;
  function open(m:PlanoMes) {setPeriod({year:m.year,month:m.month});navigate("/");}
  return <div className="e-page">
    <div className="e-section-title"><h1>Comparar meses</h1><Link to="/">Meu mês ›</Link></div>
    <p className="e-page-sub">O saldo de cada mês parte do fechamento calculado para o mês anterior.</p>
    <div className="e-filter" role="group" aria-label="Quantidade de meses">{([3,6,12] as const).map(n=><button key={n} aria-pressed={count===n} className={count===n?"on":""} onClick={()=>setCount(n)}>{n} meses</button>)}</div>
    <LoadError error={horizon.error}/>
    {months.length>0&&<>
      <div className="e-comparison" role="table" aria-label="Comparação de meses">
        <div className="e-comparison-head" role="row" style={{gridTemplateColumns:`minmax(170px,1.3fr) repeat(${months.length},minmax(120px,1fr))`}}><span role="columnheader">Informação</span>{months.map(m=><button role="columnheader" key={`${m.year}-${m.month}`} onClick={()=>open(m)}>{formatPeriod({year:m.year,month:m.month})}</button>)}</div>
        {labels.map(l=><div className="e-comparison-row" role="row" key={l.key} style={{gridTemplateColumns:`minmax(170px,1.3fr) repeat(${months.length},minmax(120px,1fr))`}}><span role="rowheader">{l.name}</span>{months.map(m=><b role="cell" className="tnum" key={`${m.year}-${m.month}`}>{l.key==="available"&&!hasOpening?"—":formatMoney(row(m)[l.key])}</b>)}</div>)}
      </div>
      <div className="e-comparison-mobile">{months.map(m=><button className="e-comparison-card" key={`${m.year}-${m.month}`} onClick={()=>open(m)}><strong>{formatPeriod({year:m.year,month:m.month})}</strong><span>Entradas {formatMoney(m.income)}</span><span>Fixas e faturas {formatMoney(row(m).fixed)}</span><span>Variáveis e a confirmar {formatMoney(row(m).variable)}</span><span>Investimentos {formatMoney(row(m).investment)}</span><b className="tnum">Sobra {hasOpening?formatMoney(m.available):"—"}</b><small>Ver contas do mês ›</small></button>)}</div>
    </>}
    {!months.length&&!horizon.isLoading&&<p className="e-empty">Ainda não há meses para comparar.</p>}
    <p className="e-note">Despesas sem classificação aparecem em “variáveis e a confirmar”. Faturas são obrigações de caixa; compras no cartão continuam no gasto do mês da compra ou parcela. Investimentos planejados são reservas.</p>
  </div>;
}
