import {test, expect, type APIRequestContext, type Page} from "@playwright/test";
import fs from "node:fs";

const fixture = JSON.parse(fs.readFileSync("../.local/saldos-users.json", "utf8"));
const api = "http://127.0.0.1:8014";
const now = new Date();
const today = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,"0")}-${String(now.getDate()).padStart(2,"0")}`;
const ym = `?year=${now.getFullYear()}&month=${now.getMonth()+1}`;
let headers: Record<string,string>, account:number, asset:number, expense:number, plan:number, familyCard:number, installment:number, invoice:number;
async function post(request:APIRequestContext,path:string,data:unknown) {
  const r=await request.post(api+path,{headers,data});expect(r.ok(),await r.text()).toBeTruthy();return r.json();
}
async function get(request:APIRequestContext,path:string) {
  const r=await request.get(api+path,{headers});expect(r.ok(),await r.text()).toBeTruthy();return r.json();
}
async function login(page:Page) {
  await page.goto("/");await page.locator("#l-email").fill(fixture.email);await page.locator("#l-senha").fill(fixture.password);
  await page.getByRole("button",{name:"Entrar",exact:true}).click();await expect(page.locator(".e-primary")).toBeVisible();
}

test.describe.serial("Saldos, investimento, Família e ícones — PostgreSQL sintético",()=>{
  test.beforeAll(async({request})=>{
    const auth=await request.post(api+"/auth/login",{data:{email:fixture.email,senha:fixture.password}});
    expect(auth.ok()).toBeTruthy();headers={Authorization:`Bearer ${(await auth.json()).access_token}`};
    expense=(await post(request,"/categories",{name:"Despesas",type:"expense",color:"#c5b289",icon:"x"})).id;
    const income=(await post(request,"/categories",{name:"Entradas",type:"income",color:"#c5b289",icon:"x"})).id;
    const investment=(await post(request,"/categories",{name:"Investimentos",type:"investment",color:"#c5b289",icon:"x"})).id;
    account=(await post(request,"/accounts",{name:"Nubank",type:"checking"})).id;
    await post(request,`/accounts/${account}/snapshots`,{balance:684.39,observed_at:"2026-10-11T21:45:00Z"});
    await post(request,"/transactions",{description:"Recebimento sem conta",date:today,amount_paid:720,category_id:income});
    asset=(await post(request,"/assets",{name:"Caixinha Nubank",asset_class:"fixed_income"})).id;
    const mp=(await post(request,"/assets",{name:"Caixinha Mercado Pago",asset_class:"fixed_income"})).id;
    await post(request,"/investments/movements",{asset_id:mp,category_id:investment,type:"contribution",amount:800,date:"2026-10-06"});
    const snapshot=await request.put(api+"/assets/snapshots",{headers,data:{asset_id:mp,year:2026,month:10,value:0,observed_on:today,reconciliation_note:"Resgate Hunter sem comprovante"}});
    expect(snapshot.ok()).toBeTruthy();
    plan=(await post(request,"/investments/plans",{type:"contribution",amount:550,date:today,asset_id:asset,category_id:investment,account_id:account,description:"Aporte Nubank sintético"})).id;
    familyCard=(await post(request,"/cards",{name:"Nubank Família",finalidade:"familia",closing_day:25,due_day:2})).id;
    const purchase=await post(request,"/purchases",{description:"Consultório Michele",card_id:familyCard,category_id:expense,total_amount:561,installments:5,purchase_date:"2026-09-10"});
    const rows=await get(request,"/transactions"+ym);
    const row=rows.find((t:{purchase_id:number;installment_no:number})=>t.purchase_id===purchase.id&&t.installment_no===2);
    installment=row.id;invoice=row.invoice_id;
    await post(request,"/purchases",{description:"Outra compra Família",card_id:familyCard,category_id:expense,total_amount:200,installments:1,purchase_date:"2026-10-01"});
  });

  test("saldo observado datado e atualização pendente; saldo real sem criar receita",async({page,request})=>{
    await login(page);
    await expect(page.locator(".e-primary")).toContainText("Saldo observado");
    await expect(page.locator(".e-primary")).toContainText("11/10");
    await expect(page.locator(".e-primary")).toContainText("Atualização pendente");
    const before=(await get(request,"/transactions"+ym)).length;
    await page.locator(".e-primary button").click();
    const field=page.getByRole("textbox",{name:"Saldo de Nubank agora"});
    await field.fill("1214,71");await field.press("Enter");
    await expect(page.getByRole("dialog")).toContainText("1.214,71");
    await page.getByRole("button",{name:"Fechar",exact:true}).click();
    await expect(page.locator(".e-primary strong")).toContainText("1.214,71");
    expect((await get(request,"/transactions"+ym)).length).toBe(before);
  });

  test("confirmar aporte uma vez; fluxo 1350 e posição sem observação explicitada",async({page,request})=>{
    await login(page);await page.getByRole("navigation").getByRole("link",{name:"Investir",exact:true}).click();
    await expect(page.locator(".e-investment-flow")).toContainText("800,00");
    await post(request,`/investments/plans/${plan}/confirm`,{date:today});
    await post(request,`/investments/plans/${plan}/confirm`,{date:today});
    await page.reload();
    await expect(page.locator(".e-investment-flow")).toContainText("1.350,00");
    await expect(page.locator(".hero")).toContainText("Posição a atualizar");
    const row=page.locator(".list a.row").filter({hasText:"Caixinha Nubank"});
    await expect(row).toContainText("Sem saldo observado");
    await expect(row).toContainText("550,00");
    expect((await get(request,"/investments/movements"+ym)).length).toBe(2);
    expect((await get(request,"/months/summary"+ym)).money_now).toBe(664.71);
    await page.screenshot({path:"../.local/investimentos-saldos.png",fullPage:true});
  });

  test("atribuir apenas parcela 2/5 ao pessoal mantém cartão Família e pagamento parcial",async({page,request})=>{
    await login(page);await page.getByRole("navigation").getByRole("link",{name:"Lançamentos",exact:true}).click();
    await page.locator(`[data-entry-key="t-${installment}"]`).click();
    await expect(page.getByRole("dialog")).toContainText("Nubank Família");
    await page.getByRole("group",{name:"Responsabilidade desta parcela",exact:true}).getByRole("button",{name:"Pessoal",exact:true}).click();
    await page.getByRole("button",{name:"Salvar responsabilidade",exact:true}).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    const row=(await get(request,"/transactions"+ym)).find((t:{id:number})=>t.id===installment);
    expect(row).toMatchObject({finalidade:"pessoal",card_id:familyCard,installment_no:2,installments:5,amount_paid:112.2});
    await post(request,`/invoices/${invoice}/payments`,{date:today,amount:112.2,account_id:account,occurred_at:new Date().toISOString()});
    const inv=await get(request,`/invoices/${invoice}`);expect(inv.remaining).toBe(200);expect(inv.status).not.toBe("paga");
    expect((await get(request,"/months/summary"+ym)).money_now).toBe(552.51);
  });

  test("informar posição observada atualiza Investir e preserva o aporte único",async({page,request})=>{
    await login(page);await page.goto("/patrimonio");
    await expect(page.locator(".hero")).toContainText("Patrimônio observado · parcial");
    const field=page.getByRole("textbox",{name:"Saldo de Caixinha Nubank",exact:true});
    await field.fill("550,00");await field.press("Enter");
    await expect(field).toHaveValue("550");
    await page.getByRole("navigation",{name:"Navegação principal"}).getByRole("link",{name:"Investir",exact:true}).click();
    await expect(page.locator(".hero .big")).toContainText("550,00");
    await expect(page.locator(".e-investment-flow")).toContainText("1.350,00");
    const r=await get(request,"/investments/summary"+ym);
    expect(r.total).toBe(550);expect(r.redeemed).toBe(0);expect(r.yield_status).toBe("nao_apurado");
  });

  test("três compras no Nubank pessoal preservam caixa e ciclo próprio",async({request})=>{
    const before=(await get(request,"/months/summary"+ym)).money_now;
    const card=(await post(request,"/cards",{name:"Nubank pessoal",finalidade:"pessoal",closing_day:25,due_day:2})).id;
    for(const [description,total_amount] of [["Transporte",60.85],["Patinetes Jet",22.17],["Almoço com Bia",40]])
      await post(request,"/purchases",{description,total_amount,installments:1,purchase_date:today,card_id:card,category_id:expense});
    const rows=(await get(request,"/transactions"+ym)).filter((t:{card_id:number})=>t.card_id===card);
    expect(rows).toHaveLength(3);expect((await get(request,`/invoices/${rows[0].invoice_id}`)).total).toBe(123.02);
    expect((await get(request,"/months/summary"+ym)).money_now).toBe(before);
  });

  for(const colorScheme of ["light","dark"] as const) test(`favicon e manifest no build em tema ${colorScheme}`,async({page,request})=>{
    await page.emulateMedia({colorScheme});await page.goto("/");
    const icons=await page.locator('link[rel="icon"]').evaluateAll(els=>els.map(e=>e.getAttribute("href")));
    expect(icons).toContain("/favicon-white-v1.png");expect(icons).toContain("/favicon-white-v1.ico");
    const manifest=await(await request.get("/manifest.webmanifest?v=white-v1")).json();
    expect(manifest.icons).toHaveLength(3);
    for(const icon of manifest.icons) { expect(icon.src).toContain("white-v1");expect((await request.get(icon.src)).headers()["content-type"]).toContain("image/png"); }
    expect((await request.get("/apple-touch-icon-white-v1.png")).ok()).toBeTruthy();
  });
});
