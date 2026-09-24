import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import TransactionForm from "../components/TransactionForm";
import { LinhaLancamento } from "../components/TransactionList";
import Segmentado from "../components/Segmentado";
import { Evolucao, Rosca, type Fatia, type PontoEvolucao } from "../components/Graficos";
import {
  useBudgetSummary,
  useCards,
  useCategories,
  useCategoryReport,
  useInvoicesSummary,
  useMonthlyReport,
  useTransactions,
} from "../lib/queries";
import { usePeriod } from "../lib/period";
import { ApiError } from "../lib/api";
import { formatDiaMes, formatMoney } from "../lib/format";
import { FRASE_FILTRO, OPCOES_FILTRO, useFiltroFinalidade } from "../lib/finalidade";
import { COR_OUTRAS } from "../lib/paleta";
import type { CardInvoices, Category, Invoice, Transaction } from "../lib/types";

/* O Início é relatório, não painel. A ordem responde as perguntas na ordem em
   que elas são feitas ao abrir o app:

     1. como foi o mês            -> saldo do mês, e o que entrou/saiu
     2. pra onde foi o dinheiro   -> gastos por categoria, com a finalidade
     3. isso é normal?            -> evolução dos gastos
     4. o que ainda vem           -> faturas
     5. o que aconteceu por último -> quatro lançamentos

   Saíram daqui: o "Fluxo" (somava entrou + gastou + investido como partes de
   um mesmo todo), o "Previsto × pago" (é pergunta de Metas, e compra no cartão
   não tem previsto — aparecia "R$ 120 de R$ 0"), o delta percentual do herói
   ("↓ 160% vs mês anterior" sobre um saldo que troca de sinal) e o "Após
   faturas", que subtraía faturas de meses futuros do fluxo de UM mês. */

const MESES_OPCOES = [
  { valor: "6", rotulo: "6 meses" },
  { valor: "12", rotulo: "12 meses" },
] as const;

