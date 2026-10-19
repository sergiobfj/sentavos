import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import MonthSheet from "./MonthSheet";
import QuickTransaction, { SAVED_EVENT } from "./essencial/QuickTransaction";
import { useCategories } from "../lib/queries";
import { usePeriod } from "../lib/period";
import { useAuth } from "../lib/auth";
import logo from "../assets/logo.png";

const ABAS = [
  { to: "/", label: "Meu mês", end: true, icon: IconCasa },
  { to: "/lancamentos", label: "Lançamentos", icon: IconLista },
  { to: "/contas-a-pagar", label: "Contas", icon: IconContas },
  { to: "/relatorios", label: "Relatórios", icon: IconGrafico },
  { to: "/investimentos", label: "Investir", icon: IconCarteira },
];

export default function Layout() {
  const { label, period, isCurrent, shift } = usePeriod();
  const { sessao, sair } = useAuth();
  const categories = useCategories(true);
  const [escolhendoMes, setEscolhendoMes] = useState(false);
  const [creating, setCreating] = useState(false);
  const [saved, setSaved] = useState(false);
  const navigate = useNavigate();
  const { pathname, search } = useLocation();

  // O botão de novo lançamento não aparece onde ele não faria nada: em
  // Configurações não há o que lançar, e em Patrimônio o que se registra é
  // saldo, que tem fluxo próprio na tela.
  // A conta de demonstração não escreve, então o botão de novo lançamento não
  // aparece pra ela: oferecer uma ação que só pode terminar em erro é pior do
  // que não oferecer.
  //
  // Em Faturas ele também sai: ali a ação é pagar a fatura, e o botão flutuante
  // cobria justamente o rodapé de total/pago/restante — visto na tela, não
  // deduzido.
  const emFaturas = new URLSearchParams(search).get("aba") === "faturas";
  const ativa = (isActive: boolean) => isActive ? "active" : "";
  const mostrarFab =
    !sessao?.somenteLeitura &&
    !emFaturas && ["/","/lancamentos"].includes(pathname);
  useEffect(() => {
    if (new URLSearchParams(search).get("novo") === "1") setCreating(true);
  }, [search]);
  useEffect(() => {
    const onSaved = () => { setSaved(true); window.setTimeout(() => setSaved(false), 2800); };
    window.addEventListener(SAVED_EVENT,onSaved);
    return () => window.removeEventListener(SAVED_EVENT,onSaved);
  }, []);
  function closeCreating() {
    setCreating(false);
    if (new URLSearchParams(search).has("novo")) navigate(`${pathname}${search.replace(/([?&])novo=1&?/,"$1").replace(/[?&]$/,"")}`,{replace:true});
  }

  return (
    <div className="app">
      {/* Só existe a partir de 900px; no celular a navegação é a pílula. */}
      <aside className="sidebar">
        <div className="brand">
          <img src={logo} alt="" />
          <span className="name"><b>s</b>entavos</span>
        </div>
        <nav className="nav">
          {ABAS.map(({ to, label, end, icon: Icon }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => ativa(isActive)}>
              <Icon /> {label}
            </NavLink>
          ))}
          <div className="e-nav-divider" />
          <NavLink to="/planejamento">Planejamento detalhado</NavLink>
          <NavLink to="/orcamento?aba=faturas">Cartões e faturas</NavLink>
          <NavLink to="/patrimonio">Patrimônio</NavLink>
          <NavLink to="/configuracoes"><IconEngrenagem /> Configurações</NavLink>
        </nav>
        <div className="foot">
          <div className="who" title={sessao?.email ?? ""}>{sessao?.email}</div>
          <button className="btn btn-ghost btn-sm" onClick={sair}>Sair</button>
        </div>
      </aside>

      <div>
        <header className="appbar">
          <img className="brand-mark" src={logo} alt="Sentavos" />

          {/* O mês é o título e o controle ao mesmo tempo. Separar os dois
              gastaria uma linha de tela pra dizer duas vezes a mesma coisa. */}
          <button className="e-month-arrow" onClick={() => shift(-1)} aria-label="Mês anterior">‹</button>
          <button
            className="month-btn"
            onClick={() => setEscolhendoMes(true)}
            aria-expanded={escolhendoMes}
            aria-label={`Mês: ${label}. Tocar para trocar.`}
          >
            <span className="e-month-full">{label.charAt(0).toUpperCase() + label.slice(1)}</span>
            <span className="e-month-short">{label.charAt(0).toUpperCase() + label.slice(1,3)} {period.year}</span>
            <span className="chev" aria-hidden>▼</span>
            {isCurrent && <span className="hoje">hoje</span>}
          </button>
          <button className="e-month-arrow" onClick={() => shift(1)} aria-label="Próximo mês">›</button>

          <button
            className="icon-btn"
            onClick={() => navigate("/configuracoes")}
            aria-label="Configurações"
          >
            <IconEngrenagem />
          </button>
        </header>

        <main className={`main${mostrarFab ? "" : " sem-fab"}`}>
          {sessao?.somenteLeitura && (
            <div className="aviso-demo">
              <b>Modo demonstração.</b> Você pode navegar por tudo, mas não
              alterar — os dados são fictícios.
            </div>
          )}
          <Outlet />
        </main>
      </div>

      {mostrarFab && (
        <button
          className="fab"
          onClick={() => setCreating(true)}
          aria-label="Novo lançamento"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeLinecap="round">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </button>
      )}

      <nav className="tabbar" aria-label="Navegação principal">
        {ABAS.map(({ to, label, end, icon: Icon }) => (
          <NavLink key={to} to={to} end={end} aria-label={label} className={({ isActive }) => ativa(isActive)}>
            <Icon />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      {escolhendoMes && <MonthSheet onFechar={() => setEscolhendoMes(false)} />}
      {creating && <QuickTransaction categories={categories.data ?? []} onClose={closeCreating}/>}
      {saved && <div className="e-toast" role="status">Lançamento salvo</div>}
    </div>
  );
}

/* Ícones em traço, 24x24, todos com o mesmo peso — misturar traço e preenchido
   faz a barra parecer montada com sobras. */

function IconCasa() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 10.2 12 3l9 7.2" />
      <path d="M5.5 9.5V20h13V9.5" />
      <path d="M9.8 20v-5.4h4.4V20" />
    </svg>
  );
}
function IconLista() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 6.5h12M8 12h12M8 17.5h12" />
      <circle cx="4" cy="6.5" r="1.3" fill="currentColor" stroke="none" />
      <circle cx="4" cy="12" r="1.3" fill="currentColor" stroke="none" />
      <circle cx="4" cy="17.5" r="1.3" fill="currentColor" stroke="none" />
    </svg>
  );
}
function IconCarteira() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 8a2 2 0 0 1 2-2h11.5a1.5 1.5 0 0 1 1.5 1.5V8" />
      <rect x="3" y="8" width="18" height="11.5" rx="2.5" />
      <circle cx="16.8" cy="13.8" r="1.15" fill="currentColor" stroke="none" />
    </svg>
  );
}
function IconGrafico() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 17.5 9 11l4 4 8-8.5" />
      <path d="M15 6.5h6v6" />
    </svg>
  );
}
function IconContas() {
  return <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>;
}
function IconEngrenagem() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3.2" />
      <path d="M19.1 14.9a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.11-1.56 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.56-1.11 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34H9a1.7 1.7 0 0 0 1.03-1.56V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87V9a1.7 1.7 0 0 0 1.56 1.03H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.56 1.03z" />
    </svg>
  );
}
