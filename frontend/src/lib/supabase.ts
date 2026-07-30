import { createClient } from "@supabase/supabase-js";

// O Supabase cuida de senha, sessão e refresh do token. O Sentavos só pergunta
// "quem está logado" e manda o token pra API — nada de hash de senha aqui.

const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

// A anon key é pública por design (vai no bundle do navegador). O que protege os
// dados é a validação do JWT na API, não o segredo dela.
export const supabaseConfigured = Boolean(url && anonKey);

// Os placeholders existem só pra o módulo carregar sem config: o createClient
// estoura com string vazia, e um throw aqui daria página branca no deploy. Com
// eles, o App consegue mostrar uma tela dizendo o que falta.
export const supabase = createClient(url || "https://placeholder.supabase.co", anonKey || "placeholder", {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
  },
});

// Token da sessão atual, ou null. O supabase-js guarda em memória e renova
// sozinho, então chamar isso a cada request não custa ida à rede.
export async function accessToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}
