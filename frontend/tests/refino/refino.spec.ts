import {test,expect,type Page,type APIRequestContext} from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const fixture=JSON.parse(fs.readFileSync(path.resolve("../.local/refino-users.json"),"utf8"));
const api="http://127.0.0.1:8014";
const shots=path.resolve("../docs/refino-ux-previsoes");
const today=new Date().toLocaleDateString("sv-SE",{timeZone:"America/Sao_Paulo"});
const ym=`year=${Number(today.slice(0,4))}&month=${Number(today.slice(5,7))}`;
let headers:Record<string,string>,account:number,asset:number,expense:number,investment:number;

async function post(request:APIRequestContext,url:string,data:unknown) {
  const r=await request.post(api+url,{headers,data});expect(r.ok(),await r.text()).toBeTruthy();return r.json();
}
async function summary(request:APIRequestContext) {return (await request.get(`${api}/months/summary?${ym}`,{headers})).json();}
async function login(page:Page,email=fixture.email) {
  await page.goto("/");await page.locator("#l-email").fill(email);await page.locator("#l-senha").fill(fixture.password);
  await page.getByRole("button",{name:"Entrar",exact:true}).click();
  await expect(page.locator(".e-primary strong")).toBeVisible();
  await expect(page.locator(".e-primary strong")).not.toHaveText("");
}

