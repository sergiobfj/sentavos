import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import MeuMes from "./pages/MeuMes";
import Lancamentos from "./pages/Lancamentos";
import Relatorios from "./pages/Relatorios";
import ContasAPagar from "./pages/ContasAPagar";
import Invoices from "./pages/Invoices";
import Investments from "./pages/Investments";
import Assets from "./pages/Assets";
import Settings from "./pages/Settings";
import Revisao from "./pages/Revisao";
import Planejamento from "./pages/Planejamento";
import PlanejamentoSimulacoes from "./pages/PlanejamentoSimulacoes";
import Compromissos from "./components/planejamento/Compromissos";
import Contas from "./pages/Contas";
import Organizar from "./pages/Organizar";
import Login from "./pages/Login";
import { useAuth } from "./lib/auth";

export default function App() {
  const { sessao, loading } = useAuth();

  // Erra-se isso uma vez por deploy: melhor dizer o que falta do que servir uma
  // tela de login que nunca autentica.
  if (!import.meta.env.VITE_API_URL) {
    return (
      <div className="login-shell">
        <div className="login-card">
          <h1 style={{ fontSize: 18, fontWeight: 750 }}>Configuração incompleta</h1>
          <p style={{ color: "var(--text-dim)", fontSize: 14, lineHeight: 1.6 }}>
            Falta <code>VITE_API_URL</code> no build. Ela é lida na hora de compilar,
            então precisa estar no host <b>antes</b> do build — definir depois não
            resolve sem recompilar.
          </p>
          <p className="hint">Veja frontend/.env.example.</p>
        </div>
      </div>
    );
  }

  // Sem isso a tela de login pisca em todo F5 de quem já está logado, no
  // intervalo entre montar e o token guardado ser lido.
  if (loading) {
    return (
      <div className="login-shell">
        <div className="loading"><div className="spinner" />Carregando…</div>
      </div>
    );
  }

  if (!sessao) return <Login />;

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<MeuMes />} />
        <Route path="/lancamentos" element={<Lancamentos />} />
        <Route path="/contas-a-pagar" element={<ContasAPagar />} />
        <Route path="/relatorios" element={<Relatorios />} />
        <Route path="/orcamento" element={<Navigate to="/faturas" replace />} />
        <Route path="/faturas" element={<Invoices />} />
        <Route path="/investimentos" element={<Investments />} />
        <Route path="/patrimonio" element={<Assets />} />
        <Route path="/configuracoes" element={<Settings />} />
        {/* Fora da barra de abas: é uma tarefa de mutirão, feita uma vez
            enquanto o histórico é organizado, não uma seção do app. */}
        <Route path="/rever" element={<Revisao />} />
        {/* Também fora da barra: planejar é semanal, não diário. A porta é a
            linha "Disponível" do Início e a lateral do desktop. */}
        <Route path="/planejamento" element={<Planejamento />} />
        <Route path="/planejamento/proximos" element={<Navigate to="/" replace />} />
        <Route path="/planejamento/simulacoes" element={<PlanejamentoSimulacoes />} />
        <Route path="/planejamento/compromissos" element={<Compromissos />} />
        <Route path="/organizar" element={<Organizar />} />
        <Route path="/contas" element={<Contas />} />
        {/* Rotas antigas: Transações virou sub-aba de Orçamento e Categorias
            entrou em Configurações. Redirecionar evita quebrar link salvo. */}
        <Route path="/transacoes" element={<Navigate to="/lancamentos" replace />} />
        <Route path="/investir" element={<Navigate to="/investimentos" replace />} />
        <Route path="/categorias" element={<Navigate to="/configuracoes?secao=categorias" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
