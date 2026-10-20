import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

// Fixture exclusiva, criada por prepare.py + capture.cjs seed. Sem dados reais.
const fixture = JSON.parse(fs.readFileSync(path.resolve("../.local/visual-v2-users.json"), "utf8"));
const api = "http://127.0.0.1:8014";
const ym = `year=${fixture.year}&month=${fixture.month}`;
let headers: Record<string, string>;
let token: string;

async function post(request: APIRequestContext, route: string, data: unknown) {
  const response = await request.post(api + route, { headers, data });
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
}
async function summary(request: APIRequestContext) {
  return (await request.get(`${api}/months/summary?${ym}`, { headers })).json();
}
async function fits(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  // Verifica também clipping interno de valores, que não causa overflow da página.
  const clipped = await page.locator(".e-row-value strong,.e-bill-amount b,.e-summary dd").evaluateAll(elements =>
    elements.filter(e => e.scrollWidth > e.clientWidth + 1).map(e => e.textContent));
  expect(clipped).toEqual([]);
}
test.beforeAll(async ({ request }) => {
  const auth = await request.post(`${api}/auth/login`, { data: { email: fixture.email, senha: fixture.password } });
  expect(auth.ok()).toBeTruthy();
  token = (await auth.json()).access_token;
  headers = { Authorization: `Bearer ${token}` };
});
test.beforeEach(async ({ page }) => {
  await page.addInitScript(({ token, year, month }) => {
    localStorage.setItem("sentavos:token", token);
    localStorage.setItem("sentavos:period", `${year}-${String(month).padStart(2, "0")}`);
  }, { token, year: fixture.year, month: fixture.month });
});

for (const width of [320, 360, 400, 768, 1440]) {
  test(`cinco áreas, formulário compacto e navegação em ${width}px`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", e => errors.push(e.message));
    page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
    page.on("response", r => { if (r.status() >= 400) errors.push(`${r.status()} ${r.url()}`); });
    await page.setViewportSize({ width, height: 860 });
    for (const [route, ready] of [["/", ".e-primary strong"], ["/lancamentos", ".e-day"], ["/contas-a-pagar", ".e-bill-row"], ["/relatorios", ".e-summary"], ["/investimentos", ".e-row"]]) {
      await page.goto(route);
      await expect(page.locator(ready).first()).toBeVisible();
      await fits(page);
      if (width < 900) {
        const nav = page.getByRole("navigation", { name: "Navegação principal" });
        await expect(nav.getByRole("link")).toHaveCount(5);
        for (const link of await nav.getByRole("link").all()) {
          const box = await link.boundingBox();
          expect(box!.height).toBeGreaterThanOrEqual(44);
          expect(await link.evaluate(e => e.scrollWidth <= e.clientWidth + 1)).toBeTruthy();
        }
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        const last = await page.locator("main").evaluate(e => {
          const children = [...e.querySelectorAll("button,a,p,summary")].filter(c => c.checkVisibility());
          return children.at(-1)!.getBoundingClientRect().bottom;
        });
        expect(last).toBeLessThan((await nav.boundingBox())!.y);
      }
    }
    await page.goto("/lancamentos");
    await page.getByRole("button", { name: "Novo lançamento", exact: true }).click();
    await expect(page.locator("#quick-value")).toBeFocused();
    const dialog = page.getByRole("dialog");
    expect((await dialog.boundingBox())!.height).toBeLessThan(580);
    await page.locator("#quick-value").fill("123456789,00");
    await page.getByText("Mais detalhes", { exact: true }).click();
    await fits(page);
    await page.setViewportSize({ width, height: 420 });
    await expect.poll(async () => {
      const save = await dialog.getByRole("button", { name: "Salvar", exact: true }).boundingBox();
      return save!.y + save!.height;
    }).toBeLessThanOrEqual(420);
    await page.getByRole("button", { name: "Fechar", exact: true }).click();
    expect(errors).toEqual([]);
  });
}

