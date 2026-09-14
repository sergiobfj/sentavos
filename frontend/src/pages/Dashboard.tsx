import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useCategories, useTransactions } from "../lib/queries";
import { usePeriod } from "../lib/period";
import { shiftPeriod } from "../lib/period";
import { transactionsApi } from "../lib/api";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../lib/api";
import { formatMoney, formatDiaMes } from "../lib/format";
import { Fluxo, PorCategoria, PrevistoVsPago } from "../components/Graficos";
import { useBudgetSummary } from "../lib/queries";
import type { Category, CategoryType, Transaction } from "../lib/types";

export default function Dashboard() {
  const { period } = usePeriod();
  const { data: transactions, isLoading, error } = useTransactions();
  const { data: categories } = useCategories(true);
  // O previsto x pago vem do resumo do orçamento, que o backend já cruza.
  const { data: resumo } = useBudgetSummary();

  // O mês anterior existe só pra comparação do cartão herói. Sem ele o número
  // grande diria "quanto sobrou" sem dizer se isso é bom — e "R$ 1.200" só
  // significa alguma coisa ao lado do mês passado.
  const anterior = shiftPeriod(period, -1);
  const { data: transacoesAnteriores } = useQuery({
    queryKey: ["transactions", anterior],
    queryFn: () => transactionsApi.list(anterior),
  });

  const catMap = useMemo(() => {
    const m = new Map<number, Category>();
    categories?.forEach((c) => m.set(c.id, c));
    return m;
  }, [categories]);

  const stats = useMemo(() => somar(transactions, catMap), [transactions, catMap]);
  const statsAnt = useMemo(
    () => somar(transacoesAnteriores, catMap),
    [transacoesAnteriores, catMap]
  );

  const recentes = useMemo(
    () =>
      [...(transactions ?? [])]
        .sort((a, b) => b.date.localeCompare(a.date) || b.id - a.id)
        .slice(0, 6),
    [transactions]
  );

  const porCategoria = useMemo(() => {
    const acc = new Map<number, number>();
    for (const t of transactions ?? []) {
      const cat = catMap.get(t.category_id);
      if (cat?.type !== "expense") continue;
      acc.set(cat.id, (acc.get(cat.id) ?? 0) + (t.amount_paid ?? 0));
    }
    const linhas = [...acc.entries()]
      .map(([id, valor]) => ({ cat: catMap.get(id)!, valor }))
      .filter((r) => r.cat && r.valor > 0)
      .map((r) => ({
        id: r.cat.id,
        nome: r.cat.name,
        icone: r.cat.icon,
        cor: r.cat.color,
        valor: r.valor,
      }));
    return { linhas };
  }, [transactions, catMap]);

  const previstoVsPago = useMemo(
    () =>
      (resumo?.items ?? [])
        .filter((i) => i.category_type === "expense")
        .map((i) => ({
          id: i.category_id,
          nome: i.category_name,
          previsto: i.planned,
          pago: i.paid,
        })),
    [resumo]
  );

  if (isLoading) return <Esqueleto />;
  if (error) return <div className="error-box">{(error as ApiError).message}</div>;

  const vazio = (transactions ?? []).length === 0;
  const variacao = calcularVariacao(stats.saldo, statsAnt.saldo);

  return (
    <>
      <section className="hero">
        <div className="rot">Carteira</div>
        <div className={`big tnum ${stats.saldo >= 0 ? "pos" : "neg"}`}>
          {formatMoney(stats.saldo)}
        </div>
        {variacao && (
          <div className={`delta ${variacao.melhorou ? "pos" : "neg"}`}>
            <span aria-hidden>{variacao.melhorou ? "↑" : "↓"}</span>
            {variacao.texto}
          </div>
        )}
      </section>

      <div className="duo">
        <div className="card">
          <div className="rot"><Bolinha cor="var(--pos)" /> Entrou</div>
          <div className="val pos tnum">{formatMoney(stats.income)}</div>
        </div>
        <div className="card">
          <div className="rot"><Bolinha cor="var(--neg)" /> Saiu</div>
          <div className="val neg tnum">{formatMoney(stats.expense)}</div>
        </div>
        <div className="card">
          <div className="rot"><Bolinha cor="var(--inv)" /> Investido</div>
          <div className="val inv tnum">{formatMoney(stats.investment)}</div>
        </div>
      </div>

      {/* A proporção entre os três, logo abaixo deles e sem título próprio: são
          os mesmos números, então merecem a faixa mas não uma seção inteira. */}
      {(stats.income > 0 || stats.expense > 0) && (
        <div style={{ marginTop: "var(--s3)" }}>
          <Fluxo
            entrou={stats.income}
            saiu={stats.expense}
            investido={stats.investment}
          />
        </div>
      )}

      {vazio ? (
        <div className="empty" style={{ marginTop: "var(--s6)" }}>
          <div className="big">🪙</div>
          <div className="tit">Nenhum lançamento neste mês</div>
          <div>Toque no <b>+</b> para registrar o primeiro.</div>
        </div>
      ) : (
        <>
          {/* Previsto x pago primeiro: é a pergunta que mais importa no meio
              do mês ("estou dentro do que planejei?"). O detalhamento de onde
              o dinheiro foi vem depois, porque responde ao passado. */}
          {previstoVsPago.length > 0 && (
            <>
              <div className="sec-title">
                <h2>Previsto × pago</h2>
                <Link to="/orcamento">Caixinhas</Link>
              </div>
              <div className="card card-pad">
                <PrevistoVsPago linhas={previstoVsPago} />
              </div>
            </>
          )}

          {porCategoria.linhas.length > 0 && (
            <>
              <div className="sec-title">
                <h2>Para onde foi</h2>
                <Link to="/orcamento?aba=lancamentos">Ver tudo</Link>
              </div>
              <div className="card card-pad">
                <PorCategoria linhas={porCategoria.linhas} />
              </div>
            </>
          )}

          {/* A lista fecha a tela. Início virou a aba de relatório, e nela o
              lançamento individual é consulta rápida -- quem quer a lista
              inteira vai em Lançamentos, que existe pra isso. */}
          <div className="sec-title">
            <h2>Últimos lançamentos</h2>
            <Link to="/orcamento?aba=lancamentos">Ver todos</Link>
          </div>
          <div className="list">
            {recentes.map((t) => (
              <LinhaLancamento key={t.id} t={t} cat={catMap.get(t.category_id)} />
            ))}
          </div>
        </>
      )}
    </>
  );
}

