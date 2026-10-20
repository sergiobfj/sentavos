// Executar da raiz. Somente API e usuários sintéticos locais.
const {chromium,request}=require('../../node_modules/playwright-core');
const fs=require('node:fs');
const path=require('node:path');
const api='http://127.0.0.1:8014';
const file='.local/visual-v2-users.json';
const shots='docs/refinamento-visual-v2';
(async()=>{
 const fixture=JSON.parse(fs.readFileSync(file,'utf8'));
 const client=await request.newContext();
 const auth=await client.post(api+'/auth/login',{data:{email:fixture.email,senha:fixture.password}});
 if(!auth.ok()) throw Error('Local fixture login failed');
 const token=(await auth.json()).access_token;
 const headers={Authorization:`Bearer ${token}`};
 async function post(url,data){const r=await client.post(api+url,{headers,data});if(!r.ok())throw Error(url+': '+await r.text());return r.json();}
 const today=new Date().toLocaleDateString('sv-SE',{timeZone:'America/Sao_Paulo'});
 const [year,month]=today.split('-').map(Number);
 if(process.argv.includes('seed')){
  if(fixture.expense) throw Error('Fixture já preparada. Execute prepare.py para criar outro usuário sintético.');
  const expense=await post('/categories',{name:'Dia a dia',type:'expense',color:'#A79AF5',icon:'•'});
  const income=await post('/categories',{name:'Salário',type:'income',color:'#67C7A2',icon:'+'});
  const investment=await post('/categories',{name:'Investimentos',type:'investment',color:'#8CAEDC',icon:'↗'});
  const account=await post('/accounts',{name:'Conta principal',type:'checking'});
  await post(`/accounts/${account.id}/snapshots`,{balance:4200,observed_at:new Date(Date.now()-120000).toISOString()});
  const asset=await post('/assets',{name:'Reserva de emergência',asset_class:'fixed_income'});
  await client.put(api+'/assets/snapshots',{headers,data:{asset_id:asset.id,year,month,value:2000}});
  for(const [description,day,value,type,planned] of [
   ['Salário',5,5800,'income',false],['Mercado e compras da semana',18,248.90,'expense',false],
   ['Café da tarde',18,18.50,'expense',false],['Internet',23,99.90,'expense',true],
   ['Seguro da Hunter',25,94,'expense',true],['Academia',12,120,'expense',false],
   ['Aporte na reserva',10,300,'investment',false],['Freelance de outubro',28,850,'income',true]
  ])await post('/transactions',{description,date:`${year}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`,[planned?'amount_planned':'amount_paid']:value,category_id:{expense:expense.id,income:income.id,investment:investment.id}[type],payment_method:'cash',account_id:account.id,expense_class:type==='expense'?'variable':null});
  const card=await post('/cards',{name:'Cartão principal',closing_day:25,due_day:5});
  await post('/purchases',{card_id:card.id,category_id:expense.id,description:'Fone de ouvido',purchase_date:`${year}-${String(month).padStart(2,'0')}-18`,total_amount:387,installments:3,expense_class:'variable'});
  for(const data of [
   {description:'Proteção veicular',amount:94,prefill:{bill_visibility:'quote',confirmed:false},question:'Cotação de proteção: confirmar se substitui o Seguro da Hunter antes de registrar.'},
   {description:'Manutenção da moto',amount:600,prefill:{installments:3,amount:200},question:'Conferir as datas de cada parcela.'},
   {description:'Serviço com valor a confirmar',amount:null}
  ])await post('/reconciliation',{year,month,kind:'obrigacao',...data});
  await post('/investments/plans',{type:'contribution',date:today,amount:400,asset_id:asset.id,account_id:account.id,category_id:investment.id});
  Object.assign(fixture,{expense:expense.id,income:income.id,investment:investment.id,account:account.id,asset:asset.id,year,month});
  fs.writeFileSync(file,JSON.stringify(fixture));
 }
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:400,height:860}});
 await page.addInitScript(({token,year,month})=>{localStorage.setItem('sentavos:token',token);localStorage.setItem('sentavos:period',`${year}-${String(month).padStart(2,'0')}`)},{token,year,month});
 fs.mkdirSync(shots,{recursive:true});
 const phase=process.argv.includes('after')?'depois':'antes';
 for(const width of phase==='depois'?[320,360,400,768,1440]:[360,400]){
  await page.setViewportSize({width,height:860});
  for(const [route,name,ready] of [['/lancamentos','lancamentos','.e-row'],['/contas-a-pagar','contas','.e-bill-row']]){
   await page.goto('http://127.0.0.1:5184'+route);await page.locator(ready).first().waitFor();await page.evaluate(()=>document.fonts.ready);await page.screenshot({path:path.join(shots,`${name}-${phase}-${width}.png`),fullPage:true,animations:'disabled'});
   console.log(JSON.stringify({phase,width,route,overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)}));
  }
 }
 if(phase==='depois'){
  await page.setViewportSize({width:400,height:860});
  for(const [route,name,ready] of [['/','meu-mes','.e-primary strong'],['/investimentos','investir','.e-row'],['/relatorios','relatorios','.e-summary']]){
   await page.goto('http://127.0.0.1:5184'+route);await page.locator(ready).first().waitFor();await page.screenshot({path:path.join(shots,`${name}-depois-400.png`),fullPage:true,animations:'disabled'});
  }
  await page.goto('http://127.0.0.1:5184/lancamentos');await page.getByRole('button',{name:'Novo lançamento',exact:true}).click();await page.getByRole('dialog').waitFor();await page.screenshot({path:path.join(shots,'formulario-depois-400.png'),animations:'disabled'});
 }
 await browser.close();await client.dispose();
})();
