import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import TransactionForm from "../components/TransactionForm";
import { MarcaEditavel } from "../components/TransactionList";
import { Rosca } from "../components/Graficos";
import {
  useAssetSummary,
  usePerfil,
  useBudgetSummary,
  useCategories,
  useTransactions,
} from "../lib/queries";
import { usePeriod } from "../lib/period";
import { ApiError } from "../lib/api";
import { formatDiaMes, formatMoney, formatYm } from "../lib/format";
import { PALETA_CATEGORIAS, fundoDaCor } from "../lib/paleta";
import {
  ASSET_CLASS_LABEL,
  INVESTMENT_CLASSES,
  type AssetSummaryItem,
  type Transaction,
} from "../lib/types";

// Esta aba não tem dados próprios de propósito: o saldo vem de Patrimônio
// (classes de investimento) e o aporte vem dos lançamentos de categoria
// "investimento". Se ela tivesse números próprios, começaria a divergir das
// outras duas telas sobre o mesmo dinheiro.

/** A cor de cada aplicação segue o ATIVO, não a posição no ranking: se o
 *  Mercado Pago passar o Nubank no mês que vem, os dois não trocam de cor.
 *  O id é estável; a ordem por valor não é. */
function corDoAtivo(itens: AssetSummaryItem[], id: number): string {
  const ids = itens.map((i) => i.asset_id).sort((a, b) => a - b);
  return PALETA_CATEGORIAS[ids.indexOf(id) % PALETA_CATEGORIAS.length].cor;
}

export default function Investments() {
  const { label, ym } = usePeriod();
  const assets = useAssetSummary();
  const perfil = usePerfil();
  const budget = useBudgetSummary();
  const transactions = useTransactions();
  const categories = useCategories();
  // O aporte errado tem que ter conserto aqui. Esta aba mostrava os aportes
  // com `cursor: default` e nada acontecia ao tocar: quem lançou R$ 500 num
  // lugar errado não tinha como apagar sem descobrir que o lançamento mora na
  // aba de Lançamentos. O jeito que sobrava era lançar −500 pra anular, e é
  // exatamente o que aconteceu duas vezes em setembro.
  const [editando, setEditando] = useState<Transaction | null>(null);

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

  // Quanto as aplicações DEVERIAM render no mês, somando as que têm taxa. Null
  // quando nenhuma tem — aí não há o que comparar e a linha não aparece.
  const comTaxa = itens.filter((i) => i.expected_yield != null);
  const esperadoTotal = comTaxa.length
    ? comTaxa.reduce((s, i) => s + (i.expected_yield ?? 0), 0)
    : null;
  const rendimento = variacao - aporte;
  const comValor = itens.filter((i) => i.value > 0);

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
            <span className="seta" aria-hidden>{variacao > 0 ? "↑" : "↓"}</span>
            {formatMoney(Math.abs(variacao))} no mês
          </div>
        )}
      </section>

      {/* Dois números em linha, separados por fio — não dois cards. O total
          já é o herói, e a variação virou a linha dele. */}
      <div className="metricas">
        <div className="metrica">
          <div className="rot">Aportado no mês</div>
          <div className="val tnum">{formatMoney(aporte)}</div>
        </div>
        <div className="metrica">
          <div className="rot">Rendeu</div>
          {temBase ? (
            <div className="val tnum">
              {rendimento > 0 ? "+" : ""}{formatMoney(rendimento)}
            </div>
          ) : (
            // Sem mês anterior o número seria o saldo inteiro travestido de
            // lucro. Melhor um traço honesto do que um número bonito e falso.
            <div className="val fraco">—</div>
          )}
          {esperadoTotal !== null && (
            <div className="s">
              esperado <span className="tnum">{formatMoney(esperadoTotal)}</span>
            </div>
          )}
        </div>
      </div>

      {/* Sem o CDI não dá pra projetar nada, e a pessoa ficaria olhando um
          traço sem saber por quê. O aviso aponta pro lugar de resolver. */}
      {perfil.data && perfil.data.cdi_annual == null &&
        itens.some((i) => i.cdi_percent != null) && (
          <div className="aviso-box" style={{ marginTop: "var(--s4)" }}>
            Você marcou a taxa das aplicações, mas falta informar o <b>CDI atual</b>{" "}
            para calcular o rendimento. <Link to="/configuracoes">Informar agora</Link>
          </div>
        )}

      <div className="sec-title">
        <h2>Onde está</h2>
        <Link to="/patrimonio">Editar</Link>
      </div>

      {/* Rosca por APLICAÇÃO, não por classe: hoje as duas são renda fixa, e
          uma rosca de classe seria um anel inteiro de uma cor só. Com uma
          aplicação só ela também some — 100% de um lugar não precisa de
          gráfico pra ser entendido. A lista embaixo é a legenda: o círculo de
          cada linha tem a cor da fatia. */}
      {comValor.length >= 2 && (
        <div style={{ marginBottom: "var(--s4)" }}>
          <Rosca
            semLegenda
            total={total}
            rotuloCentro="investido"
            fatias={comValor.map((i) => ({
              id: String(i.asset_id),
              nome: i.name,
              cor: corDoAtivo(itens, i.asset_id),
              valor: i.value,
              pct: (i.value / total) * 100,
            }))}
          />
        </div>
      )}

      <div className="list">
        {itens.map((item) => (
          // Ativo se edita em Patrimônio: duas telas editando o mesmo ativo é
          // como as duas começam a discordar.
          <Link className="row" key={item.asset_id} to="/patrimonio">
            <div
              className="avatar"
              style={{ background: fundoDaCor(corDoAtivo(itens, item.asset_id), 26) }}
              aria-hidden
            >
              {item.asset_class === "crypto" ? "₿" : item.asset_class === "equity" ? "📊" : "🏦"}
            </div>
            <div className="mid">
              <div className="t">{item.name}</div>
              <div className="s">
                {ASSET_CLASS_LABEL[item.asset_class]}
                {item.cdi_percent != null && <> · {item.cdi_percent}% do CDI</>}
                {/* Saldo herdado de mês anterior: sem avisar, o número parece
                    atual e a pessoa confia num dado que não atualizou. */}
                {item.as_of && item.as_of !== ym && <> · de {formatYm(item.as_of)}</>}
              </div>
            </div>
            <div className="amt tnum">
              {formatMoney(item.value)}
              {total > 0 && <span className="sub">{Math.round((item.value / total) * 100)}%</span>}
            </div>
            <MarcaEditavel />
          </Link>
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
              <button className="row" key={t.id} onClick={() => setEditando(t)}>
                <div className="avatar" style={{ background: fundoDaCor("#93a6dc", 18) }} aria-hidden>
                  🏦
                </div>
                <div className="mid">
                  <div className="t">{t.description}</div>
                  <div className="s">{formatDiaMes(t.date)}</div>
                </div>
                <div className="amt tnum">{formatMoney(t.amount_paid)}</div>
                <MarcaEditavel />
              </button>
            ))}
          </div>
        </>
      )}

      {editando && categories.data && (
        <TransactionForm
          categories={categories.data}
          transaction={editando}
          onClose={() => setEditando(null)}
        />
      )}
    </>
  );
}

function Esqueleto() {
  return (
    <>
      <div className="skel" style={{ height: 64, width: "60%", marginTop: "var(--s3)" }} />
      <div className="skel" style={{ height: 64, marginTop: "var(--s4)" }} />
      <div className="sec-title"><h2>Onde está</h2></div>
      <div className="skel" style={{ height: 160, borderRadius: "var(--r)" }} />
    </>
  );
}
