import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Budget from "./pages/Budget";
import Investments from "./pages/Investments";
import Assets from "./pages/Assets";
import Settings from "./pages/Settings";

export default function App() {
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
