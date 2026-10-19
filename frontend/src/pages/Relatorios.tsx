import { useMemo, useState } from "react";
import { Evolucao, Rosca, type Fatia, type PontoEvolucao } from "../components/Graficos";
import { LoadError, SectionTitle, Summary } from "../components/essencial/Common";
import { useCategoryReport, useMonthHealth, useMonthlyReport } from "../lib/queries";
import { usePeriod } from "../lib/period";
import { OPCOES_FILTRO, useFiltroFinalidade } from "../lib/finalidade";
import { useLeituraDoGasto } from "../lib/natureza";
import { COR_OUTRAS } from "../lib/paleta";
import { formatMoney } from "../lib/format";

export default function Relatorios() {
  const {period,label} = usePeriod();
  const [purpose,setPurpose] = useFiltroFinalidade();
  const [reading,setReading] = useLeituraDoGasto();
  const [window,setWindow] = useState<6|12>(6);
  const category = useCategoryReport(purpose, reading==="vida"?"consumption":"todas");
  const monthly = useMonthlyReport(window,purpose);
  const health = useMonthHealth();
  const point = monthly.data?.months.find(p=>p.year===period.year&&p.month===period.month);
  const slices = useMemo<Fatia[]>(()=>{
    const r = category.data;
    if (!r) return [];
    return [...r.categories.map(c=>({id:String(c.category_id),nome:c.name,cor:c.color,valor:c.value,pct:c.pct})),...(r.others?[{id:"others",nome:`Outras (${r.others.count})`,cor:COR_OUTRAS,valor:r.others.value,pct:r.others.pct}]:[])];
  },[category.data]);
  const series = useMemo<PontoEvolucao[]>(()=> (monthly.data?.months??[]).map(m=>({chave:`${m.year}-${m.month}`,rotulo:new Date(m.year,m.month-1,1).toLocaleDateString("pt-BR",{month:"short"}).replace(".",""),mesLongo:new Date(m.year,m.month-1,1).toLocaleDateString("pt-BR",{month:"long",year:"numeric"}),valor:purpose!=="todos"&&m.expense===0&&m.expense_sem_finalidade>0?null:reading==="vida"?m.consumption:m.expense,atual:m.year===period.year&&m.month===period.month})),[monthly.data,period,purpose,reading]);
  const cashReliable = health.data?.trustworthy_balance !== false;
  return <div className="e-page">
    <SectionTitle title="Relatórios"/>
    <p className="e-page-sub">Como o dinheiro se movimentou em {label}.</p>
    <div className="e-filter" role="group" aria-label="Finalidade">{OPCOES_FILTRO.map(f=><button key={f.valor} className={purpose===f.valor?"on":""} aria-pressed={purpose===f.valor} onClick={()=>setPurpose(f.valor)}>{f.rotulo}</button>)}</div>
    <Summary items={[{label:"Entrou",value:point?.income},{label:"Gastou",value:point?.expense},{label:"Investiu",value:point?.investment},{label:"Sobrou no caixa",value:cashReliable?point?.cash_flow:null,text:"A conferir"}]} />
    <p className="e-note">Gasto considera compras no mês da compra ou parcela. Sobra é o fluxo de caixa do mês, após pagamentos e aportes; não é o saldo das contas. O filtro de finalidade se aplica aos gastos.</p>
    {!cashReliable&&<p className="e-note">Há movimentos que precisam de conferência para fechar o resultado de caixa.</p>}
    {purpose!=="todos"&&category.data?.sem_finalidade.count? <p className="e-note">{category.data.sem_finalidade.count} gastos sem finalidade ficaram fora deste filtro.</p>:null}
    <LoadError error={category.error||monthly.error||health.error}/>
    <SectionTitle title="Para onde foi"><div className="e-filter e-filter-inline" role="group" aria-label="Tipo de gasto"><button className={reading==="total"?"on":""} aria-pressed={reading==="total"} onClick={()=>setReading("total")}>Gasto total</button><button className={reading==="vida"?"on":""} aria-pressed={reading==="vida"} onClick={()=>setReading("vida")}>Custo de vida</button></div></SectionTitle>
    {category.data?.total ? <Rosca fatias={slices} total={category.data.total} rotuloCentro={reading==="vida"?"custo de vida":"gastos"}/> : <p className="e-empty">Nenhum gasto conhecido neste filtro.</p>}
    <SectionTitle title="Evolução dos gastos"><div className="e-filter e-filter-inline" role="group" aria-label="Período da evolução"><button className={window===6?"on":""} aria-pressed={window===6} onClick={()=>setWindow(6)}>6 meses</button><button className={window===12?"on":""} aria-pressed={window===12} onClick={()=>setWindow(12)}>12 meses</button></div></SectionTitle>
    {series.some(p=>p.valor!=null) ? <Evolucao pontos={series}/> : <p className="e-empty">A evolução aparece quando houver gastos registrados.</p>}
    {reading==="vida"&&point&&<p className="e-note">Fora do custo de vida: {formatMoney(point.asset_acquisition)} em aquisições e {formatMoney(point.financial)} em compromissos financeiros. Ambos permanecem no gasto total.</p>}
  </div>;
}
