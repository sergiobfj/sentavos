import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import Modal from "../Modal";
import ConfirmDialog from "../ConfirmDialog";
import type { InvestmentPlan } from "../../lib/tiposContas";
import { useAccounts, useAssets, useCards, useCreateMovement, useCreatePurchase, useCreateTransaction, useCreateInvestmentPlan, useEditInvestmentPlan } from "../../lib/queries";
import { usePeriod } from "../../lib/period";
import { useAuth } from "../../lib/auth";
import { parseMoney, todayIso } from "../../lib/format";
import { instanteSeHoje, lembrarConta, ultimaConta } from "../../lib/tiposContas";
import type { Category, ExpenseClass, Finalidade, Natureza } from "../../lib/types";
import { ExpenseClassField, LoadError } from "./Common";

export const SAVED_EVENT = "sentavos:lancamento-salvo";
type Kind = "expense" | "income" | "contribution" | "redemption";
export default function QuickTransaction({ categories, onClose, initialKind = "expense", plan }: { categories: Category[]; onClose: () => void; initialKind?: Kind; plan?: InvestmentPlan }) {
  const { sessao } = useAuth();
  const accounts = useAccounts(); const cards = useCards(); const assets = useAssets();
  const create = useCreateTransaction(); const purchase = useCreatePurchase(); const movement = useCreateMovement();
  const createPlan = useCreateInvestmentPlan(); const editPlan = useEditInvestmentPlan();
  const [discard, setDiscard] = useState(false);
  const { setPeriod } = usePeriod();
  const [kind, setKind] = useState<Kind>(plan?.type ?? initialKind); const [value, setValue] = useState(plan ? plan.amount.toFixed(2).replace(".",",") : "");
  const [origin, setOrigin] = useState(plan?.account_id ? `account:${plan.account_id}` : ""); const [category, setCategory] = useState(plan?.category_id ? String(plan.category_id) : ""); const [asset, setAsset] = useState(plan?.asset_id ? String(plan.asset_id) : "");
  const [description, setDescription] = useState(plan?.description ?? ""); const [date, setDate] = useState(plan?.date ?? todayIso()); const [installments, setInstallments] = useState(1);
  const [planned, setPlanned] = useState(!!plan); const [expenseClass, setExpenseClass] = useState<ExpenseClass | null>("variable");
  const [purpose, setPurpose] = useState<Finalidade>("pessoal"); const [nature, setNature] = useState<Natureza | null>(null); const [note, setNote] = useState("");
  const inputRef = useRef<HTMLInputElement>(null); const saving = useRef(false); const originTouched = useRef(false);
  useEffect(() => { inputRef.current?.focus(); }, []);
  const availableAccounts = (accounts.data ?? []).filter(a => !a.archived && a.type !== "reconciliation");
  useEffect(() => {
    if (plan || originTouched.current || !accounts.data) return;
    try {
      const lastOrigin = localStorage.getItem(`sentavos:origem:${sessao?.email}`);
      if (lastOrigin?.startsWith("card:") && kind === "expense" && cards.data?.some(c=>!c.archived && c.id===Number(lastOrigin.split(":")[1]))) {
        setOrigin(lastOrigin); return;
      }
    } catch { /* preferências podem estar indisponíveis */ }
    const last = ultimaConta(); const selected = accounts.data.find(a=>a.id===last && !a.archived && a.type!=="reconciliation");
    if (selected) setOrigin(`account:${selected.id}`);
    else if (availableAccounts.length===1) setOrigin(`account:${availableAccounts[0].id}`);
  }, [accounts.data,cards.data,kind]);
  const investment = kind === "contribution" || kind === "redemption";
  const card = origin.startsWith("card:"); const accountId = origin.startsWith("account:") ? Number(origin.split(":")[1]) : null;
  const amount = parseMoney(value); const type = investment ? "investment" : kind;
  const availableCategories = categories.filter(c=>!c.archived && c.type===type);
  const selectedCategory = availableCategories.find(c=>String(c.id)===category) ?? (investment && availableCategories.length === 1 ? availableCategories[0] : undefined);
  const availableAssets = (assets.data ?? []).filter(a=>["fixed_income","equity","crypto"].includes(a.asset_class));
  const pending = create.isPending || purchase.isPending || movement.isPending || createPlan.isPending || editPlan.isPending;
  const valid = !sessao?.somenteLeitura && amount!=null && amount>0 && amount<=999999999 && !!date &&
    (investment && planned || origin!=="" && !!selectedCategory && (!investment || !!availableAssets.find(a=>String(a.id)===asset))) &&
    (!card || kind==="expense") && (planned || date<=todayIso());
  function close() { if (!pending) { if (value || description) setDiscard(true); else onClose(); } }
  async function submit(e: React.FormEvent) {
    e.preventDefault(); if (!valid || amount==null || saving.current) return;
    saving.current = true;
    const label = description.trim() || (investment ? `${kind==="contribution" ? "Aporte" : "Resgate"} · ${availableAssets.find(a=>String(a.id)===asset)?.name ?? "Investimento a definir"}` : selectedCategory?.name ?? "Lançamento");
    try {
      if (investment && planned) {
        const data = {type:kind as "contribution"|"redemption", amount, date, asset_id:asset?Number(asset):null, account_id:accountId, category_id:selectedCategory?.id??null, description:description.trim() || label};
        if (plan) await editPlan.mutateAsync({id:plan.id,data}); else await createPlan.mutateAsync(data);
      }
      else if (card) await purchase.mutateAsync({ card_id:Number(origin.split(":")[1]), category_id:selectedCategory!.id, total_amount:amount, installments, purchase_date:date, description:label, finalidade:purpose, note:note.trim()||null, expense_class:expenseClass, planned });
      else if (investment) await movement.mutateAsync({ asset_id:Number(asset), type:kind, amount, date, account_id:accountId, category_id:selectedCategory!.id, description:label, note:note.trim()||null, occurred_at:instanteSeHoje(date) });
      else await create.mutateAsync({ date, description:label, category_id:selectedCategory!.id, amount_paid:planned?null:amount, amount_planned:planned?amount:null, payment_method:"cash", account_id:accountId, occurred_at:planned?null:instanteSeHoje(date), finalidade:kind==="expense"?purpose:null, nature:kind==="expense"?nature:null, expense_class:kind==="expense"?expenseClass:null, note:note.trim()||null });
      if (!card) lembrarConta(accountId);
      try { if (card || accountId) localStorage.setItem(`sentavos:origem:${sessao?.email}`,origin); } catch { /* opcional */ }
      const [year,month] = date.split("-").map(Number); setPeriod({year,month});
      window.dispatchEvent(new CustomEvent(SAVED_EVENT,{detail:planned?"Previsão salva":"Lançamento salvo"})); onClose();
    } catch { /* mensagem vem da mutation; manter o formulário para corrigir */ }
    finally { saving.current=false; }
  }
  return <><Modal title={plan ? "Editar previsão" : "Novo lançamento"} onClose={close} footer={<button className="btn btn-primary" type="submit" form="quick-transaction" disabled={!valid || pending}>{pending?"Salvando…":planned ? investment ? plan ? "Salvar previsão" : kind==="contribution" ? "Planejar aporte" : "Planejar resgate" : "Salvar previsão" : "Salvar"}</button>}>
    <form id="quick-transaction" className="m-body e-quick" onSubmit={submit}>
      <label htmlFor="quick-value">Valor</label><div className="e-money-input"><span>R$</span><input ref={inputRef} id="quick-value" inputMode="decimal" autoComplete="off" placeholder="0,00" value={value} onChange={e=>{const raw=e.target.value.replace(/[^\d]/g,"");setValue(raw ? (Number(raw)/100).toLocaleString("pt-BR",{minimumFractionDigits:2,maximumFractionDigits:2}) : "");}} required/></div>
      <div className="e-kind" role="group" aria-label="Tipo do lançamento">{([{value:"expense",label:"Despesa"},{value:"income",label:"Entrada"},{value:"contribution",label:"Aporte"},{value:"redemption",label:"Resgate"}] as const).map(k=><button key={k.value} type="button" disabled={!!plan && k.value!==kind} aria-pressed={kind===k.value} onClick={()=>{setKind(k.value);setCategory("");if(card)setOrigin("");}}>{k.label}</button>)}</div>
      <label className="e-planned-switch"><span>Ainda é previsto</span><input role="switch" type="checkbox" checked={planned} disabled={!!plan} onChange={e=>setPlanned(e.target.checked)}/></label>
      {planned&&<div className="field e-planned-date"><label htmlFor="quick-date">Data prevista</label><input id="quick-date" type="date" value={date} onChange={e=>setDate(e.target.value)} required/></div>}
      <div className="e-quick-fields">
      <div className="field"><label htmlFor="quick-origin">{investment ? kind==="contribution"?"De qual conta":"Para qual conta" : "Conta ou cartão"}</label><select id="quick-origin" value={origin} onChange={e=>{originTouched.current=true;setOrigin(e.target.value);}} required={!planned}><option value="">{planned?"A definir":"Selecionar"}</option>{availableAccounts.map(a=><option key={a.id} value={`account:${a.id}`}>{a.name}</option>)}{kind==="expense"&&(cards.data??[]).filter(c=>!c.archived).map(c=><option key={`c-${c.id}`} value={`card:${c.id}`}>Cartão · {c.name}</option>)}<option value="unassigned">Conta ainda não informada</option></select><LoadError error={accounts.error}/></div>
      {(!investment || availableCategories.length!==1)&&<div className="field"><label htmlFor="quick-category">Categoria</label><select id="quick-category" value={selectedCategory?.id??category} onChange={e=>setCategory(e.target.value)} required={!investment||!planned}><option value="">Selecionar categoria</option>{availableCategories.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select>{!availableCategories.length&&<Link to="/configuracoes?secao=categorias" onClick={onClose}>Cadastrar categoria</Link>}</div>}
      {investment&&<div className="field"><label htmlFor="quick-asset">{kind==="contribution"?"Investir em":"Resgatar de"}</label><select id="quick-asset" value={asset} onChange={e=>setAsset(e.target.value)} required={!planned}><option value="">{planned?"Investimento a definir":"Selecionar investimento"}</option>{availableAssets.map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select><LoadError error={assets.error}/></div>}
      </div>
      {card&&<div className="field"><label htmlFor="quick-installments">Parcelas</label><select id="quick-installments" value={installments} onChange={e=>setInstallments(Number(e.target.value))}>{[1,2,3,4,5,6,8,10,12,18,24,36,48,60,72].map(n=><option value={n} key={n}>{n===1?"À vista no cartão":`${n} parcelas`}</option>)}</select><p className="hint">Sai da conta ao pagar a fatura.</p></div>}
      <details className="e-details"><summary>Mais detalhes</summary><div className="field"><label htmlFor="quick-description">Descrição opcional</label><input id="quick-description" maxLength={120} placeholder={selectedCategory?.name??"Descrição"} value={description} onChange={e=>setDescription(e.target.value)}/></div>{!planned&&<div className="field"><label htmlFor="quick-date">Data</label><input id="quick-date" type="date" value={date} max={todayIso()} onChange={e=>setDate(e.target.value)} required/></div>}{kind==="expense"&&<><ExpenseClassField value={expenseClass} onChange={setExpenseClass}/><div className="field"><label htmlFor="quick-purpose">Finalidade</label><select id="quick-purpose" value={purpose} onChange={e=>setPurpose(e.target.value as Finalidade)}><option value="pessoal">Pessoal</option><option value="familia">Família</option><option value="empresa">Empresa</option></select></div>{!card&&<div className="field"><label htmlFor="quick-nature">Análise do gasto</label><select id="quick-nature" value={nature??""} onChange={e=>setNature(e.target.value?e.target.value as Natureza:null)}><option value="">Padrão da categoria</option><option value="consumption">Custo de vida</option><option value="asset_acquisition">Aquisição extraordinária</option><option value="financial">Compromisso financeiro</option></select></div>}</>}{(!investment||!planned)&&<div className="field"><label htmlFor="quick-note">Observação opcional</label><textarea id="quick-note" value={note} onChange={e=>setNote(e.target.value)}/></div>}</details>
      {date>todayIso()&&!planned&&<p className="e-notice">Marque “Ainda é previsto” para uma data futura.</p>}
      <LoadError error={create.error||purchase.error||movement.error||createPlan.error||editPlan.error}/>
    </form>
  </Modal>{discard&&<ConfirmDialog title="Descartar alterações?" confirmLabel="Descartar" consequences={["As informações deste lançamento serão perdidas."]} onConfirm={onClose} onCancel={()=>setDiscard(false)}/>}</>;
}
