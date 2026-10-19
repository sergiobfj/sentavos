import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { CalculoSheet, ContasSheet, ItensSheet, SimularGastoSheet } from "../components/planejamento/Folhas";
import { EntryEditor, LoadError, MonthGroup, SectionTitle, Summary, transactionLine, type FinancialLine } from "../components/essencial/Common";
import { useAccountsSummary, useCategories, useInvestmentSummary, usePlanningHorizon, usePlanningMonth, useTransactions } from "../lib/queries";
import { currentPeriod, formatPeriod, usePeriod } from "../lib/period";
import { useAuth } from "../lib/auth";
import { formatMoney } from "../lib/format";
import type { Transaction } from "../lib/types";
import type { PlanoItem } from "../lib/tiposPlanejamento";

function itemLine(item: PlanoItem, navigate: (path: string) => void): FinancialLine {
  const target = item.commitment_id != null ? `/planejamento/compromissos?id=${item.commitment_id}` : item.invoice_id != null ? "/orcamento?aba=faturas" : null;
  return { key: item.key, description: item.description, date: item.date, value: item.remaining, income: item.direction === "entrada", detail: item.detail ?? undefined, status: item.status === "vencido" ? "Vencido" : item.certainty === "estimado" ? "A confirmar" : item.direction === "entrada" ? "A receber" : "A pagar", onClick: target ? () => navigate(target) : undefined };
}

