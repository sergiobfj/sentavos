import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { budgetsApi, categoriesApi, transactionsApi } from "./api";
import { usePeriod } from "./period";
import type {
  BudgetSet,
  CategoryCreate,
  CategoryUpdate,
  TransactionCreate,
  TransactionUpdate,
} from "./types";

const keys = {
  transactions: ["transactions"] as const,
  categories: ["categories"] as const,
  budgets: ["budgets"] as const,
};

// O summary de orçamento soma amount_planned/amount_paid das transações, então
// mexer em transação (ou em categoria) desatualiza o orçamento também.
function invalidateMovement(qc: QueryClient) {
  qc.invalidateQueries({ queryKey: keys.transactions });
  qc.invalidateQueries({ queryKey: keys.budgets });
}

// ---------- Transações ----------
// O mês entra na queryKey: sem ele o react-query serviria o cache do mês
// anterior. Como keys.transactions virou prefixo, os invalidateQueries
// abaixo continuam limpando todos os meses de uma vez.
export function useTransactions() {
  const { period, ym } = usePeriod();
  return useQuery({
    queryKey: [...keys.transactions, ym],
    queryFn: () => transactionsApi.list(period),
  });
}

export function useCreateTransaction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: TransactionCreate) => transactionsApi.create(data),
    onSuccess: () => invalidateMovement(qc),
  });
}

export function useUpdateTransaction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: TransactionUpdate }) =>
      transactionsApi.update(id, data),
    onSuccess: () => invalidateMovement(qc),
  });
}

export function useDeleteTransaction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => transactionsApi.remove(id),
    onSuccess: () => invalidateMovement(qc),
  });
}

// ---------- Orçamento ----------
export function useBudgetSummary() {
  const { period, ym } = usePeriod();
  return useQuery({
    queryKey: [...keys.budgets, "summary", ym],
    queryFn: () => budgetsApi.summary(period),
  });
}

export function useSetBudget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: BudgetSet) => budgetsApi.set(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.budgets }),
  });
}

export function useDeleteBudget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => budgetsApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.budgets }),
  });
}

// ---------- Categorias ----------
export function useCategories() {
  return useQuery({ queryKey: keys.categories, queryFn: categoriesApi.list });
}

export function useCreateCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CategoryCreate) => categoriesApi.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.categories });
      // Categoria nova entra no summary como linha zerada.
      qc.invalidateQueries({ queryKey: keys.budgets });
    },
  });
}

export function useUpdateCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: CategoryUpdate }) =>
      categoriesApi.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.categories });
      // O summary carrega nome, cor e ícone da categoria.
      qc.invalidateQueries({ queryKey: keys.budgets });
    },
  });
}

export function useDeleteCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => categoriesApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.categories });
      invalidateMovement(qc);
    },
  });
}
