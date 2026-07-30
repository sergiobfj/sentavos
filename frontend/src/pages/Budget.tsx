import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import TransactionForm from "../components/TransactionForm";
import TransactionList from "../components/TransactionList";
import {
  useBudgetSummary,
  useCategories,
  useSetBudget,
  useTransactions,
} from "../lib/queries";
import { usePeriod } from "../lib/period";
import { ApiError } from "../lib/api";
import { formatMoney, parseMoney } from "../lib/format";
import type { BudgetSummaryItem, Category, CategoryType, Transaction } from "../lib/types";

// Despesa primeiro: é onde o orçamento aperta. Receita fecha a lista porque
// funciona como referência ("cabe no que entra?"), não como teto.
const SECTIONS: { type: CategoryType; title: string; hint: string }[] = [
  { type: "expense", title: "Despesas", hint: "O teto que você se dá em cada categoria" },
  { type: "investment", title: "Investimentos", hint: "Quanto pretende guardar no mês" },
  { type: "income", title: "Receitas", hint: "Quanto espera receber no mês" },
];

type Tab = "metas" | "lancamentos";

export default function Budget() {
  const { label } = usePeriod();
  // A sub-aba vive na URL pra sobreviver ao F5 e poder ser linkada de fora.
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("aba") === "lancamentos" ? "lancamentos" : "metas";
  const { data: categories } = useCategories();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Transaction | null>(null);

  function selectTab(next: Tab) {
    setParams(
      (prev) => {
        const p = new URLSearchParams(prev);
        if (next === "metas") p.delete("aba");
        else p.set("aba", next);
        return p;
      },
      { replace: true }
    );
  }

  if (categories && categories.length === 0) {
    return (
      <>
        <BudgetHead label={label} />
        <div className="panel">
          <div className="empty">
            <div className="big">🎯</div>
            Crie uma <b>categoria</b> pra começar a orçar.
            <div style={{ marginTop: 14 }}>
              <Link className="btn btn-primary" to="/configuracoes">Ir para configurações</Link>
            </div>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <BudgetHead
        label={label}
        action={
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            + Nova transação
          </button>
        }
      />

      <div className="subtabs" role="tablist">
        <button
          role="tab"
          aria-selected={tab === "metas"}
          className={tab === "metas" ? "active" : ""}
          onClick={() => selectTab("metas")}
        >
          Metas
        </button>
        <button
          role="tab"
          aria-selected={tab === "lancamentos"}
          className={tab === "lancamentos" ? "active" : ""}
          onClick={() => selectTab("lancamentos")}
        >
          Lançamentos
        </button>
      </div>

      {tab === "metas" ? <Metas /> : <Lancamentos categories={categories} onEdit={setEditing} />}

      {creating && categories && (
        <TransactionForm categories={categories} onClose={() => setCreating(false)} />
      )}
      {editing && categories && (
        <TransactionForm
          categories={categories}
          transaction={editing}
          onClose={() => setEditing(null)}
        />
      )}
    </>
  );
}

function BudgetHead({ label, action }: { label: string; action?: React.ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <div className="eyebrow">Planejamento</div>
        <h1>Orçamento</h1>
        <p>Quanto você planejou e quanto já foi, em {label}.</p>
      </div>
      {action}
    </div>
  );
}

// ---------- Metas ----------

function Metas() {
  const { data, isLoading, error } = useBudgetSummary();

  const bySection = useMemo(() => {
    const groups = new Map<CategoryType, BudgetSummaryItem[]>();
    for (const item of data?.items ?? []) {
      const list = groups.get(item.category_type) ?? [];
      list.push(item);
      groups.set(item.category_type, list);
    }
    return groups;
  }, [data]);

  if (isLoading) {
    return (
      <div className="panel">
        <div className="loading"><div className="spinner" />Carregando orçamento…</div>
      </div>
    );
  }
  if (error) {
    return <div className="panel"><div className="error-box">{(error as ApiError).message}</div></div>;
  }

  const totals = data?.totals;
  // A sobra é o que o mês devolve se tudo for exatamente ao orçado.
  const leftover = totals
    ? totals.income.budgeted - totals.expense.budgeted - totals.investment.budgeted
    : 0;

  return (
    <>
      <div className="stat-grid">
        <Stat label="Receita orçada" value={totals?.income.budgeted ?? 0} tone="pos" />
        <Stat label="Despesa orçada" value={totals?.expense.budgeted ?? 0} tone="neg" />
        <Stat
          label="Já gasto"
          value={totals?.expense.paid ?? 0}
          tone="gold"
          sub={usageLabel(totals?.expense.paid ?? 0, totals?.expense.budgeted ?? 0)}
        />
        <Stat
          label="Sobra planejada"
          value={leftover}
          tone={leftover >= 0 ? "pos" : "neg"}
          sub="Receita − despesa − investimento orçados"
        />
      </div>

      {SECTIONS.map(({ type, title, hint }) => {
        const items = bySection.get(type) ?? [];
        if (items.length === 0) return null;
        return <Section key={type} title={title} hint={hint} type={type} items={items} />;
      })}
    </>
  );
}

function Section({
  title,
  hint,
  type,
  items,
}: {
  title: string;
  hint: string;
  type: CategoryType;
  items: BudgetSummaryItem[];
}) {
  const budgeted = items.reduce((acc, i) => acc + i.budgeted, 0);
  const paid = items.reduce((acc, i) => acc + i.paid, 0);

  return (
    <div className="panel" style={{ marginTop: 16 }}>
      <div className="panel-head">
        <div>
          <h2>{title}</h2>
          <div className="hint" style={{ marginTop: 3 }}>{hint}</div>
        </div>
        <div className="num" style={{ fontSize: 13.5, color: "var(--text-dim)" }}>
          {formatMoney(paid)} de {formatMoney(budgeted)}
        </div>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Categoria</th>
              <th style={{ width: 150 }}>Orçado</th>
              <th className="num">Previsto</th>
              <th className="num">{type === "income" ? "Recebido" : "Pago"}</th>
              <th style={{ width: 190 }}>Uso</th>
              <th className="num">{type === "income" ? "A receber" : "Resta"}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <BudgetRow key={item.category_id} item={item} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function BudgetRow({ item }: { item: BudgetSummaryItem }) {
  const remaining = item.budgeted - item.paid;
  const over = item.budgeted > 0 && remaining < 0;
  // Estourar receita é bom, estourar despesa não — a cor segue o tipo.
  const overIsGood = item.category_type === "income";

  return (
    <tr>
      <td>
        <span className="chip">
          <span className="dot" style={{ background: item.color }} />
          {item.icon} {item.category_name}
        </span>
      </td>
      <td>
        <MetaInput item={item} />
      </td>
      <td className="num" style={{ color: "var(--text-dim)" }}>
        {item.planned ? formatMoney(item.planned) : "—"}
      </td>
      <td className="num" style={{ fontWeight: 650 }}>
        {item.paid ? formatMoney(item.paid) : "—"}
      </td>
      <td>
        <Usage item={item} />
      </td>
      <td
        className="num"
        style={{
          fontWeight: 650,
          color: !item.budgeted
            ? "var(--text-faint)"
            : over
              ? overIsGood ? "var(--income)" : "var(--expense)"
              : "var(--text-dim)",
        }}
      >
        {item.budgeted ? formatMoney(remaining) : "—"}
      </td>
    </tr>
  );
}

function Usage({ item }: { item: BudgetSummaryItem }) {
  if (!item.budgeted) {
    return <span style={{ fontSize: 12.5, color: "var(--text-faint)" }}>sem meta</span>;
  }

  const ratio = item.paid / item.budgeted;
  const pct = Math.round(ratio * 100);
  const over = ratio > 1;
  const color = over
    ? item.category_type === "income" ? "var(--income)" : "var(--expense)"
    : ratio >= 0.8
      ? "var(--gold)"
      : item.color;

  return (
    <div className="usage">
      <div className="bar-track slim">
        {/* Passou de 100% a barra fica cheia; o número ao lado conta o resto. */}
        <div className="bar-fill" style={{ width: `${Math.min(100, pct)}%`, background: color }} />
      </div>
      <span className="pct" style={over ? { color } : undefined}>{pct}%</span>
    </div>
  );
}

function MetaInput({ item }: { item: BudgetSummaryItem }) {
  const { period } = usePeriod();
  const setBudget = useSetBudget();
  const saved = item.budget_id ? String(item.budgeted).replace(".", ",") : "";
  const [value, setValue] = useState(saved);

  // Trocar de mês remonta a linha com outro valor salvo; sem isso o input
  // continuaria mostrando o que foi digitado no mês anterior.
  useEffect(() => setValue(saved), [saved]);

  function commit() {
    const amount = parseMoney(value);
    // Campo apagado sem meta salva: nada a fazer.
    if (amount === null && !item.budget_id) {
      setValue("");
      return;
    }
    if (amount === item.budgeted) return;

    setBudget.mutate({
      category_id: item.category_id,
      year: period.year,
      month: period.month,
      amount: amount ?? 0,
    });
  }

  return (
    <input
      className="meta-input"
      inputMode="decimal"
      placeholder="0,00"
      aria-label={`Orçado para ${item.category_name}`}
      value={value}
      disabled={setBudget.isPending}
      onChange={(e) => setValue(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
        if (e.key === "Escape") setValue(saved);
      }}
    />
  );
}

// ---------- Lançamentos ----------

function Lancamentos({
  categories,
  onEdit,
}: {
  categories?: Category[];
  onEdit: (t: Transaction) => void;
}) {
  const { label } = usePeriod();
  const { data: transactions, isLoading, error } = useTransactions();

  return (
    <div className="panel">
      {isLoading && <div className="loading"><div className="spinner" />Carregando…</div>}
      {error && <div className="error-box">{(error as ApiError).message}</div>}

      {transactions && transactions.length > 0 && (
        <TransactionList
          transactions={transactions}
          categories={categories ?? []}
          onEdit={onEdit}
        />
      )}

      {!isLoading && !error && transactions?.length === 0 && (
        <div className="empty">
          <div className="big">🧾</div>
          Nenhuma transação em {label}.
        </div>
      )}
    </div>
  );
}

// ---------- Auxiliares ----------

function Stat({
  label,
  value,
  tone,
  sub,
}: {
  label: string;
  value: number;
  tone: "pos" | "neg" | "gold";
  sub?: string;
}) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className={`value ${tone}`}>{formatMoney(value)}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

function usageLabel(paid: number, budgeted: number): string {
  if (!budgeted) return "Nenhuma meta definida ainda";
  return `${Math.round((paid / budgeted) * 100)}% do orçado`;
}
