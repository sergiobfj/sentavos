import { NavLink, Outlet } from "react-router-dom";
import logo from "../assets/logo.png";

const links = [
  { to: "/", label: "Painel", end: true, icon: IconGrid },
  { to: "/transacoes", label: "Transações", icon: IconList },
  { to: "/categorias", label: "Categorias", icon: IconTag },
];

export default function Layout() {
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <img src={logo} alt="Sentavos" />
          <span className="name">
            <b>s</b>entavos
          </span>
        </div>
        <nav className="nav">
          {links.map(({ to, label, end, icon: Icon }) => (
            <NavLink key={to} to={to} end={end}>
              <Icon />
              <span className="txt">{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="foot">Cada centavo no seu lugar.</div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}

function IconGrid() {
  return (
    <svg className="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
    </svg>
  );
}
function IconList() {
  return (
    <svg className="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="8" y1="6" x2="21" y2="6" />
      <line x1="8" y1="12" x2="21" y2="12" />
      <line x1="8" y1="18" x2="21" y2="18" />
      <line x1="3" y1="6" x2="3.01" y2="6" />
      <line x1="3" y1="12" x2="3.01" y2="12" />
      <line x1="3" y1="18" x2="3.01" y2="18" />
    </svg>
  );
}
function IconTag() {
  return (
    <svg className="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20.59 13.41 13.42 20.6a2 2 0 0 1-2.83 0L3 13V3h10l7.59 7.59a2 2 0 0 1 0 2.82z" />
      <line x1="7" y1="7" x2="7.01" y2="7" />
    </svg>
  );
}
