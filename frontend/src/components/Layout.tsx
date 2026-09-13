import { useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import MonthSheet from "./MonthSheet";
import { usePeriod } from "../lib/period";
import { useAuth } from "../lib/auth";
import logo from "../assets/logo.png";

// Quatro abas, não cinco. Configurações sai da barra e vira o ⚙️ do topo: é a
// tela que se abre uma vez por mês, e ocupar um quarto da faixa do polegar com
// ela tiraria espaço das quatro que se usam todo dia.
const ABAS = [
  { to: "/", label: "Início", end: true, icon: IconCasa },
  { to: "/orcamento", label: "Orçamento", icon: IconAlvo },
  { to: "/patrimonio", label: "Patrimônio", icon: IconCarteira },
  { to: "/investimentos", label: "Investir", icon: IconGrafico },
];

export default function Layout() {
  const { label, isCurrent } = usePeriod();
  const { sessao, sair } = useAuth();
  const [escolhendoMes, setEscolhendoMes] = useState(false);
  const navigate = useNavigate();
  const { pathname } = useLocation();

  // O botão de novo lançamento não aparece onde ele não faria nada: em
  // Configurações não há o que lançar, e em Patrimônio o que se registra é
  // saldo, que tem fluxo próprio na tela.
  // A conta de demonstração não escreve, então o botão de novo lançamento não
  // aparece pra ela: oferecer uma ação que só pode terminar em erro é pior do
  // que não oferecer.
  const mostrarFab =
    !sessao?.somenteLeitura &&
    (pathname === "/" || pathname.startsWith("/orcamento"));

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
            <NavLink key={to} to={to} end={end}>
              <Icon /> {label}
            </NavLink>
          ))}
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
          <button
            className="month-btn"
            onClick={() => setEscolhendoMes(true)}
            aria-expanded={escolhendoMes}
            aria-label={`Mês: ${label}. Tocar para trocar.`}
          >
            <span style={{ textTransform: "capitalize" }}>{label}</span>
            <span className="chev" aria-hidden>▼</span>
            {isCurrent && <span className="hoje">hoje</span>}
          </button>

          <button
            className="icon-btn"
            onClick={() => navigate("/configuracoes")}
            aria-label="Configurações"
          >
            <IconEngrenagem />
          </button>
        </header>

        <main className="main">
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
          onClick={() => navigate("/orcamento?aba=lancamentos&novo=1")}
          aria-label="Novo lançamento"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeLinecap="round">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </button>
      )}

      <nav className="tabbar" aria-label="Navegação principal">
        {ABAS.map(({ to, label, end, icon: Icon }) => (
          <NavLink key={to} to={to} end={end}>
            <Icon />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      {escolhendoMes && <MonthSheet onFechar={() => setEscolhendoMes(false)} />}
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
function IconAlvo() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="4.6" />
      <circle cx="12" cy="12" r="1.2" fill="currentColor" />
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
function IconEngrenagem() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3.2" />
      <path d="M19.1 14.9a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.11-1.56 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.56-1.11 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34H9a1.7 1.7 0 0 0 1.03-1.56V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87V9a1.7 1.7 0 0 0 1.56 1.03H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.56 1.03z" />
    </svg>
  );
}
