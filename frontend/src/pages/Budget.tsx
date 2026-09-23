import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import MoneyCell from "../components/MoneyCell";
import TransactionForm from "../components/TransactionForm";
import TransactionList from "../components/TransactionList";
import Invoices from "./Invoices";
import {
  useBudgetSummary,
  useCategories,
  useDeleteBudget,
  useInvoicesSummary,
  useSetBudget,
  useTransactions,
} from "../lib/queries";
import { usePeriod } from "../lib/period";
import { ApiError } from "../lib/api";
import { formatMoney } from "../lib/format";
import type { BudgetSummaryItem, Category, CategoryType, Transaction } from "../lib/types";

// Despesa primeiro: é onde o orçamento aperta. Receita fecha a lista porque
// funciona como referência ("cabe no que entra?"), não como teto.
const SECTIONS: { type: CategoryType; title: string; hint: string }[] = [
  { type: "expense", title: "Despesas", hint: "O teto que você se dá em cada categoria no mês" },
  { type: "investment", title: "Investimentos", hint: "Quanto pretende guardar no mês" },
  { type: "income", title: "Receitas", hint: "Quanto espera receber no mês" },
];

type Tab = "metas" | "lancamentos" | "faturas";

// Faturas entra aqui e não na barra de baixo: as quatro abas do polegar são as
// de todo dia, e fatura se olha uma ou duas vezes por mês. Ela mora ao lado dos
// lançamentos porque é a mesma pergunta — o que aconteceu com meu dinheiro.
const ABAS: { id: Tab; rotulo: string }[] = [
  { id: "metas", rotulo: "Orçamento" },
  { id: "lancamentos", rotulo: "Lançamentos" },
  { id: "faturas", rotulo: "Faturas" },
];

