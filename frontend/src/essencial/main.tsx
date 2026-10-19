import React, {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createRoot } from "react-dom/client";
import {
  HashRouter,
  NavLink,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import {
  accountBalance,
  assetBalance,
  createDemoState,
  createQuickEntries,
  CURRENT_MONTH,
  day,
  invested,
  knownBalance,
  money,
  monthEntries,
  monthLabel,
  parseAmount,
  projection,
  shiftMonth,
  sum,
  TODAY,
  totals,
  type DemoState,
  type Entry,
  type ExpenseClass,
  type Kind,
  type Purpose,
  type QuickInput,
} from "./model";
import "./styles.css";

type IconName =
  | "month"
  | "list"
  | "chart"
  | "invest"
  | "settings"
  | "plus"
  | "arrow"
  | "left"
  | "right"
  | "close"
  | "wallet"
  | "card"
  | "check";
function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    month: (
      <>
        <rect x="4" y="5" width="16" height="16" rx="2" />
        <path d="M8 3v4m8-4v4M4 11h16m-11 4h2v2H9z" />
      </>
    ),
    list: (
      <>
        <path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" />
      </>
    ),
    chart: (
      <>
        <path d="M4 4v16h17M8 15l4-5 4 2 4-7" />
      </>
    ),
    invest: (
      <>
        <path d="M5 20h14M7 16v-5m5 5V7m5 9V4M5 8l6-5 3 1" />
      </>
    ),
    settings: (
      <>
        <path d="m9 3-.7 2.3-2.3.5-1.7 2.9 1.6 1.8v3L4.3 15l1.7 2.9 2.3.5L9 21h6l.7-2.6 2.3-.5 1.7-2.9-1.6-1.5v-3l1.6-1.8L18 5.8l-2.3-.5L15 3z" />
        <circle cx="12" cy="12" r="3" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
    arrow: <path d="M5 12h14m-5-5 5 5-5 5" />,
    left: <path d="m14 6-6 6 6 6" />,
    right: <path d="m10 6 6 6-6 6" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    wallet: (
      <>
        <rect x="3" y="6" width="18" height="14" rx="2" />
        <path d="m4 6 13-3v3m0 6h4v4h-4z" />
      </>
    ),
    card: (
      <>
        <rect x="3" y="5" width="18" height="14" rx="2" />
        <path d="M3 10h18m-14 5h3" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}
const NAV: { to: string; label: string; icon: IconName }[] = [
  { to: "/", label: "Meu mês", icon: "month" },
  { to: "/lancamentos", label: "Lançamentos", icon: "list" },
  { to: "/relatorios", label: "Relatórios", icon: "chart" },
  { to: "/investir", label: "Investir", icon: "invest" },
];
interface DemoContextValue {
  state: DemoState;
  setState: React.Dispatch<React.SetStateAction<DemoState>>;
  month: string;
  setMonth: (m: string) => void;
  openQuick: (kind?: QuickInput["kind"]) => void;
  openAccounts: () => void;
  openAdvanced: () => void;
}
const DemoContext = createContext<DemoContextValue>(null!);
const useDemo = () => useContext(DemoContext);
function App() {
  const [state, setState] = useState(createDemoState);
  const [month, setMonth] = useState(CURRENT_MONTH);
  const [quick, setQuick] = useState<QuickInput["kind"] | null>(null);
  const [accounts, setAccounts] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [toast, setToast] = useState("");
  const [lastAccount, setLastAccount] = useState("Nubank");
  const location = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname, month]);
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 5000);
    return () => clearTimeout(timer);
  }, [toast]);
  const active = NAV.find((n) => n.to === location.pathname) ?? NAV[0];
  const showQuick =
    location.pathname === "/" || location.pathname === "/lancamentos";
  return (
    <DemoContext.Provider
      value={{
        state,
        setState,
        month,
        setMonth,
        openQuick: (kind = "expense") => setQuick(kind),
        openAccounts: () => setAccounts(true),
        openAdvanced: () => setAdvanced(true),
      }}
    >
      <div className="essential-app">
        <a className="skip-link" href="#content">
          Ir para o conteúdo
        </a>
        <aside className="side">
          <NavLink to="/" className="brand" aria-label="Sentavos, Meu mês">
            <span className="brand-symbol">
              s<span>·</span>
            </span>
            <span>
              sentavos<small>ESSENCIAL</small>
            </span>
          </NavLink>
          <p className="nav-caption">SEU DIA A DIA</p>
          <nav aria-label="Navegação principal desktop">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.to === "/"}>
                <Icon name={n.icon} />
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="secondary-nav">
            <button onClick={() => setAccounts(true)}>
              <Icon name="wallet" />
              Contas e saldos
            </button>
            <NavLink to="/cartoes">
              <Icon name="card" />
              Cartões e faturas
            </NavLink>
            <button onClick={() => setAdvanced(true)}>
              <Icon name="settings" />
              Configurações
            </button>
          </div>
          <div className="side-foot">
            <span className="demo-dot" />
            Ambiente de demonstração<small>Nenhum dado real é utilizado.</small>
          </div>
        </aside>
        <div className="workspace">
          <div className="demo-banner">
            <span>PROTÓTIPO</span> Dados fictícios · hoje, 18/10/2026{" "}
            <span className="banner-extra">
              · alterações duram até recarregar
            </span>
          </div>
          <header className="topbar">
            <span className="mobile-wordmark">
              sentavos<span>·</span>
            </span>
            <span className="desktop-breadcrumb">
              Seu dinheiro / <b>{active.label}</b>
            </span>
            <button
              className="icon-button"
              aria-label="Configurações"
              onClick={() => setAdvanced(true)}
            >
              <Icon name="settings" />
            </button>
          </header>
          <main id="content" tabIndex={-1}>
            <div className="page-heading">
              <div>
                <p className="eyebrow">
                  {location.pathname === "/"
                    ? "CLAREZA PARA O DIA A DIA"
                    : "SENTAVOS ESSENCIAL"}
                </p>
                <h1>
                  {location.pathname === "/cartoes"
                    ? "Cartões e faturas"
                    : location.pathname === "/comparar"
                      ? "Próximos meses"
                      : active.label}
                </h1>
              </div>
              <MonthControl />
            </div>
            <Routes>
              <Route path="/" element={<MyMonth />} />
              <Route path="/lancamentos" element={<Transactions />} />
              <Route path="/relatorios" element={<Reports />} />
              <Route path="/investir" element={<Invest />} />
              <Route path="/comparar" element={<Compare />} />
              <Route path="/cartoes" element={<Cards />} />
              <Route path="*" element={<MissingPage />} />
            </Routes>
            <footer className="content-foot">
              sentavos essencial <span>Menos esforço. Mais clareza.</span>
            </footer>
          </main>
        </div>
        {showQuick && (
          <button
            className={`quick-fab${location.pathname === "/lancamentos" ? " transaction-fab" : ""}`}
            aria-label="Novo lançamento"
            onClick={() => setQuick("expense")}
          >
            <Icon name="plus" size={24} />
            <span>Novo lançamento</span>
          </button>
        )}
        <nav className="bottom-nav" aria-label="Navegação principal mobile">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"}>
              <Icon name={n.icon} />
              <span>{n.label}</span>
            </NavLink>
          ))}
        </nav>
        {quick && (
          <QuickSheet
            initialKind={quick}
            lastAccount={lastAccount}
            close={() => setQuick(null)}
            saved={(input) => {
              const entries = createQuickEntries(
                input,
                `new-${crypto.randomUUID()}`,
              );
              setState((s) => ({ ...s, entries: [...s.entries, ...entries] }));
              setLastAccount(input.account);
              setMonth(input.date.slice(0, 7));
              setQuick(null);
              setToast("Lançamento salvo na demonstração.");
            }}
          />
        )}
        {accounts && <AccountSheet close={() => setAccounts(false)} />}
        {advanced && <AdvancedSheet close={() => setAdvanced(false)} />}
        <div className="toast" role="status" aria-live="polite">
          {toast && (
            <span>
              <Icon name="check" />
              {toast}
            </span>
          )}
        </div>
      </div>
    </DemoContext.Provider>
  );
}
function MonthControl() {
  const { month, setMonth } = useDemo();
  return (
    <div className="month-control">
      <button
        className="icon-button"
        aria-label="Mês anterior"
        disabled={month <= "2026-01"}
        onClick={() => setMonth(shiftMonth(month, -1))}
      >
        <Icon name="left" size={16} />
      </button>
      <label className="month-pick">
        <span>{monthLabel(month, true)}</span>
        <input
          aria-label="Selecionar mês e ano"
          type="month"
          min="2026-01"
          max="2027-03"
          value={month}
          onChange={(e) => {
            if (
              /^202[67]-(0[1-9]|1[0-2])$/.test(e.target.value) &&
              e.target.value <= "2027-03"
            )
              setMonth(e.target.value);
          }}
        />
      </label>
      <button
        className="icon-button"
        aria-label="Próximo mês"
        disabled={month >= "2027-03"}
        onClick={() => setMonth(shiftMonth(month, 1))}
      >
        <Icon name="right" size={16} />
      </button>
    </div>
  );
}
function SectionHeading({
  title,
  detail,
  action,
}: {
  title: string;
  detail?: string;
  action?: ReactNode;
}) {
  return (
    <div className="section-heading">
      <div>
        <h2>{title}</h2>
        {detail && <p>{detail}</p>}
      </div>
      {action}
    </div>
  );
}
function LinkButton({
  children,
  onClick,
}: {
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button className="text-button" onClick={onClick}>
      {children}
      <Icon name="right" size={15} />
    </button>
  );
}
function Summary({
  items,
}: {
  items: {
    label: string;
    value: number | null;
    positive?: boolean;
    action?: () => void;
  }[];
}) {
  return (
    <dl className="summary">
      {items.map((i) => (
        <div key={i.label}>
          <dt>{i.label}</dt>
          <dd className={i.positive ? "positive" : ""}>
            {i.action ? (
              <button onClick={i.action}>
                {i.value == null ? "Não apurado" : money(i.value)}
                <Icon name="right" size={12} />
              </button>
            ) : i.value == null ? (
              "Não apurado"
            ) : (
              money(i.value)
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function MyMonth() {
  const { state, month, setMonth, openAccounts } = useDemo();
  const navigate = useNavigate();
  const p = projection(state, month);
  const [calculation, setCalculation] = useState(false);
  const [planning, setPlanning] = useState(false);
  const [simulate, setSimulate] = useState(false);
  const current = month === CURRENT_MONTH;
  const past = month < CURRENT_MONTH;
  const selected = monthEntries(state, month);
  const t = totals(selected);
  const accountsNotice = state.accounts.some((a) => a.stale)
    ? "Há saldos desatualizados · conferir contas"
    : "Saldos observados entre 11 e 18/10 · ver contas";
  return (
    <>
      <section className="balance-overview" aria-label="Resumo do seu dinheiro">
        <div className="balance-now">
          <button className="balance-link" onClick={openAccounts}>
            <span className="metric-label">
              {current
                ? "Meu dinheiro agora"
                : "Dinheiro conhecido hoje · 18/10"}
              <Icon name="right" size={15} />
            </span>
            <strong className="hero-number" data-testid="money-now">
              {money(knownBalance(state))}
            </strong>
          </button>
          <span className="balance-date">{accountsNotice}</span>
        </div>
        <div className="balance-future">
          <button
            className="balance-link"
            onClick={() => p && setCalculation(true)}
            disabled={!p}
          >
            <span className="metric-label">
              {past
                ? "Resultado de receitas e gastos"
                : current
                  ? "Previsão depois das contas"
                  : `Previsão para ${monthLabel(month)}`}
              <Icon name="right" size={15} />
            </span>
            <strong
              className={`forecast-number ${(p?.available ?? t.result) >= 0 ? "positive" : "attention"}`}
              data-testid="forecast"
            >
              {money(p?.available ?? t.result)}
            </strong>
          </button>
          <span className="balance-date">
            {past
              ? "Por competência · não é saldo em conta"
              : "Já considera o que você separou para guardar."}
          </span>
        </div>
      </section>
      <Summary
        items={[
          {
            label: "A receber",
            value: p?.income ?? 0,
            action: () => setPlanning(true),
          },
          {
            label: "A pagar",
            value: p ? p.fixed + p.variable + p.invoices : 0,
            action: () => setPlanning(true),
          },
          {
            label: "Investido hoje",
            value: invested(state),
            action: () => navigate("/investir"),
          },
        ]}
      />
      {!current && (
        <p className="quiet-note">
          {past
            ? "Você está consultando um mês encerrado. O dinheiro conhecido acima é de hoje."
            : "Esta é uma projeção. Os saldos dos próximos meses ainda não foram observados."}{" "}
          <button onClick={() => setMonth(CURRENT_MONTH)}>
            Voltar para outubro
          </button>
        </p>
      )}
      <div className="month-actions">
        <button className="soft-button" onClick={() => setSimulate(true)}>
          E se eu gastar a mais?
          <Icon name="arrow" size={16} />
        </button>
        <LinkButton onClick={() => setPlanning(true)}>
          Ver planejamento
        </LinkButton>
      </div>
      <SectionHeading
        title="Seu mês, organizado"
        detail="O que já aconteceu e o que ainda vem."
      />
      <div className="month-groups">
        <EntryGroup
          title="Entradas"
          entries={selected.filter((e) => e.kind === "income")}
          kind="income"
        />
        <EntryGroup
          title="Despesas fixas"
          entries={selected.filter(
            (e) => e.kind === "expense" && e.expenseClass === "fixed",
          )}
          kind="expense"
        />
        <EntryGroup
          title="Despesas variáveis"
          entries={selected.filter(
            (e) => e.kind === "expense" && e.expenseClass !== "fixed",
          )}
          kind="expense"
        />
        <EntryGroup
          title="Investimentos"
          entries={selected.filter(
            (e) => e.kind === "contribution" || e.kind === "redemption",
          )}
          kind="contribution"
        />
      </div>
      <section className="invoices-inline">
        <Icon name="card" />
        <div>
          <h3>Cartões e faturas</h3>
          <p>
            {money(
              sum(
                selected.filter(
                  (e) => e.kind === "invoice" && e.status === "planned",
                ),
              ),
            )}{" "}
            a pagar neste mês
          </p>
        </div>
        <LinkButton onClick={() => navigate("/cartoes")}>
          Ver faturas
        </LinkButton>
      </section>
      <SectionHeading
        title="Um olhar para a frente"
        action={
          <LinkButton onClick={() => navigate("/comparar")}>
            Ver próximos meses
          </LinkButton>
        }
      />
      <div className="future-preview">
        {[1, 2].map((i) => {
          const future = shiftMonth(
            month < CURRENT_MONTH ? CURRENT_MONTH : month,
            i,
          );
          const m = projection(state, future);
          return (
            m && (
              <button
                key={future}
                className="future-month"
                onClick={() => {
                  setMonth(future);
                  setPlanning(true);
                }}
              >
                <h3>
                  {monthLabel(future)}
                  <Icon name="arrow" size={17} />
                </h3>
                <dl>
                  <div>
                    <dt>Entradas previstas</dt>
                    <dd>{money(m.income)}</dd>
                  </div>
                  <div>
                    <dt>Contas previstas</dt>
                    <dd>{money(m.fixed + m.variable + m.invoices)}</dd>
                  </div>
                  <div className="future-total">
                    <dt>Livre no fim do mês</dt>
                    <dd className={m.available >= 0 ? "positive" : "attention"}>
                      {money(m.available)}
                    </dd>
                  </div>
                </dl>
                <span>Ver compromissos</span>
              </button>
            )
          );
        })}
      </div>
      {calculation && p && (
        <Sheet
          title="De onde vem a previsão"
          close={() => setCalculation(false)}
        >
          <p className="sheet-intro">
            {monthLabel(month, true)} · valores conhecidos e previstos.
          </p>
          <Calculation month={month} />
          <p className="quiet-note">
            Despesas pagas já estão no saldo. Compras no cartão entram uma vez,
            pelo pagamento da fatura. Guardar dinheiro muda onde ele está; não é
            gasto.
          </p>
        </Sheet>
      )}
      {planning && <Planning close={() => setPlanning(false)} />}
      {simulate && <Simulation close={() => setSimulate(false)} />}
    </>
  );
}
function EntryGroup({
  title,
  entries,
  kind,
}: {
  title: string;
  entries: Entry[];
  kind: Kind;
}) {
  const [expanded, setExpanded] = useState(false);
  const done = entries.filter((e) => e.status === "done"),
    pending = entries.filter((e) => e.status === "planned");
  const sorted = [...pending]
    .sort((a, b) => a.date.localeCompare(b.date))
    .concat([...done].sort((a, b) => b.date.localeCompare(a.date)));
  const summary =
    kind === "income"
      ? `${money(sum(done))} recebido · ${money(sum(pending))} a receber`
      : kind === "contribution"
        ? `${money(sum(done.filter((e) => e.kind === "contribution")))} aportado · ${money(sum(done.filter((e) => e.kind === "redemption")))} resgatado`
        : `${money(sum(done))} gasto · ${money(sum(pending))} pendente`;
  return (
    <section className="entry-group">
      <div className="group-heading">
        <h3>{title}</h3>
        <p>{summary}</p>
      </div>
      <div>
        {(expanded ? sorted : sorted.slice(0, 3)).map((e) => (
          <EntryRow key={e.id} entry={e} compact />
        ))}
      </div>
      {entries.length === 0 && (
        <p className="empty-inline">Nenhum lançamento neste mês.</p>
      )}
      {sorted.length > 3 && (
        <button
          className="group-expand"
          aria-expanded={expanded}
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? "Recolher" : `Ver todos (${entries.length})`}
          <Icon name={expanded ? "left" : "right"} size={14} />
        </button>
      )}
    </section>
  );
}
function statusLabel(e: Entry) {
  return e.status === "planned"
    ? e.kind === "income"
      ? "A receber"
      : e.kind === "contribution" || e.kind === "redemption"
        ? "Previsto"
        : "A pagar"
    : e.kind === "income"
      ? "Recebido"
      : e.kind === "contribution"
        ? "Aporte"
        : e.kind === "redemption"
          ? "Resgate"
          : e.card
            ? "No cartão"
            : "Pago";
}
function EntryRow({
  entry: e,
  compact = false,
  onClick,
}: {
  entry: Entry;
  compact?: boolean;
  onClick?: () => void;
}) {
  const income = e.kind === "income" || e.kind === "redemption";
  const content = (
    <>
      <div className="entry-description">
        <strong>{e.description}</strong>
        <span>
          {compact
            ? `${day(e.date)}${e.card ? ` · ${e.card}` : ""}`
            : `${e.category} · ${e.card ?? e.account ?? "Conta a definir"} · ${day(e.date)}`}
        </span>
      </div>
      <div className="entry-value">
        <strong className={income ? "positive" : ""}>
          {income ? "+" : "−"}
          {money(e.amount)}
        </strong>
        <span className={e.status === "planned" ? "attention" : ""}>
          {statusLabel(e)}
        </span>
      </div>
    </>
  );
  return onClick ? (
    <button className="entry-row entry-button" onClick={onClick}>
      {content}
    </button>
  ) : (
    <div className="entry-row">{content}</div>
  );
}
function Calculation({ month }: { month: string }) {
  const { state } = useDemo();
  const p = projection(state, month);
  if (!p) return <p>Não há projeção para este período na demonstração.</p>;
  const lines = [
    [
      month === CURRENT_MONTH
        ? "Dinheiro conhecido hoje"
        : "Saldo previsto no início",
      p.opening,
    ],
    ["Entradas a receber", p.income],
    ["Despesas fixas a pagar", -p.fixed],
    ["Despesas variáveis previstas", -p.variable],
    ["Faturas a pagar", -p.invoices],
    ["Aportes planejados", -p.contributions],
    ["Resgates previstos", p.redemptions],
    ["Saldo previsto em conta", p.projected],
    ["Separado em reservas", -p.reserve],
    ["Livre depois das contas e reservas", p.available],
  ] as const;
  return (
    <dl className="calculation">
      {lines.map(([label, amount], i) => (
        <div
          className={i === lines.length - 1 ? "calculation-total" : ""}
          key={label}
        >
          <dt>{label}</dt>
          <dd
            className={i === lines.length - 1 && amount >= 0 ? "positive" : ""}
          >
            {money(amount)}
          </dd>
        </div>
      ))}
    </dl>
  );
}
function Simulation({ close }: { close: () => void }) {
  const { state, month } = useDemo();
  const [value, setValue] = useState("200");
  const p = projection(state, month);
  const amount = parseAmount(value);
  const result = p && amount ? p.available - amount : null;
  return (
    <Sheet title="E se eu gastar a mais?" close={close}>
      <p className="sheet-intro">
        Experimente um valor. Nenhum lançamento será criado.
      </p>
      <label className="field">
        Gasto adicional
        <input
          autoFocus
          inputMode="decimal"
          placeholder="0,00"
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
      </label>
      {result !== null ? (
        <div className="simulation-result" role="status">
          <span>Previsão depois desse gasto</span>
          <strong className={result >= 0 ? "positive" : "attention"}>
            {money(result)}
          </strong>
          <p>
            {result >= 0
              ? "Esse valor cabe na previsão conhecida. Contas ainda não registradas podem mudar o resultado."
              : "Esse gasto ultrapassa a previsão. Reveja os compromissos antes de decidir."}
          </p>
        </div>
      ) : (
        <p className="quiet-note">
          {p
            ? "Informe um valor maior que zero, usando vírgula para os centavos."
            : "Escolha outubro ou um mês futuro para simular."}
        </p>
      )}
      <button className="primary-button full-width" onClick={close}>
        Concluir simulação
      </button>
    </Sheet>
  );
}
function Planning({ close }: { close: () => void }) {
  const { state, month } = useDemo();
  const pending = monthEntries(state, month)
    .filter((e) => e.status === "planned")
    .sort((a, b) => a.date.localeCompare(b.date));
  const p = projection(state, month);
  return (
    <Sheet title={`Planejamento de ${monthLabel(month)}`} close={close}>
      {p && (
        <div className="planning-total">
          <span className="metric-label">A pagar no mês</span>
          <strong className="forecast-number">
            {money(p.fixed + p.variable + p.invoices)}
          </strong>
          <p className="quiet-note">
            Contas previstas, incluindo faturas. Aportes ficam separados.
          </p>
        </div>
      )}
      <details className="chart-data">
        <summary>Ver cálculo completo da previsão</summary>
        <Calculation month={month} />
      </details>
      <SectionHeading title="O que ainda vem" />
      {pending.map((e) => (
        <EntryRow entry={e} key={e.id} />
      ))}
      {!pending.length && (
        <p className="empty-inline">Nenhum compromisso previsto neste mês.</p>
      )}
      <p className="quiet-note">
        As reservas reduzem o valor livre, sem virar despesa. O financiamento
        aparece como compromisso separado das faturas.
      </p>
    </Sheet>
  );
}

function Transactions() {
  const { state, month, setState, openQuick } = useDemo();
  const [filter, setFilter] = useState("Todos");
  const [search, setSearch] = useState("");
  const [detail, setDetail] = useState<Entry | null>(null);
  const [pendingOnly, setPendingOnly] = useState(false);
  const [filters, setFilters] = useState(false);
  const all = monthEntries(state, month);
  const t = totals(all);
  const filtered = all.filter(
    (e) =>
      (filter === "Todos" ||
        (filter === "Entradas" && e.kind === "income") ||
        (filter === "Despesas" && e.kind === "expense") ||
        (filter === "Investimentos" &&
          (e.kind === "contribution" || e.kind === "redemption"))) &&
      (!pendingOnly || e.status === "planned") &&
      `${e.description} ${e.category} ${e.account ?? ""}`
        .toLocaleLowerCase("pt-BR")
        .includes(search.toLocaleLowerCase("pt-BR")),
  );
  const done = filtered
    .filter((e) => e.status === "done")
    .sort((a, b) => b.date.localeCompare(a.date));
  const pending = filtered
    .filter((e) => e.status === "planned")
    .sort((a, b) => a.date.localeCompare(b.date));
  return (
    <>
      <div className="page-intro">
        <p>Registrar, conferir e seguir o dia.</p>
        <button
          className="primary-button desktop-action"
          onClick={() => openQuick()}
        >
          <Icon name="plus" size={17} />
          Novo lançamento
        </button>
      </div>
      <Summary
        items={[
          { label: "Entrou", value: t.income },
          { label: "Saiu da conta", value: t.cashExpense },
          { label: "Aportado", value: t.contributed },
        ]}
      />
      <div className="list-toolbar">
        <div className="segments" aria-label="Filtrar lançamentos">
          {["Todos", "Entradas", "Despesas", "Investimentos"].map((f) => (
            <button
              key={f}
              aria-pressed={filter === f}
              className={filter === f ? "selected" : ""}
              onClick={() => setFilter(f)}
            >
              {f}
            </button>
          ))}
        </div>
        <button
          className="text-button"
          onClick={() => setFilters(!filters)}
          aria-expanded={filters}
        >
          Filtros{pendingOnly || search ? " · ativos" : ""}
        </button>
      </div>
      {filters && (
        <div className="filter-panel">
          <label className="field">
            Buscar lançamento
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Descrição, categoria ou conta"
            />
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={pendingOnly}
              onChange={(e) => setPendingOnly(e.target.checked)}
            />
            Somente previstos
          </label>
        </div>
      )}
      <div className="transaction-list">
        {done.length > 0 && (
          <>
            <SectionHeading
              title="Realizados"
              detail={`${done.length} lançamentos`}
            />
            {done.map((e) => (
              <EntryRow key={e.id} entry={e} onClick={() => setDetail(e)} />
            ))}
          </>
        )}
        {pending.length > 0 && (
          <>
            <SectionHeading
              title="Ainda previstos"
              detail="Separados do que já aconteceu."
            />
            {pending.map((e) => (
              <EntryRow key={e.id} entry={e} onClick={() => setDetail(e)} />
            ))}
          </>
        )}
        {filtered.length === 0 && (
          <div className="empty-state">
            <Icon name="list" size={30} />
            <h2>Nenhum lançamento por aqui</h2>
            <p>Experimente outro filtro ou registre uma movimentação.</p>
            <button className="soft-button" onClick={() => openQuick()}>
              Novo lançamento
            </button>
          </div>
        )}
      </div>
      <p className="quiet-note">
        “Saiu da conta” inclui pagamentos de fatura, sem somar novamente as
        compras. Aportes e resgates ficam separados de receitas e gastos.
      </p>
      {detail && (
        <Sheet title={detail.description} close={() => setDetail(null)}>
          <EntryRow entry={detail} />
          <dl className="calculation">
            <div>
              <dt>Categoria</dt>
              <dd>{detail.category}</dd>
            </div>
            <div>
              <dt>Conta ou cartão</dt>
              <dd>{detail.card ?? detail.account ?? "A definir"}</dd>
            </div>
            <div>
              <dt>Data</dt>
              <dd>{day(detail.date)}/2026</dd>
            </div>
            <div>
              <dt>Situação</dt>
              <dd>{statusLabel(detail)}</dd>
            </div>
          </dl>
          {detail.kind === "expense" && (
            <label className="field">
              <span id="detail-expense-class-label">Organizar como</span>
              <select
                aria-labelledby="detail-expense-class-label"
                aria-describedby="detail-expense-class-help"
                value={detail.expenseClass ?? "variable"}
                onChange={(e) => {
                  const next = {
                    ...detail,
                    expenseClass: e.target.value as ExpenseClass,
                  };
                  setState((s) => ({
                    ...s,
                    entries: s.entries.map((entry) =>
                      entry.id === detail.id ? next : entry,
                    ),
                  }));
                  setDetail(next);
                }}
              >
                <option value="fixed">Despesa fixa</option>
                <option value="variable">Despesa variável</option>
              </select>
              <small id="detail-expense-class-help">
                Você pode corrigir sem mudar a categoria.
              </small>
            </label>
          )}
          <p className="quiet-note">
            Edição completa e baixas serão conectadas aos fluxos existentes na
            integração. Esta demonstração permite conferir os dados e ajustar a
            classificação.
          </p>
        </Sheet>
      )}
    </>
  );
}

function Compare() {
  const { state, month, setMonth } = useDemo();
  const base = month < CURRENT_MONTH ? CURRENT_MONTH : month;
  const [planning, setPlanning] = useState(false);
  const months = [0, 1, 2].map((i) => shiftMonth(base, i));
  const rows: {
    label: string;
    value: (p: NonNullable<ReturnType<typeof projection>>) => number;
  }[] = [
    { label: "Saldo de partida", value: (p) => p.opening },
    { label: "Entradas previstas", value: (p) => p.income },
    { label: "Despesas fixas", value: (p) => p.fixed },
    { label: "Despesas variáveis", value: (p) => p.variable },
    { label: "Faturas", value: (p) => p.invoices },
    { label: "Aportes previstos", value: (p) => p.contributions },
    { label: "Resgates previstos", value: (p) => p.redemptions },
    { label: "Saldo previsto em conta", value: (p) => p.projected },
    { label: "Reservas", value: (p) => p.reserve },
    { label: "Livre no fim do mês", value: (p) => p.available },
  ];
  return (
    <>
      <p className="page-intro">O que entra, o que sai e o que deve sobrar.</p>
      <p className="quiet-note">
        Três meses a partir do mês selecionado. A demonstração tem previsões de
        outubro/2026 a março/2027.
      </p>
      <div className="comparison-desktop">
        <table>
          <caption>
            Previsões mensais em reais. Outubro considera apenas o que falta
            acontecer.
          </caption>
          <thead>
            <tr>
              <th scope="col">Informação</th>
              {months.map((ym) => (
                <th scope="col" key={ym}>
                  {monthLabel(ym, true)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr
                className={i === rows.length - 1 ? "comparison-total" : ""}
                key={row.label}
              >
                <th scope="row">{row.label}</th>
                {months.map((ym) => {
                  const p = projection(state, ym);
                  return (
                    <td key={ym}>{p ? money(row.value(p)) : "Não previsto"}</td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="comparison-mobile">
        {months.map((ym) => {
          const p = projection(state, ym);
          return (
            p && (
              <section className="comparison-month" key={ym}>
                <h2>{monthLabel(ym, true)}</h2>
                <dl>
                  {rows.map((row, i) => (
                    <div
                      className={
                        i === rows.length - 1 ? "comparison-total" : ""
                      }
                      key={row.label}
                    >
                      <dt>{row.label}</dt>
                      <dd>{money(row.value(p))}</dd>
                    </div>
                  ))}
                </dl>
                <LinkButton
                  onClick={() => {
                    setMonth(ym);
                    setPlanning(true);
                  }}
                >
                  Ver compromissos
                </LinkButton>
              </section>
            )
          );
        })}
      </div>
      <p className="quiet-note">
        O saldo final previsto de um mês é o saldo de partida do próximo. A
        reserva limita o dinheiro livre; não sai da conta. Em outubro, entradas
        e despesas são apenas as que ainda faltam.
      </p>
      {planning && <Planning close={() => setPlanning(false)} />}
    </>
  );
}

const CHART_COLORS = [
  "#98b8a2",
  "#b6a68e",
  "#8d9ea9",
  "#b48d7c",
  "#aaa2b6",
  "#798a72",
];
function Reports() {
  const { state, month } = useDemo();
  const [purpose, setPurpose] = useState("Todos");
  const [reading, setReading] = useState("total");
  const [windowSize, setWindowSize] = useState(6);
  const [explain, setExplain] = useState(false);
  const entries = monthEntries(state, month);
  const all = totals(entries);
  const expenses = entries.filter(
    (e) =>
      e.kind === "expense" &&
      e.status === "done" &&
      (purpose === "Todos" || e.purpose === purpose) &&
      (reading === "total" || !e.nature || e.nature === "consumption"),
  );
  const expense = sum(expenses);
  const groups = Object.entries(
    expenses.reduce<Record<string, number>>(
      (a, e) => ({ ...a, [e.category]: (a[e.category] ?? 0) + e.amount }),
      {},
    ),
  ).sort((a, b) => b[1] - a[1]);
  let angle = 0;
  const stops = groups.map(([, value], i) => {
    const from = angle;
    angle += expense ? (value / expense) * 100 : 0;
    return `${CHART_COLORS[i % CHART_COLORS.length]} ${from}% ${angle}%`;
  });
  const points = Array.from({ length: windowSize }, (_, i) => {
    const ym = shiftMonth(month, i - windowSize + 1);
    const list = monthEntries(state, ym).filter(
      (e) =>
        e.kind === "expense" &&
        e.status === "done" &&
        (purpose === "Todos" || e.purpose === purpose) &&
        (reading === "total" || !e.nature || e.nature === "consumption"),
    );
    return { ym, amount: sum(list), hasData: list.length > 0 };
  });
  const max = Math.max(...points.map((p) => p.amount), 1);
  const coordinates = points.map(
    (p, i) =>
      `${30 + (i * 460) / (points.length - 1)},${140 - (p.amount / max) * 110}`,
  );
  return (
    <>
      <div className="page-intro">
        <p>Entenda como seu dinheiro foi utilizado.</p>
        <LinkButton onClick={() => setExplain(true)}>
          Entender os números
        </LinkButton>
      </div>
      <div className="report-top">
        <div>
          <span className="metric-label">
            Quanto sobrou das receitas e gastos
          </span>
          <strong
            className={`forecast-number ${all.result >= 0 ? "positive" : "attention"}`}
          >
            {money(all.result)}
          </strong>
          <p className="quiet-note">
            Resultado por competência · não é saldo da conta.
          </p>
        </div>
        <Summary
          items={[
            { label: "Entrou", value: all.income },
            { label: "Gasto total", value: all.expense },
            { label: "Aportado", value: all.contributed },
          ]}
        />
      </div>
      <div className="report-filters">
        <label className="field">
          Analisar gastos de
          <select value={purpose} onChange={(e) => setPurpose(e.target.value)}>
            {["Todos", "Pessoal", "Família", "Empresa"].map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </label>
        <label className="field">
          Leitura dos gastos
          <select value={reading} onChange={(e) => setReading(e.target.value)}>
            <option value="total">Gasto total</option>
            <option value="living">Custo de vida</option>
          </select>
        </label>
      </div>
      <p className="quiet-note">
        Os filtros abaixo se aplicam aos gráficos de gastos. O resumo acima
        mostra o mês completo.
      </p>
      <div className="report-grid">
        <section className="chart-section">
          <SectionHeading
            title="Para onde foi"
            detail={`${reading === "total" ? "Gasto total" : "Custo de vida"} · ${purpose.toLowerCase()}`}
          />
          {expense > 0 ? (
            <>
              <div className="donut-wrap">
                <div
                  className="donut"
                  role="img"
                  aria-label={`Distribuição de ${money(expense)}. Detalhes na lista abaixo.`}
                  style={{ background: `conic-gradient(${stops.join(",")})` }}
                >
                  <div>
                    <span>
                      {reading === "total" ? "Gastos" : "Custo de vida"}
                    </span>
                    <strong>{money(expense)}</strong>
                  </div>
                </div>
              </div>
              <ul className="category-breakdown">
                {groups.map(([name, value], i) => (
                  <li key={name}>
                    <span>
                      <i
                        style={{
                          background: CHART_COLORS[i % CHART_COLORS.length],
                        }}
                      />
                      {name}
                    </span>
                    <strong>{money(value)}</strong>
                    <small>{Math.round((value / expense) * 100)}%</small>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="empty-inline">
              Nenhum gasto registrado neste recorte.
            </p>
          )}
        </section>
        <section className="chart-section">
          <SectionHeading
            title="Evolução dos gastos"
            action={
              <div className="segments small-segments">
                {[6, 12].map((n) => (
                  <button
                    key={n}
                    aria-pressed={windowSize === n}
                    className={windowSize === n ? "selected" : ""}
                    onClick={() => setWindowSize(n)}
                  >
                    {n} meses
                  </button>
                ))}
              </div>
            }
          />
          <p className="quiet-note">
            {reading === "total" ? "Gasto total" : "Custo de vida"} · mês
            selecionado ainda pode estar incompleto.
          </p>
          <svg
            className="line-chart"
            viewBox="0 0 520 180"
            role="img"
            aria-label={`Evolução em ${windowSize} meses. Valores na tabela expansível.`}
          >
            <path
              d="M30 30h460M30 85h460M30 140h460"
              stroke="var(--line)"
              strokeDasharray="3 5"
            />
            {points.map((p, i) =>
              i > 0 && p.hasData && points[i - 1].hasData ? (
                <path
                  key={p.ym}
                  d={`M${coordinates[i - 1]}L${coordinates[i]}`}
                  fill="none"
                  stroke="var(--positive)"
                  strokeWidth="2.5"
                />
              ) : null,
            )}
            {points.map((p, i) => (
              <g key={p.ym}>
                {p.hasData && (
                  <circle
                    cx={30 + (i * 460) / (points.length - 1)}
                    cy={140 - (p.amount / max) * 110}
                    r="3"
                    fill="var(--positive)"
                  />
                )}
                {(windowSize === 6 || i % 2 === 0) && (
                  <text
                    x={30 + (i * 460) / (points.length - 1)}
                    y="170"
                    textAnchor="middle"
                    fill="var(--muted)"
                    fontSize="12"
                  >
                    {monthLabel(p.ym).slice(0, 3)}
                  </text>
                )}
              </g>
            ))}
          </svg>
          <details className="chart-data">
            <summary>Ver valores por mês</summary>
            <dl className="calculation">
              {points.map((p) => (
                <div key={p.ym}>
                  <dt>{monthLabel(p.ym, true)}</dt>
                  <dd>{p.hasData ? money(p.amount) : "Sem registros"}</dd>
                </div>
              ))}
            </dl>
          </details>
          <p className="quiet-note">
            Sem registros não significa gasto zero. Não ligamos trechos sem
            dados.
          </p>
          <div className="report-note">
            <h3>O total continua completo</h3>
            <p>
              Financiamentos e aquisições entram no gasto total. A leitura
              “Custo de vida” permite analisar o consumo separadamente.
            </p>
          </div>
        </section>
      </div>
      {explain && (
        <Sheet
          title="Cada número tem uma função"
          close={() => setExplain(false)}
        >
          <div className="explanation">
            <h3>Resultado do mês</h3>
            <p>
              Receitas recebidas menos gastos por competência, incluindo
              parcelas de cartão. Não desconta aportes nem pagamentos de fatura
              novamente.
            </p>
            <h3>Dinheiro disponível</h3>
            <p>
              Saldo conhecido das contas. Pode incluir dinheiro de meses
              anteriores e resgates. Você o encontra em Meu mês.
            </p>
            <h3>Saída de caixa</h3>
            <p>
              Gastos à vista mais pagamentos de fatura. Aportes são mostrados
              separadamente. Compras no cartão saem da conta quando a fatura é
              paga.
            </p>
            <h3>Investimentos</h3>
            <p>
              Aporte não é gasto. Resgate não é receita comum. O rendimento só
              aparece quando for possível apurá-lo.
            </p>
          </div>
        </Sheet>
      )}
    </>
  );
}

function Invest() {
  const { state, month, openQuick, openAdvanced } = useDemo();
  const t = totals(monthEntries(state, month));
  return (
    <>
      <p className="page-intro">Seu dinheiro guardado, em um só lugar.</p>
      <section className="investment-hero">
        <span className="metric-label">Quanto tenho guardado hoje</span>
        <strong className="hero-number">{money(invested(state))}</strong>
        <p className="balance-date">Saldos conhecidos de 17 e 18/10/2026</p>
        <div className="investment-actions">
          <button
            className="primary-button"
            onClick={() => openQuick("contribution")}
          >
            <Icon name="plus" size={17} />
            Aportar
          </button>
          <button
            className="soft-button"
            onClick={() => openQuick("redemption")}
          >
            Resgatar
            <Icon name="arrow" size={16} />
          </button>
        </div>
      </section>
      <SectionHeading title="Onde está guardado" />
      {state.assets
        .filter((a) => !a.stale)
        .map((a) => (
          <div className="asset-row" key={a.name}>
            <span className="asset-mark">
              <Icon name="invest" />
            </span>
            <div>
              <h3>{a.name}</h3>
              <p>
                Saldo de {day(a.observed)}
                {state.entries.some((e) => e.afterBalance && e.asset === a.name)
                  ? " + movimentações registradas"
                  : ""}
              </p>
            </div>
            <strong>{money(assetBalance(state, a.name))}</strong>
          </div>
        ))}
      <details className="stale-assets">
        <summary>1 investimento com saldo antigo · fora do total</summary>
        {state.assets
          .filter((a) => a.stale)
          .map((a) => (
            <div className="entry-row" key={a.name}>
              <div>
                <h3>{a.name}</h3>
                <p className="attention">
                  Último saldo em {day(a.observed)} · desatualizado
                </p>
              </div>
              <strong>{money(a.value)}</strong>
            </div>
          ))}
        <p className="quiet-note">
          Atualize o saldo no patrimônio completo para incluir um valor
          conhecido neste mês.
        </p>
      </details>
      <SectionHeading title={`Movimentações de ${monthLabel(month)}`} />
      <Summary
        items={[
          { label: "Aportado", value: t.contributed },
          { label: "Resgatado", value: t.redeemed },
          { label: "Rendimento", value: null },
        ]}
      />
      <p className="quiet-note">
        Rendimento não apurado: falta uma base conciliada para comparar os
        saldos, descontando aportes e resgates.
      </p>
      <section className="investment-history">
        {monthEntries(state, month)
          .filter((e) => e.kind === "contribution" || e.kind === "redemption")
          .map((e) => (
            <EntryRow key={e.id} entry={e} />
          ))}
      </section>
      <div className="secondary-link">
        <div>
          <h3>Patrimônio completo</h3>
          <p>Outros ativos, histórico e atualização de saldos.</p>
        </div>
        <LinkButton onClick={openAdvanced}>Acessar</LinkButton>
      </div>
    </>
  );
}
function Cards() {
  const { state, month } = useDemo();
  const [detail, setDetail] = useState(false);
  const pending = monthEntries(state, month).filter(
    (e) => e.kind === "invoice" && e.status === "planned",
  );
  const paid = monthEntries(state, month).filter(
    (e) => e.kind === "invoice" && e.status === "done",
  );
  const nextMonths = [1, 2, 3].map((n) => shiftMonth(month, n));
  return (
    <>
      <p className="page-intro">
        O que pagar agora e o que já está comprometido.
      </p>
      <button className="invoice-card" onClick={() => setDetail(true)}>
        <span className="card-visual">
          <Icon name="card" size={26} />
          <span>nu</span>
        </span>
        <div>
          <h2>Nubank Pessoal</h2>
          <p>Fatura de {monthLabel(month)}</p>
          <strong className="forecast-number">{money(sum(pending))}</strong>
          <small>
            {pending.length
              ? "Pendente · vence dia 02"
              : `${money(sum(paid))} pago · nenhuma pendência registrada`}
          </small>
        </div>
        <Icon name="right" />
      </button>
      <SectionHeading title="Próximas faturas" />
      <dl className="calculation">
        {nextMonths.map((ym) => (
          <div key={ym}>
            <dt>{monthLabel(ym, true)}</dt>
            <dd>
              {money(
                sum(
                  monthEntries(state, ym).filter(
                    (e) => e.kind === "invoice" && e.status === "planned",
                  ),
                ),
              )}
            </dd>
          </div>
        ))}
      </dl>
      <p className="quiet-note">
        Valores conhecidos. Novas compras podem alterar as próximas faturas. O
        financiamento é um compromisso separado em Meu mês.
      </p>
      {detail && (
        <Sheet
          title={`Nubank · ${monthLabel(month)}`}
          close={() => setDetail(false)}
        >
          <Summary
            items={[
              { label: "Pendente", value: sum(pending) },
              { label: "Pago", value: sum(paid) },
            ]}
          />
          {[...pending, ...paid].map((e) => (
            <EntryRow entry={e} key={e.id} />
          ))}
          <p className="quiet-note">
            Pagamento, baixa parcial e reconciliação continuarão no fluxo atual.
            Não há pagamentos reais neste protótipo.
          </p>
        </Sheet>
      )}
    </>
  );
}
function AccountSheet({ close }: { close: () => void }) {
  const { state } = useDemo();
  return (
    <Sheet title="Contas e saldos" close={close}>
      <p className="sheet-intro">
        Dinheiro líquido conhecido. Investimentos ficam separados.
      </p>
      {state.accounts.map((a) => (
        <div className="entry-row" key={a.name}>
          <div>
            <h3>{a.name}</h3>
            <p className={a.stale ? "attention" : "muted"}>
              {a.stale ? "Desatualizado · " : "Saldo observado em "}
              {day(a.observed)}
              {state.entries.some((e) => e.afterBalance && e.account === a.name)
                ? " + movimentações"
                : ""}
            </p>
          </div>
          <strong>{money(accountBalance(state, a.name))}</strong>
        </div>
      ))}
      <dl className="calculation">
        <div className="calculation-total">
          <dt>Dinheiro conhecido</dt>
          <dd>{money(knownBalance(state))}</dd>
        </div>
      </dl>
      <p className="quiet-note">
        Nenhum saldo agregado é dividido por banco automaticamente. Na
        integração, contas sem saldo e valores a distribuir terão aviso próprio.
      </p>
    </Sheet>
  );
}
function AdvancedSheet({ close }: { close: () => void }) {
  const { openAccounts } = useDemo();
  const navigate = useNavigate();
  const [selected, setSelected] = useState("");
  return (
    <Sheet title="Configurações e mais" close={close}>
      <p className="sheet-intro">
        As ferramentas completas continuam acessíveis, por assunto.
      </p>
      {[
        {
          title: "Financeiro",
          items: [
            "Contas e saldos",
            "Cartões e faturas",
            "Categorias",
            "Recorrências",
            "Patrimônio completo",
            "Orçamento por categoria",
          ],
        },
        {
          title: "Dados",
          items: ["Conferir mês", "Histórico completo", "Simulações salvas"],
        },
        { title: "Conta", items: ["Perfil"] },
      ].map((group) => (
        <section className="settings-group" key={group.title}>
          <h3>{group.title}</h3>
          {group.items.map((item) => (
            <button
              key={item}
              onClick={() => {
                if (item === "Contas e saldos") {
                  close();
                  openAccounts();
                } else if (item === "Cartões e faturas") {
                  close();
                  navigate("/cartoes");
                } else setSelected(item);
              }}
            >
              {item}
              <Icon name="right" size={16} />
            </button>
          ))}
        </section>
      ))}
      {selected && (
        <p className="advanced-notice" role="status">
          <b>{selected}</b>
          <br />
          Esta função está preservada na aplicação atual. Sua integração com a
          nova navegação é a próxima fase; não foi recriada nesta demonstração.
        </p>
      )}
    </Sheet>
  );
}
function MissingPage() {
  const navigate = useNavigate();
  return (
    <div className="empty-state">
      <h2>Esta página não faz parte do protótipo</h2>
      <button className="primary-button" onClick={() => navigate("/")}>
        Ir para Meu mês
      </button>
    </div>
  );
}

function Sheet({
  title,
  close,
  children,
  footer,
}: {
  title: string;
  close: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const closeRef = useRef(close);
  closeRef.current = close;
  useEffect(() => {
    const dialog = ref.current!;
    const previous = document.activeElement as HTMLElement | null;
    dialog.showModal();
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      dialog.close();
      document.body.style.overflow = oldOverflow;
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="sheet"
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault();
        closeRef.current();
      }}
      onClick={(e) => {
        if (e.target === ref.current) {
          const rect = ref.current.getBoundingClientRect();
          if (
            e.clientX < rect.left ||
            e.clientX > rect.right ||
            e.clientY < rect.top ||
            e.clientY > rect.bottom
          )
            closeRef.current();
        }
      }}
    >
      <div className="sheet-handle" aria-hidden="true" />
      <header className="sheet-header">
        <h2>{title}</h2>
        <button
          className="icon-button"
          type="button"
          aria-label="Fechar"
          onClick={close}
        >
          <Icon name="close" />
        </button>
      </header>
      <div className="sheet-body">{children}</div>
      {footer && <footer className="sheet-footer">{footer}</footer>}
    </dialog>
  );
}
function QuickSheet({
  initialKind,
  lastAccount,
  close,
  saved,
}: {
  initialKind: QuickInput["kind"];
  lastAccount: string;
  close: () => void;
  saved: (input: QuickInput) => void;
}) {
  const { state } = useDemo();
  const [kind, setKind] = useState(initialKind);
  const [value, setValue] = useState("");
  const [account, setAccount] = useState(
    state.accounts.some((a) => a.name === lastAccount) ? lastAccount : "",
  );
  const [card, setCard] = useState("");
  const [category, setCategory] = useState("");
  const [asset, setAsset] = useState(
    state.assets.find((a) => !a.stale)?.name ?? "",
  );
  const [description, setDescription] = useState("");
  const [date, setDate] = useState(TODAY);
  const [installments, setInstallments] = useState(1);
  const [expenseClass, setExpenseClass] = useState<ExpenseClass>("variable");
  const [purpose, setPurpose] = useState<Purpose>("Pessoal");
  const [error, setError] = useState("");
  const amountRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    amountRef.current?.focus();
  }, []);
  const investment = kind === "contribution" || kind === "redemption";
  const categories =
    kind === "income"
      ? ["Salário", "Outras entradas"]
      : ["Alimentação", "Transporte", "Casa", "Saúde", "Compras", "Outros"];
  const amount = parseAmount(value);
  const insufficient =
    kind === "redemption" &&
    amount != null &&
    amount > assetBalance(state, asset);
  const valid =
    amount != null &&
    (card || account) &&
    (investment ? asset : category) &&
    !insufficient;
  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!valid || amount == null) {
      setError(
        insufficient
          ? "O resgate ultrapassa o saldo conhecido deste investimento."
          : "Confira o valor, a conta e a categoria.",
      );
      return;
    }
    saved({
      amount,
      kind,
      account,
      category: investment ? "Investimentos" : category,
      description:
        description ||
        (investment
          ? kind === "contribution"
            ? `Aporte · ${asset}`
            : `Resgate · ${asset}`
          : category),
      date,
      card: kind === "expense" ? card : "",
      installments,
      asset,
      expenseClass,
      purpose,
    });
  }
  return (
    <Sheet
      title="Novo lançamento"
      close={close}
      footer={
        <>
          <span>Somente nesta demonstração</span>
          <button
            form="quick-form"
            type="submit"
            className="primary-button"
            disabled={!valid}
          >
            Salvar
            <Icon name="check" size={17} />
          </button>
        </>
      }
    >
      <form id="quick-form" onSubmit={submit}>
        <label className="amount-field" htmlFor="quick-amount">
          Valor
          <span>
            <span>R$</span>
            <input
              ref={amountRef}
              id="quick-amount"
              inputMode="decimal"
              autoComplete="off"
              placeholder="0,00"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              aria-describedby="amount-help"
              required
            />
          </span>
        </label>
        <small id="amount-help" className="amount-help">
          Use vírgula para os centavos.
        </small>
        <div className="segments quick-kinds" aria-label="Tipo de lançamento">
          {(
            [
              { kind: "expense", label: "Despesa" },
              { kind: "income", label: "Entrada" },
              { kind: "contribution", label: "Aporte" },
              { kind: "redemption", label: "Resgate" },
            ] as const
          ).map((t) => (
            <button
              type="button"
              key={t.kind}
              aria-pressed={kind === t.kind}
              className={kind === t.kind ? "selected" : ""}
              onClick={() => {
                setKind(t.kind);
                setCategory("");
                setCard("");
              }}
            >
              {t.label}
            </button>
          ))}
        </div>
        <label className="field">
          {investment
            ? kind === "contribution"
              ? "De qual conta sai?"
              : "Em qual conta entra?"
            : kind === "income"
              ? "Receber em"
              : "Conta ou cartão"}
          <select
            value={card ? "card" : account}
            required
            onChange={(e) => {
              if (e.target.value === "card") setCard("Nubank Pessoal");
              else {
                setCard("");
                setAccount(e.target.value);
              }
            }}
          >
            <option value="" disabled>
              Selecione uma conta
            </option>
            {state.accounts.map((a) => (
              <option value={a.name} key={a.name}>
                {a.name}
              </option>
            ))}
            {kind === "expense" && (
              <option value="card">Cartão · Nubank Pessoal</option>
            )}
          </select>
        </label>
        {investment ? (
          <label className="field">
            Investimento
            <select
              value={asset}
              onChange={(e) => setAsset(e.target.value)}
              required
            >
              {state.assets
                .filter((a) => !a.stale)
                .map((a) => (
                  <option key={a.name}>{a.name}</option>
                ))}
            </select>
          </label>
        ) : (
          <label className="field">
            Categoria
            <select
              value={category}
              required
              onChange={(e) => setCategory(e.target.value)}
            >
              <option value="" disabled>
                Selecione uma categoria
              </option>
              {categories.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
        )}
        {kind === "expense" && !category && (
          <div
            className="category-shortcuts"
            aria-label="Categorias frequentes"
          >
            {["Alimentação", "Transporte", "Outros"].map((c) => (
              <button
                className="soft-button"
                type="button"
                key={c}
                onClick={() => setCategory(c)}
              >
                {c}
              </button>
            ))}
          </div>
        )}
        {card && (
          <>
            <label className="field">
              Parcelas
              <select
                value={installments}
                onChange={(e) => setInstallments(Number(e.target.value))}
              >
                {[1, 2, 3, 4, 5, 6, 8, 10, 12, 24].map((n) => (
                  <option key={n} value={n}>
                    {n === 1 ? "À vista no cartão" : `${n} parcelas`}
                  </option>
                ))}
              </select>
            </label>
            <p className="quiet-note">
              Prévia demonstrativa: compra por competência, sem saída imediata
              da conta. A fatura é prevista para o mês seguinte. Na integração,
              vale a regra do cartão cadastrado.
            </p>
          </>
        )}
        <details className="more-fields">
          <summary>
            Mais detalhes <span>Descrição, data e organização</span>
          </summary>
          <label className="field">
            Descrição <small>opcional</small>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={category || "Ex.: Almoço"}
            />
          </label>
          <label className="field">
            Data
            <input
              type="date"
              value={date}
              min={TODAY}
              max={TODAY}
              onChange={(e) => setDate(e.target.value)}
            />
            <small>
              O protótipo registra no dia demonstrado. O histórico será tratado
              pela API existente.
            </small>
          </label>
          {kind === "expense" && (
            <>
              <label className="field">
                Organizar como
                <select
                  value={expenseClass}
                  onChange={(e) =>
                    setExpenseClass(e.target.value as ExpenseClass)
                  }
                >
                  <option value="variable">Despesa variável</option>
                  <option value="fixed">Despesa fixa</option>
                </select>
              </label>
              <label className="field">
                Finalidade
                <select
                  value={purpose}
                  onChange={(e) => setPurpose(e.target.value as Purpose)}
                >
                  {["Pessoal", "Família", "Empresa"].map((p) => (
                    <option key={p}>{p}</option>
                  ))}
                </select>
              </label>
            </>
          )}
        </details>
        {insufficient && (
          <p className="attention" role="alert">
            O valor supera o saldo conhecido deste investimento.
          </p>
        )}
        {error && (
          <p className="attention" role="alert">
            {error}
          </p>
        )}
      </form>
    </Sheet>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <HashRouter>
      <App />
    </HashRouter>
  </React.StrictMode>,
);
