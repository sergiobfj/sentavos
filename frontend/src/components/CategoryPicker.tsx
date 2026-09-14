import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { Category, CategoryType } from "../lib/types";

/** Escolha de categoria: um botão que abre uma folha com as opções em grade.
 *
 * Substituiu o `<select>` nativo. No celular ele abre uma roleta de texto puro,
 * onde 28 categorias viram 28 linhas iguais e achar "Mercado" é rolar até
 * encontrar. Aqui cada uma aparece com o ícone e a cor que você deu pra ela —
 * e a cor é justamente o que o olho acha antes de ler.
 *
 * A lista já chega filtrada pelo tipo escolhido no formulário: procurar
 * "Salário" numa lista que também tem "Aluguel" é trabalho que a tela pode
 * poupar de quem está lançando.
 */
export default function CategoryPicker({
  categories,
  tipo,
  valor,
  aoEscolher,
}: {
  categories: Category[];
  tipo: CategoryType;
  valor: number | null;
  aoEscolher: (id: number) => void;
}) {
  const [aberto, setAberto] = useState(false);
  const doTipo = categories.filter((c) => c.type === tipo && !c.archived);
  const escolhida = categories.find((c) => c.id === valor) ?? null;

  useEffect(() => {
    const aoTeclar = (e: KeyboardEvent) => e.key === "Escape" && setAberto(false);
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, []);

  return (
    <>
      <button type="button" className="cat-trigger" onClick={() => setAberto(true)}>
        {escolhida ? (
          <>
            <span
              className="avatar"
              style={{
                width: 32, height: 32, fontSize: 15,
                background: `color-mix(in srgb, ${escolhida.color} 22%, transparent)`,
              }}
            >
              {escolhida.icon}
            </span>
            <span className="nome">{escolhida.name}</span>
          </>
        ) : (
          <span className="nome vazio">
            {doTipo.length === 0 ? "Nenhuma categoria ainda" : "Escolher categoria"}
          </span>
        )}
        <span className="chev" aria-hidden>▼</span>
      </button>

      {aberto && (
        <div
          className="month-sheet"
          onClick={() => setAberto(false)}
          role="dialog"
          aria-label="Escolher categoria"
        >
          <div className="card" onClick={(e) => e.stopPropagation()}>
            <div className="ano" style={{ marginBottom: "var(--s3)" }}>
              <b>Categoria</b>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setAberto(false)}>
                Fechar
              </button>
            </div>

            {doTipo.length === 0 ? (
              <div className="empty" style={{ padding: "var(--s5) 0" }}>
                <div className="tit">Nenhuma categoria deste tipo</div>
                <div>Crie a primeira em Configurações.</div>
                <Link
                  className="btn btn-primary"
                  to="/configuracoes"
                  style={{ marginTop: "var(--s4)" }}
                  onClick={() => setAberto(false)}
                >
                  Criar categoria
                </Link>
              </div>
            ) : (
              <div className="cat-opcoes">
                {doTipo.map((c) => (
                  <button
                    type="button"
                    key={c.id}
                    className={c.id === valor ? "on" : ""}
                    onClick={() => {
                      aoEscolher(c.id);
                      setAberto(false);
                    }}
                  >
                    <span
                      className="avatar"
                      style={{ background: `color-mix(in srgb, ${c.color} 24%, transparent)` }}
                    >
                      {c.icon}
                    </span>
                    <span className="rot">{c.name}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
