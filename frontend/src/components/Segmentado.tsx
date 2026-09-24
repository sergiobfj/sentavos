/** Controle segmentado: poucas opções fixas, todas visíveis, uma escolhida.
 *
 * Serve o filtro de finalidade, a janela de 6/12 meses e a finalidade nos
 * formulários. Um `<select>` aqui esconderia atrás de um toque uma resposta
 * que cabe inteira na largura da tela.
 */
export default function Segmentado<T extends string>({
  opcoes,
  valor,
  aoEscolher,
  rotulo,
  largo = false,
}: {
  opcoes: { valor: T; rotulo: string }[];
  valor: T | null;
  aoEscolher: (v: T) => void;
  rotulo: string;
  largo?: boolean;
}) {
  return (
    <div className={`segmented${largo ? " largo" : ""}`} role="group" aria-label={rotulo}>
      {opcoes.map((o) => (
        <button
          type="button"
          key={o.valor}
          className={o.valor === valor ? "on" : ""}
          aria-pressed={o.valor === valor}
          onClick={() => aoEscolher(o.valor)}
        >
          {o.rotulo}
        </button>
      ))}
    </div>
  );
}
