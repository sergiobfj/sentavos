import { test, expect } from "@playwright/test";
import {
  createDemoState,
  knownBalance,
  invested,
  projection,
  monthEntries,
  totals,
  createQuickEntries,
  parseAmount,
  type QuickInput,
} from "./prototypeModel";

const input: QuickInput = {
  amount: 2500,
  kind: "expense",
  account: "Nubank",
  category: "Alimentação",
  description: "",
  date: "2026-10-18",
  card: "",
  installments: 1,
  asset: "Caixinha Mercado Pago",
  expenseClass: "variable",
  purpose: "Pessoal",
};
test("saldo conhecido não é resultado e ativos antigos não entram no total", () => {
  const state = createDemoState();
  expect(knownBalance(state)).toBe(68439);
  expect(totals(monthEntries(state, "2026-10")).result).toBe(61020);
  expect(invested(state)).toBe(1284500);
});
test("projeção usa apenas pendências e transporta saldo antes de reservas", () => {
  const state = createDemoState();
  const oct = projection(state, "2026-10")!;
  const nov = projection(state, "2026-11")!;
  expect(oct.available).toBe(96631);
  expect(oct.projected).toBe(106631);
  expect(nov.opening).toBe(oct.projected);
  expect(oct.fixed).toBe(73808);
  expect(nov.invoices).toBe(6590);
  expect(nov.fixed).toBe(79808);
  expect(projection(state, "2026-09")).toBeNull();
});
test("Pix altera conta e previsão uma vez; descrição é opcional", () => {
  const state = createDemoState();
  state.entries.push(...createQuickEntries(input, "pix"));
  expect(knownBalance(state)).toBe(65939);
  expect(projection(state, "2026-10")!.available).toBe(94131);
  expect(state.entries.at(-1)!.description).toBe("Alimentação");
});
test("aporte e resgate alocam dinheiro, sem alterar receitas e gastos", () => {
  const state = createDemoState();
  const before = totals(monthEntries(state, "2026-10"));
  state.entries.push(
    ...createQuickEntries(
      { ...input, amount: 80000, kind: "contribution" },
      "aporte",
    ),
  );
  expect(knownBalance(state)).toBe(-11561);
  expect(invested(state)).toBe(1364500);
  expect(totals(monthEntries(state, "2026-10")).expense).toBe(before.expense);
  state.entries.push(
    ...createQuickEntries(
      { ...input, amount: 50000, kind: "redemption" },
      "resgate",
    ),
  );
  expect(knownBalance(state)).toBe(38439);
  expect(invested(state)).toBe(1314500);
  expect(totals(monthEntries(state, "2026-10")).income).toBe(before.income);
});
test("cartão preserva saldo, parcelas fecham em centavos e fatura não duplica gasto", () => {
  const state = createDemoState();
  const before = totals(monthEntries(state, "2026-10"));
  const entries = createQuickEntries(
    { ...input, amount: 10001, card: "Nubank Pessoal", installments: 3 },
    "card",
  );
  expect(
    entries
      .filter((e) => e.kind === "expense")
      .reduce((n, e) => n + e.amount, 0),
  ).toBe(10001);
  expect(
    entries
      .filter((e) => e.kind === "invoice")
      .reduce((n, e) => n + e.amount, 0),
  ).toBe(10001);
  state.entries.push(...entries);
  expect(knownBalance(state)).toBe(68439);
  expect(totals(monthEntries(state, "2026-10")).expense).toBe(
    before.expense + 3335,
  );
  expect(totals(monthEntries(state, "2026-10")).cashExpense).toBe(
    before.cashExpense,
  );
  expect(projection(state, "2026-11")!.invoices).toBe(6590 + 3335);
});
test("entrada monetária rejeita negativos, vazio, ambiguidade e excesso de casas", () => {
  expect(parseAmount("25")).toBe(2500);
  expect(parseAmount("1.234,56")).toBe(123456);
  for (const value of [
    "",
    "0",
    "-25",
    "25.50",
    "1,234",
    "abc",
    "Infinity",
    "1e9",
  ])
    expect(parseAmount(value)).toBeNull();
});
test("todas as datas fictícias são válidas, inclusive fevereiro", () => {
  for (const entry of createDemoState().entries)
    expect(new Date(`${entry.date}T12:00:00Z`).toISOString().slice(0, 10)).toBe(
      entry.date,
    );
});
