import {test,expect} from "@playwright/test";
import fs from "node:fs";

const local=JSON.parse(fs.readFileSync("../.local/situacao-ui-session.json","utf8"));
test.beforeEach(async({page})=>{
  await page.addInitScript(token=>{
    localStorage.setItem("sentavos:token",token);
    localStorage.setItem("sentavos:period","2026-11");
  },local.token);
  await page.route("**/*",route=>{
    const origin=new URL(route.request().url()).origin;
    return ["http://127.0.0.1:5191","http://127.0.0.1:8021"].includes(origin)?route.continue():route.abort();
  });
});

test("meu mês mostra saldo, reservas e ajuste sem duplicar salário",async({page})=>{
  await page.goto("/");
  await expect(page.locator(".e-primary strong")).toContainText("496,32");
  await expect(page.getByText("Tenho agora",{exact:true})).toBeVisible();
  await expect(page.locator(".e-primary")).toContainText("saldo observado em 09/11");
  const summary=page.locator(".e-summary").first();
  await expect(summary).toContainText("Reserva de emergência");
  await expect(summary).toContainText("634,00");
  await expect(summary).toContainText("473,00");
  await expect(summary).toContainText("23,32");
  await expect(page.getByText(/Saldo de ajuste:/)).toContainText("1.142,00");
  await expect(page.locator(".e-projection-value")).not.toContainText("R$");
  await page.getByRole("button",{name:/Entradas/}).click();
  await expect(page.locator(".e-group-detail")).toContainText("942,32");
  await expect(page.locator(".e-group-detail")).toContainText("Recebido");
  await expect(page.getByRole("navigation",{name:"Navegação principal"}).getByRole("link")).toHaveCount(5);
  await page.screenshot({path:"../.local/situacao-meu-mes.png",fullPage:true});
});

test("contas e fatura preservam obrigações, total manual e responsabilidades",async({page})=>{
  await page.goto("/contas-a-pagar");
  const due=page.locator(".e-bill-section[aria-label='A pagar']");
  await expect(due.locator(".e-bill-row")).toHaveCount(5);
  await expect(page.locator(".e-summary")).toContainText("1.402,85");
  for(const description of ["Seguro saúde da viagem para Argentina","Academia","Internet","Emplacamento e seguro da moto","Fatura Nubank"])
    await expect(due).toContainText(description);
  await expect(due).not.toContainText("Dentista");
  await expect(due).not.toContainText("Hunter");
  await expect(due.getByText("Vencimento não informado",{exact:true})).toHaveCount(4);
  await page.getByRole("link",{name:"Faturas ›",exact:true}).click();
  await page.locator(".fatura-linha").filter({hasText:"815,85"}).click();
  await expect(page.locator(".hero .big")).toContainText("815,85");
  await expect(page.getByRole("note")).toContainText("816,65");
  await expect(page.getByRole("note")).toContainText("0,80");
  for(const amount of ["251,90","399,56","165,19"])await expect(page.locator(".fatura-total").filter({hasText:amount})).toHaveCount(1);
  await expect(page.getByText("Dentista",{exact:true})).toHaveCount(1);
  await expect(page.locator("main")).toContainText("SECCO");
  await page.screenshot({path:"../.local/situacao-fatura.png",fullPage:true});
});

test("investimentos mostram posição separada sem aporte ou rendimento inventado",async({page})=>{
  await page.goto("/investimentos");
  await expect(page.locator(".hero .big")).toContainText("634,00");
  await expect(page.locator("main")).toContainText("Reserva de emergência · Nubank");
  await expect(page.locator("main")).not.toContainText("Caixinha Mercado Pago");
  await expect(page.locator(".e-investment-flow")).toContainText("Não apurado");
  await expect(page.locator(".e-investment-flow")).not.toContainText("634,00");
  await expect(page.locator("main [role=alert]")).toHaveCount(0);
  await page.screenshot({path:"../.local/situacao-investimentos.png",fullPage:true});
});
