import {test,expect} from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const fixture=path.resolve("../.local/reset-total-ui-session.json");
const local=fs.existsSync(fixture)?JSON.parse(fs.readFileSync(fixture,"utf8")):null;
test.skip(!local,"Requer cópia local de ensaio; nunca usa produção.");
test.describe.serial("Reinício e preenchimento manual",()=>{
  test.beforeEach(async({page})=>{
    await page.addInitScript(token=>{
      localStorage.setItem("sentavos:token",token);
      localStorage.setItem("sentavos:period","2026-11");
    },local.token);
    // Qualquer URL compilada para a API é redirecionada exclusivamente ao servidor local.
    await page.route("**/*",async route=>{
      const u=new URL(route.request().url());
      if(u.origin==="http://127.0.0.1:5189") return route.continue();
      const response=await route.fetch({url:"http://127.0.0.1:8020"+u.pathname+u.search});
      return route.fulfill({response});
    });
    await page.goto("/");
    await expect(page.locator(".e-primary strong")).toContainText("696,00");
  });
  test("novembro vazio, saldo datado e cinco abas",async({page})=>{
    await expect(page.locator(".e-primary")).toContainText("29/10");
    await expect(page.locator(".e-primary")).toContainText("Atualização pendente");
    await expect(page.locator(".e-projection")).toContainText("Aguardando informações");
    await expect(page.locator(".e-summary")).not.toContainText("R$");
    await page.screenshot({path:"../.local/reset-total-meu-mes.png",fullPage:true});
    const nav=page.getByRole("navigation",{name:"Navegação principal"});
    await expect(nav.getByRole("link")).toHaveCount(5);
    for(const name of ["Lançamentos","Contas","Relatórios","Investir"]){
      await nav.getByRole("link",{name,exact:true}).click();
      await page.waitForLoadState("networkidle");
      await expect(page.locator("main")).not.toContainText("Financiamento Hunter");
      await expect(page.locator("main [role=alert]")).toHaveCount(0);
    }
  });
  test("fatura desconhecida, valor manual e pagamento real",async({page,request})=>{
    await page.getByRole("navigation").getByRole("link",{name:"Contas",exact:true}).click();
    await page.getByRole("link",{name:"Faturas ›",exact:true}).click();
    await page.locator(".fatura-linha").first().click();
    await expect(page.locator("main")).toContainText("A preencher");
    await expect(page.getByRole("button",{name:"Pagar fatura",exact:true})).toHaveCount(0);
    await page.screenshot({path:"../.local/reset-total-fatura-vazia.png",fullPage:true});
    await page.getByRole("button",{name:"Preencher valor da fatura"}).click();
    await page.locator("#invoice-total").fill("500,00");
    await page.getByRole("button",{name:"Salvar valor",exact:true}).click();
    await expect(page.getByRole("button",{name:"Pagar fatura",exact:true})).toBeVisible();
    const headers={Authorization:`Bearer ${local.token}`};
    const rows=await request.get("http://127.0.0.1:8020/transactions?year=2026&month=11",{headers});
    expect(await rows.json()).toEqual([]);
    await page.getByRole("button",{name:"Pagar fatura",exact:true}).click();
    const dialog=page.getByRole("dialog");
    await dialog.locator("input[inputmode=decimal]").fill("120,00");
    await dialog.getByRole("group").getByRole("button",{name:local.accountName,exact:true}).click();
    await dialog.getByRole("button",{name:"Confirmar",exact:true}).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.locator(".fatura-total.destaque")).toContainText("380,00");
    const cash=await request.get("http://127.0.0.1:8020/budgets/summary?year=2026&month=11",{headers});
    expect((await cash.json()).caixa).toMatchObject({gasto_total:0,faturas_pagas:120});
  });
  test("novas entradas, despesas e contas a pagar",async({page})=>{
    for(const kind of ["Entrada","Despesa"]){
      await page.getByRole("button",{name:"Novo lançamento",exact:true}).click();
      await page.getByRole("group",{name:"Tipo do lançamento"}).getByRole("button",{name:kind,exact:true}).click();
      await page.locator("#quick-value").fill(kind==="Entrada"?"5000":"700");
      await page.locator("#quick-origin").selectOption(`account:${local.accountId}`);
      await page.locator("#quick-category").selectOption({index:1});
      await page.getByRole("dialog").getByRole("button",{name:"Salvar",exact:true}).click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
    }
    await page.getByRole("navigation").getByRole("link",{name:"Contas",exact:true}).click();
    await page.getByRole("button",{name:"Nova conta a pagar"}).click();
    await page.locator("#c-desc").fill("Conta manual após reset");
    await page.locator("#c-valor").fill("30,00");
    await page.locator("#c-primeira").fill("2026-11-20");
    await page.locator(".cat-trigger").click();
    await page.locator(".cat-opcoes button").first().click();
    await page.getByRole("dialog").getByRole("button",{name:"Salvar",exact:true}).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.locator(".e-bill-section[aria-label='A pagar']")).toContainText("Conta manual após reset");
  });
});
