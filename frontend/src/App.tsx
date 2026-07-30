import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Budget from "./pages/Budget";
import Investments from "./pages/Investments";
import Assets from "./pages/Assets";
import Settings from "./pages/Settings";
import Login from "./pages/Login";
import { useAuth } from "./lib/auth";
import { supabaseConfigured } from "./lib/supabase";

export default function App() {
  const { session, loading } = useAuth();

  // Erra-se isso uma vez por deploy: melhor dizer o que falta do que servir uma
  // tela de login que nunca autentica.
  if (!supabaseConfigured) {
    return (
      <div className="login-shell">
        <div className="login-card">
          <h1 style={{ fontSize: 18, fontWeight: 750 }}>Configuração incompleta</h1>
          <p style={{ color: "var(--text-dim)", fontSize: 14, lineHeight: 1.6 }}>
            Faltam <code>VITE_SUPABASE_URL</code> e/ou <code>VITE_SUPABASE_ANON_KEY</code> no
            build. Elas são lidas na hora de compilar, então precisam estar no host
            <b> antes</b> do build — definir depois não resolve sem recompilar.
          </p>
          <p className="hint">Veja frontend/.env.example.</p>
        </div>
      </div>
    );
  }

  // Sem isso a tela de login pisca em todo F5 de quem já está logado, no
  // intervalo entre montar e o Supabase devolver a sessão salva.
  if (loading) {
    return (
      <div className="login-shell">
        <div className="loading"><div className="spinner" />Carregando…</div>
      </div>
    );
  }

  if (!session) return <Login />;

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/orcamento" element={<Budget />} />
        <Route path="/investimentos" element={<Investments />} />
        <Route path="/patrimonio" element={<Assets />} />
        <Route path="/configuracoes" element={<Settings />} />
        {/* Rotas antigas: Transações virou sub-aba de Orçamento e Categorias
            entrou em Configurações. Redirecionar evita quebrar link salvo. */}
        <Route path="/transacoes" element={<Navigate to="/orcamento?aba=lancamentos" replace />} />
        <Route path="/categorias" element={<Navigate to="/configuracoes" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
