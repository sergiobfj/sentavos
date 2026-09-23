import { formatMoney } from "../lib/format";

/* ===========================================================================
   Gráficos do Sentavos
   ===========================================================================

   As cores das marcas NÃO são as mesmas do texto. O app usa verde e vermelho
   vivos pra "+R$ 942" e "−R$ 120", que é a convenção de dinheiro e lê bem. Mas
   como preenchimento de barra, aquele par reprovou na verificação de daltonismo
   (ΔE 5,5 em deuteranopia — abaixo do piso de 6). Quem não distingue verde de
   vermelho veria duas barras da mesma cor.

   As marcas usam um trio validado contra a superfície escura: aqua, laranja e
   azul, com pior par ΔE 9,4 — acima da meta de 8. Texto segue com as cores
   vivas, porque ali o sinal (+/−) e a palavra já carregam o significado.

   Toda série também vem com rótulo direto, então a cor nunca é a única pista.
   =========================================================================== */

export const VIZ = {
  entrou: "#199e70",
  saiu: "#d95926",
  investido: "#3987e5",
} as const;

/** Barras pareadas: previsto ao lado de pago, por categoria.
 *
 * Duas barras finas e não uma barra com marcador: o marcador ("bullet") mostra
 * bem "cheguei em X% da meta", mas some quando o previsto é zero — e aqui
 * lançamento sem previsto é comum. Duas barras sempre dizem a verdade, mesmo
 * quando uma delas é zero.
 */
export function PrevistoVsPago({
  linhas,
  limite = 6,
}: {
  linhas: { id: number; nome: string; previsto: number; pago: number }[];
  limite?: number;
}) {
  const visiveis = linhas
    .filter((l) => l.previsto > 0 || l.pago > 0)
    .sort((a, b) => Math.max(b.previsto, b.pago) - Math.max(a.previsto, a.pago))
    .slice(0, limite);

  if (visiveis.length === 0) return null;

  // Uma escala só pra todas as linhas: escalar cada uma pelo próprio máximo
  // faria uma categoria de R$ 50 desenhar a mesma barra de uma de R$ 2.000.
  const max = Math.max(...visiveis.flatMap((l) => [l.previsto, l.pago]), 1);

  return (
    <div className="viz">
      <div className="viz-legenda">
        <span><i style={{ background: "var(--surface-3)" }} />Previsto</span>
        <span><i style={{ background: VIZ.saiu }} />Pago</span>
      </div>

      {visiveis.map((l) => {
        const estourou = l.previsto > 0 && l.pago > l.previsto;
        return (
          <div className="viz-linha" key={l.id}>
            <div className="viz-rot">
              <span className="nome">{l.nome}</span>
              <span className="val tnum">
                {formatMoney(l.pago)}
                <span className="de"> de {formatMoney(l.previsto)}</span>
              </span>
            </div>

            <div className="viz-par">
              <div
                className="viz-barra"
                style={{ width: `${(l.previsto / max) * 100}%`, background: "var(--surface-3)" }}
                title={`Previsto: ${formatMoney(l.previsto)}`}
              />
              <div
                className="viz-barra"
                style={{
                  width: `${(l.pago / max) * 100}%`,
                  // Estourar o previsto é o que se quer notar de relance, então
                  // ganha cor própria em vez de só um número diferente.
                  background: estourou ? "var(--neg)" : VIZ.saiu,
                }}
                title={`Pago: ${formatMoney(l.pago)}`}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** Barras horizontais por categoria, cada uma na cor que o dono deu pra ela.
 *
 * Aqui a cor vem do usuário e não dá pra validar contra daltonismo — por isso
 * cada barra carrega o nome ao lado. O rótulo direto é o que torna a cor
 * dispensável pra entender o gráfico.
 */
export function PorCategoria({
  linhas,
  limite = 5,
}: {
  linhas: { id: number; nome: string; icone: string; cor: string; valor: number }[];
  limite?: number;
}) {
  const visiveis = linhas
    .filter((l) => l.valor > 0)
    .sort((a, b) => b.valor - a.valor)
    .slice(0, limite);

  if (visiveis.length === 0) return null;
  const max = visiveis[0].valor;
  const total = visiveis.reduce((s, l) => s + l.valor, 0);

  return (
    <div className="viz">
      {visiveis.map((l) => (
        <div className="viz-linha" key={l.id}>
          <div className="viz-rot">
            <span className="nome">{l.icone} {l.nome}</span>
            <span className="val tnum">
              {formatMoney(l.valor)}
              <span className="de"> · {Math.round((l.valor / total) * 100)}%</span>
            </span>
          </div>
          <div className="viz-par">
            <div
              className="viz-barra alta"
              style={{ width: `${Math.max((l.valor / max) * 100, 2)}%`, background: l.cor }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

/** Uma faixa só com entrou, saiu e investido, na proporção do mês.
 *
 * Substitui três gráficos separados. A pergunta que ela responde — "o que
 * entrou cobriu o que saiu?" — se lê melhor com as três partes lado a lado do
 * que com três desenhos que obrigam a comparar de cabeça.
 */
export function Fluxo({
  entrou,
  saiu,
  investido,
}: {
  entrou: number;
  saiu: number;
  investido: number;
}) {
  const total = entrou + saiu + investido;
  if (total <= 0) return null;

  const partes = [
    { rot: "Entrou", valor: entrou, cor: VIZ.entrou },
    // "Gastou" e não "Saiu": com cartão, o que se gastou e o que saiu da conta
    // deixaram de ser o mesmo número, e esta faixa mostra o do gasto. O cartão
    // de cima usa a mesma palavra — duas palavras pro mesmo número fariam
    // parecer que são dois.
    { rot: "Gastou", valor: saiu, cor: VIZ.saiu },
    { rot: "Investido", valor: investido, cor: VIZ.investido },
  ].filter((p) => p.valor > 0);

  return (
    <div className="viz">
      <div className="seg" style={{ height: 14 }}>
        {partes.map((p) => (
          <div
            key={p.rot}
            style={{ width: `${(p.valor / total) * 100}%`, background: p.cor }}
            title={`${p.rot}: ${formatMoney(p.valor)}`}
          />
        ))}
      </div>
      <div className="viz-legenda" style={{ marginTop: "var(--s3)" }}>
        {partes.map((p) => (
          <span key={p.rot}>
            <i style={{ background: p.cor }} />
            {p.rot} <b className="tnum">{formatMoney(p.valor)}</b>
          </span>
        ))}
      </div>
    </div>
  );
}
