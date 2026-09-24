import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import {
  assetsApi,
  budgetsApi,
  cardsApi,
  categoriesApi,
  formaApi,
  invoicesApi,
  perfilApi,
  purchasesApi,
  reportsApi,
  transactionsApi,
} from "./api";
import { shiftPeriod, toYm, usePeriod } from "./period";
import type {
  AssetCreate,
  AssetSnapshotSet,
  AssetUpdate,
  BudgetSet,
  CardCreate,
  CardUpdate,
  CategoryCreate,
  CategoryUpdate,
  FiltroFinalidade,
  PaymentMethod,
  PurchaseCreate,
  PurchaseUpdate,
  TransactionCreate,
  TransactionUpdate,
} from "./types";

const keys = {
  transactions: ["transactions"] as const,
  categories: ["categories"] as const,
  budgets: ["budgets"] as const,
  assets: ["assets"] as const,
  cards: ["cards"] as const,
  invoices: ["invoices"] as const,
  reports: ["reports"] as const,
};

// O summary de orçamento soma amount_planned/amount_paid das transações, então
// mexer em transação (ou em categoria) desatualiza o orçamento também.
//
// As faturas entram na mesma invalidação desde que o cartão existe: uma compra
// muda a fatura, e o resumo de orçamento passou a carregar o bloco de caixa, que
// desconta pagamento de fatura. Esquecer um dos três deixaria a tela com dois
// números do mesmo mês discordando — que é o defeito mais caro de depurar aqui.
function invalidateMovement(qc: QueryClient) {
  qc.invalidateQueries({ queryKey: keys.transactions });
  qc.invalidateQueries({ queryKey: keys.budgets });
  qc.invalidateQueries({ queryKey: keys.invoices });
  // Os relatórios são as mesmas somas vistas de outro ângulo.
  qc.invalidateQueries({ queryKey: keys.reports });
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

// ---------- Relatórios ----------
// Finalidade e janela entram na chave: sem elas, trocar de "Pessoal" pra
// "Família" serviria do cache o número do filtro anterior.

export function useCategoryReport(finalidade: FiltroFinalidade) {
  const { period, ym } = usePeriod();
  return useQuery({
    queryKey: [...keys.reports, "categories", ym, finalidade],
    queryFn: () => reportsApi.categories(period, finalidade),
  });
}

/** Os `meses` terminados no mês selecionado, inclusive. */
export function useMonthlyReport(meses: number, finalidade: FiltroFinalidade) {
  const { period } = usePeriod();
  const de = shiftPeriod(period, -(meses - 1));
  return useQuery({
    queryKey: [...keys.reports, "monthly", toYm(de), toYm(period), finalidade],
    queryFn: () => reportsApi.monthly(de, period, finalidade),
    // Trocar 6 ↔ 12 meses mantém a linha anterior na tela até a nova chegar,
    // em vez de piscar um esqueleto no lugar do gráfico.
    placeholderData: (anterior) => anterior,
  });
}

// ---------- Categorias ----------
export function useCategoriesComUso() {
  return useQuery({
    queryKey: [...keys.categories, "uso"],
    queryFn: categoriesApi.listComUso,
  });
}

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
      // O summary e os relatórios carregam nome, cor e ícone da categoria.
      qc.invalidateQueries({ queryKey: keys.budgets });
      qc.invalidateQueries({ queryKey: keys.reports });
    },
  });
}

export function useDeleteCategory() {
  const qc = useQueryClient();
  return useMutation({
    // `moverPara` opcional: com ele os lançamentos trocam de categoria antes
    // da exclusão, sem ele a API recusa apagar categoria com histórico.
    mutationFn: ({ id, moverPara }: { id: number; moverPara?: number | null }) =>
      categoriesApi.remove(id, moverPara),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.categories });
      invalidateMovement(qc);
    },
  });
}


// ---------- Cartões ----------
export function useCards(incluirArquivados = false) {
  // Mesma armadilha das categorias: sem o parâmetro na chave, arquivar um
  // cartão o faria sumir da tela onde se desarquiva.
  return useQuery({
    queryKey: [...keys.cards, incluirArquivados],
    queryFn: () => cardsApi.list(incluirArquivados),
  });
}

export function useCreateCard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CardCreate) => cardsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.cards }),
  });
}

export function useUpdateCard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: CardUpdate }) => cardsApi.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.cards });
      // Classificar o cartão dá finalidade às compras dele que não tinham.
      qc.invalidateQueries({ queryKey: keys.reports });
      // O nome do cartão aparece na linha da parcela e no resumo de faturas.
      qc.invalidateQueries({ queryKey: keys.invoices });
      qc.invalidateQueries({ queryKey: keys.transactions });
    },
  });
}

export function useDeleteCard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => cardsApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.cards });
      qc.invalidateQueries({ queryKey: keys.invoices });
    },
  });
}

// ---------- Faturas ----------
export function useInvoicesSummary() {
  const { period, ym } = usePeriod();
  return useQuery({
    queryKey: [...keys.invoices, "summary", ym],
    queryFn: () => invoicesApi.summary(period),
  });
}

export function useInvoice(id: number | null) {
  return useQuery({
    queryKey: [...keys.invoices, "detalhe", id],
    queryFn: () => invoicesApi.get(id!),
    enabled: id != null,
  });
}

export function usePayInvoice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, amount, date }: { id: number; amount: number; date: string }) =>
      invoicesApi.pay(id, { amount, date }),
    // Pagar fatura é saída de caixa: muda a Carteira, que vem do resumo de
    // orçamento. Por isso invalida tudo, não só a fatura.
    onSuccess: () => invalidateMovement(qc),
  });
}

export function useUndoPayment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (paymentId: number) => invoicesApi.undoPayment(paymentId),
    onSuccess: () => invalidateMovement(qc),
  });
}

export function useCandidatosAPagamento(invoiceId: number | null) {
  return useQuery({
    queryKey: [...keys.invoices, "candidatos", invoiceId],
    queryFn: () => invoicesApi.candidates(invoiceId!),
    enabled: invoiceId != null,
  });
}

export function useReconcile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, transactionId }: { id: number; transactionId: number }) =>
      invoicesApi.reconcile(id, transactionId),
    onSuccess: () => invalidateMovement(qc),
  });
}

// ---------- Compras no cartão ----------
export function usePurchase(id: number | null) {
  return useQuery({
    queryKey: ["purchases", id],
    queryFn: () => purchasesApi.get(id!),
    enabled: id != null,
  });
}

export function useCreatePurchase() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: PurchaseCreate) => purchasesApi.create(data),
    onSuccess: () => invalidateMovement(qc),
  });
}

export function useUpdatePurchase() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: PurchaseUpdate }) =>
      purchasesApi.update(id, data),
    onSuccess: (_, { id }) => {
      invalidateMovement(qc);
      qc.invalidateQueries({ queryKey: ["purchases", id] });
    },
  });
}

export function useDeletePurchase() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => purchasesApi.remove(id),
    onSuccess: () => invalidateMovement(qc),
  });
}

// ---------- Forma de pagamento do histórico ----------
export function useDefinirForma() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      metodo,
      card_id,
      installments,
    }: {
      id: number;
      metodo: PaymentMethod;
      card_id?: number;
      installments?: number;
    }) => formaApi.um(id, { metodo, card_id, installments }),
    onSuccess: () => invalidateMovement(qc),
  });
}

export function useDefinirFormaEmLote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { ids: number[]; metodo: PaymentMethod; card_id?: number }) =>
      formaApi.lote(data),
    onSuccess: () => invalidateMovement(qc),
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
