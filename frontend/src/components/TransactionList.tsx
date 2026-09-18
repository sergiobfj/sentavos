import { useMemo } from "react";
import { formatDiaMes, formatMoney, sinalDoValor } from "../lib/format";
import type { Category, Transaction } from "../lib/types";

// Só a lista: quem chama cuida de loading, erro e do formulário. Tocar na
// linha abre a edição — no celular não cabe um botão "Editar" por linha, e a
// linha inteira é um alvo bem maior que ele.
//
// O lápis no fim da linha não é um segundo botão: é a linha dizendo que faz
// alguma coisa. Sem ele não havia nenhum sinal de que dava pra tocar, e o
// resultado foi previsível — em vez de editar o lançamento errado, lançava-se
// um valor negativo por cima pra anular. Um ícone teria evitado isso.

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
        const sinal = sinalDoValor(cat?.type, valor);

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
            <MarcaEditavel />
          </button>
        );
      })}
    </div>
  );
}

/** Só o desenho. O invólucro é de quem chama, porque ele muda de natureza:
 *  numa linha que é toda clicável, o lápis é um `span` aria-hidden — só o
 *  aviso de que a linha faz algo, e botão dentro de botão seria HTML inválido.
 *  Numa linha que tem campo editável dentro (o saldo, em Patrimônio), a linha
 *  não pode ser botão, e aí o lápis é o botão de verdade. */
export function IconeLapis() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 20h4.2L19 9.2a2.1 2.1 0 0 0 0-3l-1.2-1.2a2.1 2.1 0 0 0-3 0L4 15.8V20z" />
      <path d="M13.8 6.2 17.8 10.2" />
    </svg>
  );
}

/** O lápis decorativo das linhas clicáveis. */
export function MarcaEditavel() {
  return (
    <span className="row-editar" aria-hidden>
      <IconeLapis />
    </span>
  );
}
