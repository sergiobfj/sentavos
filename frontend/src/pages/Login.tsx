import { useState } from "react";
import { supabase } from "../lib/supabase";
import logo from "../assets/logo.png";

export default function Login() {
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [entrando, setEntrando] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    setEntrando(true);

    const { error } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password: senha,
    });

    // Não distingue "e-mail não existe" de "senha errada" — é o que o Supabase
    // devolve, e detalhar ajudaria quem está testando e-mails.
    if (error) {
      setErro(
        error.message === "Invalid login credentials"
          ? "E-mail ou senha incorretos."
          : error.message
      );
      setEntrando(false);
      return;
    }
    // Sessão pronta: o AuthProvider troca a tela sozinho, sem setState aqui
    // (o componente já vai ter saído da árvore).
  }

  return (
    <div className="login-shell">
      <form className="login-card" onSubmit={submit}>
        <div className="brand" style={{ justifyContent: "center", marginBottom: 6 }}>
          <img src={logo} alt="Sentavos" />
          <span className="name"><b>s</b>entavos</span>
        </div>
        <p className="login-tag">Cada centavo no seu lugar.</p>

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
