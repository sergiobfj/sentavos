import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import Modal from "../Modal";
import { useAccounts, useAssets, useCards, useCreateMovement, useCreatePurchase, useCreateTransaction } from "../../lib/queries";
import { usePeriod } from "../../lib/period";
import { useAuth } from "../../lib/auth";
import { parseMoney, todayIso } from "../../lib/format";
import { instanteSeHoje, lembrarConta, ultimaConta } from "../../lib/tiposContas";
import type { Category, ExpenseClass, Finalidade, Natureza } from "../../lib/types";
import { ExpenseClassField, LoadError } from "./Common";

export const SAVED_EVENT = "sentavos:lancamento-salvo";
type Kind = "expense" | "income" | "contribution" | "redemption";
export default function QuickTransaction({ categories, onClose }: { categories: Category[]; onClose: () => void }) {
  const { sessao } = useAuth();
  const accounts = useAccounts(); const cards = useCards(); const assets = useAssets();
  const create = useCreateTransaction(); const purchase = useCreatePurchase(); const movement = useCreateMovement();
  const { setPeriod } = usePeriod();
  const [kind, setKind] = useState<Kind>("expense"); const [value, setValue] = useState("");
  const [origin, setOrigin] = useState(""); const [category, setCategory] = useState(""); const [asset, setAsset] = useState("");
  const [description, setDescription] = useState(""); const [date, setDate] = useState(todayIso); const [installments, setInstallments] = useState(1);
  const [planned, setPlanned] = useState(false); const [expenseClass, setExpenseClass] = useState<ExpenseClass | null>("variable");
  const [purpose, setPurpose] = useState<Finalidade>("pessoal"); const [nature, setNature] = useState<Natureza | null>(null); const [note, setNote] = useState("");
  const inputRef = useRef<HTMLInputElement>(null); const saving = useRef(false); const originTouched = useRef(false);
  useEffect(() => { inputRef.current?.focus(); }, []);
  const availableAccounts = (accounts.data ?? []).filter(a => !a.archived && a.type !== "reconciliation");
  useEffect(() => {
    if (originTouched.current || !accounts.data) return;
    const last = ultimaConta(); const selected = accounts.data.find(a=>a.id===last && !a.archived && a.type!=="reconciliation");
    if (selected) setOrigin(`account:${selected.id}`);
    else if (availableAccounts.length===1) setOrigin(`account:${availableAccounts[0].id}`);
  }, [accounts.data]);
  const investment = kind === "contribution" || kind === "redemption";
  const card = origin.startsWith("card:"); const accountId = origin.startsWith("account:") ? Number(origin.split(":")[1]) : null;
  const amount = parseMoney(value); const type = investment ? "investment" : kind;
  const availableCategories = categories.filter(c=>!c.archived && c.type===type);
  const selectedCategory = availableCategories.find(c=>String(c.id)===category);
  const availableAssets = (assets.data ?? []).filter(a=>["fixed_income","equity","crypto"].includes(a.asset_class));
  const pending = create.isPending || purchase.isPending || movement.isPending;
  const valid = !sessao?.somenteLeitura && amount!=null && amount>0 && amount<=999999999 && origin!=="" && !!selectedCategory && (!investment || !!availableAssets.find(a=>String(a.id)===asset)) && (!card || kind==="expense") && (planned || date<=todayIso());
  async function submit(e: React.FormEvent) {
    e.preventDefault(); if (!valid || amount==null || !selectedCategory || saving.current) return;
    saving.current = true;
    const label = description.trim() || (investment ? `${kind==="contribution" ? "Aporte" : "Resgate"} · ${availableAssets.find(a=>String(a.id)===asset)?.name}` : selectedCategory.name);
    try {
      if (card) await purchase.mutateAsync({ card_id:Number(origin.split(":")[1]), category_id:selectedCategory.id, total_amount:amount, installments, purchase_date:date, description:label, finalidade:purpose, note:note.trim()||null, expense_class:expenseClass });
      else if (investment) await movement.mutateAsync({ asset_id:Number(asset), type:kind, amount, date, account_id:accountId, category_id:selectedCategory.id, description:label, occurred_at:instanteSeHoje(date) });
      else await create.mutateAsync({ date, description:label, category_id:selectedCategory.id, amount_paid:planned?null:amount, amount_planned:planned?amount:null, payment_method:"cash", account_id:accountId, occurred_at:planned?null:instanteSeHoje(date), finalidade:kind==="expense"?purpose:null, nature:kind==="expense"?nature:null, expense_class:kind==="expense"?expenseClass:null, note:note.trim()||null });
      if (!card) lembrarConta(accountId);
      const [year,month] = date.split("-").map(Number); setPeriod({year,month});
      window.dispatchEvent(new CustomEvent(SAVED_EVENT)); onClose();
    } catch { /* mensagem vem da mutation; manter o formulário para corrigir */ }
    finally { saving.current=false; }
  }
  return <Modal title="Novo lançamento" onClose={()=>{if(!pending)onClose();}} footer={<><button className="btn btn-ghost" onClick={onClose} disabled={pending}>Cancelar</button><button className="btn btn-primary" type="submit" form="quick-transaction" disabled={!valid || pending}>{pending?"Salvando…":"Salvar"}</button></>}>
    <form id="quick-transaction" className="m-body e-quick" onSubmit={submit}>
      <label htmlFor="quick-value">Valor</label><div className="e-money-input"><span>R$</span><input ref={inputRef} id="quick-value" inputMode="decimal" autoComplete="off" placeholder="0,00" value={value} onChange={e=>setValue(e.target.value)} required/></div>
      <div className="tipo-toggle" role="group" aria-label="Tipo do lançamento">{([{value:"expense",label:"Despesa"},{value:"income",label:"Entrada"},{value:"contribution",label:"Aporte"},{value:"redemption",label:"Resgate"}] as const).map(k=><button key={k.value} type="button" className={kind===k.value?"on":""} aria-pressed={kind===k.value} onClick={()=>{setKind(k.value);setCategory("");setPlanned(false);if(card)setOrigin("");}}>{k.label}</button>)}</div>
      <div className="field"><label htmlFor="quick-origin">{investment ? kind==="contribution"?"Conta de origem":"Conta de destino" : "Conta ou cartão"}</label><select id="quick-origin" value={origin} onChange={e=>{originTouched.current=true;setOrigin(e.target.value);if(e.target.value.startsWith("card:"))setPlanned(false);}} required><option value="" disabled>Selecionar</option>{availableAccounts.map(a=><option key={a.id} value={`account:${a.id}`}>{a.name}</option>)}{kind==="expense"&&(cards.data??[]).filter(c=>!c.archived).map(c=><option key={`c-${c.id}`} value={`card:${c.id}`}>Cartão · {c.name}</option>)}<option value="unassigned">Conta ainda não informada</option></select>{origin==="unassigned"&&<p className="hint">O lançamento não atualizará o saldo de uma conta até você vinculá-la. <Link to="/contas" onClick={onClose}>Organizar contas</Link></p>}<LoadError error={accounts.error}/></div>
      <div className="field"><label htmlFor="quick-category">Categoria</label><select id="quick-category" value={category} onChange={e=>setCategory(e.target.value)} required><option value="" disabled>Selecionar categoria</option>{availableCategories.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select>{!availableCategories.length&&<p className="hint"><Link to="/configuracoes?secao=categorias" onClick={onClose}>Cadastrar categoria</Link></p>}</div>
      {!category&&<div className="e-shortcuts">{availableCategories.slice(0,3).map(c=><button type="button" className="btn btn-ghost btn-sm" key={c.id} onClick={()=>setCategory(String(c.id))}>{c.name}</button>)}</div>}
      {investment&&<div className="field"><label htmlFor="quick-asset">Investimento</label><select id="quick-asset" value={asset} onChange={e=>setAsset(e.target.value)} required><option value="" disabled>Selecionar investimento</option>{availableAssets.map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select><LoadError error={assets.error}/>{!availableAssets.length&&<Link to="/patrimonio" onClick={onClose}>Cadastrar investimento</Link>}</div>}
      {card&&<div className="field"><label htmlFor="quick-installments">Parcelas</label><select id="quick-installments" value={installments} onChange={e=>setInstallments(Number(e.target.value))}>{[1,2,3,4,5,6,8,10,12,18,24,36,48,60,72].map(n=><option value={n} key={n}>{n===1?"1 parcela":`${n} parcelas`}</option>)}</select><p className="hint">O cartão cadastrado define a fatura. O dinheiro sai ao pagar a fatura.</p></div>}
      <details className="e-details"><summary>Mais detalhes</summary><div className="field"><label htmlFor="quick-description">Descrição opcional</label><input id="quick-description" placeholder={selectedCategory?.name??"Descrição"} value={description} onChange={e=>setDescription(e.target.value)}/></div><div className="field"><label htmlFor="quick-date">Data</label><input id="quick-date" type="date" value={date} onChange={e=>setDate(e.target.value)} required/></div>{!investment&&!card&&<label className="e-checkbox"><input type="checkbox" checked={planned} onChange={e=>setPlanned(e.target.checked)}/>Ainda é previsto</label>}{kind==="expense"&&<><ExpenseClassField value={expenseClass} onChange={setExpenseClass}/><div className="field"><label htmlFor="quick-purpose">Finalidade</label><select id="quick-purpose" value={purpose} onChange={e=>setPurpose(e.target.value as Finalidade)}><option value="pessoal">Pessoal</option><option value="familia">Família</option><option value="empresa">Empresa</option></select></div>{!card&&<div className="field"><label htmlFor="quick-nature">Análise do gasto</label><select id="quick-nature" value={nature??""} onChange={e=>setNature(e.target.value?e.target.value as Natureza:null)}><option value="">Usar padrão da categoria</option><option value="consumption">Custo de vida</option><option value="asset_acquisition">Aquisição extraordinária</option><option value="financial">Compromisso financeiro</option></select></div>}</>}<div className="field"><label htmlFor="quick-note">Observação opcional</label><textarea id="quick-note" value={note} onChange={e=>setNote(e.target.value)}/></div></details>
      {date>todayIso()&&!planned&&<p className="e-notice">Para uma entrada ou despesa futura, marque “Ainda é previsto”.</p>}
      <LoadError error={create.error||purchase.error||movement.error}/>
    </form>
  </Modal>;
}
