import { useEffect } from "react";
import { currentPeriod, usePeriod } from "../lib/period";

const MESES = [
  "jan", "fev", "mar", "abr", "mai", "jun",
  "jul", "ago", "set", "out", "nov", "dez",
];

/** Folha de escolha de mês, subindo do rodapé.
 *
 * Substituiu os dois `<select>` que havia antes. Select nativo no celular abre
 * uma roleta que exige mirar num item de 20px e confirmar — três toques pra
 * trocar de mês, numa ação que é a mais frequente do app. Aqui é um toque, e
 * os alvos são botões de 44px que o polegar acerta sem olhar.
 */
export default function MonthSheet({ onFechar }: { onFechar: () => void }) {
  const { period, setPeriod, goToCurrent, isCurrent } = usePeriod();
  const agora = currentPeriod();

  // Esc fecha no desktop; no celular o toque no fundo escuro resolve.
  useEffect(() => {
    const aoTeclar = (e: KeyboardEvent) => e.key === "Escape" && onFechar();
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, [onFechar]);

  function escolher(mes: number) {
    setPeriod({ ...period, month: mes });
    onFechar();
  }

  return (
    <div className="month-sheet" onClick={onFechar} role="dialog" aria-label="Escolher mês">
      {/* stopPropagation pra tocar dentro do cartão não fechar a folha. */}
      <div className="card" onClick={(e) => e.stopPropagation()}>
        <div className="ano">
          <button
            className="icon-btn"
            onClick={() => setPeriod({ ...period, year: period.year - 1 })}
            aria-label="Ano anterior"
          >
            <Chevron dir="esq" />
          </button>
          <b className="tnum">{period.year}</b>
          <button
            className="icon-btn"
            onClick={() => setPeriod({ ...period, year: period.year + 1 })}
            aria-label="Próximo ano"
          >
            <Chevron dir="dir" />
          </button>
        </div>

        <div className="meses">
          {MESES.map((nome, i) => {
            const mes = i + 1;
            const ehAtual = period.month === mes;
            // Mês no futuro fica visível mas apagado: dá pra ir até lá lançar
            // algo previsto, e ao mesmo tempo fica claro que ainda não chegou.
            const futuro =
              period.year > agora.year ||
              (period.year === agora.year && mes > agora.month);
            return (
              <button
                key={nome}
                className={ehAtual ? "on" : ""}
                onClick={() => escolher(mes)}
                style={futuro && !ehAtual ? { opacity: 0.42 } : undefined}
                aria-current={ehAtual ? "true" : undefined}
              >
                {nome}
              </button>
            );
          })}
        </div>

        {!isCurrent && (
          <button
            className="btn btn-ghost btn-block"
            style={{ marginTop: "var(--s4)" }}
            onClick={() => {
              goToCurrent();
              onFechar();
            }}
          >
            Voltar para o mês atual
          </button>
        )}
      </div>
    </div>
  );
}

function Chevron({ dir }: { dir: "esq" | "dir" }) {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d={dir === "esq" ? "M15 5l-7 7 7 7" : "M9 5l7 7-7 7"} />
    </svg>
  );
}
