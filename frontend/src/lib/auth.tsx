import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { carregarSessao, guardarSessao, limparSessao, type Sessao } from "./session";

interface AuthValue {
  sessao: Sessao | null;
  // Enquanto true, ainda não se sabe se há sessão salva — mostrar login aqui
  // faria a tela piscar em todo F5 de quem já está logado.
  loading: boolean;
  entrar: (token: string) => void;
  sair: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

// Quando a API recusa o token no meio do uso, o api.ts avisa por aqui. É um
// evento do navegador em vez de import direto porque o caminho contrário
// (api.ts importando o contexto do React) criaria ciclo entre os dois módulos.
export const EVENTO_SESSAO_EXPIRADA = "sentavos:sessao-expirada";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [sessao, setSessao] = useState<Sessao | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setSessao(carregarSessao());
    setLoading(false);
  }, []);

  const sair = useCallback(() => {
    limparSessao();
    setSessao(null);
  }, []);

  // Cobre dois casos: a API derrubando a sessão (401) e o logout feito em outra
  // aba, que dispara "storage" só nas outras abas — que é exatamente o que se
  // quer, já que a aba que deslogou já se atualizou sozinha.
  useEffect(() => {
    const aoExpirar = () => sair();
    const aoMudarStorage = () => setSessao(carregarSessao());

    window.addEventListener(EVENTO_SESSAO_EXPIRADA, aoExpirar);
    window.addEventListener("storage", aoMudarStorage);
    return () => {
      window.removeEventListener(EVENTO_SESSAO_EXPIRADA, aoExpirar);
      window.removeEventListener("storage", aoMudarStorage);
    };
  }, [sair]);

  const entrar = useCallback((token: string) => {
    setSessao(guardarSessao(token));
  }, []);

  return (
    <AuthContext.Provider value={{ sessao, loading, entrar, sair }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth precisa estar dentro de <AuthProvider>");
  return ctx;
}
