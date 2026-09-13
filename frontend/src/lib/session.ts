// Guarda o token de acesso no navegador. Substituiu o cliente do Supabase.
//
// O token fica em localStorage, e não em cookie httpOnly, por uma razão prática:
// o front mora na Vercel e a API no Railway, domínios diferentes. Cookie entre
// domínios distintos exige SameSite=None, e o Safari do iPhone bloqueia isso com
// força — quebraria exatamente o caso de uso que motivou tudo, que é abrir o app
// no celular. Com Bearer no cabeçalho, não existe esse problema.
//
// A troca é que um XSS conseguiria ler o token. O que reduz esse risco aqui: a
// CSP do vercel.json não deixa carregar script de fora nem inline, e o app não
// renderiza HTML de terceiros em lugar nenhum.

const CHAVE = "sentavos:token";

export interface Sessao {
  token: string;
  email: string;
  nome: string;
  // Conta de demonstração: navega mas não altera. Serve só pra esconder botão
  // que daria erro — quem barra de verdade é a API, que não confia no cliente.
  somenteLeitura: boolean;
  // Segundos desde a época, como vem no JWT.
  expiraEm: number;
}

function decodificarPayload(token: string): Record<string, unknown> | null {
  try {
    const meio = token.split(".")[1];
    if (!meio) return null;
    // O JWT usa base64url; o atob quer base64 comum.
    const base64 = meio.replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(base64));
  } catch {
    return null;
  }
}

/** Lê o token guardado, ou null se não houver, estiver corrompido ou vencido. */
export function carregarSessao(): Sessao | null {
  let token: string | null = null;
  try {
    token = localStorage.getItem(CHAVE);
  } catch {
    // Navegador em modo restrito pode bloquear o acesso; tratar como sem sessão.
    return null;
  }
  if (!token) return null;

  const payload = decodificarPayload(token);
  const exp = typeof payload?.exp === "number" ? payload.exp : 0;
  // O sub virou o id da conta quando o app deixou de ter um usuário só; o
  // e-mail passou a vir num campo próprio.
  const email = typeof payload?.email === "string" ? payload.email : "";
  const nome = typeof payload?.nome === "string" ? payload.nome : email;
  const somenteLeitura = payload?.ro === true;

  // A checagem de validade aqui é conveniência, não segurança: ela evita mandar
  // um token obviamente vencido e levar 401 de volta. Quem decide de verdade é a
  // API, que verifica a assinatura — este lado só lê o conteúdo, sem validar.
  if (!exp || !email || exp * 1000 <= Date.now()) {
    limparSessao();
    return null;
  }

  return { token, email, nome, somenteLeitura, expiraEm: exp };
}

export function guardarSessao(token: string): Sessao | null {
  try {
    localStorage.setItem(CHAVE, token);
  } catch {
    /* sem localStorage, a sessão dura só enquanto a aba estiver aberta */
  }
  return carregarSessao();
}

export function limparSessao(): void {
  try {
    localStorage.removeItem(CHAVE);
  } catch {
    /* nada a fazer */
  }
}