export default function Budget() {
  // A sub-aba vive na URL pra sobreviver ao F5 e poder ser linkada de fora.
  const [params, setParams] = useSearchParams();
  const aba = params.get("aba");
  const tab: Tab =
    aba === "lancamentos" ? "lancamentos" : aba === "faturas" ? "faturas" : "metas";
  const { data: categories } = useCategories();
  const [creating, setCreating] = useState(false);

  // O + do shell chega aqui mudando a URL para ?novo=1.
  //
  // Precisa ser efeito, e não valor inicial do useState: o inicializador roda
  // só na primeira montagem, então tocar no + já estando em Orçamento mudava a
  // URL e não abria nada — o componente não remonta numa navegação interna.
  // Vindo da tela de Início funcionava, o que fazia o bug parecer intermitente.
  useEffect(() => {
    if (params.get("novo") === "1") setCreating(true);
  }, [params]);
  const [editing, setEditing] = useState<Transaction | null>(null);

  function fecharCriacao() {
    setCreating(false);
    if (params.get("novo")) {
      setParams(
        (prev) => {
          const p = new URLSearchParams(prev);
          p.delete("novo");
          return p;
        },
        { replace: true }
      );
    }
  }

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
      <div className="empty">
        <div className="big">🎯</div>
        <div className="tit">Sem categorias ainda</div>
        <div>Crie uma para começar a orçar.</div>
        <div style={{ marginTop: "var(--s4)" }}>
          <Link className="btn btn-primary" to="/configuracoes">Criar categoria</Link>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="subtabs" role="tablist">
        {ABAS.map(({ id, rotulo }) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            className={tab === id ? "active" : ""}
            onClick={() => selectTab(id)}
          >
            {rotulo}
          </button>
        ))}
      </div>

      {tab === "metas" && <Metas />}
      {tab === "lancamentos" && <Lancamentos categories={categories} onEdit={setEditing} />}
      {tab === "faturas" && <Invoices />}

      {creating && categories && (
        <TransactionForm categories={categories} onClose={fecharCriacao} />
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
      <>
        <div className="skel" style={{ height: 150, borderRadius: "var(--r-lg)" }} />
        <div className="duo" style={{ gridTemplateColumns: "1fr 1fr" }}>
          <div className="skel" style={{ height: 72 }} />
          <div className="skel" style={{ height: 72 }} />
        </div>
        <div className="sec-title"><h2>Despesas</h2></div>
        <div className="skel" style={{ height: 220, borderRadius: "var(--r)" }} />
      </>
    );
  }
  if (error) return <div className="error-box">{(error as ApiError).message}</div>;

  const totals = data?.totals;
  const gasto = totals?.expense.paid ?? 0;
  const orcadoDespesa = totals?.expense.budgeted ?? 0;
  const estourou = orcadoDespesa > 0 && gasto > orcadoDespesa;
  const resta = orcadoDespesa - gasto;
  const entrou = totals?.income.paid ?? 0;
  const investido = totals?.investment.paid ?? 0;
  const noCartao = data?.caixa.no_cartao ?? 0;

  return (
    <>
      {/* O herói é o gasto do mês contra o teto do mês, e nada mais. Antes era
          "falta distribuir", que só fazia sentido com caixinha: sem pote pra
          encher, distribuir não é a ação de ninguém. Gastei quanto, de quanto,
          e quanto falta — é o que se confere de cabeça na fila do mercado. */}
      <section className="hero">
        <div className="rot">Gasto em despesas</div>
        <div className={`big tnum ${estourou ? "neg" : ""}`}>{formatMoney(gasto)}</div>
        {orcadoDespesa > 0 ? (
          <>
            <div className="delta" style={estourou ? { color: "var(--neg)" } : undefined}>
              {estourou
                ? `${formatMoney(-resta)} acima do teto de ${formatMoney(orcadoDespesa)}`
                : `de ${formatMoney(orcadoDespesa)} — faltam ${formatMoney(resta)}`}
            </div>
            <div className="bar-track" style={{ marginTop: "var(--s3)" }}>
              <div
                className={`bar-fill ${estourou ? "over" : ""}`}
                style={{
                  width: `${Math.min(100, (gasto / orcadoDespesa) * 100)}%`,
                  background: estourou ? "var(--neg)" : gasto / orcadoDespesa >= 0.8 ? "var(--gold)" : "var(--pos)",
                }}
              />
            </div>
          </>
        ) : (
          // Sem teto nenhum, o convite é definir o primeiro — não um zero que
          // parece número.
          <div className="delta">Sem teto definido. Preencha ao lado de uma categoria.</div>
        )}
      </section>

      {/* Entrou e sobrou vêm do realizado, não do orçado: número orçado em
          cartão herói mostra intenção com cara de fato. */}
      <div className="duo" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <div className="card">
          <div className="rot">Entrou no mês</div>
          <div className="val pos tnum">{formatMoney(entrou)}</div>
        </div>
        <div className="card">
          <div className="rot">Sobrou</div>
          <div className={`val tnum ${entrou - gasto - investido >= 0 ? "pos" : "neg"}`}>
            {formatMoney(entrou - gasto - investido)}
          </div>
          {/* Este "sobrou" é do eixo do GASTO: desconta tudo que foi consumido,
              inclusive o que está na fatura e ainda não saiu da conta. A linha
              só aparece quando há cartão no mês, porque sem ele os dois eixos
              dão o mesmo número e a explicação seria ruído. */}
          {noCartao > 0 && (
            <div className="s" style={{ marginTop: 2 }}>
              {formatMoney(noCartao)} ainda na fatura
            </div>
          )}
        </div>
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
  type,
  items,
}: {
  title: string;
  hint: string;
  type: CategoryType;
  items: BudgetSummaryItem[];
}) {
  const orcado = items.reduce((acc, i) => acc + i.budgeted, 0);
  const pago = items.reduce((acc, i) => acc + i.paid, 0);

  // Categoria sem meta e sem movimento é ruído: ela existe pra poder receber
  // uma meta, mas listar todas empurra as que importam pra fora da tela.
  //
  // A ordem também é escolhida, e não a que o banco devolveu (tipo + nome
  // alfabético). Com 28 categorias, ordem alfabética faz "Academia" abrir a
  // lista e a que estourou o orçamento aparecer lá embaixo — exatamente o
  // contrário do que se abre a tela pra ver. Aqui: primeiro quem passou do
  // teto, depois quem mais consumiu.
  const ordenar = (a: BudgetSummaryItem, b: BudgetSummaryItem) => {
    // Estourar só faz sentido contra uma alocação deste mês.
    const estourouA = a.budgeted > 0 && a.paid > a.budgeted;
    const estourouB = b.budgeted > 0 && b.paid > b.budgeted;
    if (estourouA !== estourouB) return estourouA ? -1 : 1;
    if (b.paid !== a.paid) return b.paid - a.paid;
    return b.budgeted - a.budgeted;
  };

  const comDado = items
    .filter((i) => i.budgeted > 0 || i.paid > 0 || i.planned > 0)
    .sort(ordenar);
  const ociosas = items.length - comDado.length;
  const [mostrarTodas, setMostrarTodas] = useState(false);
  const visiveis = mostrarTodas ? [...items].sort(ordenar) : comDado;

  return (
    <>
      <div className="sec-title">
        <h2>{title}</h2>
        <span className="tnum" style={{ fontSize: 13, color: "var(--text-dim)" }}>
          {/* Sem teto na seção, "de R$ 0,00" não é informação — é um zero que
              parece meta de zero reais. */}
          {orcado > 0 ? `${formatMoney(pago)} de ${formatMoney(orcado)}` : formatMoney(pago)}
        </span>
      </div>

      <div className="col-meta">teto do mês</div>
      <div className="list">
        {visiveis.map((item) => (
          <BudgetRow key={item.category_id} item={item} />
        ))}
      </div>

      {ociosas > 0 && (
        <button
          className="btn btn-ghost btn-sm btn-block"
          style={{ marginTop: "var(--s2)" }}
          onClick={() => setMostrarTodas((v) => !v)}
        >
          {mostrarTodas
            ? "Esconder as sem movimento"
            : `Mostrar mais ${ociosas} ${type === "income" ? "receita" : "categoria"}${ociosas > 1 ? "s" : ""} sem movimento`}
        </button>
      )}
    </>
  );
}