test.describe.serial("Refino com API e PostgreSQL reais, dados sintéticos",()=>{
  test.beforeAll(async({request})=>{
    fs.mkdirSync(shots,{recursive:true});
    const auth=await request.post(api+"/auth/login",{data:{email:fixture.email,senha:fixture.password}});
    expect(auth.ok()).toBeTruthy();headers={Authorization:`Bearer ${(await auth.json()).access_token}`};
    expense=(await post(request,"/categories",{name:"Dia a dia",type:"expense",color:"#c5b289",icon:"•"})).id;
    const income=(await post(request,"/categories",{name:"Salário",type:"income",color:"#a3c9ac",icon:"+"})).id;
    investment=(await post(request,"/categories",{name:"Investimentos",type:"investment",color:"#b4c5b5",icon:"↗"})).id;
    account=(await post(request,"/accounts",{name:"Conta de validação",type:"checking"})).id;
    await post(request,`/accounts/${account}/snapshots`,{balance:1000,observed_at:new Date(Date.now()-120000).toISOString()});
    asset=(await post(request,"/assets",{name:"Caixinha de Emergência",asset_class:"fixed_income"})).id;
    await request.put(api+"/assets/snapshots",{headers,data:{asset_id:asset,year:Number(today.slice(0,4)),month:Number(today.slice(5,7)),value:0}});
    await post(request,"/transactions",{description:"Salário previsto",date:today,amount_planned:500,category_id:income});
    for(const [description,amount,expense_class] of [["Internet",60,"fixed"],["Academia",120,"fixed"],["Compra Pix",40,"variable"]] as const)
      await post(request,"/transactions",{description,date:today,amount_planned:amount,category_id:expense,expense_class,payment_method:"cash",account_id:account});
  });

  test("criar aporte previsto mantém caixa e posição, atualiza os cinco números",async({page,request})=>{
    await login(page);
    await page.getByRole("button",{name:"Novo lançamento",exact:true}).click();
    await expect(page.locator("#quick-value")).toBeFocused();
    await page.getByRole("button",{name:"Aporte",exact:true}).click();
    await page.locator("#quick-value").fill("400,00");
    await page.getByRole("switch",{name:"Ainda é previsto"}).check();
    await page.locator("#quick-asset").selectOption(String(asset));
    await page.getByRole("button",{name:"Planejar aporte",exact:true}).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByRole("status")).toHaveText("Previsão salva");
    await expect(page.locator(".e-projection-value")).toContainText("880,00");
    await expect(page.locator(".e-to-invest")).toContainText("400,00");
    const r=await summary(request);
    expect([r.money_now,r.to_receive,r.to_pay,r.contributed,r.to_invest,r.projected]).toEqual([1000,500,220,0,400,880]);
  });

  for(const width of [320,360,400,768,1440]) test(`responsivo ${width}px, primeira dobra e capturas`,async({page})=>{
    await page.setViewportSize({width,height:width<700?740:960});await login(page);
    await expect(page.locator(".e-to-invest")).toContainText("400,00");
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
    for(const selector of [".e-primary strong",".e-projection-value",".e-summary"]){
      const box=await page.locator(selector).boundingBox();expect(box).not.toBeNull();expect(box!.y+box!.height).toBeLessThan(600);
    }
    await expect(page.getByText("Comparar meses",{exact:true})).toHaveCount(0);
    if(width===360||width===400){
      await page.screenshot({path:path.join(shots,`meu-mes-${width}.png`),fullPage:true,animations:"disabled"});
      await page.getByRole("button",{name:"Novo lançamento",exact:true}).click();
      await page.screenshot({path:path.join(shots,`formulario-${width}.png`),animations:"disabled"});
      const modal=await page.getByRole("dialog").boundingBox();expect(modal!.height).toBeLessThan(560);
      await page.setViewportSize({width,height:420});
      const save=await page.getByRole("dialog").getByRole("button",{name:"Salvar",exact:true}).boundingBox();
      expect(save!.y+save!.height).toBeLessThanOrEqual(420);
      await page.setViewportSize({width,height:740});
      await page.getByText("Mais detalhes",{exact:true}).click();
      await page.screenshot({path:path.join(shots,`formulario-detalhes-${width}.png`),animations:"disabled"});
      await page.getByRole("button",{name:"Fechar",exact:true}).click();
      await page.getByRole("navigation",{name:"Navegação principal"}).getByRole("link",{name:"Contas",exact:true}).click();
      await expect(page.locator(".e-list").first()).toContainText("Internet");
      await expect(page.locator(".e-list").first()).toContainText("Academia");
      await expect(page.locator(".e-list").first()).toContainText("Compra Pix");
      await page.screenshot({path:path.join(shots,`contas-${width}.png`),fullPage:true,animations:"disabled"});
      await page.getByRole("navigation",{name:"Navegação principal"}).getByRole("link",{name:"Investir",exact:true}).click();
      await expect(page.locator(".e-row").filter({hasText:"Previsto"})).toContainText("400,00");
      await page.screenshot({path:path.join(shots,`investir-${width}.png`),fullPage:true,animations:"disabled"});
    }
  });

  test("editar, confirmar e repetir não duplicam o aporte",async({page,request})=>{
    await login(page);await page.goto("/investimentos");
    await page.locator(".e-row").filter({hasText:"Previsto"}).click();
    await page.getByRole("button",{name:"Editar previsão",exact:true}).click();
    await page.locator("#quick-value").fill("350,00");
    await page.getByRole("button",{name:"Salvar previsão",exact:true}).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.locator(".e-row").filter({hasText:"Previsto"})).toContainText("350,00");
    await page.locator(".e-row").filter({hasText:"Previsto"}).click();
    await page.getByRole("checkbox",{name:"O dinheiro já foi movimentado"}).check();
    await page.getByRole("button",{name:"Confirmar realização",exact:true}).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.locator(".e-row").filter({hasText:"Previsto"})).toHaveCount(0);
    let r=await summary(request);expect([r.money_now,r.contributed,r.to_invest,r.projected]).toEqual([650,350,0,930]);
    const plans=await(await request.get(api+`/investments/plans?${ym}`,{headers})).json();
    await post(request,`/investments/plans/${plans[0].id}/confirm`,{date:today});
    r=await summary(request);expect(r.contributed).toBe(350);
  });

  test("confirmação concorrente no Postgres gera um único movimento",async({request})=>{
    const p=await post(request,"/investments/plans",{type:"contribution",date:today,amount:50,asset_id:asset,account_id:account,category_id:investment});
    const result=await Promise.all([post(request,`/investments/plans/${p.id}/confirm`,{date:today}),post(request,`/investments/plans/${p.id}/confirm`,{date:today})]);
    expect(result[0].movement_id).toBe(result[1].movement_id);
    const r=await summary(request);expect(r.contributed).toBe(400);expect(r.money_now).toBe(600);
  });

  test("cancelamento, despesa prevista e cartão sem baixa imediata",async({page,request})=>{
    const p=await post(request,"/investments/plans",{type:"redemption",date:today,amount:200});
    const before=await summary(request);expect(before.money_now).toBe(600);
    await post(request,`/investments/plans/${p.id}/cancel`,{});
    expect((await summary(request)).projected).toBe(before.projected-200);
    await login(page);await page.getByRole("button",{name:"Novo lançamento",exact:true}).click();
    await page.locator("#quick-value").fill("75,00");await page.locator("#quick-category").selectOption(String(expense));
    await page.getByRole("switch",{name:"Ainda é previsto"}).check();
    await page.getByRole("button",{name:"Salvar previsão",exact:true}).click();
    await expect(page.locator(".e-summary")).toContainText("295,00");
    expect((await summary(request)).money_now).toBe(600);
    const card=await post(request,"/cards",{name:"Mercado Pago",closing_day:8,due_day:13});
    await post(request,"/purchases",{card_id:card.id,category_id:expense,description:"Emplacamento",total_amount:904,installments:4,purchase_date:today,expense_class:"variable"});
    expect((await summary(request)).money_now).toBe(600);
    await page.goto("/");await page.getByRole("button",{name:/Despesas variáveis/}).click();
    await expect(page.locator(".e-group-detail")).toContainText("No cartão");
  });

  test("demo, relatórios, configuração e logout preservados",async({page})=>{
    await login(page);await page.goto("/relatorios");await expect(page.locator("main")).toBeVisible();
    await page.goto("/configuracoes");
    for(const text of ["Compromissos e recorrências","Conferir mês","Simulações salvas"])await expect(page.getByText(text,{exact:true})).toHaveCount(0);
    await page.getByRole("button",{name:"Sair da conta",exact:true}).click();await expect(page.locator("#l-email")).toBeVisible();
    await login(page,fixture.demo);await expect(page.getByRole("button",{name:"Novo lançamento",exact:true})).toHaveCount(0);
    await expect(page.getByText("Modo demonstração.",{exact:true})).toBeVisible();
  });

  test("mês com muitos registros e valores grandes continua legível em 320px",async({page,request})=>{
    const before=await summary(request);
    for(let n=0;n<20;n++)await post(request,"/transactions",{date:today,description:`Despesa prevista de descrição longa para validação ${n}`,amount_planned:999999.99,category_id:expense,payment_method:"cash",account_id:account,expense_class:"variable"});
    const after=await summary(request);
    expect(after.to_pay).toBeCloseTo(before.to_pay+20*999999.99,2);
    expect(after.money_now).toBe(before.money_now);
    await page.setViewportSize({width:320,height:740});await login(page);
    await expect(page.locator(".e-summary")).toContainText("20.000.");
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
    await page.goto("/contas-a-pagar");await expect(page.locator(".e-list").first().locator(".e-bill-row")).toHaveCount(after.due.length);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
  });
});
