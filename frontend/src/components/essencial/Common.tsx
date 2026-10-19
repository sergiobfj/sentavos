import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../lib/auth";
import { formatDiaMes, formatMoney } from "../../lib/format";
import type { Category, ExpenseClass, Transaction } from "../../lib/types";
import TransactionForm from "../TransactionForm";
import Modal from "../Modal";

export function SectionTitle({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="e-section-title"><h2>{title}</h2>{children}</div>;
}
export function Summary({ items }: { items: { label: string; value: number | null | undefined; to?: string; onClick?: () => void; text?: string }[] }) {
  return <dl className="e-summary">{items.map(i => <div key={i.label}><dt>{i.label}</dt><dd>{i.to ? <Link to={i.to}>{i.value == null ? i.text ?? "—" : formatMoney(i.value)} ›</Link> : i.onClick ? <button onClick={i.onClick}>{i.value == null ? i.text ?? "—" : formatMoney(i.value)} ›</button> : i.value == null ? i.text ?? "—" : formatMoney(i.value)}</dd></div>)}</dl>;
}
export function LoadError({ error, retry }: { error: unknown; retry?: () => void }) {
  if (!error) return null;
  return <p className="e-notice" role="alert">{error instanceof Error ? error.message : "Não foi possível carregar esta informação."} {retry && <button className="link" onClick={retry}>Tentar novamente</button>}</p>;
}
export function ExpenseClassField({ value, onChange, suggested = false }: { value: ExpenseClass | null; onChange: (v: ExpenseClass | null) => void; suggested?: boolean }) {
  return <div className="field"><label htmlFor="expense-class">Organização da despesa</label><select id="expense-class" value={value ?? ""} onChange={e => onChange(e.target.value ? e.target.value as ExpenseClass : null)}><option value="">{suggested ? "Usar classificação do compromisso" : "A confirmar"}</option><option value="fixed">Fixa</option><option value="variable">Variável</option></select><p className="hint">Independente da categoria e da natureza do gasto.</p></div>;
}
export interface FinancialLine { key: string; description: string; date: string; value: number | null; detail?: string; status: string; income?: boolean; onClick?: () => void }
export function FinancialRow({ line }: { line: FinancialLine }) {
  const content = <><span className="e-row-text"><strong>{line.description}</strong><small>{line.detail ? `${line.detail} · ` : ""}{formatDiaMes(line.date)}</small></span><span className="e-row-value"><strong className={line.income ? "pos" : ""}>{line.value == null ? "—" : `${line.income ? "+" : "−"}${formatMoney(Math.abs(line.value))}`}</strong><small>{line.status}</small></span></>;
  return line.onClick ? <button className="e-row" data-entry-key={line.key} onClick={line.onClick}>{content}</button> : <div className="e-row" data-entry-key={line.key}>{content}</div>;
}
export function transactionLine(t: Transaction, cat?: Category, onClick?: () => void): FinancialLine {
  const investment = cat?.type === "investment";
  const value = t.amount_paid ?? t.amount_planned;
  const status = t.amount_paid == null ? cat?.type === "income" ? "A receber" : investment ? "Previsto" : "A pagar" : cat?.type === "income" ? "Recebido" : investment ? (value ?? 0) < 0 ? "Resgate" : "Aporte" : t.card_name ? "No cartão" : "Pago";
  return { key: `t-${t.id}`, description: t.description, date: t.date, value, income: cat?.type === "income" || investment && (value ?? 0) < 0, detail: [cat?.name, t.card_name ? `${t.card_name}${(t.installments ?? 1) > 1 ? ` · ${t.installment_no}/${t.installments}` : ""}` : t.account_name].filter(Boolean).join(" · "), status, onClick };
}
export function EntryEditor({ transaction, categories, onClose }: { transaction: Transaction; categories: Category[]; onClose: () => void }) {
  const { sessao } = useAuth();
  if (!sessao?.somenteLeitura) return <TransactionForm transaction={transaction} categories={categories} onClose={onClose}/>;
  return <Modal title={transaction.description} onClose={onClose}><div className="m-body"><FinancialRow line={transactionLine(transaction,categories.find(c=>c.id===transaction.category_id))}/><p className="hint">Consulta da demonstração. Os dados não podem ser alterados.</p></div></Modal>;
}
export function MonthGroup({ title, summary, lines, note }: { title: string; summary: string; lines: FinancialLine[]; note?: string }) {
  const [expanded, setExpanded] = useState(false);
  return <section className="e-group"><header><h3>{title}</h3><p>{summary}</p></header>{(expanded ? lines : lines.slice(0,3)).map(l=><FinancialRow key={l.key} line={l}/>)}{!lines.length && <p className="e-empty">Nenhum lançamento conhecido neste mês.</p>}{note && <p className="e-note">{note}</p>}{lines.length>3 && <button className="e-expand" aria-expanded={expanded} onClick={()=>setExpanded(!expanded)}>{expanded ? "Recolher" : `Ver todos (${lines.length})`} ›</button>}</section>;
}
