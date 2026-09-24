/* ===========================================================================
   Paleta de dados do Sentavos
   ===========================================================================

   Cor de interface (fundo, texto, dourado da marca) mora em index.css, como
   token. Aqui mora a cor que é DADO: a de cada categoria e a das marcas dos
   gráficos. Hex e não var(--x) porque o Recharts escreve a cor como atributo
   do SVG, e atributo não resolve variável de CSS.

   ## A paleta de categorias

   Doze cores fechadas, no lugar do seletor livre. O seletor livre foi o que
   produziu 13 categorias em cinco tons de vermelho: numa rosca, isso vira uma
   mancha só.

   Validadas contra o grafite do app (#161615) com o validador de paleta:
     - luminosidade na faixa escura (OKLCH L 0,48–0,67) e croma acima do piso;
     - contraste ≥ 3:1 contra o fundo, todas;
     - vizinhas na ordem abaixo: ΔE ≥ 8,1 pra daltonismo (deutan/protan) e
       ≥ 19,3 pra visão normal.

   A ordem é o mecanismo, não enfeite: é a sequência em que as cores são
   distribuídas, e vizinhas na lista são as que mais vão aparecer lado a lado.
   Doze cores NÃO passam comparadas todas contra todas (nenhuma paleta de doze
   passa) — por isso a rosca mostra no máximo seis fatias, sempre com legenda
   de nome e emoji, e a cor nunca é a única pista.

   Nenhuma é o dourado da marca: dourado é ação e seleção, e uma fatia dourada
   pareceria botão.
   =========================================================================== */

export const PALETA_CATEGORIAS: { cor: string; nome: string }[] = [
  { cor: "#3987e5", nome: "Azul" },
  { cor: "#d95926", nome: "Laranja" },
  { cor: "#199e70", nome: "Água" },
  { cor: "#c98500", nome: "Âmbar" },
  { cor: "#d55181", nome: "Magenta" },
  { cor: "#6aa84f", nome: "Verde" },
  { cor: "#9085e9", nome: "Violeta" },
  { cor: "#e66767", nome: "Coral" },
  { cor: "#1f94ad", nome: "Petróleo" },
  { cor: "#8f9a2e", nome: "Oliva" },
  { cor: "#b066c9", nome: "Lilás" },
  { cor: "#b8703f", nome: "Caramelo" },
];

/** O resto agrupado ("Outras"). Cinza de propósito: é o que não tem identidade. */
export const COR_OUTRAS = "#5b5a56";

/** Marca das séries de gráfico que não são categoria (linha de evolução). */
export const COR_SERIE = "#3987e5";

/** Classes de patrimônio: sempre a mesma cor pra mesma classe, em qualquer mês. */
export const COR_CLASSE: Record<string, string> = {
  checking: "#3987e5",
  fixed_income: "#199e70",
  equity: "#9085e9",
  crypto: "#c98500",
  real_estate: "#b8703f",
  vehicle: "#1f94ad",
};

/** A primeira cor da paleta que nenhuma categoria usa ainda — a sugestão do
 *  formulário de categoria nova. Quando todas estão em uso, recomeça do começo. */
export function proximaCorLivre(emUso: string[]): string {
  const usadas = new Set(emUso.map((c) => c.toLowerCase()));
  return (PALETA_CATEGORIAS.find((p) => !usadas.has(p.cor)) ?? PALETA_CATEGORIAS[0]).cor;
}

export function ehCorDaPaleta(cor: string): boolean {
  return PALETA_CATEGORIAS.some((p) => p.cor === cor.toLowerCase());
}

/** Fundo translúcido da cor da categoria, pro círculo do ícone. */
export function fundoDaCor(cor: string, pct = 20): string {
  return `color-mix(in srgb, ${cor} ${pct}%, transparent)`;
}

/* ---------- Ícones de categoria ----------
   Emoji e não biblioteca de ícones: instalar uma biblioteca inteira pra 70
   desenhos pesaria mais que o app. Agrupados pelo que a pessoa procura, não
   por ordem do Unicode. */
export const EMOJIS: { grupo: string; itens: string[] }[] = [
  { grupo: "Casa", itens: ["🏠", "🔑", "💡", "🚿", "🛋️", "🧹", "🔧", "📦"] },
  { grupo: "Comida", itens: ["🛒", "🍔", "🍽️", "☕", "🥖", "🍕", "🍺", "🥗"] },
  { grupo: "Transporte", itens: ["🚗", "🚌", "⛽", "🅿️", "🚕", "✈️", "🚲", "🛵"] },
  { grupo: "Saúde", itens: ["💊", "🏥", "🦷", "🏋️", "🧘", "🩺", "💆", "🧴"] },
  { grupo: "Lazer", itens: ["⚽", "🎬", "🎮", "🎵", "📚", "🎭", "🏖️", "🎉"] },
  { grupo: "Pessoal", itens: ["👕", "👟", "👜", "✂️", "💄", "🎓", "📱", "🖥️"] },
  { grupo: "Família", itens: ["👨‍👩‍👧", "👶", "🐶", "🐱", "💝", "🎁", "🧸", "💍"] },
  { grupo: "Trabalho", itens: ["🏢", "💼", "🧾", "📊", "🖨️", "🤝", "📺", "🌐"] },
  { grupo: "Dinheiro", itens: ["💰", "💵", "🏦", "📈", "🐷", "🎯", "💳", "🪙"] },
];