function LinhaLancamento({ t, cat }: { t: Transaction; cat?: Category }) {
  const valor = t.amount_paid ?? t.amount_planned ?? 0;
  const sinal = cat?.type === "income" ? "+" : cat?.type === "expense" ? "−" : "";
  const tom = cat?.type === "income" ? "pos" : cat?.type === "expense" ? "neg" : "inv";
  // Só previsto, ainda não pago: o valor é uma promessa, e mostrar igual ao
  // realizado faria o mês parecer fechado quando não está.
  const soPrevisto = t.amount_paid === null || t.amount_paid === undefined;

  return (
    <Link className="row" to="/orcamento?aba=lancamentos">
      <div
        className="avatar"
        style={{ background: `color-mix(in srgb, ${cat?.color ?? "#666"} 22%, transparent)` }}
      >
        {cat?.icon ?? "•"}
      </div>
      <div className="mid">
        <div className="t">{t.description}</div>
        <div className="s">
          {formatDiaMes(t.date)}
          {cat && <> · {cat.name}</>}
        </div>
      </div>
      <div className={`amt tnum ${soPrevisto ? "" : tom}`}>
        {sinal}{formatMoney(Math.abs(valor))}
        {soPrevisto && <span className="sub">previsto</span>}
      </div>
    </Link>
  );
}

function Bolinha({ cor }: { cor: string }) {
  return (
    <span
      style={{
        width: 7, height: 7, borderRadius: 99, background: cor, display: "inline-block",
      }}
    />
  );
}

function Esqueleto() {
  return (
    <>
      <div className="skel" style={{ height: 132, borderRadius: "var(--r-lg)" }} />
      <div className="duo">
        {[0, 1, 2].map((i) => (
          <div key={i} className="skel" style={{ height: 72 }} />
        ))}
      </div>
      <div className="sec-title"><h2>Últimos lançamentos</h2></div>
      <div className="skel" style={{ height: 240, borderRadius: "var(--r)" }} />
    </>
  );
}

function somar(transacoes: Transaction[] | undefined, catMap: Map<number, Category>) {
  const totais: Record<CategoryType, number> = { income: 0, expense: 0, investment: 0 };
  for (const t of transacoes ?? []) {
    const cat = catMap.get(t.category_id);
    if (!cat) continue;
    totais[cat.type] += t.amount_paid ?? 0;
  }
  return { ...totais, saldo: totais.income - totais.expense - totais.investment };
}

/** Compara o saldo com o do mês anterior.
 *
 * Em porcentagem só quando ela significa alguma coisa: sair de -50 para +200 dá
 * "-500%", um número tecnicamente correto e completamente inútil. Quando o mês
 * anterior foi negativo ou perto de zero, a comparação vira o valor absoluto.
 */
function calcularVariacao(
  atual: number,
  anterior: number
): { texto: string; melhorou: boolean } | null {
  if (!Number.isFinite(anterior) || anterior === 0) return null;
  const diferenca = atual - anterior;
  if (Math.abs(diferenca) < 0.01) return null;

  const melhorou = diferenca > 0;
  if (anterior > 0) {
    const pct = Math.round((diferenca / anterior) * 100);
    if (Math.abs(pct) <= 999) {
      return { texto: `${Math.abs(pct)}% vs. mês anterior`, melhorou };
    }
  }
  return { texto: `${formatMoney(Math.abs(diferenca))} vs. mês anterior`, melhorou };
}