test("navegação entre abas e seletor de mês preservam contexto", async ({ page }) => {
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Navegação principal" });
  for (const [label, route] of [["Lançamentos", "/lancamentos"], ["Contas", "/contas-a-pagar"], ["Relatórios", "/relatorios"], ["Investir", "/investimentos"], ["Meu mês", "/"]]) {
    await nav.getByRole("link", { name: label, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`${route}$`));
    await expect(nav.getByRole("link", { name: label, exact: true })).toHaveAttribute("aria-current", "page");
  }
  await page.getByRole("button", { name: /Mês: / }).click();
  const dialog = page.getByRole("dialog", { name: "Escolher mês" });
  await expect(dialog).toBeVisible();
  await fits(page);
  await dialog.getByRole("button", { name: "jan", exact: true }).click();
  await nav.getByRole("link", { name: "Lançamentos", exact: true }).click();
  await expect(page.locator(".e-heading-period")).toHaveText("janeiro");
  await expect(page.getByText("Nenhum lançamento neste mês.", { exact: true })).toBeVisible();
});

test("filtros, datas, estados e ações secundárias do extrato", async ({ page, request }) => {
  const before = await summary(request);
  await page.goto("/lancamentos");
  await expect(page.locator(".e-row")).toHaveCount(9);
  await expect(page.locator(".e-day")).toHaveCount(7);
  const filter = page.getByRole("group", { name: "Filtrar lançamentos" });
  await filter.getByRole("button", { name: "Entradas", exact: true }).click();
  await expect(page.locator(".e-row")).toHaveCount(2);
  await expect(page.locator(".e-row").filter({ hasText: "Freelance" })).toContainText("A receber");
  await filter.getByRole("button", { name: "Despesas", exact: true }).click();
  await expect(page.locator(".e-row")).toHaveCount(6);
  const card = page.locator(".e-row").filter({ hasText: "Fone de ouvido" });
  await expect(card).toContainText("No cartão");
  await expect(card).not.toContainText("Pago");
  await card.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.locator("#c-desc")).toHaveValue("Fone de ouvido");
  await page.getByRole("button", { name: "Fechar", exact: true }).click();
  await filter.getByRole("button", { name: "Investimentos", exact: true }).click();
  await expect(page.locator(".e-row")).toHaveCount(1);
  await expect(page.locator(".e-row")).toContainText("Aporte");
  await page.getByText("Mais opções", { exact: true }).click();
  for (const name of ["Orçamento e metas", "Compromissos", "Conferir mês"]) await expect(page.getByRole("link", { name, exact: true })).toBeVisible();
  expect(await summary(request)).toEqual(before);
});

test("Contas distingue cotação, parcelas, desconhecido e pagamento sem somar pendências", async ({ page, request }) => {
  const before = await summary(request);
  await page.goto("/contas-a-pagar");
  await expect(page.locator(".e-summary")).toContainText("3 itens");
  await expect(page.getByRole("region", { name: "A pagar", exact: true })).toContainText("Seguro da Hunter");
  const review = page.getByRole("region", { name: "A conferir", exact: true });
  await expect(review).toContainText("Proteção veicular");
  await expect(review.locator(".e-bill-row").filter({ hasText: "Proteção veicular" })).toContainText("Cotação");
  await expect(review.locator(".e-bill-row").filter({ hasText: "Serviço com valor" })).toContainText("A confirmar");
  await expect(review.locator(".e-bill-row").filter({ hasText: "Serviço com valor" })).not.toContainText("R$ 0,00");
  await review.getByRole("button", { name: /Proteção veicular/ }).click();
  await expect(page.getByRole("dialog")).toContainText("confirmar se substitui o Seguro da Hunter");
  await page.getByRole("button", { name: "Já paguei", exact: true }).click();
  await expect(page.getByLabel("Conta de origem", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Registrar pagamento real", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Fechar", exact: true }).click();
  await review.getByRole("button", { name: /Manutenção da moto/ }).click();
  await expect(page.getByRole("dialog")).toContainText("Nenhum pagamento será criado aqui");
  await page.getByRole("button", { name: "Fechar", exact: true }).click();
  await page.getByRole("link", { name: "Faturas ›", exact: true }).click();
  await expect(page.locator(".fatura-linha").first()).toBeVisible();
  await page.locator(".fatura-linha").first().click();
  await expect(page.locator("main")).toContainText("Cartão principal");
  await fits(page);
  expect(await summary(request)).toEqual(before);
});

