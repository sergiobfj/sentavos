import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useAssetSummary, useBudgetSummary, useCategories, useTransactions } from "../lib/queries";
import { usePeriod } from "../lib/period";
import { ApiError } from "../lib/api";
import { formatDate, formatMoney, formatYm } from "../lib/format";
import {
  ASSET_CLASS_LABEL,
  ASSET_CLASS_ORDER,
  INVESTMENT_CLASSES,
  type AssetClass,
  type AssetSummaryItem,
} from "../lib/types";

// Esta aba não tem dados próprios de propósito: o saldo vem de Patrimônio
// (classes de investimento) e o aporte vem dos lançamentos de categoria
// "investimento". Se ela tivesse números próprios, começaria a divergir das
// outras duas telas sobre o mesmo dinheiro.

const CLASS_COLOR: Record<string, string> = {
  fixed_income: "var(--income)",
  equity: "var(--investment)",
  crypto: "var(--gold)",
};

export default function Investments() {
  const { label, ym } = usePeriod();
  const assets = useAssetSummary();
  const budget = useBudgetSummary();
  const transactions = useTransactions();
  const categories = useCategories();

  const isLoading = assets.isLoading || budget.isLoading;
  const error = (assets.error || budget.error) as ApiError | null;

  const items = useMemo(
    () =>
      (assets.data?.items ?? [])
        .filter((i) => INVESTMENT_CLASSES.includes(i.asset_class))
        .sort((a, b) => b.value - a.value),
    [assets.data]
  );

  // Os aportes do mês: lançamentos em categoria de tipo investimento. É a mesma
  // fonte que alimenta o "Investido" do painel e do orçamento.
  const aportes = useMemo(() => {
    const investCats = new Set(
      (categories.data ?? []).filter((c) => c.type === "investment").map((c) => c.id)
    );
    return (transactions.data ?? [])
      .filter((t) => investCats.has(t.category_id))
      .sort((a, b) => b.date.localeCompare(a.date));
  }, [transactions.data, categories.data]);

  const head = (
    <div className="page-head">
      <div>
        <div className="eyebrow">Carteira</div>
        <h1>Investimento</h1>
        <p>Quanto você já guardou e quanto isso virou, em {label}.</p>
      </div>
    </div>
  );

  if (isLoading) {
    return (
      <>
        {head}
        <div className="panel">
          <div className="loading"><div className="spinner" />Carregando carteira…</div>
        </div>
      </>
    );
  }
  if (error) {
    return (
      <>
        {head}
        <div className="panel"><div className="error-box">{error.message}</div></div>
      </>
    );
  }

  const total = items.reduce((acc, i) => acc + i.value, 0);
  const previous = items.reduce((acc, i) => acc + i.previous, 0);
  const change = total - previous;
  const aporte = budget.data?.totals.investment.paid ?? 0;

  // Rendimento é o que sobrou da variação depois de descontar o que você
  // colocou. Só faz sentido com um mês anterior pra comparar: no primeiro mês
  // o saldo inteiro apareceria como "rendimento", o que seria falso.
  const hasBaseline = previous > 0;
  const rendimento = change - aporte;

  if (items.length === 0) {
    return (
      <>
        {head}
        <div className="panel">
          <div className="empty">
            <div className="big">📈</div>
            Nenhum investimento cadastrado ainda. Esta aba lê os ativos de
            <b> renda fixa</b>, <b>renda variável</b> e <b>cripto</b> do Patrimônio.
            {aporte > 0 && (
              <div style={{ marginTop: 10, color: "var(--text-dim)" }}>
                Você já aportou {formatMoney(aporte)} em {label} — cadastre onde esse
                dinheiro está pra acompanhar o rendimento.
              </div>
            )}
            <div style={{ marginTop: 14 }}>
              <Link className="btn btn-primary" to="/patrimonio">Ir para patrimônio</Link>
            </div>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      {head}

      <div className="stat-grid">
        <Stat label="Total investido" value={total} tone="gold" />
        <Stat
          label="Aporte no mês"
          value={aporte}
          tone="pos"
          sub="Lançamentos de categoria investimento"
        />
        <Stat
          label="Variação no mês"
          value={change}
          tone={change >= 0 ? "pos" : "neg"}
          signed
          sub={hasBaseline ? `Contra ${formatMoney(previous)} no mês anterior` : "Sem mês anterior"}
        />
        {hasBaseline ? (
          <Stat
            label="Rendimento estimado"
            value={rendimento}
            tone={rendimento >= 0 ? "pos" : "neg"}
            signed
            sub="Variação − aporte"
          />
        ) : (
          <div className="stat">
            <div className="label">Rendimento estimado</div>
            <div className="value" style={{ color: "var(--text-faint)" }}>—</div>
            <div className="sub">Precisa de um mês anterior com saldo pra comparar</div>
          </div>
        )}
      </div>

      <div className="two-col">
        <div className="panel">
          <div className="panel-head">
            <h2>Onde está o dinheiro</h2>
            <div className="num" style={{ fontSize: 13.5, color: "var(--text-dim)" }}>
              {formatMoney(total)}
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Ativo</th>
                  <th className="num">Saldo</th>
                  <th className="num">Fatia</th>
                  <th className="num">Variação</th>
                  <th>Referência</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.asset_id}>
                    <td>
                      <div style={{ fontWeight: 600 }}>{item.name}</div>
                      <div style={{ fontSize: 12.5, color: "var(--text-faint)" }}>
                        {ASSET_CLASS_LABEL[item.asset_class]}
                      </div>
                    </td>
                    <td className="num" style={{ fontWeight: 650 }}>{formatMoney(item.value)}</td>
                    <td className="num" style={{ color: "var(--text-dim)" }}>
                      {total > 0 ? `${Math.round((item.value / total) * 100)}%` : "—"}
                    </td>
                    <td
                      className="num"
                      style={{
                        fontWeight: 650,
                        color:
                          item.change === 0
                            ? "var(--text-faint)"
                            : item.change > 0
                              ? "var(--income)"
                              : "var(--expense)",
                      }}
                    >
                      {item.change === 0 ? "—" : formatSigned(item.change)}
                    </td>
                    <td>
                      {item.as_of == null ? (
                        <span style={{ fontSize: 12.5, color: "var(--text-faint)" }}>sem saldo</span>
                      ) : item.as_of === ym ? (
                        <span className="badge income">deste mês</span>
                      ) : (
                        <span
                          className="badge"
                          style={{ color: "var(--text-dim)", background: "var(--surface-3)" }}
                        >
                          de {formatYm(item.as_of)}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head"><h2>Composição</h2></div>
          <div className="panel-body">
            <Allocation items={items} total={total} />
          </div>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 16 }}>
        <div className="panel-head">
          <div>
            <h2>Aportes de {label}</h2>
            <div className="hint" style={{ marginTop: 3 }}>
              De onde vem o número do aporte
            </div>
          </div>
          <Link className="btn btn-ghost btn-sm" to="/orcamento?aba=lancamentos">
            Ver lançamentos
          </Link>
        </div>
        {aportes.length === 0 ? (
          <div className="empty">
            Nenhum aporte lançado em {label}. Aporte é transação em categoria de
            tipo <b>investimento</b>.
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <tbody>
                {aportes.map((t) => (
                  <tr key={t.id}>
                    <td style={{ whiteSpace: "nowrap", color: "var(--text-dim)", width: 140 }}>
                      {formatDate(t.date)}
                    </td>
                    <td style={{ fontWeight: 600 }}>{t.description}</td>
                    <td className="num" style={{ fontWeight: 650, color: "var(--gold)" }}>
                      {formatMoney(t.amount_paid)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

function Allocation({ items, total }: { items: AssetSummaryItem[]; total: number }) {
  const byClass = useMemo(() => {
    const acc = new Map<AssetClass, number>();
    for (const item of items) {
      acc.set(item.asset_class, (acc.get(item.asset_class) ?? 0) + item.value);
    }
    return ASSET_CLASS_ORDER.filter((c) => acc.has(c)).map((c) => ({
      classe: c,
      value: acc.get(c) ?? 0,
    }));
  }, [items]);

  if (total <= 0) {
    return <div className="empty">Sem saldo lançado pra calcular a composição.</div>;
  }

  return (
    <>
      {byClass.map(({ classe, value }) => (
        <div className="breakdown-item" key={classe}>
          <div className="btop">
            <span>{ASSET_CLASS_LABEL[classe]}</span>
            <span className="v">
              {Math.round((value / total) * 100)}% · {formatMoney(value)}
            </span>
          </div>
          <div className="bar-track">
            <div
              className="bar-fill"
              style={{
                width: `${(value / total) * 100}%`,
                background: CLASS_COLOR[classe] ?? "var(--gold)",
              }}
            />
          </div>
        </div>
      ))}
    </>
  );
}

function Stat({
  label,
  value,
  tone,
  sub,
  signed,
}: {
  label: string;
  value: number;
  tone: "pos" | "neg" | "gold";
  sub?: string;
  signed?: boolean;
}) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className={`value ${tone}`}>{signed ? formatSigned(value) : formatMoney(value)}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

function formatSigned(value: number): string {
  return `${value > 0 ? "+" : ""}${formatMoney(value)}`;
}
