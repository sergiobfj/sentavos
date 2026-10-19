import { useState } from "react";
import { Link } from "react-router-dom";
import { useAccountsSummary, usePlanningMonth, useReconciliation } from "../../lib/queries";
import { currentPeriod } from "../../lib/period";
import { formatDiaMes, formatMoney, parseMoney } from "../../lib/format";

export default function HunterAdvance() {
  const period = currentPeriod();
  const planning = usePlanningMonth(period,null);
  const accounts = useAccountsSummary();
  const reconciliation = useReconciliation(period);
  const [stage,setStage] = useState<"now"|"first"|"all">("now");
  const [extra,setExtra] = useState("");
  const [advance,setAdvance] = useState("800");
  const month = planning.data?.months[0];
  const known = (accounts.data?.accounts??[]).some(a=>!a.archived&&!a.restricted&&a.balance!=null);
  const incomes = (month?.items??[]).filter(i=>i.direction==="entrada"&&i.remaining>0).sort((a,b)=>a.date.localeCompare(b.date));
  const firstDate = incomes[0]?.date;
  const firstIncome = incomes.filter(i=>i.date===firstDate).reduce((n,i)=>n+i.remaining,0);
  const obligations = (month?.expense??0)+(month?.reserved??0);
  const base = known&&month ? month.opening-obligations : null;
  const stages = {
    now:base,
    first:base==null?null:base+firstIncome,
    all:base==null?null:base+(month?.income??0),
  };
  const chosen=stages[stage];
  const spending=parseMoney(extra)||0;
  const amount=parseMoney(advance)||0;
  const after=chosen==null?null:chosen-spending-amount;
  const unresolved=(reconciliation.data?.items??[]).filter(i=>i.status==="pendente"||i.status==="confirmar").length;
  return <details className="e-advance"><summary>Simular antecipação da Hunter <span>›</span></summary>
    <p>Escolha quando o dinheiro entrar. A conta já reserva os pagamentos registrados.</p>
    <div className="e-advance-stages" role="group" aria-label="Etapa da simulação">
      <button aria-pressed={stage==="now"} onClick={()=>setStage("now")}>Agora<b>{stages.now==null?"—":formatMoney(stages.now)}</b></button>
      <button aria-pressed={stage==="first"} onClick={()=>setStage("first")}>Após {firstDate?formatDiaMes(firstDate):"primeiras entradas"}<b>{stages.first==null?"—":formatMoney(stages.first)}</b></button>
      <button aria-pressed={stage==="all"} onClick={()=>setStage("all")}>Após todas entradas<b>{stages.all==null?"—":formatMoney(stages.all)}</b></button>
    </div>
    <div className="e-advance-meta"><span>Compromissos e reservas registrados</span><b>{formatMoney(obligations)}</b></div>
    <div className="e-advance-inputs"><label>Gasto extra<input inputMode="decimal" value={extra} onChange={e=>setExtra(e.target.value)} placeholder="R$ 0"/></label><label>Antecipação simulada<input inputMode="decimal" value={advance} onChange={e=>setAdvance(e.target.value)} placeholder="R$ 0"/></label></div>
    <div className="e-advance-options">{[200,500,800,1000].map(n=><button key={n} onClick={()=>setAdvance(String(n))}>{formatMoney(n)}</button>)}</div>
    <div className="e-advance-result"><span>Depois do gasto e da antecipação</span><b className="tnum">{after==null?"—":formatMoney(after)}</b></div>
    <p className="e-bills-footnote">{unresolved?`${unresolved} informações ainda precisam de conferência; este teto não é um máximo seguro confirmado. `:""}Valores previstos só entram na etapa escolhida após recebimento. Simular não cria pagamento ou transação. <Link to="/organizar">Conferir mês</Link></p>
  </details>;
}
