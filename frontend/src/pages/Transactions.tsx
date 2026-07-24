import { useMemo, useState } from "react";
import Modal from "../components/Modal";
import {
  useCategories,
  useCreateTransaction,
  useDeleteTransaction,
  useTransactions,
  useUpdateTransaction,
} from "../lib/queries";
import { ApiError } from "../lib/api";
import { formatDate, formatMoney, todayIso } from "../lib/format";
import type { Category, Transaction } from "../lib/types";

export default function Transactions() {
  const { data: transactions, isLoading, error } = useTransactions();
  const { data: categories } = useCategories();
  const [editing, setEditing] = useState<Transaction | null>(null);
  const [creating, setCreating] = useState(false);

  const catMap = useMemo(() => {
    const m = new Map<number, Category>();
    categories?.forEach((c) => m.set(c.id, c));
    return m;
  }, [categories]);

  const sorted = useMemo(
    () => [...(transactions ?? [])].sort((a, b) => b.date.localeCompare(a.date)),
    [transactions]
  );

  const noCategories = categories && categories.length === 0;

  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">Movimentações</div>
          <h1>Transações</h1>
          <p>Tudo que entrou, saiu ou foi guardado.</p>
        </div>
        <button className="btn btn-primary" disabled={noCategories} onClick={() => setCreating(true)}>
          + Nova transação
        </button>
      </div>

      {noCategories && (
        <div className="panel" style={{ marginBottom: 16 }}>
          <div className="empty">Crie uma <b>categoria</b> antes de lançar transações.</div>
        </div>
      )}

      <div className="panel">
        {isLoading && <div className="loading"><div className="spinner" />Carregando…</div>}
        {error && <div className="error-box">{(error as ApiError).message}</div>}

        {sorted.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Data</th>
                  <th>Descrição</th>
                  <th>Categoria</th>
                  <th className="num">Previsto</th>
                  <th className="num">Pago</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((t) => {
                  const cat = catMap.get(t.category_id);
                  return (
                    <tr key={t.id}>
                      <td style={{ color: "var(--text-dim)", whiteSpace: "nowrap" }}>{formatDate(t.date)}</td>
                      <td>
                        <div style={{ fontWeight: 600 }}>{t.description}</div>
                        {t.note && <div style={{ fontSize: 12.5, color: "var(--text-faint)" }}>{t.note}</div>}
                      </td>
                      <td>
                        {cat ? (
                          <span className="chip">
                            <span className="dot" style={{ background: cat.color }} />
                            {cat.icon} {cat.name}
                          </span>
                        ) : (
                          <span style={{ color: "var(--text-faint)" }}>—</span>
                        )}
                      </td>
                      <td className="num" style={{ color: "var(--text-dim)" }}>
                        {t.amount_planned != null ? formatMoney(t.amount_planned) : "—"}
                      </td>
                      <td className="num" style={{ fontWeight: 650 }}>
                        {t.amount_paid != null ? formatMoney(t.amount_paid) : "—"}
                      </td>
                      <td>
                        <div className="row-actions">
                          <button className="btn btn-ghost btn-sm" onClick={() => setEditing(t)}>Editar</button>
                          <DeleteButton id={t.id} label={t.description} />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {!isLoading && !error && sorted.length === 0 && (
          <div className="empty">
            <div className="big">🧾</div>
            Nenhuma transação ainda.
          </div>
        )}
      </div>

      {creating && categories && <TransactionForm categories={categories} onClose={() => setCreating(false)} />}
      {editing && categories && (
        <TransactionForm categories={categories} transaction={editing} onClose={() => setEditing(null)} />
      )}
    </>
  );
}

function DeleteButton({ id, label }: { id: number; label: string }) {
  const del = useDeleteTransaction();
  return (
    <button
      className="btn btn-ghost btn-sm btn-danger"
      disabled={del.isPending}
      onClick={() => {
        if (confirm(`Excluir "${label}"?`)) del.mutate(id);
      }}
    >
      Excluir
    </button>
  );
}

function TransactionForm({
  categories,
  transaction,
  onClose,
}: {
  categories: Category[];
  transaction?: Transaction;
  onClose: () => void;
}) {
  const isEdit = !!transaction;
  const [form, setForm] = useState({
    date: transaction?.date ?? todayIso(),
    description: transaction?.description ?? "",
    category_id: transaction?.category_id ?? categories[0]?.id ?? 0,
    amount_planned: transaction?.amount_planned?.toString() ?? "",
    amount_paid: transaction?.amount_paid?.toString() ?? "",
    note: transaction?.note ?? "",
  });
  const create = useCreateTransaction();
  const update = useUpdateTransaction();
  const pending = create.isPending || update.isPending;
  const err = (create.error || update.error) as ApiError | null;

  function num(v: string): number | null {
    const t = v.trim();
    if (t === "") return null;
    const n = Number(t.replace(",", "."));
    return Number.isFinite(n) ? n : null;
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const payload = {
      date: form.date,
      description: form.description.trim(),
      category_id: Number(form.category_id),
      amount_planned: num(form.amount_planned),
      amount_paid: num(form.amount_paid),
      note: form.note.trim() || null,
    };
    if (isEdit) {
      update.mutate({ id: transaction!.id, data: payload }, { onSuccess: onClose });
    } else {
      create.mutate(payload, { onSuccess: onClose });
    }
  }

  return (
    <Modal
      title={isEdit ? "Editar transação" : "Nova transação"}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          <button type="submit" form="tx-form" className="btn btn-primary" disabled={pending || !form.description.trim()}>
            {pending ? "Salvando…" : "Salvar"}
          </button>
        </>
      }
    >
      <form id="tx-form" className="m-body" onSubmit={submit}>
        <div className="field">
          <label htmlFor="t-desc">Descrição</label>
          <input id="t-desc" value={form.description} autoFocus placeholder="Ex.: Conta de luz"
            onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </div>
        <div className="field row2">
          <div className="field">
            <label htmlFor="t-date">Data</label>
            <input id="t-date" type="date" value={form.date}
              onChange={(e) => setForm({ ...form, date: e.target.value })} />
          </div>
          <div className="field">
            <label htmlFor="t-cat">Categoria</label>
            <select id="t-cat" value={form.category_id}
              onChange={(e) => setForm({ ...form, category_id: Number(e.target.value) })}>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>{c.icon} {c.name}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="field row2">
          <div className="field">
            <label htmlFor="t-planned">Previsto (R$)</label>
            <input id="t-planned" inputMode="decimal" value={form.amount_planned} placeholder="0,00"
              onChange={(e) => setForm({ ...form, amount_planned: e.target.value })} />
          </div>
          <div className="field">
            <label htmlFor="t-paid">Pago (R$)</label>
            <input id="t-paid" inputMode="decimal" value={form.amount_paid} placeholder="0,00"
              onChange={(e) => setForm({ ...form, amount_paid: e.target.value })} />
          </div>
        </div>
        <div className="field">
          <label htmlFor="t-note">Observação</label>
          <textarea id="t-note" value={form.note} placeholder="Opcional"
            onChange={(e) => setForm({ ...form, note: e.target.value })} />
        </div>
        {err && <div className="error-box" style={{ padding: 0, textAlign: "left" }}>{err.message}</div>}
      </form>
    </Modal>
  );
}
