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
