import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import {
  assetsApi,
  budgetsApi,
  categoriesApi,
  perfilApi,
  transactionsApi,
} from "./api";
import { usePeriod } from "./period";
import type {
  AssetCreate,
  AssetSnapshotSet,
  AssetUpdate,
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
  assets: ["assets"] as const,
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

// ---------- Patrimônio ----------
// Um saldo lançado muda o mês atual e todos os meses seguintes que herdam
// dele, então a invalidação limpa o prefixo inteiro em vez de só este mês.
export function useAssetSummary() {
  const { period, ym } = usePeriod();
  return useQuery({
    queryKey: [...keys.assets, "summary", ym],
    queryFn: () => assetsApi.summary(period),
  });
}

export function useAssets() {
  return useQuery({ queryKey: [...keys.assets, "list"], queryFn: assetsApi.list });
}

export function useCreateAsset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: AssetCreate) => assetsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.assets }),
  });
}

export function useUpdateAsset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: AssetUpdate }) => assetsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.assets }),
  });
}

export function useDeleteAsset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => assetsApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.assets }),
  });
}

export function useSetAssetSnapshot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: AssetSnapshotSet) => assetsApi.setSnapshot(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.assets }),
  });
}

export function useDeleteAssetSnapshot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => assetsApi.removeSnapshot(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.assets }),
  });
}

// ---------- Categorias ----------
export function useCategories(incluirArquivadas = false) {
  // A chave leva o parâmetro: sem isso as duas listas (a do formulário e a de
  // Configurações) compartilhariam cache, e arquivar uma categoria a faria
  // sumir da tela onde se desarquiva.
  return useQuery({
    queryKey: [...keys.categories, incluirArquivadas],
    queryFn: () => categoriesApi.list(incluirArquivadas),
  });
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


// ---------- Perfil ----------
export function usePerfil() {
  return useQuery({ queryKey: ["perfil"], queryFn: perfilApi.get });
}

export function useSetCdi() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (cdi: number | null) => perfilApi.setCdi(cdi),
    // O CDI muda a projeção de todo ativo, então o resumo de patrimônio
    // precisa ser refeito junto — senão o número novo só apareceria no F5.
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["perfil"] });
      qc.invalidateQueries({ queryKey: keys.assets });
    },
  });
}
