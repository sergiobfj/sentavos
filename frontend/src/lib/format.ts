import type { CategoryType } from "./types";

const brl = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

export function formatMoney(value: number | null | undefined): string {
  return brl.format(value ?? 0);
}

export function formatDate(iso: string): string {
  // iso vem como YYYY-MM-DD; evita timezone construindo local
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  return new Date(y, m - 1, d).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

// Devolve null pra campo vazio ou lixo, que os endpoints tratam como "sem valor".
export function parseMoney(value: string): number | null {
  const raw = value.trim();
  if (raw === "") return null;
  // Se tem vírgula, ela é o decimal e o ponto é milhar ("1.234,56"). Sem
  // vírgula, o ponto é o decimal ("1234.56") — é como sai do teclado numérico.
  const normalized = raw.includes(",") ? raw.replace(/\./g, "").replace(",", ".") : raw;
  const n = Number(normalized);
  return Number.isFinite(n) ? n : null;
}

// "2026-05" -> "mai/2026". É o formato que o backend usa no as_of dos saldos.
export function formatYm(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  if (!y || !m) return ym;
  const mes = new Date(y, m - 1, 1).toLocaleDateString("pt-BR", { month: "short" });
  return `${mes.replace(".", "")}/${y}`;
}

export function todayIso(): string {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

// "2026-09-13" -> "13 set". Data curta pra linha de lista: no celular a lista
// é estreita e o ano quase nunca importa — todo lançamento visível é do mês
// que está selecionado no topo.
export function formatDiaMes(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  const mes = new Date(y, m - 1, d).toLocaleDateString("pt-BR", { month: "short" });
  return `${d} ${mes.replace(".", "")}`;
}

/** Prévia das parcelas, para o formulário mostrar antes de salvar.
 *
 * Espelha `dividir_em_parcelas` de `app/cartao.py`, que é quem DECIDE: o valor
 * que vale é o que volta do servidor. Isto aqui existe só pra a tela poder
 * dizer "3 parcelas de R$ 300,00" enquanto a pessoa ainda está escolhendo.
 *
 * A conta é em centavos inteiros porque float não fecha — `100/3*3` não dá 100.
 * O que sobra vai na primeira parcela, que é a que aparece no mês da compra.
 */
export function dividirEmParcelas(total: number, parcelas: number): number[] {
  if (parcelas < 1) return [];
  const centavos = Math.round(total * 100);
  const base = Math.floor(centavos / parcelas);
  const resto = centavos - base * parcelas;
  return [(base + resto) / 100, ...Array(parcelas - 1).fill(base / 100)];
}

/** "2026-09" → "setembro/2026". Por extenso porque aparece em frase corrida
 *  ("1ª em setembro/2026"), onde "set/2026" lê como abreviação de formulário. */
export function formatMesPorExtenso(ano: number, mes: number): string {
  const nome = new Date(ano, mes - 1, 1).toLocaleDateString("pt-BR", { month: "long" });
  return `${nome}/${ano}`;
}

/** O sinal que vai na frente do valor, por tipo de categoria.
 *
 * Despesa e receita têm sinal fixo, e o valor guardado é sempre positivo.
 * Investimento não: aporte é positivo e retirada é negativa, no mesmo campo.
 * Por isso o menos dele vem do NÚMERO, não do tipo — sem isto, `Math.abs`
 * apagava o sinal e um aporte de 500 ficava idêntico à retirada de −500 que o
 * anulava.
 */
export function sinalDoValor(tipo: CategoryType | undefined, valor: number): string {
  if (tipo === "income") return "+";
  if (tipo === "expense") return "−";
  return valor < 0 ? "−" : "";
}
