// Exclusivamente demonstração. Valores em centavos, sem acesso à API ou storage.
// Na integração, substituir estas projeções pelos resultados do domínio Python.
export const TODAY = "2026-10-18";
export const CURRENT_MONTH = TODAY.slice(0, 7);
export type Kind =
  "income" | "expense" | "contribution" | "redemption" | "invoice";
export type ExpenseClass = "fixed" | "variable";
export type Purpose = "Pessoal" | "Família" | "Empresa";
export interface Entry {
  id: string;
  date: string;
  description: string;
  amount: number;
  kind: Kind;
  category: string;
  status: "done" | "planned";
  account?: string;
  card?: string;
  asset?: string;
  expenseClass?: ExpenseClass;
  nature?: "consumption" | "acquisition" | "financial";
  purpose?: Purpose;
  afterBalance?: boolean;
  note?: string;
}
export interface DemoAccount {
  name: string;
  balance: number;
  observed: string;
  stale?: boolean;
}
export interface DemoAsset {
  name: string;
  value: number;
  observed: string;
  stale?: boolean;
}
export interface DemoState {
  entries: Entry[];
  accounts: DemoAccount[];
  assets: DemoAsset[];
}

export const money = (cents: number) =>
  (cents / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
export const day = (date: string) => `${date.slice(8, 10)}/${date.slice(5, 7)}`;
export function monthLabel(ym: string, year = false) {
  const [y, m] = ym.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString("pt-BR", {
    month: "long",
    ...(year ? { year: "numeric" } : {}),
  });
}
export function shiftMonth(ym: string, offset: number) {
  const [y, m] = ym.split("-").map(Number);
  const d = new Date(y, m - 1 + offset, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
export function parseAmount(value: string): number | null {
  const normalized = value.trim().replace(/\s/g, "");
  if (!/^(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?$/.test(normalized))
    return null;
  const n = Math.round(
    Number(normalized.replace(/\./g, "").replace(",", ".")) * 100,
  );
  return Number.isSafeInteger(n) && n > 0 && n <= 99999999999 ? n : null;
}
export const sum = (items: Entry[]) => items.reduce((s, e) => s + e.amount, 0);
export const cashSign = (e: Entry) =>
  e.kind === "income" || e.kind === "redemption"
    ? 1
    : e.card && e.kind === "expense"
      ? 0
      : -1;
export function accountBalance(state: DemoState, name: string) {
  const account = state.accounts.find((a) => a.name === name);
  return (
    (account?.balance ?? 0) +
    state.entries
      .filter(
        (e) => e.afterBalance && e.status === "done" && e.account === name,
      )
      .reduce((n, e) => n + cashSign(e) * e.amount, 0)
  );
}
export function knownBalance(state: DemoState) {
  return state.accounts.reduce((n, a) => n + accountBalance(state, a.name), 0);
}
export function assetBalance(state: DemoState, name: string) {
  return (
    (state.assets.find((a) => a.name === name)?.value ?? 0) +
    state.entries
      .filter((e) => e.afterBalance && e.status === "done" && e.asset === name)
      .reduce(
        (n, e) =>
          n +
          (e.kind === "contribution"
            ? e.amount
            : e.kind === "redemption"
              ? -e.amount
              : 0),
        0,
      )
  );
}
export function invested(state: DemoState) {
  return state.assets
    .filter((a) => !a.stale)
    .reduce((n, a) => n + assetBalance(state, a.name), 0);
}
export function monthEntries(state: DemoState, month: string) {
  return state.entries.filter((e) => e.date.startsWith(month));
}
export function totals(entries: Entry[]) {
  const done = entries.filter((e) => e.status === "done");
  const income = sum(done.filter((e) => e.kind === "income"));
  const expense = sum(done.filter((e) => e.kind === "expense"));
  const contributed = sum(done.filter((e) => e.kind === "contribution"));
  const redeemed = sum(done.filter((e) => e.kind === "redemption"));
  const cashExpense = sum(
    done.filter(
      (e) => e.kind === "invoice" || (e.kind === "expense" && !e.card),
    ),
  );
  return {
    income,
    expense,
    contributed,
    redeemed,
    cashExpense,
    result: income - expense,
    cashResult: income - cashExpense - contributed + redeemed,
  };
}
export interface Projection {
  month: string;
  opening: number;
  income: number;
  fixed: number;
  variable: number;
  invoices: number;
  contributions: number;
  redemptions: number;
  reserve: number;
  projected: number;
  available: number;
}
export function projection(state: DemoState, month: string): Projection | null {
  if (month < CURRENT_MONTH || month > "2027-03") return null;
  let opening = knownBalance(state);
  let result: Projection | null = null;
  for (let ym = CURRENT_MONTH; ym <= month; ym = shiftMonth(ym, 1)) {
    const pending = monthEntries(state, ym).filter(
      (e) => e.status === "planned",
    );
    const take = (kind: Kind) => sum(pending.filter((e) => e.kind === kind));
    const fixed = sum(
      pending.filter(
        (e) => e.kind === "expense" && !e.card && e.expenseClass === "fixed",
      ),
    );
    const variable = sum(
      pending.filter(
        (e) => e.kind === "expense" && !e.card && e.expenseClass !== "fixed",
      ),
    );
    const income = take("income"),
      invoices = take("invoice"),
      contributions = take("contribution"),
      redemptions = take("redemption");
    // Reserva não é despesa e não é transportada como uma saída entre meses.
    const reserve = 10000;
    const projected =
      opening +
      income +
      redemptions -
      fixed -
      variable -
      invoices -
      contributions;
    result = {
      month: ym,
      opening,
      income,
      fixed,
      variable,
      invoices,
      contributions,
      redemptions,
      reserve,
      projected,
      available: projected - reserve,
    };
    opening = projected;
  }
  return result;
}

export function createDemoState(): DemoState {
  const entries: Entry[] = [
    {
      id: "oct-salary",
      date: "2026-10-05",
      description: "Salário",
      amount: 94000,
      kind: "income",
      category: "Salário",
      status: "done",
      account: "Nubank",
    },
    {
      id: "oct-net",
      date: "2026-10-08",
      description: "Internet",
      amount: 6000,
      kind: "expense",
      category: "Casa",
      status: "done",
      account: "Nubank",
      expenseClass: "fixed",
      purpose: "Pessoal",
    },
    {
      id: "oct-market",
      date: "2026-10-16",
      description: "Mercado",
      amount: 14890,
      kind: "expense",
      category: "Alimentação",
      status: "done",
      account: "Mercado Pago",
      expenseClass: "variable",
      purpose: "Família",
    },
    {
      id: "oct-food",
      date: "2026-10-18",
      description: "Almoço",
      amount: 2500,
      kind: "expense",
      category: "Alimentação",
      status: "done",
      account: "Nubank",
      expenseClass: "variable",
      purpose: "Pessoal",
    },
    {
      id: "oct-uber",
      date: "2026-10-17",
      description: "Uber",
      amount: 1800,
      kind: "expense",
      category: "Transporte",
      status: "done",
      account: "Nubank",
      expenseClass: "variable",
      purpose: "Pessoal",
    },
    {
      id: "oct-coffee",
      date: "2026-10-14",
      description: "Café",
      amount: 1200,
      kind: "expense",
      category: "Alimentação",
      status: "done",
      account: "Carteira",
      expenseClass: "variable",
      purpose: "Pessoal",
    },
    {
      id: "oct-asset",
      date: "2026-10-10",
      description: "Caixinha de reserva",
      amount: 80000,
      kind: "contribution",
      category: "Investimentos",
      status: "done",
      account: "Nubank",
      asset: "Caixinha Mercado Pago",
    },
    {
      id: "oct-card",
      date: "2026-10-12",
      description: "Farmácia",
      amount: 6590,
      kind: "expense",
      category: "Saúde",
      status: "done",
      card: "Nubank Pessoal",
      expenseClass: "variable",
      purpose: "Pessoal",
    },
    {
      id: "oct-card-pay",
      date: "2026-10-02",
      description: "Fatura Nubank · outubro",
      amount: 9500,
      kind: "invoice",
      category: "Pagamento de fatura",
      status: "done",
      account: "Nubank",
    },
    {
      id: "oct-advance",
      date: "2026-10-20",
      description: "Adiantamento",
      amount: 72000,
      kind: "income",
      category: "Salário",
      status: "planned",
      account: "Nubank",
    },
    {
      id: "oct-extra",
      date: "2026-10-28",
      description: "Trabalho extra",
      amount: 70000,
      kind: "income",
      category: "Outras entradas",
      status: "planned",
      account: "Nubank",
    },
    {
      id: "oct-gym",
      date: "2026-10-22",
      description: "Academia",
      amount: 12000,
      kind: "expense",
      category: "Saúde",
      status: "planned",
      expenseClass: "fixed",
      purpose: "Pessoal",
    },
    {
      id: "oct-finance",
      date: "2026-10-25",
      description: "Financiamento · 1/48",
      amount: 61808,
      kind: "expense",
      category: "Transporte",
      status: "planned",
      expenseClass: "fixed",
      nature: "financial",
      purpose: "Pessoal",
    },
    {
      id: "oct-grocery-plan",
      date: "2026-10-24",
      description: "Compras da semana",
      amount: 10000,
      kind: "expense",
      category: "Alimentação",
      status: "planned",
      expenseClass: "variable",
      purpose: "Família",
    },
    {
      id: "oct-contribute",
      date: "2026-10-30",
      description: "Guardar na caixinha",
      amount: 20000,
      kind: "contribution",
      category: "Investimentos",
      status: "planned",
      account: "Nubank",
      asset: "Caixinha Mercado Pago",
    },
  ];
  // Série demonstrativa consistente: movimentos de competência, não saldos.
  ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09"].forEach(
    (ym, index) => {
      entries.push({
        id: `${ym}-salary`,
        date: `${ym}-05`,
        description: "Salário",
        amount: 236000,
        kind: "income",
        category: "Salário",
        status: "done",
        account: "Nubank",
      });
      [88000 + index * 3200, 25000 - index * 1800, 12000 + index * 900].forEach(
        (amount, i) =>
          entries.push({
            id: `${ym}-${i}`,
            date: `${ym}-12`,
            description: ["Compras do mês", "Transporte", "Casa"][i],
            amount,
            kind: "expense",
            category: ["Alimentação", "Transporte", "Casa"][i],
            status: "done",
            purpose: "Pessoal",
            expenseClass: i === 2 ? "fixed" : "variable",
          }),
      );
    },
  );
  for (let offset = 1; offset <= 5; offset++) {
    const ym = shiftMonth(CURRENT_MONTH, offset);
    const [year, month] = ym.split("-").map(Number);
    const lastDay = new Date(year, month, 0).getDate();
    const planned = (
      id: string,
      description: string,
      amount: number,
      kind: Kind,
      date: number,
      extra: Partial<Entry> = {},
    ) =>
      entries.push({
        id: `${ym}-${id}`,
        date: `${ym}-${String(Math.min(date, lastDay)).padStart(2, "0")}`,
        description,
        amount,
        kind,
        category: kind === "income" ? "Salário" : "Outros",
        status: "planned",
        ...extra,
      });
    planned("salary", "Salário", 236000, "income", 5);
    planned("internet", "Internet", 6000, "expense", 8, {
      expenseClass: "fixed",
      category: "Casa",
      purpose: "Pessoal",
    });
    planned("gym", "Academia", 12000, "expense", 22, {
      expenseClass: "fixed",
      category: "Saúde",
      purpose: "Pessoal",
    });
    planned(
      "finance",
      `Financiamento · ${offset + 1}/48`,
      61808,
      "expense",
      25,
      {
        expenseClass: "fixed",
        nature: "financial",
        category: "Transporte",
        purpose: "Pessoal",
      },
    );
    planned("variable", "Gastos do dia a dia", 50000, "expense", 28, {
      expenseClass: "variable",
      purpose: "Pessoal",
    });
    planned("investment", "Guardar na caixinha", 30000, "contribution", 30, {
      asset: "Caixinha Mercado Pago",
    });
    if (offset === 1)
      planned("invoice", "Fatura Nubank · novembro", 6590, "invoice", 2);
  }
  return {
    entries,
    accounts: [
      { name: "Nubank", balance: 48000, observed: TODAY },
      { name: "Mercado Pago", balance: 17439, observed: TODAY },
      { name: "Carteira", balance: 3000, observed: "2026-10-11" },
    ],
    assets: [
      { name: "Caixinha Mercado Pago", value: 824500, observed: "2026-10-18" },
      { name: "Caixinha Nubank", value: 460000, observed: "2026-10-17" },
      { name: "CDB antigo", value: 80000, observed: "2026-08-31", stale: true },
    ],
  };
}

export interface QuickInput {
  amount: number;
  kind: Exclude<Kind, "invoice">;
  account: string;
  category: string;
  description: string;
  date: string;
  card: string;
  installments: number;
  asset: string;
  expenseClass: ExpenseClass;
  purpose: Purpose;
}
export function createQuickEntries(input: QuickInput, id: string): Entry[] {
  const base: Entry = {
    id,
    date: input.date,
    amount: input.amount,
    kind: input.kind,
    description: input.description.trim() || input.category,
    category: input.category,
    status: "done",
    account: input.account,
    expenseClass: input.kind === "expense" ? input.expenseClass : undefined,
    purpose: input.kind === "expense" ? input.purpose : undefined,
    afterBalance: true,
  };
  if (input.kind === "contribution" || input.kind === "redemption")
    base.asset = input.asset;
  if (input.kind !== "expense" || !input.card) return [base];
  // Prévia demonstrativa. A integração delegará competência e vencimento à API de compras.
  const installment = Math.floor(input.amount / input.installments);
  return Array.from({ length: input.installments }, (_, i): Entry[] => {
    const ym = shiftMonth(input.date.slice(0, 7), i);
    const amount =
      installment + (i === 0 ? input.amount % input.installments : 0);
    return [
      {
        ...base,
        id: `${id}-${i}`,
        amount,
        date: `${ym}-01`,
        account: undefined,
        card: input.card,
        afterBalance: false,
        description:
          input.installments > 1
            ? `${base.description} · ${i + 1}/${input.installments}`
            : base.description,
      },
      {
        id: `${id}-invoice-${i}`,
        date: `${shiftMonth(ym, 1)}-02`,
        amount,
        kind: "invoice",
        category: "Pagamento de fatura",
        status: "planned",
        description: "Fatura Nubank · compra demonstrativa",
      },
    ];
  }).flat();
}