function BudgetRow({ item }: { item: BudgetSummaryItem }) {
  const resta = item.budgeted - item.paid;
  const estourou = item.budgeted > 0 && resta < 0;
  // Estourar receita é bom, estourar despesa não — a cor segue o tipo.
  const estourarEhBom = item.category_type === "income";
  const razao = item.budgeted > 0 ? item.paid / item.budgeted : 0;
  const pct = Math.round(razao * 100);

  const corBarra = estourou
    ? estourarEhBom ? "var(--pos)" : "var(--neg)"
    : razao >= 0.8
      ? "var(--gold)"
      : item.color;

  return (
    <div className="row budget-row">
      <div className="budget-top">
        <div
          className="avatar"
          style={{ background: `color-mix(in srgb, ${item.color} 22%, transparent)` }}
        >
          {item.icon}
        </div>
        <div className="mid">
          <div className="t">{item.category_name}</div>
          <div className="s">
            {item.paid > 0 ? (
              <>
                {/* Sem a palavra, "R$ 770,00" solto embaixo do nome não diz se
                    é o que se gastou, o que se planejou ou o que sobrou. */}
                <b style={{ color: "var(--text)" }}>{formatMoney(item.paid)}</b>
                <span> {item.category_type === "income" ? "recebidos" : "gastos"}</span>
                {/* "Faltam" só com teto: sem denominador, faltar não é nada. */}
                {item.budgeted > 0 && (
                  <span style={{ color: estourou ? corEstouro(item) : "var(--text-faint)" }}>
                    {" · "}
                    {estourou ? `${formatMoney(-resta)} acima` : `faltam ${formatMoney(resta)}`}
                  </span>
                )}
                {item.budgeted === 0 && item.planned > 0 && (
                  <> · {formatMoney(item.planned)} previsto</>
                )}
              </>
            ) : item.planned > 0 ? (
              <>{formatMoney(item.planned)} previsto</>
            ) : item.budgeted > 0 ? (
              <>teto de {formatMoney(item.budgeted)}, nada gasto ainda</>
            ) : (
              "sem movimento"
            )}
          </div>
        </div>
        <div className="saldo-input">
          <MetaInput item={item} />
        </div>
      </div>

      {/* A barra só aparece quando há meta: sem teto, "quanto por cento" não
          tem denominador e a barra seria decoração. */}
      {item.budgeted > 0 && (
        <div className="budget-bar">
          <div className="bar-track">
            <div
              className={`bar-fill ${estourou ? "over" : ""}`}
              style={{ width: `${Math.min(100, pct)}%`, background: corBarra }}
            />
          </div>
          <span className="tnum" style={{ color: estourou ? corBarra : "var(--text-faint)" }}>
            {pct}%
          </span>
        </div>
      )}
    </div>
  );
}