export default function MeuMes() {
  const { period, isCurrent } = usePeriod();
  const { sessao } = useAuth();
  const navigate = useNavigate();
  const [editing, setEditing] = useState<Transaction | null>(null);
  const [sheet, setSheet] = useState<"calculo" | "contas" | "saidas" | "simular" | null>(null);
  const accounts = useAccountsSummary();
  const planning = usePlanningMonth(period, null);
  const planningNow = usePlanningMonth(currentPeriod(), null);
  const investments = useInvestmentSummary(currentPeriod());
  const transactions = useTransactions();
  const categories = useCategories(true);
  const now = currentPeriod();
  const distance = (period.year - now.year) * 12 + period.month - now.month;
  const horizon = usePlanningHorizon(Math.min(Math.max(distance + 4, 4), 24));
  const month = planning.data?.months.find(m => m.year === period.year && m.month === period.month);
  const accountsKnown = (accounts.data?.accounts ?? []).filter(a => !a.archived && !a.restricted && a.balance != null);
  const legacyBalance = planningNow.data?.months[0]?.opening_source === "saldos" && planningNow.data.accounts.some(a=>a.included&&!a.stale&&a.as_of!=null) ? planningNow.data.months[0].opening : null;
  const moneyNow = accountsKnown.length ? accounts.data?.free : legacyBalance;
  const legacyDate = planningNow.data?.accounts.filter(a=>a.included&&!a.stale&&a.as_of!=null).map(a=>a.observed_on ?? a.as_of).sort()[0];
  const stale = (!!accounts.data && (accounts.data.stale_count > 0 || accounts.data.without_balance_count > 0 || accounts.data.maybe_incomplete || accounts.data.unassigned_movements > 0 || accounts.data.to_distribute !== 0)) || (!!planningNow.data?.balance_warning.desatualizado && !accountsKnown.length);
  const hasOpening = !!planningNow.data?.accounts.some(a => a.included && !a.stale && a.quality !== "sem_saldo" && a.as_of != null);
  const projected = month && hasOpening ? month.available : null;
  const catMap = useMemo(() => new Map((categories.data ?? []).map(c => [c.id,c])), [categories.data]);
  const realized = useMemo(() => (transactions.data ?? []).filter(t => t.amount_paid != null).sort((a,b) => b.date.localeCompare(a.date) || b.id-a.id), [transactions.data]);
  const paid = (type: string, expenseClass?: "fixed" | "variable" | null) => realized.filter(t => {
    const c = catMap.get(t.category_id);
    return c?.type === type && (type !== "expense" || (t.effective_expense_class ?? null) === expenseClass);
  });
  const pending = (month?.items ?? []).filter(i => i.status !== "pago" && i.remaining > 0);
  const incomes = paid("income");
  const fixed = paid("expense", "fixed");
  const variable = paid("expense", "variable");
  const unclassified = paid("expense", null);
  const invested = paid("investment");
  const contributed = invested.reduce((sum,t)=>sum+Math.max(t.amount_paid??0,0),0);
  const redeemed = invested.reduce((sum,t)=>sum+Math.max(-(t.amount_paid??0),0),0);
  const dueIncome = pending.filter(i => i.direction === "entrada" && i.category_type !== "investment");
  const dueFixed = pending.filter(i => i.direction === "saida" && (i.expense_class === "fixed" || i.source === "cartao"));
  const dueVariable = pending.filter(i => i.direction === "saida" && i.source !== "cartao" && i.expense_class !== "fixed" && i.category_type !== "investment");
  const dueInvestment = pending.filter(i => i.category_type === "investment");
  const toLines = (ts: Transaction[], items: PlanoItem[]) => [...items.map(i => itemLine(i,navigate)), ...ts.map(t => transactionLine(t,catMap.get(t.category_id),() => setEditing(t)))];
  const sumPaid = (ts: Transaction[]) => ts.reduce((sum,t) => sum + (t.amount_paid ?? 0),0);
  const sumDue = (items: PlanoItem[]) => items.reduce((sum,i) => sum + i.remaining,0);
  const preview = (horizon.data?.months ?? []).filter(m => (m.year - period.year)*12 + m.month-period.month > 0).slice(0,3);
  const noBalances = !!accounts.data && moneyNow == null;
  const investmentUnknown = !!investments.data?.stale_names.length && investments.data.total === 0;

  return <div className="e-month">
    <div className="e-lead">
      <section className="e-primary" aria-labelledby="e-money-label">
        <p id="e-money-label">{stale ? "Dinheiro conhecido nas contas" : "Meu dinheiro agora"}</p>
        <strong className="tnum">{moneyNow == null ? "—" : formatMoney(moneyNow)}</strong>
        <button className="e-subtle" onClick={() => setSheet("contas")}>{noBalances ? "Informe um saldo para começar" : stale ? `Saldo conhecido${legacyDate && legacyDate.length>=10 ? ` em ${legacyDate.slice(8,10)}/${legacyDate.slice(5,7)}` : ""} · conferir contas` : "Ver saldos das contas"} ›</button>
      </section>
      <section className="e-projection" aria-labelledby="e-projection-label">
        <p id="e-projection-label">{isCurrent ? "Previsão depois das contas" : `Previsão para ${formatPeriod(period)}`}</p>
        <button onClick={() => setSheet("calculo")} disabled={!month} className="e-projection-value tnum">{projected == null ? "—" : formatMoney(projected)} <span>›</span></button>
        {month && <small>{projected == null ? "Saldo de partida ainda não conhecido" : month.reserved > 0 ? `Já considera ${formatMoney(month.reserved)} reservados` : "Ver cálculo"}</small>}
      </section>
    </div>
    <LoadError error={accounts.error || planning.error || investments.error || transactions.error} />
    <Summary items={[{label:"A receber",value:month?.income},{label:"A pagar",value:month?.expense,onClick:()=>setSheet("saidas")},{label:"Investido",value:investmentUnknown?null:investments.data?.total,text:investmentUnknown?"A atualizar":undefined,to:"/investimentos"}]} />
    {(planning.data?.balance_warning.desatualizado || stale) && <p className="e-note">Previsão baseada nos saldos conhecidos. {accounts.data?.to_distribute ? "Parte do saldo agregado ainda precisa ser distribuída. " : ""}Confira as contas para aumentar a precisão.</p>}
    <div className="e-groups">
      <MonthGroup title="Entradas" summary={`${formatMoney(sumPaid(incomes))} recebido · ${formatMoney(sumDue(dueIncome))} a receber`} lines={toLines(incomes,dueIncome)} />
      <MonthGroup title="Despesas fixas" summary={`${formatMoney(sumPaid(fixed))} pago · ${formatMoney(sumDue(dueFixed))} a pagar`} lines={toLines(fixed,dueFixed)} />
      <MonthGroup title="Despesas variáveis" summary={`${formatMoney(sumPaid(variable)+sumPaid(unclassified))} gasto · ${formatMoney(sumDue(dueVariable))} pendente`} lines={toLines([...variable,...unclassified],dueVariable)} note={unclassified.length ? `${unclassified.length} ${unclassified.length===1?"despesa precisa":"despesas precisam"} de classificação.` : undefined} />
      <MonthGroup title="Investimentos" summary={`${investmentUnknown?"Saldo a atualizar":investments.data?`${formatMoney(investments.data.total)} guardado`:"Saldo não carregado"} · ${formatMoney(contributed)} aportado · ${formatMoney(redeemed)} resgatado`} lines={toLines(invested,dueInvestment)} note={month?.reserves.some(r=>r.source==="aporte") ? "Aportes planejados entram como reserva, sem virar despesa." : undefined} />
    </div>
    <SectionTitle title="Próximos meses"><Link to="/planejamento/proximos">Comparar meses ›</Link></SectionTitle>
    <div className="e-preview">{preview.map(m => <Link key={`${m.year}-${m.month}`} to="/planejamento/proximos" className="e-preview-month"><strong>{formatPeriod({year:m.year,month:m.month})}</strong><span>Entra {formatMoney(m.income)} · Sai {formatMoney(m.expense)}</span><b className="tnum">Sobra {hasOpening ? formatMoney(m.available) : "—"}</b></Link>)}{!preview.length && <p className="e-empty">Próximos meses ainda não disponíveis.</p>}</div>
    <div className="e-secondary-links"><Link to="/planejamento">Ver planejamento detalhado</Link><Link to="/orcamento?aba=faturas">Faturas</Link><Link to="/planejamento/compromissos">Compromissos</Link></div>
    {editing && <EntryEditor transaction={editing} categories={categories.data ?? []} onClose={()=>setEditing(null)}/>}
    {sheet === "calculo" && month && planning.data && <CalculoSheet mes={month} contas={planning.data.accounts} onContas={()=>setSheet("contas")} onClose={()=>setSheet(null)}/>}
    {sheet === "saidas" && month && <ItensSheet mes={month} direcao="saida" onClose={()=>setSheet(null)}/>}
    {sheet === "contas" && planning.data && <ContasSheet contas={planning.data.accounts} aviso={planning.data.balance_warning} period={period} podeEscrever={!sessao?.somenteLeitura} onClose={()=>setSheet(null)}/>}
    {sheet === "simular" && month && <SimularGastoSheet mes={month} podeEscrever={false} onClose={()=>setSheet(null)}/>}
    <button className="e-simulate" onClick={()=>setSheet("simular")} disabled={!month}>E se eu gastar mais? ›</button>
  </div>;
}
