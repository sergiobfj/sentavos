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
  planningApi,
  commitmentsApi,
  provisionsApi,
  scenariosApi,
  reconciliationApi,
  accountsApi,
  transfersApi,
  investmentsApi,
} from "./api";
import type { AccountCreate, AccountUpdate, InvestmentMovementCreate, TransferCreate } from "./tiposContas";
import type {
  CommitmentCreate,
  CommitmentUpdate,
  ProvisionCreate,
  ProvisionUpdate,
  ReconciliationItem,
  ReconciliationItemCreate,
  ScenarioItemCreate,
} from "./tiposPlanejamento";
import { shiftPeriod, toYm, usePeriod, type Period } from "./period";
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
  // Planejamento: tudo que deriva de lançamento, fatura, saldo e compromisso.
  planning: ["planning"] as const,
  commitments: ["commitments"] as const,
  provisions: ["provisions"] as const,
  scenarios: ["scenarios"] as const,
  reconciliation: ["reconciliation"] as const,
  // Contas: o saldo calculado depende de lançamento, fatura paga e transferência.
  accounts: ["accounts"] as const,
  transfers: ["transfers"] as const,
  investments: ["investments"] as const,
};

// O planejamento lê tudo: lançamento previsto, fatura, saldo, compromisso,
// reserva. E a conferência sugere correspondências entre lançamentos. Mexer em
// qualquer um desses deixa os três velhos.
function invalidatePlanning(qc: QueryClient) {
  qc.invalidateQueries({ queryKey: keys.planning });
  qc.invalidateQueries({ queryKey: keys.commitments });
  qc.invalidateQueries({ queryKey: keys.provisions });
  qc.invalidateQueries({ queryKey: keys.reconciliation });
}

// O summary de orçamento soma amount_planned/amount_paid das transações, então
// mexer em transação (ou em categoria) desatualiza o orçamento também.
//
// As faturas entram na mesma invalidação desde que o cartão existe: uma compra
// muda a fatura, e o resumo de orçamento passou a carregar o bloco de caixa, que
// desconta pagamento de fatura. Esquecer um dos três deixaria a tela com dois
// números do mesmo mês discordando — que é o defeito mais caro de depurar aqui.
function invalidateMovement(qc: QueryClient) {
  qc.invalidateQueries({ queryKey: keys.investments });
  qc.invalidateQueries({ queryKey: keys.transfers });
  qc.invalidateQueries({ queryKey: keys.transactions });
  qc.invalidateQueries({ queryKey: keys.budgets });
  qc.invalidateQueries({ queryKey: keys.invoices });
  // Os relatórios são as mesmas somas vistas de outro ângulo.
  qc.invalidateQueries({ queryKey: keys.reports });
  // Apagar um lançamento pode desfazer a baixa de um compromisso.
  invalidatePlanning(qc);
  // Lançamento com conta mexe no saldo dela — e o patrimônio soma contas.
  qc.invalidateQueries({ queryKey: keys.accounts });
  qc.invalidateQueries({ queryKey: keys.assets });
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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.assets });
      qc.invalidateQueries({ queryKey: keys.planning });
    },
  });
}

export function useUpdateAsset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: AssetUpdate }) => assetsApi.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.assets });
      qc.invalidateQueries({ queryKey: keys.planning });
    },
  });
}

export function useDeleteAsset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => assetsApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.assets });
      qc.invalidateQueries({ queryKey: keys.planning });
    },
  });
}

export function useSetAssetSnapshot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: AssetSnapshotSet) => assetsApi.setSnapshot(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.assets });
      qc.invalidateQueries({ queryKey: keys.planning });
    },
  });
}

export function useDeleteAssetSnapshot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => assetsApi.removeSnapshot(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.assets });
      qc.invalidateQueries({ queryKey: keys.planning });
    },
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
    mutationFn: ({ id, ...data }: {
      id: number; amount: number; date: string; account_id?: number | null; occurred_at?: string | null;
    }) => invoicesApi.pay(id, data),
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


// ---------- Planejamento ----------
// O mês e o cenário entram na chave: sem eles, trocar de cenário serviria do
// cache a conta do anterior.

export function usePlanningMonth(period: Period, scenarioId: number | null, enabled = true) {
  return useQuery({
    queryKey: [...keys.planning, "month", toYm(period), scenarioId],
    queryFn: () => planningApi.month(period, scenarioId),
    enabled,
    placeholderData: (anterior) => anterior,
  });
}

export function usePlanningHorizon(months: number, scenarioId: number | null = null) {
  return useQuery({
    queryKey: [...keys.planning, "horizon", months, scenarioId],
    queryFn: () => planningApi.horizon(months, scenarioId),
    placeholderData: (anterior) => anterior,
  });
}

export function useComparacao(period: Period, scenarioId: number | null) {
  return useQuery({
    queryKey: [...keys.planning, "compare", toYm(period), scenarioId],
    queryFn: () => planningApi.compare(period, scenarioId!),
    enabled: scenarioId != null,
  });
}

