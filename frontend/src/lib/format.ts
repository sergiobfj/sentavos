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

export function todayIso(): string {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}
