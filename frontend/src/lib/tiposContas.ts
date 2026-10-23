// Contas financeiras: onde o dinheiro líquido está. O saldo e a qualidade dele
// vêm prontos do servidor (app/dominio/contas.py) — aqui só se formata.

import { formatDiaMes, formatYm } from "./format";

export type AccountType = "checking" | "payment" | "cash" | "benefit" | "reconciliation";
export type Qualidade = "reconciliado" | "calculado" | "desatualizado" | "sem_saldo";

export const ACCOUNT_TYPE_LABEL: Record<AccountType, string> = {
  checking: "Conta corrente",
  payment: "Conta de pagamento",
  cash: "Dinheiro",
  benefit: "Benefício",
  reconciliation: "A distribuir",
};

export const ACCOUNT_TYPE_ORDER: AccountType[] = ["checking", "payment", "cash", "benefit"];

export interface FinancialAccount {
  id: number;
  name: string;
  institution: string | null;
  type: AccountType;
  currency: string;
  include_in_planning: boolean;
  restricted: boolean;
  archived: boolean;
  created_at: string;
  balance: number | null;
  quality: Qualidade;
  observed_at: string | null;
  observed_balance: number | null;
  movements_after: number;
  maybe_incomplete: boolean;
}

export interface AccountsSummary {
  possible_overlap?: boolean;
  accounts: FinancialAccount[];
  total: number;
  free: number;
  restricted: number;
  to_distribute: number;
  stale_count: number;
  without_balance_count: number;
  maybe_incomplete: boolean;
  unassigned_movements: number;
}

export interface AccountCreate {
  name: string;
  type: AccountType;
  institution?: string | null;
  include_in_planning?: boolean | null;
  restricted?: boolean | null;
}

export type AccountUpdate = Partial<AccountCreate> & { archived?: boolean };

export interface AccountSnapshot {
  id: number;
  account_id: number;
  observed_at: string;
  balance: number;
  source: "manual" | "migration" | "reconciliation";
  note: string | null;
  difference: number | null;
  accepted_difference: number | null;
  pending_difference: number | null;
}

export interface AccountMovement {
  date: string;
  occurred_at: string | null;
  amount: number;
  kind: "entrada" | "saida" | "aporte" | "resgate" | "fatura" | "transferencia";
  description: string;
  source: string;
  source_id: number;
  after_observation: boolean;
}

export interface Transfer {
  id: number;
  from_account_id: number;
  to_account_id: number;
  from_name: string;
  to_name: string;
  amount: number;
  date: string;
  occurred_at: string | null;
  description: string | null;
  note: string | null;
}

export interface TransferCreate {
  from_account_id: number;
  to_account_id: number;
  amount: number;
  date: string;
  occurred_at?: string | null;
  description?: string | null;
}

/** "Atualizado hoje" · "Atualizado em 11/10" · "Calculado desde 11/10" ·
 *  "Desatualizado · saldo de set/2026" · "Sem saldo". Uma frase, o estado do número. */
export function estadoDaConta(c: Pick<FinancialAccount, "quality" | "observed_at">, hoje = new Date()): string {
  if (c.quality === "sem_saldo" || !c.observed_at) return "Sem saldo";
  const dia = c.observed_at.slice(0, 10);
  const local = new Date(c.observed_at);
  const mesmoDia =
    local.getFullYear() === hoje.getFullYear() && local.getMonth() === hoje.getMonth() && local.getDate() === hoje.getDate();
  if (c.quality === "desatualizado") return `Desatualizado · saldo de ${formatYm(dia.slice(0, 7))}`;
  if (c.quality === "calculado") return `Calculado desde ${formatDiaMes(localIso(local))}`;
  return mesmoDia ? "Atualizado hoje" : `Atualizado em ${formatDiaMes(localIso(local))}`;
}

function localIso(d: Date): string {
  const z = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`;
}

/** Instante de agora, pra lançamento de hoje: deixa claro se veio antes ou
 *  depois do saldo observado no mesmo dia. Data passada não ganha hora. */
export function instanteSeHoje(dataIso: string): string | null {
  return dataIso === localIso(new Date()) ? new Date().toISOString() : null;
}

const ULTIMA = "sentavos:ultima-conta";

export function ultimaConta(): number | null {
  try {
    const v = localStorage.getItem(ULTIMA);
    return v ? Number(v) : null;
  } catch {
    return null;
  }
}

export function lembrarConta(id: number | null): void {
  try {
    if (id == null) localStorage.removeItem(ULTIMA);
    else localStorage.setItem(ULTIMA, String(id));
  } catch {
    /* sem storage: só não lembra */
  }
}

// ---------- Investimento (dominio/investimentos.py) ----------
// Rendimento, aportado e resgatado vêm prontos: a tela não recalcula.

export type YieldStatus = "apurado" | "nao_apurado" | "sem_base";
export type MovementType = "contribution" | "redemption" | "adjustment";

export interface InvestmentAssetItem {
  position_pending?: boolean;
  observed_on?: string | null;
  has_observation?: boolean;
  asset_id: number;
  name: string;
  asset_class: "fixed_income" | "equity" | "crypto";
  value: number;
  previous: number;
  stale: boolean;
  as_of: string | null;
  reconciliation_note: string | null;
  cdi_percent: number | null;
  expected_yield: number | null;
  share: number | null;
  contributed: number;
  redeemed: number;
  adjusted: number;
  yield_amount: number | null;
  yield_status: YieldStatus;
}

export interface InvestmentSummary {
  position_pending?: boolean;
  year: number;
  month: number;
  items: InvestmentAssetItem[];
  total: number;
  previous_total: number;
  variation: number | null;
  contributed: number;
  redeemed: number;
  adjusted: number;
  yield_amount: number | null;
  yield_status: YieldStatus;
  reasons: string[];
  expected_yield: number | null;
  unlinked: number;
  stale_names: string[];
  stale_total: number;
}

export interface InvestmentMovement {
  id: number;
  asset_id: number;
  asset_name: string;
  type: MovementType;
  amount: number;
  date: string;
  account_id: number | null;
  account_name: string | null;
  note: string | null;
  transaction_id: number | null;
}

export interface InvestmentMovementCreate {
  asset_id: number;
  type: MovementType;
  amount: number;
  date: string;
  account_id?: number | null;
  transaction_id?: number | null;
  category_id?: number | null;
  description?: string | null;
  note?: string | null;
  occurred_at?: string | null;
}

export interface InvestmentPlanData {
  type: "contribution" | "redemption";
  amount: number;
  date: string;
  asset_id: number | null;
  account_id: number | null;
  category_id: number | null;
  description: string;
}
export interface InvestmentPlan extends InvestmentPlanData {
  id: number;
  status: "planned" | "completed" | "cancelled";
  asset_name: string | null;
  account_name: string | null;
  movement_id: number | null;
  overdue: boolean;
}
export interface MonthSummary {
  plan: import("./tiposPlanejamento").PlanoResposta;
  month: import("./tiposPlanejamento").PlanoMes;
  money_now: number | null;
  balance_date: string | null;
  balance_stale: boolean;
  balance_pending?: boolean;
  balance_kind?: "observado" | "calculado";
  to_receive: number;
  to_pay: number;
  to_check: number;
  contributed: number;
  redeemed: number;
  to_invest: number;
  projected: number | null;
  partial: boolean;
  reasons: string[];
  due: import("./tiposPlanejamento").PlanoItem[];
  estimated: import("./tiposPlanejamento").PlanoItem[];
  review: import("./tiposPlanejamento").ReconciliationItem[];
  paid_cash_ids: number[];
}