test("estado vazio nas duas páginas", async ({ page, request }) => {
  const auth = await request.post(`${api}/auth/login`, { data: { email: fixture.demo, senha: fixture.password } });
  expect(auth.ok()).toBeTruthy();
  const demoToken = (await auth.json()).access_token;
  await page.addInitScript(t => localStorage.setItem("sentavos:token", t), demoToken);
  for (const route of ["/lancamentos", "/contas-a-pagar"]) {
    await page.goto(route);
    await expect(page.locator(".e-empty").first()).toBeVisible();
    await expect(page.locator(".e-row,.e-bill-row")).toHaveCount(0);
    await fits(page);
  }
});

test("lista extensa, nomes longos e valores altos nas cinco larguras", async ({ page, request }) => {
  const ids: number[] = [];
  const before = await summary(request);
  try {
    for (let n = 0; n < 24; n++) {
      const t = await post(request, "/transactions", { description: `Validação de nome longo — manutenção e serviços com várias informações de referência ${n}`, date: `${fixture.year}-${String(fixture.month).padStart(2, "0")}-22`, amount_planned: 9999999.99, category_id: fixture.expense, payment_method: "cash", account_id: fixture.account, expense_class: "variable" });
      ids.push(t.id);
    }
    for (const width of [320, 360, 400, 768, 1440]) {
      await page.setViewportSize({ width, height: 860 });
      for (const route of ["/lancamentos", "/contas-a-pagar"]) {
        await page.goto(route);
        await expect(page.locator("main")).toContainText("Validação de nome longo");
        await expect(page.locator("main")).toContainText("9.999.999,99");
        await fits(page);
      }
    }
  } finally {
    for (const id of ids) expect((await request.delete(`${api}/transactions/${id}`, { headers })).ok()).toBeTruthy();
  }
  expect(await summary(request)).toEqual(before);
});

test("criar, editar e excluir previsão conserva o caixa e a estrutura de Meu mês", async ({ page, request }) => {
  const before = await summary(request);
  await page.goto("/lancamentos");
  await page.getByRole("button", { name: "Novo lançamento", exact: true }).click();
  await page.locator("#quick-value").fill("75,00");
  await page.locator("#quick-category").selectOption(String(fixture.expense));
  await page.getByRole("switch", { name: "Ainda é previsto" }).check();
  await page.getByText("Mais detalhes", { exact: true }).click();
  await page.locator("#quick-description").fill("Previsão de validação visual");
  await page.getByRole("button", { name: "Salvar previsão", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const row = page.locator(".e-row").filter({ hasText: "Previsão de validação visual" });
  await expect(row).toContainText("A pagar");
  expect((await summary(request)).money_now).toBe(before.money_now);
  await row.click();
  await page.locator("#t-desc").fill("Previsão editada na validação");
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.locator(".e-row").filter({ hasText: "Previsão editada na validação" }).click();
  await page.getByRole("button", { name: "Excluir", exact: true }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Excluir", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(await summary(request)).toEqual(before);
  await page.goto("/");
  for (const label of ["Tenho agora", "A receber", "A pagar", "Investido no mês", "A investir", "Vai sobrar", "Resumo do mês"]) await expect(page.getByText(label, { exact: true })).toBeVisible();
});

test("tokens de texto e estados mantêm contraste AA nas superfícies", async ({ page }) => {
  await page.goto("/lancamentos");
  const colors = await page.evaluate(() => {
    const style = getComputedStyle(document.documentElement);
    return Object.fromEntries(["--bg", "--surface", "--surface-2", "--text", "--text-dim", "--text-faint", "--accent-hi", "--pos", "--attention", "--neg", "--accent", "--accent-ink"].map(v => [v, style.getPropertyValue(v).trim()]));
  });
  function luminance(hex: string) {
    const rgb = hex.replace("#", "").match(/../g)!.map(n => parseInt(n, 16) / 255).map(n => n <= .04045 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4);
    return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
  }
  function contrast(a: string, b: string) { const x = luminance(a), y = luminance(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); }
  for (const text of ["--text", "--text-dim", "--text-faint", "--accent-hi", "--pos", "--attention", "--neg"]) for (const surface of ["--bg", "--surface", "--surface-2"]) expect(contrast(colors[text], colors[surface]), `${text} / ${surface}`).toBeGreaterThanOrEqual(4.5);
  expect(contrast(colors["--accent"], colors["--accent-ink"])).toBeGreaterThanOrEqual(4.5);
});