// Estourar receita é bom (recebi mais que esperava), estourar despesa não.
function corEstouro(item: BudgetSummaryItem): string {
  return item.category_type === "income" ? "var(--pos)" : "var(--neg)";
}

function MetaInput({ item }: { item: BudgetSummaryItem }) {
  const { period } = usePeriod();
  const setBudget = useSetBudget();
  const deleteBudget = useDeleteBudget();

  return (
    <MoneyCell
      // Meta de zero é o MESMO que sem meta agora que não há caixinha, então
      // ela mostra o campo vazio e pontilhado como as outras. Antes aparecia
      // um "0" sólido, que lia como "teto de zero reais" — e era só o resíduo
      // de alguém tocar no campo e sair dele.
      saved={item.budget_id && item.budgeted !== 0 ? item.budgeted : null}
      ariaLabel={`Teto de ${item.category_name}`}
      pending={setBudget.isPending || deleteBudget.isPending}
      onCommit={(amount) => {
        // Esvaziar o campo apaga a meta, em vez de gravar zero. A API de
        // exclusão de meta já existia e não tinha porta nenhuma na tela: quem
        // definia um teto por engano ficava com um "R$ 0,00" pregado na linha,
        // que parece teto de zero reais — e teto de zero e "sem teto" são
        // coisas diferentes na hora de ler a barra.
        //
        // Não tem confirmação de propósito: é edição em linha e se desfaz
        // digitando o número de novo. Diálogo aqui seria pedágio no caminho de
        // quem só quer corrigir um dígito.
        if (amount === null) {
          if (item.budget_id) deleteBudget.mutate(item.budget_id);
          return;
        }
        setBudget.mutate({
          category_id: item.category_id,
          year: period.year,
          month: period.month,
          amount,
        });
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
  const [, setParams] = useSearchParams();
  const { data: transactions, isLoading, error } = useTransactions();
  // Os pagamentos de fatura entram na mesma lista: eles são o maior desembolso
  // do mês, e uma lista de "o que aconteceu com meu dinheiro" sem eles mandaria
  // procurar noutra tela. Vêm do resumo que a aba de Faturas já busca.
  const { data: faturas } = useInvoicesSummary();
  const pagamentos = faturas?.payments ?? [];

  const vazio = transactions?.length === 0 && pagamentos.length === 0;

  return (
    <>
      {isLoading && <div className="skel" style={{ height: 260, borderRadius: "var(--r)" }} />}
      {error && <div className="error-box">{(error as ApiError).message}</div>}

      {transactions && (transactions.length > 0 || pagamentos.length > 0) && (
        <TransactionList
          transactions={transactions}
          categories={categories ?? []}
          payments={pagamentos}
          onEdit={onEdit}
          onAbrirFatura={() => setParams({ aba: "faturas" }, { replace: true })}
        />
      )}

      {!isLoading && !error && vazio && (
        <div className="empty">
          <div className="big">🧾</div>
          <div className="tit">Nada lançado em {label}</div>
          <div>Toque no <b>+</b> para registrar.</div>
        </div>
      )}
    </>
  );
}

// ---------- Auxiliares ----------


