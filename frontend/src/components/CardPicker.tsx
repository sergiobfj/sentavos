import { Link } from "react-router-dom";
import { FINALIDADE_LABEL, type Card } from "../lib/types";

/** Escolha do cartão: botões lado a lado, não uma folha.
 *
 * O `CategoryPicker` abre folha porque são 23 categorias e a cor é o que o olho
 * acha antes de ler. Cartão é outra coisa: são um ou dois, têm nome curto e
 * nenhuma cor própria. Uma folha aqui seria um toque a mais pra escolher entre
 * duas opções que já cabem na largura da tela.
 */
export default function CardPicker({
  cards,
  valor,
  aoEscolher,
}: {
  cards: Card[];
  valor: number | null;
  aoEscolher: (id: number) => void;
}) {
  const ativos = cards.filter((c) => !c.archived);

  if (ativos.length === 0) {
    return (
      <div className="hint" style={{ display: "grid", gap: "var(--s3)" }}>
        <span>Nenhum cartão cadastrado ainda.</span>
        <Link className="btn btn-sm" to="/configuracoes">
          Cadastrar cartão
        </Link>
      </div>
    );
  }

  return (
    <div className="chip-grid" role="group" aria-label="Cartão">
      {ativos.map((c) => (
        <button
          type="button"
          key={c.id}
          className={c.id === valor ? "on" : ""}
          onClick={() => aoEscolher(c.id)}
          aria-pressed={c.id === valor}
        >
          <b>{c.name}</b>
          <span>
            {c.finalidade ? `${FINALIDADE_LABEL[c.finalidade]} · ` : ""}fecha {c.closing_day}, vence {c.due_day}
          </span>
        </button>
      ))}
    </div>
  );
}
