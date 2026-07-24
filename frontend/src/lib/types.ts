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

export const CATEGORY_TYPE_LABEL: Record<CategoryType, string> = {
  expense: "Despesa",
  income: "Receita",
  investment: "Investimento",
};
