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
        // Os atualizados primeiro, por valor; os desatualizados no fim.
        .sort((a, b) => Number(!!a.stale) - Number(!!b.stale) || b.value - a.value),
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

  if (assets.isLoading || budget.isLoading || transactions.isLoading) return <Esqueleto />;
  if (erro) return <div className="error-box">{erro.message}</div>;

  // Saldo desatualizado (último conhecido é de mês anterior) aparece na lista,
  // mas não soma: o Nubank de setembro não pode inflar o "investido" de hoje.
  const atuais = itens.filter((i) => !i.stale);
  const desatualizados = itens.filter((i) => i.stale);
  const total = atuais.reduce((acc, i) => acc + i.value, 0);
  const anterior = atuais.reduce((acc, i) => acc + i.previous, 0);
  const variacao = total - anterior;
  const aporte = budget.data?.totals.investment.paid ?? 0;

  // Rendimento é o que sobrou da variação depois de descontar o que você
  // colocou. Só faz sentido com um mês anterior pra comparar: no primeiro mês
  // o saldo inteiro apareceria como "rendimento", o que seria falso.
  const temBase = anterior > 0;

  // Quanto as aplicações DEVERIAM render no mês, somando as que têm taxa. Null
  // quando nenhuma tem — aí não há o que comparar e a linha não aparece.
  const comTaxa = atuais.filter((i) => i.expected_yield != null);
  const esperadoTotal = comTaxa.length
    ? comTaxa.reduce((s, i) => s + (i.expected_yield ?? 0), 0)
    : null;
  const rendimento = variacao - aporte;
  const comValor = atuais.filter((i) => i.value > 0);

  // Aporte e resgate separados: o resgate é dinheiro que SAIU do investimento,
  // não prejuízo nem gasto. Somados num número só, um resgate de R$ 1.000
  // pareceria um mês sem aporte.
  const aportado = aportes.reduce((s, t) => s + Math.max(t.amount_paid ?? 0, 0), 0);
  const resgatado = aportes.reduce((s, t) => s + Math.max(-(t.amount_paid ?? 0), 0), 0);

  // Saldo lançado por conferência: no mês houve um movimento cujo valor não
  // está registrado (a caixinha usada numa compra, sem o extrato). A conta
  // variação − aportes daria um "prejuízo" que não aconteceu. Traço + motivo.
  // Aplicação sem saldo do mês também deixa o rendimento sem conta possível.
  const conferidos = itens.filter((i) => i.reconciliation_note);
  const naoApurado = conferidos.length > 0 || desatualizados.length > 0;
  // O desatualizado já é dito embaixo do total; aqui só entra como motivo
  // quando não há outro, pra não repetir a mesma frase duas vezes na tela.
  const motivos = conferidos.length
    ? conferidos.map((i) => `${i.name} — ${i.reconciliation_note}`)
    : [`${desatualizados.map((i) => i.name).join(", ")} sem saldo de ${label}.`];

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
        {/* Com aplicação desatualizada, a variação do total não é apurável. */}
        {temBase && desatualizados.length === 0 && Math.abs(variacao) >= 0.01 && (
          <div className={`delta ${variacao > 0 ? "pos" : "neg"}`}>
            <span className="seta" aria-hidden>{variacao > 0 ? "↑" : "↓"}</span>
            {formatMoney(Math.abs(variacao))} no mês
          </div>
        )}
        {desatualizados.length > 0 && (
          <div className="nota">
            Não entra no total:{" "}
            {desatualizados.map((i, n) => (
              <span key={i.asset_id}>
                {n > 0 && ", "}
                {i.name} ({formatMoney(i.value)} em {i.as_of ? formatYm(i.as_of) : "—"})
              </span>
            ))}
            {" "}— sem saldo de {label}.
          </div>
        )}
      </section>

      {/* Dois números em linha, separados por fio — não dois cards. O total
          já é o herói, e a variação virou a linha dele. */}
      <div className="metricas">
        <div className="metrica">
          <div className="rot">Aportado</div>
          <div className="val tnum">{formatMoney(aportado)}</div>
          {/* O resgate é linha do aporte, não terceira coluna: três valores
              em dinheiro não cabem lado a lado em 360px. Mês sem resgate não
              ganha um zero. */}
          {resgatado > 0 ? (
            <div className="s">
              resgatado <span className="tnum">{formatMoney(resgatado)}</span>
            </div>
          ) : (
            naoApurado && <div className="s">resgate não conciliado</div>
          )}
        </div>
        <div className="metrica">
          <div className="rot">Rendeu</div>
          {naoApurado ? (
            <>
              <div className="val fraco">—</div>
              <div className="s">não apurado</div>
            </>
          ) : temBase ? (
            <div className="val tnum">
              {rendimento > 0 ? "+" : ""}{formatMoney(rendimento)}
            </div>
          ) : (
            // Sem mês anterior o número seria o saldo inteiro travestido de
            // lucro. Melhor um traço honesto do que um número bonito e falso.
            <div className="val fraco">—</div>
          )}
          {esperadoTotal !== null && !naoApurado && (
            <div className="s">
              esperado <span className="tnum">{formatMoney(esperadoTotal)}</span>
            </div>
          )}
        </div>
      </div>
      {naoApurado && (
        <p className="nota">
          Rendimento de {label} não apurado: {motivos.join(" ")}
        </p>
      )}

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
          <Link className={`row${item.stale ? " desatualizado" : ""}`} key={item.asset_id} to="/patrimonio">
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
                {/* Saldo lançado por conferência: é o que a linha precisa dizer
                    neste mês, e a legenda só tem lugar pra uma coisa. */}
                {item.stale ? (
                  <span className="aviso-txt">não atualizado · {item.as_of ? formatYm(item.as_of) : ""}</span>
                ) : item.reconciliation_note ? (
                  "ajuste de conferência"
                ) : (
                  <>
                    {ASSET_CLASS_LABEL[item.asset_class]}
                    {item.cdi_percent != null && <> · {item.cdi_percent}% do CDI</>}
                    {/* Saldo herdado de mês anterior: sem avisar, o número parece
                        atual e a pessoa confia num dado que não atualizou. */}
                    {item.as_of && item.as_of !== ym && <> · de {formatYm(item.as_of)}</>}
                  </>
                )}
              </div>
            </div>
            <div className="amt tnum">
              {formatMoney(item.value)}
              {total > 0 && !item.stale && <span className="sub">{Math.round((item.value / total) * 100)}%</span>}
            </div>
            <MarcaEditavel />
          </Link>
        ))}
      </div>

      {aportes.length > 0 && (
        <>
          <div className="sec-title">
            <h2>{resgatado > 0 ? "Aportes e resgates" : "Aportes"} de {label}</h2>
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
