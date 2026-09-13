import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import MoneyCell from "../components/MoneyCell";
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
import { formatMoney } from "../lib/format";
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
  // A sub-aba vive na URL pra sobreviver ao F5 e poder ser linkada de fora.
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("aba") === "lancamentos" ? "lancamentos" : "metas";
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
  // A sobra é o que o mês devolve se tudo for exatamente ao orçado.
  const leftover = totals
    ? totals.income.budgeted - totals.expense.budgeted - totals.investment.budgeted
    : 0;

  return (
    <>
      {/* O heroi do orçamento é o quanto já foi, contra o teto. É a pergunta
          que a tela responde; receita e sobra são contexto. */}
      <section className="hero">
        <div className="rot">Gasto em despesas</div>
        <div className="big tnum">{formatMoney(gasto)}</div>
        {orcadoDespesa > 0 ? (
          <>
            <div className="delta" style={estourou ? { color: "var(--neg)" } : undefined}>
              de {formatMoney(orcadoDespesa)} orçado
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
          <div className="delta">Nenhuma meta definida ainda</div>
        )}
      </section>

      <div className="duo" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <div className="card">
          <div className="rot">Receita orçada</div>
          <div className="val pos tnum">{formatMoney(totals?.income.budgeted ?? 0)}</div>
        </div>
        <div className="card">
          <div className="rot">Sobra planejada</div>
          <div className={`val tnum ${leftover >= 0 ? "pos" : "neg"}`}>
            {formatMoney(leftover)}
          </div>
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
          {formatMoney(pago)} de {formatMoney(orcado)}
        </span>
      </div>

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
                <b style={{ color: "var(--text)" }}>{formatMoney(item.paid)}</b>
                {item.budgeted > 0 && (
                  <>
                    {" · "}
                    <span style={estourou ? { color: estourarEhBom ? "var(--pos)" : "var(--neg)" } : undefined}>
                      {estourou ? `passou ${formatMoney(-resta)}` : `resta ${formatMoney(resta)}`}
                    </span>
                  </>
                )}
              </>
            ) : item.planned > 0 ? (
              <>previsto {formatMoney(item.planned)}</>
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

function MetaInput({ item }: { item: BudgetSummaryItem }) {
  const { period } = usePeriod();
  const setBudget = useSetBudget();

  return (
    <MoneyCell
      saved={item.budget_id ? item.budgeted : null}
      ariaLabel={`Orçado para ${item.category_name}`}
      pending={setBudget.isPending}
      onCommit={(amount) =>
        setBudget.mutate({
          category_id: item.category_id,
          year: period.year,
          month: period.month,
          amount: amount ?? 0,
        })
      }
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
    <>
      {isLoading && <div className="skel" style={{ height: 260, borderRadius: "var(--r)" }} />}
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
          <div className="tit">Nada lançado em {label}</div>
          <div>Toque no <b>+</b> para registrar.</div>
        </div>
      )}
    </>
  );
}

// ---------- Auxiliares ----------


