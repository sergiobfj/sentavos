import { test, expect, type APIRequestContext, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const apiBase = process.env.SENTAVOS_E2E_API ?? "http://127.0.0.1:8012";
const localFixture = path.resolve(process.cwd(),"../.local/essencial-review-users.json");
const local = fs.existsSync(localFixture) ? JSON.parse(fs.readFileSync(localFixture,"utf8")) as {users:{email:string;read_only:boolean}[];password:string} : null;
const email = process.env.SENTAVOS_E2E_EMAIL ?? local?.users.find(u=>!u.read_only)?.email;
const demoEmail = process.env.SENTAVOS_E2E_DEMO_EMAIL ?? local?.users.find(u=>u.read_only)?.email;
const password = process.env.SENTAVOS_E2E_PASSWORD ?? local?.password;

async function login(page:Page, user=email) {
  if (!user || !password) throw new Error("Configure SENTAVOS_E2E_EMAIL e SENTAVOS_E2E_PASSWORD para a cópia local.");
  await page.goto("/");
  await page.locator("#l-email").fill(user);
  await page.locator("#l-senha").fill(password);
  await page.getByRole("button",{name:"Entrar"}).click();
  await expect(page.getByRole("navigation",{name:"Navegação principal"})).toBeVisible();
}
async function apiLogin(request:APIRequestContext) {
  const r = await request.post(`${apiBase}/auth/login`,{data:{email,senha:password}});
  expect(r.ok()).toBeTruthy();
  return {Authorization:`Bearer ${(await r.json()).access_token}`};
}

test.describe.serial("Sentavos Essencial com PostgreSQL local e APIs reais",()=>{
  test.beforeAll(async ({request})=>{
    const headers = await apiLogin(request);
    const accounts = await request.get(`${apiBase}/accounts/summary`,{headers});
    expect(accounts.ok()).toBeTruthy();
    if ((await accounts.json()).accounts.length) return;
    const now = new Date();
    const plan = await request.get(`${apiBase}/planning/month?year=${now.getFullYear()}&month=${now.getMonth()+1}`,{headers});
    expect(plan.ok()).toBeTruthy();
    const known = (await plan.json()).months[0].opening as number;
    const created = await request.post(`${apiBase}/accounts`,{headers,data:{name:"Conta de validação local",type:"checking",include_in_planning:true}});
    expect(created.ok()).toBeTruthy();
    const snapshot = await request.post(`${apiBase}/accounts/${(await created.json()).id}/snapshots`,{headers,data:{balance:known}});
    expect(snapshot.ok()).toBeTruthy();
  });

  test("1–3: saldo, contas pendentes e previsão aparecem no primeiro olhar",async ({page})=>{
    await login(page);
    await expect(page.locator(".e-primary strong")).toContainText("R$");
    await expect(page.locator(".e-projection-value")).toContainText("R$");
    await expect(page.locator(".e-summary")).toContainText("A receber");
    await expect(page.locator(".e-summary")).toContainText("A pagar");
    await expect(page.getByRole("navigation",{name:"Navegação principal"}).getByRole("link")).toHaveCount(4);
    const bounds=await page.locator(".e-primary strong").boundingBox();
    expect(bounds && bounds.y<350).toBeTruthy();
    await page.locator(".e-projection-value").click();
    await expect(page.getByRole("dialog")).toBeVisible();
  });

  test("4 e 8: registra Pix uma vez e edita a despesa",async ({page,request})=>{
    await login(page);
    const headers=await apiLogin(request);
    const now=new Date();const ym=`?year=${now.getFullYear()}&month=${now.getMonth()+1}`;
    const beforeRows=await(await request.get(`${apiBase}/transactions${ym}`,{headers})).json();
    const beforeIds=new Set(beforeRows.map((t:{id:number})=>t.id));
    await page.getByRole("button",{name:"Novo lançamento"}).click();
    await expect(page.locator("#quick-value")).toBeFocused();
    await page.locator("#quick-value").fill("25");
    await page.locator("#quick-category").selectOption({index:1});
    await expect(page.locator("#quick-origin")).not.toHaveValue("");
    await page.getByRole("button",{name:"Salvar",exact:true}).click();
    await expect(page.getByRole("status")).toContainText("Lançamento salvo");
    const after=await(await request.get(`${apiBase}/transactions${ym}`,{headers})).json();
    expect(after.length).toBe(beforeRows.length+1);
    const created=after.find((t:{id:number})=>!beforeIds.has(t.id));
    expect(created).toBeTruthy();
    await page.getByRole("navigation",{name:"Navegação principal"}).getByRole("link",{name:"Lançamentos"}).click();
    const row=page.locator(`.e-row[data-entry-key="t-${created.id}"]`);
    await expect(row).toBeVisible();
    await row.click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.locator("#t-desc").fill("Pix conferido no Essencial");
    await page.locator("#t-classe").selectOption("fixed");
    await page.getByRole("dialog").getByRole("button",{name:"Salvar",exact:true}).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    const updated=await(await request.get(`${apiBase}/transactions${ym}`,{headers})).json();
    expect(updated.find((t:{id:number})=>t.id===created.id)).toMatchObject({description:"Pix conferido no Essencial",expense_class:"fixed"});
    await expect(page.locator(`.e-row[data-entry-key="t-${created.id}"]`)).toContainText("Pix conferido no Essencial");
    const removed=await request.delete(`${apiBase}/transactions/${created.id}`,{headers});
    expect(removed.ok()).toBeTruthy();
  });

  test("5: encontra faturas e compromissos do próximo mês",async ({page})=>{
    await login(page);
    await page.getByRole("button",{name:"Próximo mês"}).click();
    await page.getByRole("navigation",{name:"Navegação principal"}).getByRole("link",{name:"Meu mês"}).click();
    await expect(page.locator(".e-summary")).toContainText("A pagar");
    await page.getByRole("link",{name:"Faturas",exact:true}).click();
    await expect(page).toHaveURL(/orcamento\?aba=faturas/);
  });

  test("cartão parcelado e aporte passam pelos fluxos financeiros existentes",async ({page,request})=>{
    await login(page);
    const headers=await apiLogin(request);
    await page.getByRole("button",{name:"Novo lançamento"}).click();
    await page.locator("#quick-value").fill("30");
    const card=await page.locator('#quick-origin option[value^="card:"]').first().getAttribute("value");
    expect(card).toBeTruthy();
    await page.locator("#quick-origin").selectOption(card!);
    await page.locator("#quick-category").selectOption({index:1});
    await page.locator("#quick-installments").selectOption("3");
    const purchasePromise=page.waitForResponse(r=>r.url().endsWith("/purchases")&&r.request().method()==="POST");
    await page.getByRole("button",{name:"Salvar",exact:true}).click();
    const purchaseResponse=await purchasePromise;
    expect(purchaseResponse.ok()).toBeTruthy();
    const purchase=await purchaseResponse.json();
    expect(purchase.installments).toBe(3);
    await expect(page.getByRole("dialog")).toHaveCount(0);
    const purchaseDelete=await request.delete(`${apiBase}/purchases/${purchase.id}`,{headers});
    expect(purchaseDelete.ok()).toBeTruthy();

    await page.getByRole("button",{name:"Novo lançamento"}).click();
    await page.getByRole("group",{name:"Tipo do lançamento"}).getByRole("button",{name:"Aporte"}).click();
    await page.locator("#quick-value").fill("20");
    await page.locator("#quick-category").selectOption({index:1});
    await page.locator("#quick-asset").selectOption({index:1});
    const movementPromise=page.waitForResponse(r=>r.url().endsWith("/investments/movements")&&r.request().method()==="POST");
    await page.getByRole("button",{name:"Salvar",exact:true}).click();
    const movementResponse=await movementPromise;
    expect(movementResponse.ok()).toBeTruthy();
    const movement=await movementResponse.json();
    expect(movement.type).toBe("contribution");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    const movementDelete=await request.delete(`${apiBase}/investments/movements/${movement.id}`,{headers});
    expect(movementDelete.ok()).toBeTruthy();
  });

  test("6 e 7: investimentos e comparação de três meses",async ({page})=>{
    await login(page);
    await page.getByRole("navigation",{name:"Navegação principal"}).getByRole("link",{name:"Investir"}).click();
    await expect(page.getByText("Saldo conhecido em investimentos")).toBeVisible();
    await expect(page.getByText("Não apurado")).toBeVisible();
    await page.goto("/planejamento/proximos");
    await expect(page.locator(".e-comparison-card")).toHaveCount(3);
    await expect(page.locator(".e-comparison-mobile")).toContainText("Fixas e faturas");
  });

  test("9: simulação de gasto não cria transação nem cenário",async ({page,request})=>{
    await login(page);
    const headers=await apiLogin(request);
    const now=new Date();const ym=`?year=${now.getFullYear()}&month=${now.getMonth()+1}`;
    const before=(await(await request.get(`${apiBase}/transactions${ym}`,{headers})).json()).length;
    await page.getByRole("button",{name:/E se eu gastar mais/}).click();
    await page.locator("#sg-valor").fill("200");
    await expect(page.getByRole("dialog")).toContainText("Depois da simulação");
    await page.getByRole("dialog").getByRole("button",{name:"Fechar"}).click();
    const after=(await(await request.get(`${apiBase}/transactions${ym}`,{headers})).json()).length;
    expect(after).toBe(before);
  });

  test("10: sai e entra novamente",async ({page})=>{
    await login(page);
    await page.getByRole("button",{name:"Configurações"}).click();
    await page.getByRole("button",{name:"Sair da conta"}).click();
    await expect(page.locator("#l-email")).toBeVisible();
    await login(page);
    await expect(page.locator(".e-primary")).toBeVisible();
  });

  test("demo continua somente leitura",async ({page})=>{
    test.skip(!demoEmail,"Conta demo não configurada");
    await login(page,demoEmail);
    await expect(page.getByRole("button",{name:"Novo lançamento"})).toHaveCount(0);
  });

  test("links antigos chegam à experiência principal",async ({page})=>{
    await login(page);
    await page.goto("/essencial.html");
    await expect.poll(()=>new URL(page.url()).pathname).toBe("/");
    await page.goto("/transacoes");
    await expect(page).toHaveURL(/\/lancamentos$/);
    await page.goto("/orcamento?aba=lancamentos&novo=1");
    await expect(page).toHaveURL(/\/lancamentos\?novo=1/);
    await expect(page.getByRole("dialog",{name:"Novo lançamento"})).toBeVisible();
    await page.getByRole("dialog").getByRole("button",{name:"Cancelar"}).click();
    await page.goto("/categorias");
    await expect(page.locator(".e-settings-detail").filter({hasText:"Categorias"})).toHaveAttribute("open","");
  });

  test("quatro telas cabem em 320, 360, 400, tablet e desktop",async ({page})=>{
    test.setTimeout(180000);
    await login(page);
    for (const width of [320,360,400,768,1440]) {
      await page.setViewportSize({width,height:860});
      for (const route of ["/","/lancamentos","/relatorios","/investimentos"]) {
        await page.goto(route);
        await expect(page.locator(".appbar")).toBeVisible();
        expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
      }
    }
  });
});