export default function Dashboard() {
  const { period } = usePeriod();
  const [editando, setEditando] = useState<Transaction | null>(null);
  const [filtro, setFiltro] = useFiltroFinalidade();
  const [janela, setJanela] = useState<"6" | "12">("6");

  const { data: transactions, isLoading, error } = useTransactions();
  const { data: categories } = useCategories(true);
  const { data: resumo } = useBudgetSummary();
  const { data: faturas } = useInvoicesSummary();
  const { data: cards } = useCards();
  const distribuicao = useCategoryReport(filtro);
  const serie = useMonthlyReport(Number(janela), filtro);

  const caixa = resumo?.caixa;
  const nomeDoMes = new Date(period.year, period.month - 1, 1).toLocaleDateString("pt-BR", {
    month: "long",
  });

  const catMap = useMemo(() => {
    const m = new Map<number, Category>();
    categories?.forEach((c) => m.set(c.id, c));
    return m;
  }, [categories]);

  // Quatro e não seis: aqui o lançamento é consulta rápida. A lista inteira
  // mora em Lançamentos, que existe pra isso.
  const recentes = useMemo(
    () =>
      [...(transactions ?? [])]
        .sort((a, b) => b.date.localeCompare(a.date) || b.id - a.id)
        .slice(0, 4),
    [transactions]
  );

  const fatias: Fatia[] = useMemo(() => {
    const d = distribuicao.data;
    if (!d) return [];
    const lista: Fatia[] = d.categories.map((c) => ({
      id: String(c.category_id),
      nome: c.name,
      icone: c.icon,
      cor: c.color,
      valor: c.value,
      pct: c.pct,
    }));
    if (d.others) {
      lista.push({
        id: "outras",
        nome: `Outras (${d.others.count})`,
        cor: COR_OUTRAS,
        valor: d.others.value,
        pct: d.others.pct,
      });
    }
    return lista;
  }, [distribuicao.data]);

  const pontos: PontoEvolucao[] = useMemo(
    () =>
      (serie.data?.months ?? []).map((m) => {
        const data = new Date(m.year, m.month - 1, 1);
        return {
          chave: `${m.year}-${m.month}`,
          rotulo: data.toLocaleDateString("pt-BR", { month: "short" }).replace(".", ""),
          mesLongo: data.toLocaleDateString("pt-BR", { month: "long", year: "numeric" }),
          // Filtrado, um mês cujo gasto é TODO sem finalidade (o histórico
          // antes dela existir) não é zero: é desconhecido.
          valor:
            filtro !== "todos" && m.expense === 0 && m.expense_sem_finalidade > 0
              ? null
              : m.expense,
          atual: m.year === period.year && m.month === period.month,
        };
      }),
    [serie.data, period, filtro]
  );

  if (isLoading) return <Esqueleto />;
  if (error) return <div className="error-box">{(error as ApiError).message}</div>;

  const pagamentos = faturas?.payments ?? [];
  const vazio = (transactions ?? []).length === 0 && pagamentos.length === 0;
  const saldo = caixa?.carteira ?? 0;
  const cartaoMexeNoSaldo = (caixa?.no_cartao ?? 0) > 0 || (caixa?.faturas_pagas ?? 0) > 0;

  // Cartão ainda sem finalidade: as compras dele ficam fora de Pessoal/Família/
  // Empresa até alguém dizer pra que ele serve. A tela avisa uma vez, baixo.
  const cartoesSemFinalidade = (cards ?? []).filter((c) => !c.archived && c.finalidade == null);

  const d = distribuicao.data;
  const semFinalidade = filtro !== "todos" && d && d.sem_finalidade.count > 0 ? d.sem_finalidade : null;

  const conhecidos = pontos.filter((p) => p.valor != null);
  const media = conhecidos.length
    ? conhecidos.reduce((s, p) => s + (p.valor ?? 0), 0) / conhecidos.length
    : 0;
  // Meses em que parte do gasto não tem finalidade: o filtro mostra só um
  // pedaço deles, e a tela diz isso uma vez, sem alarde.
  const mesesIncompletos =
    filtro === "todos" ? 0 : (serie.data?.months ?? []).filter((m) => m.expense_sem_finalidade > 0).length;

  return (
    <>
      {/* ---------- Saldo do mês ----------
          Era "Carteira", e o nome dizia uma coisa que o número não é: não é
          quanto há na conta, é quanto SOBROU do fluxo deste mês — entradas
          menos o que saiu da conta (à vista, investido e faturas pagas). */}
      <section className="hero" aria-labelledby="saldo-rotulo">
        <div className="big tnum">{formatMoney(saldo)}</div>
        <div className="rot" id="saldo-rotulo">Saldo do mês</div>
        <div className="indicadores">
          <span><i style={{ background: "var(--pos)" }} aria-hidden /><b className="tnum">{formatMoney(caixa?.entrou ?? 0)}</b> entrou</span>
          <span><i style={{ background: "var(--neg)" }} aria-hidden /><b className="tnum">{formatMoney(caixa?.gasto_total ?? 0)}</b> gastou</span>
          <span><i style={{ background: "var(--inv)" }} aria-hidden /><b className="tnum">{formatMoney(caixa?.investido ?? 0)}</b> investiu</span>
        </div>
        {/* Entrou − gastou − investiu não fecha com o saldo quando há cartão, e
            a frase diz por quê em vez de deixar a conta parecer errada. */}
        {cartaoMexeNoSaldo && (
          <div className="nota">
            O saldo desconta as faturas pagas no mês ({formatMoney(caixa?.faturas_pagas ?? 0)}),
            não as compras no cartão.
          </div>
        )}
      </section>

      {(caixa?.sem_forma_definida_qtd ?? 0) > 0 && (
        <Link className="aviso-acao" to="/rever">
          <div>
            <b>
              {caixa!.sem_forma_definida_qtd}{" "}
              {caixa!.sem_forma_definida_qtd === 1 ? "lançamento" : "lançamentos"} sem forma de pagamento
            </b>{" "}
            · {formatMoney(caixa!.sem_forma_definida)} contando como saída da conta
          </div>
          <span aria-hidden>›</span>
        </Link>
      )}

      {vazio ? (
        <div className="empty" style={{ marginTop: "var(--s6)" }}>
          <div className="big">🪙</div>
          <div className="tit">Nenhum lançamento em {nomeDoMes}</div>
          <div>Toque no <b>+</b> para registrar o primeiro.</div>
        </div>
      ) : (
        <>
          {/* ---------- Gastos ---------- */}
          <div className="sec-title">
            <h2>Gastos</h2>
          </div>
          <Segmentado
            rotulo="Finalidade dos gastos"
            opcoes={OPCOES_FILTRO}
            valor={filtro}
            aoEscolher={setFiltro}
            largo
          />

          <div className="total-filtro">
            <div className="v tnum">{formatMoney(d?.total ?? 0)}</div>
            <div className="r">{FRASE_FILTRO[filtro]} em {nomeDoMes}</div>
          </div>

          {distribuicao.isLoading ? (
            <div className="skel" style={{ height: 184 }} />
          ) : fatias.length > 0 ? (
            <Rosca fatias={fatias} total={d?.total ?? 0} rotuloCentro="gastos" />
          ) : (
            <div className="hint">Nenhum gasto com esta finalidade em {nomeDoMes}.</div>
          )}

          {semFinalidade && (
            <div className="nota">
              {semFinalidade.count}{" "}
              {semFinalidade.count === 1 ? "lançamento" : "lançamentos"} deste mês (
              {formatMoney(semFinalidade.value)}) não {semFinalidade.count === 1 ? "tem" : "têm"} finalidade
              definida e {semFinalidade.count === 1 ? "fica" : "ficam"} fora deste filtro.
            </div>
          )}
          {cartoesSemFinalidade.length > 0 && (
            <>
              <div className="nota">
                {cartoesSemFinalidade.map((c) => c.name).join(", ")}{" "}
                {cartoesSemFinalidade.length === 1 ? "ainda não tem" : "ainda não têm"} finalidade,
                e as compras {cartoesSemFinalidade.length === 1 ? "dele" : "deles"} só aparecem em Todos.
              </div>
              <Link className="link-seta" to="/configuracoes">Classificar cartões</Link>
            </>
          )}

          {/* ---------- Evolução ---------- */}
          <div className="sec-title">
            <h2>Evolução dos gastos</h2>
          </div>
          <div className="cabeca-grafico">
            <Segmentado
              rotulo="Período da evolução"
              opcoes={[...MESES_OPCOES]}
              valor={janela}
              aoEscolher={setJanela}
            />
            {conhecidos.length > 0 && (
              <div className="resumo-linha">
                média <b className="tnum">{formatMoney(media)}</b>/mês
              </div>
            )}
          </div>
          {serie.isLoading ? (
            <div className="skel" style={{ height: 176 }} />
          ) : (
            <Evolucao pontos={pontos} />
          )}
          {mesesIncompletos > 0 && (
            <div className="nota">
              Parte dos lançamentos de {mesesIncompletos}{" "}
              {mesesIncompletos === 1 ? "mês" : "meses"} deste período não tem finalidade
              definida. Mês sem nenhuma aparece como um vão na linha.
            </div>
          )}

          <ResumoDeFaturas cartoes={faturas?.cards ?? []} />

          {/* ---------- Últimos lançamentos ---------- */}
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

/** As faturas em uma linha por cartão: quanto e quando.
 *
 * A que vence no mês selecionado, se houver; senão a próxima. É informação,
 * não assunto — a tela de Faturas é que é operacional.
 */
function ResumoDeFaturas({ cartoes }: { cartoes: CardInvoices[] }) {
  const linhas = cartoes
    .map((c) => ({ cartao: c, fatura: c.current ?? c.next }))
    .filter((l): l is { cartao: CardInvoices; fatura: Invoice } => l.fatura != null);

  if (linhas.length === 0) return null;

  return (
    <>
      <div className="sec-title">
        <h2>Faturas</h2>
        <Link to="/orcamento?aba=faturas">Ver faturas</Link>
      </div>
      <ul className="faturas-mini">
        {linhas.map(({ cartao, fatura }) => {
          const paga = fatura.status === "paga";
          return (
            <li key={cartao.card_id}>
              <div style={{ minWidth: 0 }}>
                <div className="n">{cartao.name}</div>
                <div className="d">
                  {/* Paga antes do vencimento é comum: "venceu 2 out" em
                      setembro seria mentira. Paga é paga, a data sai. */}
                  {paga
                    ? "paga"
                    : fatura.status === "atrasada"
                      ? `atrasada · venceu ${formatDiaMes(fatura.due_date)}`
                      : `vence ${formatDiaMes(fatura.due_date)}`}
                </div>
              </div>
              <div className="v tnum">
                {formatMoney(paga ? fatura.total : fatura.remaining)}
                {!paga && fatura.paid > 0 && <small>de {formatMoney(fatura.total)}</small>}
              </div>
            </li>
          );
        })}
      </ul>
    </>
  );
}

function Esqueleto() {
  return (
    <>
      <div className="skel" style={{ height: 40, width: "60%", marginTop: "var(--s3)" }} />
      <div className="skel" style={{ height: 16, width: "40%", marginTop: "var(--s2)" }} />
      <div className="skel" style={{ height: 16, width: "85%", marginTop: "var(--s3)" }} />
      <div className="sec-title"><h2>Gastos</h2></div>
      <div className="skel" style={{ height: 44, borderRadius: "var(--r-pill)" }} />
      <div className="skel" style={{ height: 184, marginTop: "var(--s4)" }} />
    </>
  );
}
