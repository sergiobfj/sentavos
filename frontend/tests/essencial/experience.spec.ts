import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/essencial.html#/");
});
test("tarefa 1: dinheiro conhecido na primeira dobra, com data e quatro abas", async ({
  page,
}) => {
  await expect(page.getByTestId("money-now")).toHaveText(/684,39/);
  await expect(
    page.getByText("Saldos observados entre 11 e 18/10 · ver contas"),
  ).toBeVisible();
  const bounds = await page.getByTestId("money-now").boundingBox();
  expect(bounds!.y + bounds!.height).toBeLessThan(400);
  await expect(
    page
      .getByRole("navigation", { name: "Navegação principal mobile" })
      .getByRole("link"),
  ).toHaveCount(4);
  await page.getByRole("button", { name: /Meu dinheiro agora/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Carteira", exact: true }),
  ).toBeVisible();
});
test("tarefa 2: simular 200 sem criar lançamento nem alterar o saldo", async ({
  page,
}) => {
  const requests: string[] = [];
  page.on("request", (r) => {
    if (r.method() !== "GET") requests.push(r.url());
  });
  await page.getByRole("button", { name: "E se eu gastar a mais?" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Previsão depois desse gasto" }),
  ).toContainText("766,31");
  await page.getByRole("button", { name: "Concluir simulação" }).click();
  await expect(page.getByTestId("forecast")).toHaveText(/966,31/);
  await expect(page.getByTestId("money-now")).toHaveText(/684,39/);
  expect(requests).toEqual([]);
});
test("tarefa 3: lançar Pix de 25 com conta anterior e categoria, sem descrição", async ({
  page,
}) => {
  await page
    .getByRole("button", { name: "Novo lançamento", exact: true })
    .click();
  await expect(page.locator("#quick-amount")).toBeFocused();
  await page.locator("#quick-amount").fill("25");
  await page.getByRole("button", { name: "Alimentação", exact: true }).click();
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByTestId("money-now")).toHaveText(/659,39/);
  await expect(page.getByTestId("forecast")).toHaveText(/941,31/);
  await page
    .getByRole("navigation", { name: "Navegação principal mobile" })
    .getByRole("link", { name: "Lançamentos", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: /^Alimentação Alimentação/ }),
  ).toBeVisible();
  await page.reload();
  await page.goto("/essencial.html#/");
  await expect(page.getByTestId("money-now")).toHaveText(/684,39/);
});
test("tarefa 4: novembro abre compromissos e fatura sem duplicar financiamento", async ({
  page,
}) => {
  await page.getByRole("button", { name: /^novembro/ }).click();
  const sheet = page.getByRole("dialog");
  await expect(sheet).toContainText("Planejamento de novembro");
  await expect(sheet).toContainText("Financiamento · 2/48");
  await expect(sheet).toContainText("Fatura Nubank · novembro");
  await expect(sheet).toContainText("1.363,98");
});
test("tarefa 5: Investir começa pelo guardado e exclui saldo antigo", async ({
  page,
}) => {
  await page
    .getByRole("navigation", { name: "Navegação principal mobile" })
    .getByRole("link", { name: "Investir", exact: true })
    .click();
  await expect(page.getByText("Quanto tenho guardado hoje")).toBeVisible();
  await expect(page.locator(".investment-hero")).toContainText("12.845,00");
  await expect(
    page.getByRole("heading", { name: "Caixinha Mercado Pago", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".summary")).toContainText("Não apurado");
  await page
    .getByText("1 investimento com saldo antigo · fora do total")
    .click();
  await expect(page.getByRole("heading", { name: "CDB antigo" })).toBeVisible();
});
test("tarefa 6: Relatórios reúne categorias, evolução e definição de resultado", async ({
  page,
}) => {
  await page
    .getByRole("navigation", { name: "Navegação principal mobile" })
    .getByRole("link", { name: "Relatórios", exact: true })
    .click();
  await expect(page.locator(".category-breakdown")).toContainText(
    "Alimentação",
  );
  await expect(page.locator(".category-breakdown")).toContainText("Transporte");
  await expect(
    page.getByText("Resultado por competência · não é saldo da conta."),
  ).toBeVisible();
  await page.getByLabel("Analisar gastos de").selectOption("Empresa");
  await expect(
    page.getByText("Nenhum gasto registrado neste recorte."),
  ).toBeVisible();
});
test("tarefa 7: comparação legível de três meses, sem rolagem horizontal", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Ver próximos meses" }).click();
  await expect(
    page.locator(".comparison-mobile .comparison-month"),
  ).toHaveCount(3);
  await expect(page.locator(".comparison-mobile")).toContainText(
    "outubro de 2026",
  );
  await expect(page.locator(".comparison-mobile")).toContainText(
    "dezembro de 2026",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Próximo mês", exact: true }).click();
  await expect(
    page.locator(".comparison-mobile .comparison-month h2").first(),
  ).toHaveText("novembro de 2026");
});
test("aporte e resgate adaptam campos e não viram gastos/receitas", async ({
  page,
}) => {
  await page.goto("/essencial.html#/investir");
  await page.getByRole("button", { name: "Aportar", exact: true }).click();
  await page.locator("#quick-amount").fill("100");
  await expect(
    page.getByRole("combobox", { name: "Investimento", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "De qual conta sai?", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await expect(page.locator(".investment-hero")).toContainText("12.945,00");
  await page.getByRole("button", { name: "Resgatar", exact: true }).click();
  await page.locator("#quick-amount").fill("200000");
  await expect(
    page.getByRole("button", { name: "Salvar", exact: true }),
  ).toBeDisabled();
  await expect(page.getByRole("alert")).toContainText("supera o saldo");
});
test("modal retém foco, fecha com Escape e volta ao botão de origem", async ({
  page,
}) => {
  const button = page.getByRole("button", {
    name: "Novo lançamento",
    exact: true,
  });
  await button.click();
  await expect(page.locator("#quick-amount")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(button).toBeFocused();
});
test("classificação fixa/variável pode ser corrigida sem mudar categoria", async ({
  page,
}) => {
  await page.goto("/essencial.html#/lancamentos");
  await page
    .getByRole("button")
    .filter({ hasText: /Almoço/ })
    .click();
  await page
    .getByRole("combobox", { name: "Organizar como", exact: true })
    .selectOption("fixed");
  await page.getByRole("button", { name: "Fechar", exact: true }).click();
  await page.goto("/essencial.html#/");
  await expect(
    page.locator(".entry-group").filter({
      has: page.getByRole("heading", { name: "Despesas fixas", exact: true }),
    }),
  ).toContainText("Almoço");
});
test("rotas diretas e mês persistem na navegação, sem chamadas à API", async ({
  page,
}) => {
  const external: string[] = [];
  page.on("request", (r) => {
    if (
      !r.url().startsWith("http://127.0.0.1:5178") &&
      !r.url().startsWith("data:")
    )
      external.push(r.url());
  });
  await page.getByRole("button", { name: "Próximo mês", exact: true }).click();
  for (const route of [
    "lancamentos",
    "relatorios",
    "investir",
    "comparar",
    "cartoes",
  ]) {
    await page.goto(`/essencial.html#/${route}`);
    await expect(page.locator("h1")).toBeVisible();
  }
  expect(external).toEqual([]);
});
for (const size of [
  { width: 320, height: 800 },
  { width: 360, height: 800 },
  { width: 400, height: 860 },
  { width: 768, height: 1024 },
  { width: 1440, height: 1000 },
]) {
  test(`layout ${size.width}px: quatro telas sem overflow e screenshots`, async ({
    page,
  }, info) => {
    await page.setViewportSize(size);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    for (const route of [
      "",
      "lancamentos",
      "relatorios",
      "investir",
      "comparar",
    ]) {
      await page.goto(`/essencial.html#/${route}`);
      await expect(page.locator("h1")).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `${route}: overflow`,
      ).toBe(true);
      const shot = info.outputPath(`${route || "meu-mes"}-${size.width}.png`);
      await page.screenshot({
        path: shot,
        fullPage: true,
        animations: "disabled",
      });
      await info.attach(`${route || "meu-mes"}-${size.width}`, {
        path: shot,
        contentType: "image/png",
      });
    }
    expect(errors).toEqual([]);
    if (size.width <= 400) {
      await page.goto("/essencial.html#/");
      await page.screenshot({
        path: info.outputPath(`primeira-dobra-${size.width}.png`),
        animations: "disabled",
      });
      await page
        .getByRole("button", { name: "Novo lançamento", exact: true })
        .click();
      await page.screenshot({
        path: info.outputPath(`lancamento-rapido-${size.width}.png`),
        animations: "disabled",
      });
    }
  });
}
