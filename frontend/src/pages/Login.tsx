import { useEffect, useState } from "react";
import { ApiError, AVISO_LOGIN, authApi } from "../lib/api";
import { useAuth } from "../lib/auth";
import logo from "../assets/logo.png";

export default function Login() {
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [entrando, setEntrando] = useState(false);
  const { entrar } = useAuth();

  // Recado de quem foi derrubado por 401. Consumido na leitura pra não ficar
  // aparecendo em todo login seguinte.
  useEffect(() => {
    try {
      const guardado = sessionStorage.getItem(AVISO_LOGIN);
      if (guardado) {
        setAviso(guardado);
        sessionStorage.removeItem(AVISO_LOGIN);
      }
    } catch {
      /* sessionStorage pode estar bloqueado */
    }
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    setEntrando(true);

    try {
      const { access_token } = await authApi.login(email.trim(), senha);
      // O entrar() troca a tela: o AuthProvider passa a ter sessão e o App
      // renderiza o Layout no lugar deste componente. Não há setState depois
      // daqui de propósito — a esta altura ele já saiu da árvore.
      entrar(access_token);
    } catch (e) {
      // A API devolve a mesma mensagem pra e-mail errado e senha errada, e é
      // assim que deve ser: distinguir os dois entregaria quais endereços têm
      // conta. O que muda aqui é só separar "credencial errada" de "API fora
      // do ar", porque a segunda não adianta o usuário tentar de novo.
      const msg =
        e instanceof ApiError
          ? e.status === 0
            ? "Não consegui falar com o servidor. Tente de novo em instantes."
            : e.message
          : "Não consegui entrar. Tente de novo.";
      setErro(msg);
      setEntrando(false);
    }
  }

  return (
    <div className="login-shell">
      <form className="login-card" onSubmit={submit}>
        <div className="brand" style={{ justifyContent: "center", marginBottom: 6 }}>
          <img src={logo} alt="Sentavos" />
          <span className="name"><b>s</b>entavos</span>
        </div>
        <p className="login-tag">Cada centavo no seu lugar.</p>

        {aviso && (
          <div className="aviso-box">{aviso}</div>
        )}

        <div className="field">
          <label htmlFor="l-email">E-mail</label>
          <input
            id="l-email"
            type="email"
            autoComplete="username"
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="l-senha">Senha</label>
          <input
            id="l-senha"
            type="password"
            autoComplete="current-password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
          />
        </div>

        {erro && <div className="error-box" style={{ padding: 0, textAlign: "left" }}>{erro}</div>}

        <button
          type="submit"
          className="btn btn-primary"
          disabled={entrando || !email.trim() || !senha}
        >
          {entrando ? "Entrando…" : "Entrar"}
        </button>
      </form>
    </div>
  );
}
