import { useState } from "react";
import { Link } from "react-router-dom";
import Modal from "../Modal";
import { useAuth } from "../../lib/auth";
import { formatDiaMes, formatMoney, todayIso } from "../../lib/format";
import { useAccountsSummary, useCategories, useLinkReconciliation, usePagarOcorrencia, useReconCommitment, useReconTransaction, useTransactions, useUpdateReconciliation, useVincularOcorrencia } from "../../lib/queries";
import type { PlanoItem, ReconciliationItem } from "../../lib/tiposPlanejamento";

export default function BillActions({ due, review, onClose }: { due?: PlanoItem; review?: ReconciliationItem; onClose: () => void }) {
  const { sessao } = useAuth();
  const [action, setAction] = useState<"paid" | "due" | "skip" | null>(null);
  const [existingId, setExistingId] = useState("");
  const [accountId, setAccountId] = useState("");
  const [balanceTiming, setBalanceTiming] = useState<"included" | "after" | "">("");
  const [categoryId, setCategoryId] = useState("");
  const [date, setDate] = useState("");
  const transactions = useTransactions();
  const accounts = useAccountsSummary();
  const categories = useCategories();
  const linkReview = useLinkReconciliation();
  const linkDue = useVincularOcorrencia();
  const payDue = usePagarOcorrencia();
  const createPayment = useReconTransaction();
  const createDue = useReconCommitment();
  const update = useUpdateReconciliation();
  const value = due?.remaining ?? review?.amount ?? 0;
  const installments = Number(review?.prefill?.installments ?? 1);
  const installmentValue = Number(review?.prefill?.amount ?? (review?.amount && installments > 1 ? review.amount / installments : value));
  const needsInstallmentDetails = !!review && installments > 1;
  const chooseAction = (next: "paid" | "due" | "skip") => {
    setAction(next);
    setExistingId("");
    setAccountId("");
    setCategoryId("");
    setDate("");
    setBalanceTiming("");
  };
  const reviewMonth = review ? `${review.year}-${String(review.month).padStart(2, "0")}` : null;
  const account = accounts.data?.accounts.find(a=>a.id===Number(accountId));
  const observedDay = account?.observed_at ? new Date(account.observed_at).toLocaleDateString("sv-SE",{timeZone:"America/Sao_Paulo"}) : null;
  const needsTiming = !!date && date === observedDay;
  const occurredAt = needsTiming && balanceTiming === "after" ? new Date().toISOString() : null;
  const candidates = (transactions.data ?? []).filter(t => t.amount_paid != null && t.amount_paid > 0 &&
    t.account_id != null && t.purchase_id == null && t.commitment_id == null && t.payment_method !== "credit" &&
    (!reviewMonth || t.date.startsWith(reviewMonth)) &&
    Math.abs((t.amount_paid ?? 0) - value) < 5);
  const error = linkReview.error || linkDue.error || payDue.error || createPayment.error || createDue.error || update.error;
  const pending = linkReview.isPending || linkDue.isPending || payDue.isPending || createPayment.isPending || createDue.isPending || update.isPending;
  const writable = !sessao?.somenteLeitura;
  const isCard = due?.invoice_id != null;
  const needsReopen = !!review?.link_missing && review.status === "resolvido";

  return <Modal title={due?.description ?? review?.description ?? "Conta"} onClose={onClose}><div className="m-body e-bill-sheet">
    <p className="e-bill-sheet-total tnum">{review?.amount == null && !due ? "Valor a confirmar" : formatMoney(value)}</p>
    <p className="hint">{due ? `Vence ${formatDiaMes(due.date)}${due.label ? ` · ${due.label}` : ""}` : installments > 1 ? `${installments} parcelas de ${formatMoney(installmentValue)} · datas a confirmar` : review?.date ? `Referência ${formatDiaMes(review.date)}` : "Vencimento não informado"}</p>
    {review?.question && <p className="e-note">{review.question}</p>}
    {isCard ? <Link to="/faturas">Ver fatura e registrar pagamento ›</Link> : <>
      {needsReopen && <p className="e-note">O vínculo anterior foi apagado. Reabra o item em Conferir mês antes de criar outro registro.</p>}
      {writable && !needsReopen && <div className="e-filter" role="group" aria-label="Situação da conta">{!needsInstallmentDetails && <button className={action === "paid" ? "on" : ""} onClick={()=>chooseAction("paid")}>Já paguei</button>}{review && <><button className={action === "due" ? "on" : ""} onClick={()=>chooseAction("due")}>Ainda vou pagar</button><button className={action === "skip" ? "on" : ""} onClick={()=>chooseAction("skip")}>Não se aplica</button></>}</div>}
      {needsInstallmentDetails && <p className="e-note">Parcelamento sem lançamentos individuais conferidos. Informe a forma de pagamento e as datas em Lançamentos; depois vincule a compra em Conferir mês. Nenhum pagamento será criado aqui.</p>}
      {action === "paid" && <><div className="field"><label htmlFor="bill-existing">Pagamento já registrado</label><select id="bill-existing" value={existingId} onChange={e=>setExistingId(e.target.value)}><option value="">Não encontrei o lançamento com conta</option>{candidates.map(t=><option key={t.id} value={t.id}>{t.date} · {t.description} · {formatMoney(t.amount_paid)}</option>)}</select><p className="hint">Se o lançamento antigo está sem conta, informe a origem em Lançamentos antes de vincular.</p></div>
        {existingId ? <button className="btn btn-primary btn-block" disabled={pending} onClick={()=>review ? linkReview.mutate({id:review.id,data:{transaction_id:Number(existingId)}},{onSuccess:onClose}) : linkDue.mutate({id:due!.commitment_id!,numero:due!.commitment_no!,transactionId:Number(existingId)},{onSuccess:onClose})}>Vincular sem nova saída</button> : <><div className="field"><label htmlFor="bill-account">Conta de origem</label><select id="bill-account" value={accountId} onChange={e=>{setAccountId(e.target.value);setBalanceTiming("");}}><option value="">Selecione a conta</option>{(accounts.data?.accounts ?? []).filter(a=>!a.archived&&!a.restricted).map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></div>{review && <div className="field"><label htmlFor="bill-category">Categoria</label><select id="bill-category" value={categoryId} onChange={e=>setCategoryId(e.target.value)}><option value="">Selecione a categoria</option>{(categories.data ?? []).filter(c=>c.type==="expense"&&!c.archived).map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></div>}<div className="field"><label htmlFor="bill-date">Data do pagamento</label><input id="bill-date" type="date" value={date} max={todayIso()} onChange={e=>{setDate(e.target.value);setBalanceTiming("");}} /></div>{needsTiming && <div className="field"><label htmlFor="bill-timing">O saldo informado hoje já inclui este pagamento?</label><select id="bill-timing" value={balanceTiming} onChange={e=>setBalanceTiming(e.target.value as "included" | "after" | "")}><option value="">Selecione</option><option value="included">Sim, já inclui</option><option value="after">Não, paguei depois do saldo</option></select></div>}<button className="btn btn-primary btn-block" disabled={pending || !accountId || !date || needsTiming && !balanceTiming || !!review && (!categoryId || !review.amount)} onClick={()=>review ? createPayment.mutate({id:review.id,data:{date,description:review.description,amount_paid:review.amount,amount_planned:null,category_id:Number(categoryId),account_id:Number(accountId),payment_method:"cash",finalidade:"pessoal",expense_class:"fixed",note:null,occurred_at:occurredAt}},{onSuccess:onClose}) : payDue.mutate({id:due!.commitment_id!,numero:due!.commitment_no!,date,account_id:Number(accountId),occurred_at:occurredAt},{onSuccess:onClose})}>Registrar pagamento real</button></>}
      </>}
      {action === "due" && review && <><div className="field"><label htmlFor="bill-due">Vencimento, se conhecido</label><input id="bill-due" type="date" value={date} onChange={e=>setDate(e.target.value)} /></div>{needsInstallmentDetails ? <p className="e-note">Registre as parcelas com a forma de pagamento correta em Lançamentos e vincule esta pendência em Conferir mês. Nenhuma fatura será criada por suposição.</p> : <>{date && <div className="field"><label htmlFor="bill-due-category">Categoria</label><select id="bill-due-category" value={categoryId} onChange={e=>setCategoryId(e.target.value)}><option value="">Selecione a categoria</option>{(categories.data ?? []).filter(c=>c.type==="expense"&&!c.archived).map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></div>}<button className="btn btn-primary btn-block" disabled={pending || !!date && (!categoryId || !review.amount)} onClick={()=>date ? createDue.mutate({id:review.id,data:{description:review.description,category_id:Number(categoryId),amount:review.amount!,first_due:date,installments:1,confirmed:true,expense_class:"fixed"}},{onSuccess:onClose}) : update.mutate({id:review.id,data:{status:"confirmar",note:"Pagamento confirmado como pendente; vencimento não informado."}},{onSuccess:onClose})}>{date ? "Adicionar a A pagar" : "Manter sem vencimento"}</button></>}</>}
      {action === "skip" && review && <button className="btn btn-primary btn-block" disabled={pending} onClick={()=>update.mutate({id:review.id,data:{status:"ignorado",note:"Não se aplica neste mês."}},{onSuccess:onClose})}>Não se aplica neste mês</button>}
    </>}
    {error && <p role="alert" className="e-notice">{error instanceof Error ? error.message : "Não foi possível salvar."}</p>}
  </div></Modal>;
}
