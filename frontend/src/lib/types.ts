// Espelha os modelos do backend (app/models.py)

export type CategoryType = "expense" | "income" | "investment";

export interface Category {
  id: number;
  name: string;
  type: CategoryType;
  color: string;
  icon: string;
}

export type CategoryCreate = Omit<Category, "id">;
export type CategoryUpdate = Partial<CategoryCreate>;

export interface Transaction {
  id: number;
  date: string; // ISO date (YYYY-MM-DD)
  description: string;
  amount_planned: number | null;
  amount_paid: number | null;
  note: string | null;
  category_id: number;
}

export type TransactionCreate = Omit<Transaction, "id">;
export type TransactionUpdate = Partial<TransactionCreate>;

// A meta de gasto de uma categoria num mês. "Orçado" (meta do mês) é outra
// coisa que "previsto" (amount_planned dos lançamentos) — as duas convivem.
export interface Budget {
  id: number;
  category_id: number;
  year: number;
  month: number;
  amount: number;
}

export type BudgetSet = Omit<Budget, "id">;

export interface BudgetSummaryItem {
  category_id: number;
  category_name: string;
  category_type: CategoryType;
  color: string;
  icon: string;
  budget_id: number | null;
  budgeted: number;
  planned: number;
  paid: number;
}

export interface BudgetSummaryTotals {
  budgeted: number;
  planned: number;
  paid: number;
}

export interface BudgetSummary {
  year: number;
  month: number;
  items: BudgetSummaryItem[];
  totals: Record<CategoryType, BudgetSummaryTotals>;
}

export const CATEGORY_TYPE_LABEL: Record<CategoryType, string> = {
  expense: "Despesa",
  income: "Receita",
  investment: "Investimento",
};

// ---------- Patrimônio ----------
// Transaction é fluxo; aqui é estoque — quanto cada coisa vale num mês.

export type AssetClass =
  | "checking"
  | "fixed_income"
  | "equity"
  | "crypto"
  | "real_estate"
  | "vehicle"
  | "debt";

export interface Asset {
  id: number;
  name: string;
  asset_class: AssetClass;
  note: string | null;
}

export type AssetCreate = Omit<Asset, "id">;
export type AssetUpdate = Partial<AssetCreate>;

export interface AssetSnapshotSet {
  asset_id: number;
  year: number;
  month: number;
  value: number;
}

export interface AssetSummaryItem {
  asset_id: number;
  name: string;
  asset_class: AssetClass;
  liability: boolean;
  note: string | null;
  // Null quando o valor foi herdado de um mês anterior: não há saldo deste
  // mês pra editar, então a tela mostra de quando ele é (as_of).
  snapshot_id: number | null;
  value: number;
  previous: number;
  change: number;
  as_of: string | null;
}

export interface AssetClassTotal {
  value: number;
  previous: number;
}

export interface AssetSummary {
  year: number;
  month: number;
  items: AssetSummaryItem[];
  by_class: Record<AssetClass, AssetClassTotal>;
  assets: number;
  liabilities: number;
  net_worth: number;
  previous_net_worth: number;
}

export const ASSET_CLASS_LABEL: Record<AssetClass, string> = {
  checking: "Conta",
  fixed_income: "Renda fixa",
  equity: "Renda variável",
  crypto: "Cripto",
  real_estate: "Imóvel",
  vehicle: "Veículo",
  debt: "Dívida",
};

// A ordem em que as classes aparecem na tela: líquido primeiro, dívida no fim.
export const ASSET_CLASS_ORDER: AssetClass[] = [
  "checking",
  "fixed_income",
  "equity",
  "crypto",
  "real_estate",
  "vehicle",
  "debt",
];

// Espelha INVESTMENT_CLASSES do backend — a aba de Investimento filtra por elas.
export const INVESTMENT_CLASSES: AssetClass[] = ["fixed_income", "equity", "crypto"];
