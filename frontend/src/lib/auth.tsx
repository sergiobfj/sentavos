import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
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
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  useEffect(() => {
    setSessao(carregarSessao());
    setLoading(false);
  }, []);

  // Sair é três coisas, e as três importam:
  //
  //  1. o token some do navegador — sem ele nenhuma chamada passa na API;
  //  2. o cache do React Query é esvaziado. Sem isso, os números da conta que
  //     saiu continuariam na memória, e quem entrasse em seguida no mesmo
  //     aparelho veria o saldo dos outros por um instante, até cada tela
  //     recarregar. `cancelQueries` antes, pra uma resposta ainda em voo não
  //     repovoar o cache depois do `clear`;
  //  3. a URL volta pro início, com `replace`: quem entrar de novo começa pelo
  //     Início, e não em Configurações, onde a outra pessoa estava.
  //
  // Não há chamada ao servidor: o JWT não tem estado lá. Invalidar todos os
  // tokens de uma vez continua sendo o SENTAVOS_TOKEN_EPOCH.
  const sair = useCallback(() => {
    limparSessao();
    queryClient.cancelQueries();
    queryClient.clear();
    setSessao(null);
    navigate("/", { replace: true });
  }, [queryClient, navigate]);

  // Cobre dois casos: a API derrubando a sessão (401) e o logout feito em outra
  // aba, que dispara "storage" só nas outras abas — que é exatamente o que se
  // quer, já que a aba que deslogou já se atualizou sozinha.
  useEffect(() => {
    const aoExpirar = () => sair();
    // Logout feito em outra aba: esta também esvazia o cache.
    const aoMudarStorage = () => {
      const atual = carregarSessao();
      if (!atual) queryClient.clear();
      setSessao(atual);
    };

    window.addEventListener(EVENTO_SESSAO_EXPIRADA, aoExpirar);
    window.addEventListener("storage", aoMudarStorage);
    return () => {
      window.removeEventListener(EVENTO_SESSAO_EXPIRADA, aoExpirar);
      window.removeEventListener("storage", aoMudarStorage);
    };
  }, [sair, queryClient]);

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
