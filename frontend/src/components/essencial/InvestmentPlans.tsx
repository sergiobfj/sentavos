import { useState } from "react";
import Modal from "../Modal";
import ConfirmDialog from "../ConfirmDialog";
import QuickTransaction from "./QuickTransaction";
import { LoadError, SectionTitle } from "./Common";
import { useCancelInvestmentPlan, useCategories, useConfirmInvestmentPlan, useInvestmentPlans } from "../../lib/queries";
import { formatDiaMes, formatMoney, todayIso } from "../../lib/format";
import { useAuth } from "../../lib/auth";
import type { InvestmentPlan } from "../../lib/tiposContas";

export default function InvestmentPlans() {
  const plans = useInvestmentPlans();
  const categories = useCategories();
  const confirm = useConfirmInvestmentPlan(), cancel = useCancelInvestmentPlan();
  const {sessao} = useAuth();
  const [selected,setSelected] = useState<InvestmentPlan|null>(null);
  const [editing,setEditing] = useState(false);
  const [cancelling,setCancelling] = useState(false);
  const [date,setDate] = useState(todayIso());
  const [executed,setExecuted] = useState(false);
  const open = (plans.data??[]).filter(p=>p.status==="planned");
  return <>
    <SectionTitle title="Próximos aportes/resgates"/>
    <LoadError error={plans.error}/>
    {open.length ? open.map(p=><button key={p.id} className="e-row" onClick={()=>{setSelected(p);setDate(todayIso());setExecuted(false);}}><span className="e-row-text"><strong>{p.asset_name??(p.description||"Investimento a definir")}</strong><small>{formatDiaMes(p.date)} · {p.type==="contribution"?"A investir":"Resgate previsto"}{p.overdue?" · Atrasado, a confirmar":""}</small></span><span className="e-row-value"><strong>{formatMoney(p.amount)}</strong><small>Previsto ›</small></span></button>):<p className="e-empty">Nenhum plano em aberto neste mês.</p>}
    {selected&&!editing&&<Modal title={selected.type==="contribution"?"Aporte previsto":"Resgate previsto"} onClose={()=>setSelected(null)}><div className="m-body e-bill-sheet"><p className="e-bill-sheet-total">{formatMoney(selected.amount)}</p><p>{selected.asset_name??"Investimento a definir"} · {selected.account_name??"Conta a definir"}</p><p className="e-note">Previsto para {formatDiaMes(selected.date)}. O dinheiro só se move quando você confirma a realização.</p>{!sessao?.somenteLeitura&&<><button className="link" onClick={()=>setEditing(true)}>Editar previsão</button><div className="field"><label htmlFor="plan-confirm-date">Data da realização</label><input id="plan-confirm-date" type="date" value={date} max={todayIso()} onChange={e=>setDate(e.target.value)}/></div><label className="e-checkbox"><input type="checkbox" checked={executed} onChange={e=>setExecuted(e.target.checked)}/>O dinheiro já foi movimentado</label><button className="btn btn-primary" disabled={!executed||!date||confirm.isPending||!selected.account_id||!selected.asset_id||!selected.category_id} onClick={()=>confirm.mutate({id:selected.id,date},{onSuccess:()=>setSelected(null)})}>{confirm.isPending?"Confirmando…":"Confirmar realização"}</button>{(!selected.account_id||!selected.asset_id||!selected.category_id)&&<p className="e-note">Complete conta, investimento e categoria em Editar previsão.</p>}<button className="link" onClick={()=>setCancelling(true)}>Cancelar previsão</button></>}<LoadError error={confirm.error}/></div></Modal>}
    {selected&&editing&&<QuickTransaction categories={categories.data??[]} plan={selected} onClose={()=>{setEditing(false);setSelected(null);}}/>}
    {selected&&cancelling&&<ConfirmDialog title="Cancelar previsão?" itemName={selected.asset_name??selected.description} confirmLabel="Cancelar previsão" consequences={["O valor deixa de entrar na projeção do mês."]} pending={cancel.isPending} error={cancel.error?.message} onCancel={()=>setCancelling(false)} onConfirm={()=>cancel.mutate(selected.id,{onSuccess:()=>{setCancelling(false);setSelected(null);}})}/>}
  </>;
}
