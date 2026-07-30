import { useState } from "react";
import Modal from "./Modal";
import { useCreateTransaction, useUpdateTransaction } from "../lib/queries";
import { usePeriod } from "../lib/period";
import { ApiError } from "../lib/api";
import { parseMoney, todayIso } from "../lib/format";
import type { Category, Transaction } from "../lib/types";

export default function TransactionForm({
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
  const { setPeriod } = usePeriod();
  const create = useCreateTransaction();
  const update = useUpdateTransaction();
  const pending = create.isPending || update.isPending;
  const err = (create.error || update.error) as ApiError | null;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const payload = {
      date: form.date,
      description: form.description.trim(),
      category_id: Number(form.category_id),
      amount_planned: parseMoney(form.amount_planned),
      amount_paid: parseMoney(form.amount_paid),
      note: form.note.trim() || null,
    };
    // Salvar um lançamento de outro mês some da lista e parece que falhou;
    // então o app acompanha a data que foi salva.
    function onSaved() {
      const [y, m] = payload.date.split("-").map(Number);
      if (y && m) setPeriod({ year: y, month: m });
      onClose();
    }

    if (isEdit) {
      update.mutate({ id: transaction!.id, data: payload }, { onSuccess: onSaved });
    } else {
      create.mutate(payload, { onSuccess: onSaved });
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
