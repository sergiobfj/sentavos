import { useMemo } from "react";
import { Link } from "react-router-dom";
import {
  useAssetSummary,
  useBudgetSummary,
  useCategories,
  useTransactions,
} from "../lib/queries";
import { usePeriod } from "../lib/period";
import { ApiError } from "../lib/api";
import { formatDiaMes, formatMoney, formatYm } from "../lib/format";
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

const COR_CLASSE: Record<string, string> = {
  fixed_income: "var(--pos)",
  equity: "var(--inv)",
  crypto: "var(--gold)",
};

export default function Investments() {
  const { label, ym } = usePeriod();
  const assets = useAssetSummary();
  const budget = useBudgetSummary();
  const transactions = useTransactions();
  const categories = useCategories();

  const erro = (assets.error || budget.error) as ApiError | null;

  const itens = useMemo(
    () =>
      (assets.data?.items ?? [])
        .filter((i) => INVESTMENT_CLASSES.includes(i.asset_class))
        .sort((a, b) => b.value - a.value),
    [assets.data]
  );

  const aportes = useMemo(() => {
    const investCats = new Set(
      (categories.data ?? []).filter((c) => c.type === "investment").map((c) => c.id)
    );
    return (transactions.data ?? [])
      .filter((t) => investCats.has(t.category_id))
      .sort((a, b) => b.date.localeCompare(a.date));
  }, [transactions.data, categories.data]);

  if (assets.isLoading || budget.isLoading) return <Esqueleto />;
  if (erro) return <div className="error-box">{erro.message}</div>;

  const total = itens.reduce((acc, i) => acc + i.value, 0);
  const anterior = itens.reduce((acc, i) => acc + i.previous, 0);
  const variacao = total - anterior;
  const aporte = budget.data?.totals.investment.paid ?? 0;

  // Rendimento é o que sobrou da variação depois de descontar o que você
  // colocou. Só faz sentido com um mês anterior pra comparar: no primeiro mês
  // o saldo inteiro apareceria como "rendimento", o que seria falso.
  const temBase = anterior > 0;
  const rendimento = variacao - aporte;

  if (itens.length === 0) {
    return (
      <div className="empty">
        <div className="big">📈</div>
        <div className="tit">Nada investido ainda</div>
        <div>
          Esta aba lê os ativos de renda fixa, renda variável e cripto do
          Patrimônio.
          {aporte > 0 && (
            <>
              {" "}Você já aportou <b>{formatMoney(aporte)}</b> em {label} — cadastre
              onde esse dinheiro está.
            </>
          )}
        </div>
        <div style={{ marginTop: "var(--s4)" }}>
          <Link className="btn btn-primary" to="/patrimonio">Ir para patrimônio</Link>
        </div>
      </div>
    );
  }

  return (
    <>
      <section className="hero">
        <div className="rot">Total investido</div>
        <div className="big tnum">{formatMoney(total)}</div>
        {temBase && Math.abs(variacao) >= 0.01 && (
          <div className={`delta ${variacao > 0 ? "pos" : "neg"}`}>
            <span aria-hidden>{variacao > 0 ? "↑" : "↓"}</span>
            {formatMoney(Math.abs(variacao))} no mês
          </div>
        )}
      </section>

      {/* Dois números, não quatro. O total já está no cartão acima, e a
          "variação" virou o selo dele — repetir os dois como cartão próprio era
          dizer a mesma coisa três vezes. */}
      <div className="duo" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <div className="card">
          <div className="rot">Aportado no mês</div>
          <div className="val inv tnum">{formatMoney(aporte)}</div>
        </div>
        <div className="card">
          <div className="rot">Rendimento</div>
          {temBase ? (
            <div className={`val tnum ${rendimento >= 0 ? "pos" : "neg"}`}>
              {rendimento > 0 ? "+" : ""}{formatMoney(rendimento)}
            </div>
          ) : (
            // Sem mês anterior o número seria o saldo inteiro travestido de
            // lucro. Melhor um traço honesto do que um número bonito e falso.
            <div className="val" style={{ color: "var(--text-faint)" }}>—</div>
          )}
        </div>
      </div>

      <div className="sec-title">
        <h2>Onde está</h2>
        <Link to="/patrimonio">Editar</Link>
      </div>

      {/* Barra empilhada só quando há mais de um tipo de aplicação. Com uma só,
          ela seria uma faixa de 100% de uma cor — enfeite ocupando espaço. */}
      <Composicao itens={itens} total={total} />

      <div className="list">
        {itens.map((item) => (
          <div className="row" key={item.asset_id} style={{ cursor: "default" }}>
            <div
              className="avatar"
              style={{
                background: `color-mix(in srgb, ${COR_CLASSE[item.asset_class] ?? "var(--gold)"} 22%, transparent)`,
              }}
            >
              {item.asset_class === "crypto" ? "₿" : item.asset_class === "equity" ? "📊" : "🏦"}
            </div>
            <div className="mid">
              <div className="t">{item.name}</div>
              <div className="s">
                {ASSET_CLASS_LABEL[item.asset_class]}
                {total > 0 && <> · {Math.round((item.value / total) * 100)}%</>}
                {/* Saldo herdado de mês anterior: sem avisar, o número parece
                    atual e a pessoa confia num dado que não atualizou. */}
                {item.as_of && item.as_of !== ym && <> · de {formatYm(item.as_of)}</>}
              </div>
            </div>
            <div className="amt tnum">{formatMoney(item.value)}</div>
          </div>
        ))}
      </div>

      {aportes.length > 0 && (
        <>
          <div className="sec-title">
            <h2>Aportes de {label}</h2>
            <Link to="/orcamento?aba=lancamentos">Ver todos</Link>
          </div>
          <div className="list">
            {/* Três e não a lista inteira: aqui o aporte é contexto do número
                lá de cima, não o assunto da tela. Quem quer todos vai na aba
                de lançamentos, que é onde eles moram. */}
            {aportes.slice(0, 3).map((t) => (
              <div className="row" key={t.id} style={{ cursor: "default" }}>
                <div
                  className="avatar"
                  style={{ background: "color-mix(in srgb, var(--inv) 20%, transparent)" }}
                >
                  🏦
                </div>
                <div className="mid">
                  <div className="t">{t.description}</div>
                  <div className="s">{formatDiaMes(t.date)}</div>
                </div>
                <div className="amt inv tnum">{formatMoney(t.amount_paid)}</div>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}

function Composicao({ itens, total }: { itens: AssetSummaryItem[]; total: number }) {
  const porClasse = useMemo(() => {
    const acc = new Map<AssetClass, number>();
    for (const item of itens) {
      acc.set(item.asset_class, (acc.get(item.asset_class) ?? 0) + item.value);
    }
    return ASSET_CLASS_ORDER.filter((c) => acc.has(c)).map((c) => ({
      classe: c,
      valor: acc.get(c) ?? 0,
    }));
  }, [itens]);

  if (total <= 0 || porClasse.length < 2) return null;

  return (
    <div style={{ marginBottom: "var(--s3)" }}>
      <div className="seg">
        {porClasse.map(({ classe, valor }) => (
          <div
            key={classe}
            style={{
              width: `${(valor / total) * 100}%`,
              background: COR_CLASSE[classe] ?? "var(--gold)",
            }}
            title={`${ASSET_CLASS_LABEL[classe]}: ${formatMoney(valor)}`}
          />
        ))}
      </div>
      <div className="seg-legend">
        {porClasse.map(({ classe, valor }) => (
          <span key={classe}>
            <i style={{ background: COR_CLASSE[classe] ?? "var(--gold)" }} />
            {ASSET_CLASS_LABEL[classe]} {Math.round((valor / total) * 100)}%
          </span>
        ))}
      </div>
    </div>
  );
}

function Esqueleto() {
  return (
    <>
      <div className="skel" style={{ height: 132, borderRadius: "var(--r-lg)" }} />
      <div className="duo" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <div className="skel" style={{ height: 72 }} />
        <div className="skel" style={{ height: 72 }} />
      </div>
      <div className="sec-title"><h2>Onde está</h2></div>
      <div className="skel" style={{ height: 160, borderRadius: "var(--r)" }} />
    </>
  );
}
