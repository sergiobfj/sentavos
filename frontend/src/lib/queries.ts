import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { categoriesApi, transactionsApi } from "./api";
import type {
  CategoryCreate,
  CategoryUpdate,
  TransactionCreate,
  TransactionUpdate,
} from "./types";

const keys = {
  transactions: ["transactions"] as const,
  categories: ["categories"] as const,
};

// ---------- Transações ----------
export function useTransactions() {
  return useQuery({ queryKey: keys.transactions, queryFn: transactionsApi.list });
}

export function useCreateTransaction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: TransactionCreate) => transactionsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.transactions }),
  });
}

export function useUpdateTransaction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: TransactionUpdate }) =>
      transactionsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.transactions }),
  });
}

export function useDeleteTransaction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => transactionsApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.transactions }),
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
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.categories }),
  });
}

export function useUpdateCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: CategoryUpdate }) =>
      categoriesApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.categories }),
  });
}

export function useDeleteCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => categoriesApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.categories });
      qc.invalidateQueries({ queryKey: keys.transactions });
    },
  });
}
