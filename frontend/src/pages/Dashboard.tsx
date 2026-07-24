import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useCategories, useTransactions } from "../lib/queries";
import { ApiError } from "../lib/api";
import { formatDate, formatMoney } from "../lib/format";
import type { Category, CategoryType } from "../lib/types";

export default function Dashboard() {
  const { data: transactions, isLoading, error } = useTransactions();
  const { data: categories } = useCategories();

  const catMap = useMemo(() => {
    const m = new Map<number, Category>();
    categories?.forEach((c) => m.set(c.id, c));
    return m;
  }, [categories]);

  const stats = useMemo(() => {
    const totals: Record<CategoryType, number> = { income: 0, expense: 0, investment: 0 };
    for (const t of transactions ?? []) {
      const cat = catMap.get(t.category_id);
      if (!cat) continue;
      totals[cat.type] += t.amount_paid ?? 0;
    }
    return { ...totals, balance: totals.income - totals.expense - totals.investment };
  }, [transactions, catMap]);

  const recent = useMemo(
    () => [...(transactions ?? [])].sort((a, b) => b.date.localeCompare(a.date)).slice(0, 6),
    [transactions]
  );

  const byExpense = useMemo(() => {
    const acc = new Map<number, number>();
    for (const t of transactions ?? []) {
      const cat = catMap.get(t.category_id);
      if (cat?.type !== "expense") continue;
      acc.set(cat.id, (acc.get(cat.id) ?? 0) + (t.amount_paid ?? 0));
    }
    const rows = [...acc.entries()]
      .map(([id, value]) => ({ cat: catMap.get(id)!, value }))
      .filter((r) => r.cat && r.value > 0)
      .sort((a, b) => b.value - a.value);
    const max = rows[0]?.value ?? 1;
    return { rows: rows.slice(0, 6), max };
  }, [transactions, catMap]);

  if (isLoading) {
    return <div className="panel"><div className="loading"><div className="spinner" />Carregando painel…</div></div>;
  }
  if (error) {
    return <div className="panel"><div className="error-box">{(error as ApiError).message}</div></div>;
  }

  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">Visão geral</div>
          <h1>Painel</h1>
          <p>Onde cada centavo está, num relance.</p>
        </div>
        <Link className="btn btn-primary" to="/transacoes">+ Nova transação</Link>
      </div>

      <div className="stat-grid">
        <Stat label="Receitas" value={stats.income} tone="pos" />
        <Stat label="Despesas" value={stats.expense} tone="neg" />
        <Stat label="Investido" value={stats.investment} tone="gold" />
        <Stat label="Saldo" value={stats.balance} tone={stats.balance >= 0 ? "pos" : "neg"} sub="Receitas − despesas − investido" />
      </div>

      <div className="two-col">
        <div className="panel">
          <div className="panel-head">
            <h2>Últimas transações</h2>
            <Link className="btn btn-ghost btn-sm" to="/transacoes">Ver todas</Link>
          </div>
          <div className="panel-body">
            {recent.length === 0 ? (
              <div className="empty">Sem transações ainda.</div>
            ) : (
              <div className="table-wrap">
                <table>
                  <tbody>
                    {recent.map((t) => {
                      const cat = catMap.get(t.category_id);
                      return (
                        <tr key={t.id}>
                          <td style={{ whiteSpace: "nowrap", color: "var(--text-dim)" }}>{formatDate(t.date)}</td>
                          <td style={{ fontWeight: 600 }}>{t.description}</td>
                          <td>
                            {cat && (
                              <span className="chip">
                                <span className="dot" style={{ background: cat.color }} />
                                {cat.icon}
                              </span>
                            )}
                          </td>
                          <td className="num" style={{ fontWeight: 650, color: toneColor(cat?.type) }}>
                            {formatMoney(t.amount_paid)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        <div className="panel">
          <div className="panel-head"><h2>Gastos por categoria</h2></div>
          <div className="panel-body">
            {byExpense.rows.length === 0 ? (
              <div className="empty">Sem gastos registrados.</div>
            ) : (
              byExpense.rows.map(({ cat, value }) => (
                <div className="breakdown-item" key={cat.id}>
                  <div className="btop">
                    <span>{cat.icon} {cat.name}</span>
                    <span className="v">{formatMoney(value)}</span>
                  </div>
                  <div className="bar-track">
                    <div className="bar-fill" style={{ width: `${(value / byExpense.max) * 100}%`, background: cat.color }} />
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </>
  );
}

function Stat({ label, value, tone, sub }: { label: string; value: number; tone: "pos" | "neg" | "gold"; sub?: string }) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className={`value ${tone}`}>{formatMoney(value)}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

function toneColor(type?: CategoryType): string {
  if (type === "income") return "var(--income)";
  if (type === "expense") return "var(--expense)";
  if (type === "investment") return "var(--gold)";
  return "var(--text)";
}
