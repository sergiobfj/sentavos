import { useMemo } from "react";
import { useDeleteTransaction } from "../lib/queries";
import { formatDate, formatMoney } from "../lib/format";
import type { Category, Transaction } from "../lib/types";

// Só a tabela: quem chama cuida de loading, erro e do formulário. Assim a
// lista serve tanto a aba de Lançamentos quanto qualquer resumo futuro.

export default function TransactionList({
  transactions,
  categories,
  onEdit,
}: {
  transactions: Transaction[];
  categories: Category[];
  onEdit: (transaction: Transaction) => void;
}) {
  const catMap = useMemo(() => {
    const m = new Map<number, Category>();
    categories.forEach((c) => m.set(c.id, c));
    return m;
  }, [categories]);

  const sorted = useMemo(
    () => [...transactions].sort((a, b) => b.date.localeCompare(a.date)),
    [transactions]
  );

  return (
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
                    <button className="btn btn-ghost btn-sm" onClick={() => onEdit(t)}>Editar</button>
                    <DeleteButton id={t.id} label={t.description} />
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
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
