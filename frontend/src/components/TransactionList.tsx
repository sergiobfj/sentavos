import { useMemo } from "react";
import { formatDiaMes, formatMoney } from "../lib/format";
import type { Category, Transaction } from "../lib/types";

// Só a lista: quem chama cuida de loading, erro e do formulário. Tocar na
// linha abre a edição — no celular não cabe um botão "Editar" por linha, e a
// linha inteira é um alvo bem maior que ele.

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
    <div className="list">
      {sorted.map((t) => {
        const cat = catMap.get(t.category_id);
        const valor = t.amount_paid ?? t.amount_planned ?? 0;
        // Sem valor pago é promessa, não movimento: marcar isso evita ler o
        // mês como fechado quando metade ainda não saiu da conta.
        const soPrevisto = t.amount_paid == null;
        const tom =
          cat?.type === "income" ? "pos" : cat?.type === "expense" ? "neg" : "inv";
        const sinal = cat?.type === "income" ? "+" : cat?.type === "expense" ? "−" : "";

        return (
          <button className="row" key={t.id} onClick={() => onEdit(t)}>
            <div
              className="avatar"
              style={{
                background: `color-mix(in srgb, ${cat?.color ?? "#666"} 22%, transparent)`,
              }}
            >
              {cat?.icon ?? "•"}
            </div>
            <div className="mid">
              <div className="t">{t.description}</div>
              <div className="s">
                {formatDiaMes(t.date)}
                {cat && <> · {cat.name}</>}
                {t.note && <> · {t.note}</>}
              </div>
            </div>
            <div className={`amt tnum ${soPrevisto ? "" : tom}`}>
              {sinal}{formatMoney(Math.abs(valor))}
              {soPrevisto && <span className="sub">previsto</span>}
            </div>
          </button>
        );
      })}
    </div>
  );
}