/** "E se eu gastar 500?" — calcula e esquece. Não invalida nada: nada mudou. */
export function useSimular() {
  return useMutation({ mutationFn: planningApi.simulate });
}

// ---------- Compromissos ----------
// Toda mudança aqui pode criar ou desfazer um lançamento (a baixa), então
// invalida o movimento inteiro — que já inclui o planejamento.

export function useCommitments() {
  return useQuery({ queryKey: [...keys.commitments, "list"], queryFn: commitmentsApi.list });
}

export function useCommitment(id: number | null) {
  return useQuery({
    queryKey: [...keys.commitments, "detalhe", id],
    queryFn: () => commitmentsApi.get(id!),
    enabled: id != null,
  });
}

function useMutacaoDeCompromisso<T>(fn: (v: T) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => invalidateMovement(qc) });
}

export const useCreateCommitment = () =>
  useMutacaoDeCompromisso((data: CommitmentCreate) => commitmentsApi.create(data));
export const useUpdateCommitment = () =>
  useMutacaoDeCompromisso(({ id, data }: { id: number; data: CommitmentUpdate }) =>
    commitmentsApi.update(id, data)
  );
export const useDeleteCommitment = () =>
  useMutacaoDeCompromisso((id: number) => commitmentsApi.remove(id));
export const usePagarOcorrencia = () =>
  useMutacaoDeCompromisso(
    ({ id, numero, ...data }: {
      id: number; numero: number; date?: string; amount?: number; account_id?: number | null; occurred_at?: string | null;
    }) => commitmentsApi.pay(id, numero, data)
  );
export const useVincularOcorrencia = () =>
  useMutacaoDeCompromisso(
    ({ id, numero, transactionId }: { id: number; numero: number; transactionId: number }) =>
      commitmentsApi.link(id, numero, transactionId)
  );
export const useDesvincularOcorrencia = () =>
  useMutacaoDeCompromisso(({ id, numero }: { id: number; numero: number }) =>
    commitmentsApi.unlink(id, numero)
  );
export const useDispensarOcorrencia = () =>
  useMutacaoDeCompromisso(({ id, numero, note }: { id: number; numero: number; note?: string | null }) =>
    commitmentsApi.skip(id, numero, note)
  );
export const useDesfazerDispensa = () =>
  useMutacaoDeCompromisso(({ id, numero }: { id: number; numero: number }) =>
    commitmentsApi.unskip(id, numero)
  );

export const usePausarRecorrencia = () =>
  useMutacaoDeCompromisso(({ id, ate }: { id: number; ate: string }) => commitmentsApi.pause(id, ate));

export const useRetomarRecorrencia = () =>
  useMutacaoDeCompromisso(({ id }: { id: number }) => commitmentsApi.resume(id));

// ---------- Reservas ----------
// Reserva não mexe em lançamento: só o planejamento e a lista dela.

function useMutacaoDePlanejamento<T>(fn: (v: T) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => invalidatePlanning(qc) });
}

export function useProvisions() {
  return useQuery({ queryKey: [...keys.provisions, "list"], queryFn: provisionsApi.list });
}

export const useCreateProvision = () =>
  useMutacaoDePlanejamento((data: ProvisionCreate) => provisionsApi.create(data));
export const useUpdateProvision = () =>
  useMutacaoDePlanejamento(({ id, data }: { id: number; data: ProvisionUpdate }) =>
    provisionsApi.update(id, data)
  );
export const useDeleteProvision = () =>
  useMutacaoDePlanejamento((id: number) => provisionsApi.remove(id));

// ---------- Cenários ----------

export function useScenarios() {
  return useQuery({ queryKey: [...keys.scenarios, "list"], queryFn: scenariosApi.list });
}

function useMutacaoDeCenario<T, R>(fn: (v: T) => Promise<R>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.scenarios });
      qc.invalidateQueries({ queryKey: keys.planning });
    },
  });
}

export const useCreateScenario = () =>
  useMutacaoDeCenario((data: { name: string; note?: string | null }) => scenariosApi.create(data));
export const useUpdateScenario = () =>
  useMutacaoDeCenario(({ id, data }: { id: number; data: { name?: string; note?: string | null } }) =>
    scenariosApi.update(id, data)
  );
export const useDeleteScenario = () => useMutacaoDeCenario((id: number) => scenariosApi.remove(id));
export const useDuplicateScenario = () =>
  useMutacaoDeCenario(({ id, name }: { id: number; name?: string }) => scenariosApi.duplicate(id, name));
export const useAddScenarioItem = () =>
  useMutacaoDeCenario(({ id, data }: { id: number; data: ScenarioItemCreate }) =>
    scenariosApi.addItem(id, data)
  );
