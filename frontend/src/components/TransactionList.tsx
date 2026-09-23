import { useMemo } from "react";
import { formatDiaMes, formatMoney, sinalDoValor } from "../lib/format";
import type { Category, InvoicePayment, Transaction } from "../lib/types";

// Só a lista: quem chama cuida de loading, erro e do formulário. Tocar na
// linha abre a edição — no celular não cabe um botão "Editar" por linha, e a
// linha inteira é um alvo bem maior que ele.
//
// O lápis no fim da linha não é um segundo botão: é a linha dizendo que faz
// alguma coisa. Sem ele não havia nenhum sinal de que dava pra tocar, e o
// resultado foi previsível — em vez de editar o lançamento errado, lançava-se
// um valor negativo por cima pra anular. Um ícone teria evitado isso.
//
// O pagamento de fatura entra nesta mesma lista, e não numa seção à parte: ele
// é o maior desembolso do mês, e uma lista de "o que aconteceu com meu dinheiro"
// sem ele mandaria procurar noutra tela. Ele vem marcado e sem categoria, porque
// gasto ele não é — o gasto foi contado quando cada compra foi lançada.

export default function TransactionList({
  transactions,
  categories,
  payments = [],
  onEdit,
  onAbrirFatura,
}: {
  transactions: Transaction[];
  categories: Category[];
  payments?: InvoicePayment[];
  onEdit: (transaction: Transaction) => void;
  onAbrirFatura?: (invoiceId: number) => void;
}) {
  const catMap = useMemo(() => {
    const m = new Map<number, Category>();
    categories.forEach((c) => m.set(c.id, c));
    return m;
  }, [categories]);

  // Os dois tipos de linha entram na mesma ordenação por data: separá-los faria
  // o pagamento do dia 2 aparecer depois da compra do dia 28.
  const linhas = useMemo(() => {
    const tudo = [
      ...transactions.map((t) => ({ tipo: "lancamento" as const, data: t.date, t })),
      ...payments.map((p) => ({ tipo: "pagamento" as const, data: p.date, p })),
    ];
    return tudo.sort((a, b) => b.data.localeCompare(a.data));
  }, [transactions, payments]);

  return (
    <div className="list">
      {linhas.map((linha) =>
        linha.tipo === "pagamento" ? (
          <LinhaPagamento
            key={`p${linha.p.id}`}
            pagamento={linha.p}
            onAbrir={onAbrirFatura}
          />
        ) : (
          <LinhaLancamento
            key={linha.t.id}
            t={linha.t}
            cat={catMap.get(linha.t.category_id)}
            onEdit={() => onEdit(linha.t)}
          />
        )
      )}
    </div>
  );
}

export function LinhaLancamento({
  t,
  cat,
  onEdit,
}: {
  t: Transaction;
  cat?: Category;
  onEdit: () => void;
}) {
  const valor = t.amount_paid ?? t.amount_planned ?? 0;
  // Sem valor pago é promessa, não movimento: marcar isso evita ler o
  // mês como fechado quando metade ainda não saiu da conta.
  const soPrevisto = t.amount_paid == null;
  const tom = cat?.type === "income" ? "pos" : cat?.type === "expense" ? "neg" : "inv";
  const sinal = sinalDoValor(cat?.type, valor);

  // "Nubank 2/10" em vez de só "Nubank": numa parcela, saber que faltam oito é
  // metade da informação. Em compra de uma vez, o "1/1" some — não diz nada.
  const marca =
    t.card_name &&
    (t.installments && t.installments > 1
      ? `${t.card_name} ${t.installment_no}/${t.installments}`
      : t.card_name);

  return (
    <button className="row" onClick={onEdit}>
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
          {marca && <> · {marca}</>}
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
}

function LinhaPagamento({
  pagamento,
  onAbrir,
}: {
  pagamento: InvoicePayment;
  onAbrir?: (invoiceId: number) => void;
}) {
  return (
    <button
      className="row"
      onClick={() => onAbrir?.(pagamento.invoice_id)}
      disabled={!onAbrir}
    >
      <div className="avatar avatar-fatura" aria-hidden>
        <IconeCartao />
      </div>
      <div className="mid">
        <div className="t">Fatura {pagamento.card_name}</div>
        {/* Sem categoria de propósito, e a palavra explica por quê: não é
            gasto, é o gasto de antes saindo da conta. */}
        <div className="s">
          {formatDiaMes(pagamento.date)} · pagamento de fatura
        </div>
      </div>
      <div className="amt tnum neg">−{formatMoney(pagamento.amount)}</div>
      {onAbrir && <MarcaEditavel />}
    </button>
  );
}

export function IconeCartao() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2.5" y="5" width="19" height="14" rx="2.5" />
      <path d="M2.5 9.5h19" />
      <path d="M6 14.5h3.5" />
    </svg>
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
