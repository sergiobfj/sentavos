import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import TransactionForm from "../components/TransactionForm";
import { LinhaLancamento } from "../components/TransactionList";
import { IconeCartao } from "../components/TransactionList";
import { useCategories, useInvoicesSummary, useTransactions } from "../lib/queries";
import { usePeriod } from "../lib/period";
import { shiftPeriod } from "../lib/period";
import { budgetsApi } from "../lib/api";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../lib/api";
import { formatMoney } from "../lib/format";
import { Fluxo, PorCategoria, PrevistoVsPago } from "../components/Graficos";
import { useBudgetSummary } from "../lib/queries";
import type { Category, Transaction } from "../lib/types";

export default function Dashboard() {
  const { period } = usePeriod();
  // Tocar num lançamento recente abre ele, e não a lista onde ele está. Levar
  // pra outra aba pra depois procurar a mesma linha de novo é trabalho que a
  // tela pode poupar — e era a distância que fazia "corrigir" parecer difícil.
  const [editando, setEditando] = useState<Transaction | null>(null);
  const { data: transactions, isLoading, error } = useTransactions();
  const { data: categories } = useCategories(true);
  // O resumo do orçamento traz duas coisas: o previsto × pago por categoria e o
  // bloco de caixa (Carteira, Gastou, faturas). Uma chamada, dois assuntos.
  const { data: resumo } = useBudgetSummary();
  const { data: faturas } = useInvoicesSummary();

  // O mês anterior existe só pra comparação do cartão herói. Sem ele o número
  // grande diria "quanto sobrou" sem dizer se isso é bom — e "R$ 1.200" só
  // significa alguma coisa ao lado do mês passado.
  //
  // Vem do mesmo resumo, e não da lista de lançamentos: a Carteira desconta
  // pagamento de fatura, que não é lançamento — calculá-la aqui daria um
  // número diferente do que o herói mostra.
  const anterior = shiftPeriod(period, -1);
  const { data: resumoAnterior } = useQuery({
    queryKey: ["budgets", "summary", `${anterior.year}-${anterior.month}`],
    queryFn: () => budgetsApi.summary(anterior),
  });

  const caixa = resumo?.caixa;
  const catMap = useMemo(() => {
    const m = new Map<number, Category>();
    categories?.forEach((c) => m.set(c.id, c));
    return m;
  }, [categories]);

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

  const pagamentos = faturas?.payments ?? [];
  const vazio = (transactions ?? []).length === 0 && pagamentos.length === 0;
  const variacao = calcularVariacao(
    caixa?.carteira ?? 0,
    resumoAnterior?.caixa.carteira ?? 0
  );

  // O cartão de fatura só entra quando há fatura. Pra quem não usa cartão, um
  // "Fatura atual R$ 0,00" ocuparia um terço da primeira dobra pra não dizer
  // nada — e aí o terceiro cartão continua sendo o investimento, como era.
  //
  // Quando há fatura em aberto mas nenhuma vence NESTE mês, o cartão mostra o
  // que está em aberto em vez de "R$ 0,00 vence neste mês". Foi o que a tela
  // mostrou: em setembro a fatura das compras só vence em outubro, e o zero
  // fazia parecer que não havia cartão nenhum.
  const venceNoMes = (caixa?.faturas_do_mes ?? 0) > 0;
  const emAberto = (caixa?.faturas_em_aberto ?? 0) > 0;
  const temFatura = venceNoMes || emAberto;

  return (
    <>
      {/* ---------- Carteira ----------
          Dinheiro de verdade: entrou, menos o que saiu à vista, menos o que foi
          investido, menos as faturas pagas no mês. Compra no cartão NÃO entra
          aqui — ela ainda não tirou nada da conta. */}
      <section className="hero">
        <div className="rot">Carteira</div>
        <div className={`big tnum ${(caixa?.carteira ?? 0) >= 0 ? "pos" : "neg"}`}>
          {formatMoney(caixa?.carteira ?? 0)}
        </div>
        {variacao && (
          <div className={`delta ${variacao.melhorou ? "pos" : "neg"}`}>
            <span aria-hidden>{variacao.melhorou ? "↑" : "↓"}</span>
            {variacao.texto}
          </div>
        )}
        {/* "Após faturas" fica ao lado da Carteira, nunca no lugar dela: é
            projeção do que já está comprometido, e não o dinheiro que está na
            conta agora. Trocar um pelo outro faria o app dizer que você tem
            menos do que tem. */}
        {(caixa?.faturas_em_aberto ?? 0) > 0 && (
          <div className="hero-secundario">
            <span>Após faturas</span>
            <b className={`tnum ${(caixa?.apos_faturas ?? 0) >= 0 ? "" : "neg"}`}>
              {formatMoney(caixa?.apos_faturas ?? 0)}
            </b>
          </div>
        )}
      </section>

      {/* O aviso da transição: lançamentos anteriores ao cartão que ainda não
          têm forma de pagamento. Até serem revisados eles contam como saída de
          caixa — que é como já eram contados —, mas a tela diz isso em vez de
          fingir que a resposta está completa. */}
      {(caixa?.sem_forma_definida_qtd ?? 0) > 0 && (
        <Link className="aviso-acao" to="/rever">
          <div>
            <b>
              {caixa!.sem_forma_definida_qtd}{" "}
              {caixa!.sem_forma_definida_qtd === 1 ? "lançamento" : "lançamentos"} sem
              forma de pagamento
            </b>
            <div>
              Somam {formatMoney(caixa!.sem_forma_definida)} e estão contando como
              saída da conta.
            </div>
          </div>
          <span aria-hidden>›</span>
        </Link>
      )}

      <div className="duo">
        <div className="card">
          <div className="rot"><Bolinha cor="var(--pos)" /> Entrou</div>
          <div className="val pos tnum">{formatMoney(caixa?.entrou ?? 0)}</div>
        </div>
        {/* "Saiu" virou "Gastou", e a mudança não é de palavra: com cartão, o
            que você gastou e o que saiu da conta deixaram de ser o mesmo
            número. Este é o do gasto — inclui a compra no cartão. */}
        <div className="card">
          <div className="rot"><Bolinha cor="var(--neg)" /> Gastou</div>
          <div className="val neg tnum">{formatMoney(caixa?.gasto_total ?? 0)}</div>
          {(caixa?.no_cartao ?? 0) > 0 && (
            <div className="s">{formatMoney(caixa!.no_cartao)} no cartão</div>
          )}
        </div>
        {/* Com cartão são quatro cartões, em duas fileiras de dois — e não três
            com um órfão embaixo. O de fatura entra; o de investimento fica,
            porque tirar um número da tela pra caber outro é resolver espaço
            perdendo informação. */}
        {temFatura && (
          <Link className="card" to="/orcamento?aba=faturas">
            <div className="rot">
              <span className="bolinha-icone" aria-hidden><IconeCartao /></span> Fatura
            </div>
            <div className="val tnum">
              {formatMoney(venceNoMes ? caixa!.faturas_do_mes : caixa!.faturas_em_aberto)}
            </div>
            <div className="s">{venceNoMes ? "vence neste mês" : "em aberto"}</div>
          </Link>
        )}
        <div className="card">
          <div className="rot"><Bolinha cor="var(--inv)" /> Investido</div>
          <div className="val inv tnum">{formatMoney(caixa?.investido ?? 0)}</div>
        </div>
      </div>

      {/* A proporção entre os três, logo abaixo deles e sem título próprio: são
          os mesmos números, então merecem a faixa mas não uma seção inteira. */}
      {((caixa?.entrou ?? 0) > 0 || (caixa?.gasto_total ?? 0) > 0) && (
        <div style={{ marginTop: "var(--s3)" }}>
          <Fluxo
            entrou={caixa?.entrou ?? 0}
            saiu={caixa?.gasto_total ?? 0}
            investido={caixa?.investido ?? 0}
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
                <Link to="/orcamento">Orçamento</Link>
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
              <LinhaLancamento
                key={t.id}
                t={t}
                cat={catMap.get(t.category_id)}
                onEdit={() => setEditando(t)}
              />
            ))}
          </div>
        </>
      )}

      {editando && categories && (
        <TransactionForm
          categories={categories}
          transaction={editando}
          onClose={() => setEditando(null)}
        />
      )}
    </>
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
    if (Math.abs(pct) <= 300) {
      return { texto: `${Math.abs(pct)}% vs. mês anterior`, melhorou };
    }
  }
  return { texto: `${formatMoney(Math.abs(diferenca))} vs. mês anterior`, melhorou };
}