export const useRemoveScenarioItem = () =>
  useMutacaoDeCenario(({ id, itemId }: { id: number; itemId: number }) =>
    scenariosApi.removeItem(id, itemId)
  );

// ---------- Conferência ----------

export function useReconciliation(period: Period) {
  return useQuery({
    queryKey: [...keys.reconciliation, toYm(period)],
    queryFn: () => reconciliationApi.list(period),
  });
}

export const useAddReconciliation = () =>
  useMutacaoDePlanejamento((data: ReconciliationItemCreate) => reconciliationApi.add(data));
export const useUpdateReconciliation = () =>
  useMutacaoDePlanejamento(
    ({ id, data }: { id: number; data: Partial<Pick<ReconciliationItem, "status" | "note" | "description" | "amount">> }) =>
      reconciliationApi.update(id, data)
  );
export const useDeleteReconciliation = () =>
  useMutacaoDePlanejamento((id: number) => reconciliationApi.remove(id));
export const useLinkReconciliation = () =>
  useMutacaoDePlanejamento(
    ({ id, data }: { id: number; data: { transaction_id?: number; commitment_id?: number } }) =>
      reconciliationApi.link(id, data)
  );
// Estes três criam dado de verdade: invalidam o movimento inteiro.
export const useReconTransaction = () =>
  useMutacaoDeCompromisso(({ id, data }: { id: number; data: TransactionCreate }) =>
    reconciliationApi.createTransaction(id, data)
  );
export const useReconCommitment = () =>
  useMutacaoDeCompromisso(({ id, data }: { id: number; data: CommitmentCreate }) =>
    reconciliationApi.createCommitment(id, data)
  );
export const useReconProvision = () =>
  useMutacaoDePlanejamento(({ id, data }: { id: number; data: ProvisionCreate }) =>
    reconciliationApi.createProvision(id, data)
  );

// ---------- Contas ----------

export function useAccounts(incluirArquivadas = false) {
  return useQuery({ queryKey: [...keys.accounts, "lista", incluirArquivadas], queryFn: () => accountsApi.list(incluirArquivadas) });
}

export function useAccountsSummary() {
  return useQuery({ queryKey: [...keys.accounts, "resumo"], queryFn: accountsApi.summary });
}

export function useAccountSnapshots(id: number | null) {
  return useQuery({
    queryKey: [...keys.accounts, "saldos", id],
    queryFn: () => accountsApi.snapshots(id!),
    enabled: id != null,
  });
}

export function useAccountMovements(id: number | null) {
  return useQuery({
    queryKey: [...keys.accounts, "movimentos", id],
    queryFn: () => accountsApi.movimentos(id!),
    enabled: id != null,
  });
}

// Mexer em conta muda saldo, patrimônio e o saldo de partida do planejamento.
function useMutacaoDeConta<T, R>(fn: (v: T) => Promise<R>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => invalidateMovement(qc) });
}

export const useCreateAccount = () => useMutacaoDeConta((data: AccountCreate) => accountsApi.create(data));
export const useUpdateAccount = () =>
  useMutacaoDeConta(({ id, data }: { id: number; data: AccountUpdate }) => accountsApi.update(id, data));
export const useDeleteAccount = () => useMutacaoDeConta((id: number) => accountsApi.remove(id));
export const useInformarSaldo = () =>
  useMutacaoDeConta(({ id, balance }: { id: number; balance: number }) => accountsApi.informarSaldo(id, { balance }));
export const useAceitarDiferenca = () =>
  useMutacaoDeConta(({ id, snapshotId }: { id: number; snapshotId: number }) => accountsApi.aceitarDiferenca(id, snapshotId));
export const useDistribuir = () =>
  useMutacaoDeConta(({ id, destinos }: { id: number; destinos: { account_id: number; amount: number }[] }) =>
    accountsApi.distribuir(id, destinos)
  );

export function useTransfers() {
  const { period, ym } = usePeriod();
  return useQuery({ queryKey: [...keys.transfers, ym], queryFn: () => transfersApi.list(period) });
}
export const useCreateTransfer = () => useMutacaoDeConta((data: TransferCreate) => transfersApi.create(data));
export const useDeleteTransfer = () => useMutacaoDeConta((id: number) => transfersApi.remove(id));

// ---------- Investimento ----------

export function useInvestmentSummary() {
  const { period, ym } = usePeriod();
  return useQuery({ queryKey: [...keys.investments, "resumo", ym], queryFn: () => investmentsApi.summary(period) });
}

export function useInvestmentMovements() {
  const { period, ym } = usePeriod();
  return useQuery({ queryKey: [...keys.investments, "movimentos", ym], queryFn: () => investmentsApi.movements(period) });
}

export const useCreateMovement = () =>
  useMutacaoDeConta((data: InvestmentMovementCreate) => investmentsApi.createMovement(data));
export const useRemoveMovement = () => useMutacaoDeConta((id: number) => investmentsApi.removeMovement(id));
