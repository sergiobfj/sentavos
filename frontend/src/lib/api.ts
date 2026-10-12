import { EVENTO_SESSAO_EXPIRADA } from "./auth";
import { carregarSessao, limparSessao } from "./session";
import type { SaudeDoMes } from "./tiposPlanejamento";
import type {
  AccountCreate,
  AccountMovement,
  AccountSnapshot,
  AccountsSummary,
  AccountUpdate,
  FinancialAccount,
  InvestmentMovement,
  InvestmentMovementCreate,
  InvestmentSummary,
  Transfer,
  TransferCreate,
} from "./tiposContas";
import type { Period } from "./period";
import type {
  Asset,
  AssetCreate,
  AssetSnapshotSet,
  AssetSummary,
  AssetUpdate,
  Budget,
  BudgetSet,
  BudgetSummary,
  CandidatoAPagamento,
  Card,
  CardCreate,
  CardUpdate,
  Category,
  CategoryComUso,
  CategoryCreate,
  CategoryReport,
  CategoryUpdate,
  Invoice,
  InvoiceDetail,
  InvoicesSummary,
  FiltroFinalidade,
  MonthlyReport,
  PaymentMethod,
  Purchase,
  PurchaseCreate,
  PurchaseUpdate,
  Transaction,
  TransactionCreate,
  TransactionUpdate,
} from "./types";
import type {
  Commitment,
  CommitmentCreate,
  CommitmentDetail,
  CommitmentUpdate,
  Comparacao,
  PlanoResposta,
  Provision,
  ProvisionCreate,
  ProvisionUpdate,
  ReconciliationItem,
  ReconciliationItemCreate,
  ReconciliationList,
  Scenario,
  ScenarioItemCreate,
} from "./tiposPlanejamento";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// Recado deixado pra tela de login quando a sessão é derrubada no meio do uso.
export const AVISO_LOGIN = "sentavos:aviso-login";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

/** `ehLogin` isenta a chamada do tratamento de 401 — veja o bloco lá embaixo. */
async function request<T>(
  path: string,
  options: RequestInit = {},
  ehLogin = false
): Promise<T> {
  // Toda chamada passa por aqui, então o token entra num lugar só — não tem
  // como uma rota nova esquecer de mandar.
  const token = carregarSessao()?.token ?? null;

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    });
  } catch {
    throw new ApiError(0, "Não consegui falar com a API. O backend está no ar?");
  }

  // Token venceu ou foi invalidado no servidor: derruba a sessão pra a tela de
  // login aparecer, em vez de deixar erro em toda aba.
  //
  // O aviso fica guardado porque a troca de tela é imediata: sem ele o usuário
  // voltaria pro login sem explicação nenhuma e ficaria tentando de novo achando
  // que errou a senha.
  //
  // O login é a exceção: ali o 401 significa "senha errada", não "sessão
  // vencida". Sem esta isenção, errar a senha mostraria "sua sessão expirou" —
  // uma mensagem que não explica nada pra quem nem chegou a entrar.
  if (res.status === 401 && !ehLogin) {
    try {
      sessionStorage.setItem(
        AVISO_LOGIN,
        "Sua sessão expirou ou foi encerrada. Entre de novo."
      );
    } catch {
      /* sessionStorage pode estar bloqueado */
    }
    limparSessao();
    // O AuthProvider escuta isto e derruba a tela pro login. Avisar por evento
    // evita que este módulo precise importar o contexto do React — o que daria
    // ciclo, já que o contexto importa daqui.
    window.dispatchEvent(new Event(EVENTO_SESSAO_EXPIRADA));
    throw new ApiError(401, "Sua sessão foi recusada. Entre de novo.");
  }

  if (!res.ok) {
    let detail = `Erro ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* corpo sem json */
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ---------- Login ----------
export const authApi = {
  login: (email: string, senha: string) =>
    request<{ access_token: string }>(
      "/auth/login",
      { method: "POST", body: JSON.stringify({ email, senha }) },
      true
    ),
};

// ---------- Transações ----------
export const transactionsApi = {
  // Sem período devolve tudo — útil pra séries de vários meses.
  list: (period?: Period) =>
    request<Transaction[]>(
      `/transactions${period ? `?year=${period.year}&month=${period.month}` : ""}`
    ),
  get: (id: number) => request<Transaction>(`/transactions/${id}`),
  create: (data: TransactionCreate) =>
    request<Transaction>("/transactions", { method: "POST", body: JSON.stringify(data) }),
  update: (id: number, data: TransactionUpdate) =>
    request<Transaction>(`/transactions/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  remove: (id: number) => request<{ message: string }>(`/transactions/${id}`, { method: "DELETE" }),
};

// ---------- Orçamento ----------
export const budgetsApi = {
  // Orçado x previsto x pago por categoria, já cruzado pelo backend.
  summary: ({ year, month }: Period) =>
    request<BudgetSummary>(`/budgets/summary?year=${year}&month=${month}`),
  list: (period?: Period) =>
    request<Budget[]>(`/budgets${period ? `?year=${period.year}&month=${period.month}` : ""}`),
  // PUT porque é idempotente: a tela só sabe categoria + mês + valor, não o id da meta.
  set: (data: BudgetSet) => request<Budget>("/budgets", { method: "PUT", body: JSON.stringify(data) }),
  remove: (id: number) => request<{ message: string }>(`/budgets/${id}`, { method: "DELETE" }),
};

// ---------- Patrimônio ----------
export const assetsApi = {
  summary: ({ year, month }: Period) =>
    request<AssetSummary>(`/assets/summary?year=${year}&month=${month}`),
  list: () => request<Asset[]>("/assets"),
  create: (data: AssetCreate) =>
    request<Asset>("/assets", { method: "POST", body: JSON.stringify(data) }),
  update: (id: number, data: AssetUpdate) =>
    request<Asset>(`/assets/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  remove: (id: number) => request<{ message: string }>(`/assets/${id}`, { method: "DELETE" }),
  // Upsert do saldo do mês, mesmo motivo do PUT de metas.
  setSnapshot: (data: AssetSnapshotSet) =>
    request<unknown>("/assets/snapshots", { method: "PUT", body: JSON.stringify(data) }),
  removeSnapshot: (id: number) =>
    request<{ message: string }>(`/assets/snapshots/${id}`, { method: "DELETE" }),
};

// ---------- Perfil ----------
export const perfilApi = {
  get: () => request<{ nome: string; email: string; cdi_annual: number | null }>("/perfil"),
  setCdi: (cdi_annual: number | null) =>
    request<{ cdi_annual: number | null }>("/perfil", {
      method: "PATCH",
      body: JSON.stringify({ cdi_annual }),
    }),
};

// ---------- Cartões ----------
export const cardsApi = {
  list: (incluirArquivados = false) =>
    request<Card[]>(`/cards${incluirArquivados ? "?incluir_arquivados=1" : ""}`),
  create: (data: CardCreate) =>
    request<Card>("/cards", { method: "POST", body: JSON.stringify(data) }),
  update: (id: number, data: CardUpdate) =>
    request<Card>(`/cards/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  // Recusa (409) cartão com compra: a saída ali é arquivar, que tira do
  // formulário sem levar o histórico junto.
  remove: (id: number) => request<{ message: string }>(`/cards/${id}`, { method: "DELETE" }),
};

// ---------- Compras no cartão ----------
// Rota própria e não POST /transactions: o que entra não é um lançamento, é uma
// compra que GERA lançamentos — um por parcela — e descobre em que fatura cada
// um cai. O backend faz as duas coisas; o front só manda a compra.
export const purchasesApi = {
  get: (id: number) => request<Purchase>(`/purchases/${id}`),
  create: (data: PurchaseCreate) =>
    request<Purchase>("/purchases", { method: "POST", body: JSON.stringify(data) }),
  update: (id: number, data: PurchaseUpdate) =>
    request<Purchase>(`/purchases/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  remove: (id: number) =>
    request<{ message: string }>(`/purchases/${id}`, { method: "DELETE" }),
};

// ---------- Faturas ----------
export const invoicesApi = {
  // Uma chamada serve três telas: Faturas, o cartão de fatura do Início e os
  // pagamentos que a lista de lançamentos mescla.
  summary: ({ year, month }: Period) =>
    request<InvoicesSummary>(`/invoices/summary?year=${year}&month=${month}`),
  list: (cardId?: number) =>
    request<Invoice[]>(`/invoices${cardId != null ? `?card_id=${cardId}` : ""}`),
  get: (id: number) => request<InvoiceDetail>(`/invoices/${id}`),
  pay: (id: number, data: { amount: number; date: string; account_id?: number | null; occurred_at?: string | null }) =>
    request<Invoice>(`/invoices/${id}/payments`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  undoPayment: (paymentId: number) =>
    request<{ message: string }>(`/invoice_payments/${paymentId}`, { method: "DELETE" }),
  // Lançamentos que PODEM ser o pagamento desta fatura. A lista é por forma
  // (despesa, paga, perto do vencimento) — nunca por nome de categoria.
  candidates: (id: number) =>
    request<CandidatoAPagamento[]>(`/invoices/${id}/candidatos-a-pagamento`),
  // Transforma um lançamento antigo no pagamento desta fatura: ele deixa de
  // contar como gasto e o dinheiro passa a sair uma vez só, como pagamento.
  reconcile: (id: number, transactionId: number) =>
    request<Invoice>(`/invoices/${id}/reconciliar`, {
      method: "POST",
      body: JSON.stringify({ transaction_id: transactionId }),
    }),
};

// ---------- Forma de pagamento do que já estava lançado ----------
export const formaApi = {
  um: (id: number, data: { metodo: PaymentMethod; card_id?: number; installments?: number }) =>
    request<{ message: string }>(`/transactions/${id}/forma-de-pagamento`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  // Em lote o parcelamento é sempre 1x: parcelar é decisão por compra, e
  // aplicar "3x" a dez lançamentos de uma vez inventaria dado.
  lote: (data: { ids: number[]; metodo: PaymentMethod; card_id?: number }) =>
    request<{ atualizados: number; ignorados: { id: number; motivo: string }[] }>(
      "/transactions/forma-de-pagamento",
      { method: "POST", body: JSON.stringify(data) }
    ),
};

// ---------- Categorias ----------
export const categoriesApi = {
  list: (incluirArquivadas = false) =>
    request<Category[]>(
      `/categories${incluirArquivadas ? "?incluir_arquivadas=1" : ""}`
    ),
  // Com o uso de cada uma (lançamentos, compras, metas) — é o que Configurações
  // precisa pra saber, antes de oferecer, se a troca de tipo vai ser recusada.
  listComUso: () =>
    request<CategoryComUso[]>("/categories?incluir_arquivadas=1&incluir_uso=1"),
  get: (id: number) => request<Category>(`/categories/${id}`),
  create: (data: CategoryCreate) =>
    request<Category>("/categories", { method: "POST", body: JSON.stringify(data) }),
  update: (id: number, data: CategoryUpdate) =>
    request<Category>(`/categories/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  // `moverPara` entrega os lançamentos a outra categoria antes de apagar esta.
  // É o que faz "fundir UBER em Transporte" ser uma operação, e não apagar
  // seis lançamentos à mão pra depois poder apagar a categoria.
  remove: (id: number, moverPara?: number | null) =>
    request<{ message: string; moved: number }>(
      `/categories/${id}${moverPara != null ? `?mover_para=${moverPara}` : ""}`,
      { method: "DELETE" }
    ),
};

// ---------- Relatórios ----------
// Uma chamada por gráfico, nunca uma por mês: a série de 12 meses é UMA ida ao
// servidor, que agrega tudo de uma vez.
export const reportsApi = {
  monthly: (de: Period, ate: Period, finalidade: FiltroFinalidade) =>
    request<MonthlyReport>(
      `/reports/monthly?from=${ym(de)}&to=${ym(ate)}&finalidade=${finalidade}`
    ),
  categories: ({ year, month }: Period, finalidade: FiltroFinalidade, top = 5) =>
    request<CategoryReport>(
      `/reports/categories?year=${year}&month=${month}&finalidade=${finalidade}&top=${top}`
    ),
};

function ym({ year, month }: Period): string {
  return `${year}-${String(month).padStart(2, "0")}`;
}

// ---------- Planejamento ----------
// A conta do mês sai pronta do servidor. Simular é POST só porque a hipótese
// vai no corpo — não grava nada, e por isso a conta demo também simula.
export const planningApi = {
  month: ({ year, month }: Period, scenarioId?: number | null) =>
    request<PlanoResposta>(
      `/planning/month?year=${year}&month=${month}${scenarioId ? `&scenario_id=${scenarioId}` : ""}`
    ),
  horizon: (months: number, scenarioId?: number | null) =>
    request<PlanoResposta>(
      `/planning/horizon?months=${months}${scenarioId ? `&scenario_id=${scenarioId}` : ""}`
    ),
  compare: ({ year, month }: Period, scenarioId: number) =>
    request<Comparacao>(`/planning/compare?year=${year}&month=${month}&scenario_id=${scenarioId}`),
  simulate: (data: { year: number; month: number; scenario_id?: number | null; extras: ScenarioItemCreate[] }) =>
    request<PlanoResposta>("/planning/simulate", { method: "POST", body: JSON.stringify(data) }),
};

export const commitmentsApi = {
  list: () => request<Commitment[]>("/commitments"),
  get: (id: number) => request<CommitmentDetail>(`/commitments/${id}`),
  create: (data: CommitmentCreate) =>
    request<CommitmentDetail>("/commitments", { method: "POST", body: JSON.stringify(data) }),
  update: (id: number, data: CommitmentUpdate) =>
    request<CommitmentDetail>(`/commitments/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  remove: (id: number) =>
    request<{ message: string; reservas_soltas: number }>(`/commitments/${id}`, { method: "DELETE" }),
  // A baixa num toque: cria o lançamento realizado já vinculado à ocorrência.
  pay: (id: number, numero: number, data: {
    date?: string; amount?: number; note?: string | null; account_id?: number | null; occurred_at?: string | null;
  }) =>
    request<CommitmentDetail>(`/commitments/${id}/ocorrencias/${numero}/pagar`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  // "Já paguei": o lançamento existe, só não sabia que era esta ocorrência.
  link: (id: number, numero: number, transactionId: number) =>
    request<CommitmentDetail>(`/commitments/${id}/ocorrencias/${numero}/vincular`, {
      method: "POST",
      body: JSON.stringify({ transaction_id: transactionId }),
    }),
  unlink: (id: number, numero: number) =>
    request<CommitmentDetail>(`/commitments/${id}/ocorrencias/${numero}/vincular`, { method: "DELETE" }),
  skip: (id: number, numero: number, note?: string | null) =>
    request<CommitmentDetail>(`/commitments/${id}/ocorrencias/${numero}/dispensar`, {
      method: "POST",
      body: JSON.stringify({ note: note ?? null }),
    }),
  unskip: (id: number, numero: number) =>
    request<CommitmentDetail>(`/commitments/${id}/ocorrencias/${numero}/dispensar`, { method: "DELETE" }),
  // Pausa = dispensa das ocorrências em aberto de hoje até o fim do mês de `ate`.
  pause: (id: number, ate: string) =>
    request<CommitmentDetail>(`/commitments/${id}/pausar`, {
      method: "POST",
      body: JSON.stringify({ ate }),
    }),
  resume: (id: number) => request<CommitmentDetail>(`/commitments/${id}/retomar`, { method: "POST" }),
};

export const provisionsApi = {
  list: () => request<Provision[]>("/provisions"),
  create: (data: ProvisionCreate) =>
    request<Provision>("/provisions", { method: "POST", body: JSON.stringify(data) }),
  update: (id: number, data: ProvisionUpdate) =>
    request<Provision>(`/provisions/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  remove: (id: number) => request<{ message: string }>(`/provisions/${id}`, { method: "DELETE" }),
};

export const scenariosApi = {
  list: () => request<Scenario[]>("/scenarios"),
  create: (data: { name: string; note?: string | null }) =>
    request<Scenario>("/scenarios", { method: "POST", body: JSON.stringify(data) }),
  update: (id: number, data: { name?: string; note?: string | null }) =>
    request<Scenario>(`/scenarios/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  remove: (id: number) => request<{ message: string }>(`/scenarios/${id}`, { method: "DELETE" }),
  duplicate: (id: number, name?: string) =>
    request<Scenario>(`/scenarios/${id}/duplicar`, { method: "POST", body: JSON.stringify({ name }) }),
  addItem: (id: number, data: ScenarioItemCreate) =>
    request<Scenario>(`/scenarios/${id}/items`, { method: "POST", body: JSON.stringify(data) }),
  removeItem: (id: number, itemId: number) =>
    request<Scenario>(`/scenarios/${id}/items/${itemId}`, { method: "DELETE" }),
};

// ---------- Conferência do mês ----------
// Revisar e aplicar, item a item. Cada criação aqui é UM toque do dono.
export const reconciliationApi = {
  list: ({ year, month }: Period) =>
    request<ReconciliationList>(`/reconciliation?year=${year}&month=${month}`),
  add: (data: ReconciliationItemCreate) =>
    request<ReconciliationItem>("/reconciliation", { method: "POST", body: JSON.stringify(data) }),
  update: (id: number, data: Partial<Pick<ReconciliationItem, "status" | "note" | "description" | "amount">>) =>
    request<ReconciliationItem>(`/reconciliation/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  remove: (id: number) => request<{ message: string }>(`/reconciliation/${id}`, { method: "DELETE" }),
  link: (id: number, data: { transaction_id?: number; commitment_id?: number }) =>
    request<ReconciliationItem>(`/reconciliation/${id}/vincular`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  createTransaction: (id: number, data: TransactionCreate) =>
    request<ReconciliationItem>(`/reconciliation/${id}/lancamento`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  createCommitment: (id: number, data: CommitmentCreate) =>
    request<ReconciliationItem>(`/reconciliation/${id}/compromisso`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  createProvision: (id: number, data: ProvisionCreate) =>
    request<ReconciliationItem>(`/reconciliation/${id}/reserva`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// ---------- Contas, saldos observados e transferências ----------
// Saldo e qualidade vêm calculados (app/dominio/contas.py); a tela só formata.

export const accountsApi = {
  list: (incluirArquivadas = false) =>
    request<FinancialAccount[]>(`/accounts${incluirArquivadas ? "?incluir_arquivadas=1" : ""}`),
  summary: () => request<AccountsSummary>("/accounts/summary"),
  get: (id: number) => request<FinancialAccount>(`/accounts/${id}`),
  create: (data: AccountCreate) =>
    request<FinancialAccount>("/accounts", { method: "POST", body: JSON.stringify(data) }),
  update: (id: number, data: AccountUpdate) =>
    request<FinancialAccount>(`/accounts/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  remove: (id: number) => request<{ message: string }>(`/accounts/${id}`, { method: "DELETE" }),
  snapshots: (id: number) => request<AccountSnapshot[]>(`/accounts/${id}/snapshots`),
  informarSaldo: (id: number, data: { balance: number; note?: string | null }) =>
    request<{ snapshot: AccountSnapshot; account: FinancialAccount }>(`/accounts/${id}/snapshots`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  aceitarDiferenca: (id: number, snapshotId: number) =>
    request<AccountSnapshot>(`/accounts/${id}/snapshots/${snapshotId}/aceitar`, { method: "POST" }),
  movimentos: (id: number) => request<AccountMovement[]>(`/accounts/${id}/movimentos`),
  distribuir: (id: number, destinos: { account_id: number; amount: number }[]) =>
    request<AccountsSummary>(`/accounts/${id}/distribuir`, {
      method: "POST",
      body: JSON.stringify({ destinos }),
    }),
};

export const transfersApi = {
  list: (period?: Period) =>
    request<Transfer[]>(`/transfers${period ? `?year=${period.year}&month=${period.month}` : ""}`),
  create: (data: TransferCreate) =>
    request<Transfer>("/transfers", { method: "POST", body: JSON.stringify(data) }),
  remove: (id: number) => request<{ message: string }>(`/transfers/${id}`, { method: "DELETE" }),
};

export const investmentsApi = {
  summary: ({ year, month }: Period) => request<InvestmentSummary>(`/investments/summary?year=${year}&month=${month}`),
  movements: ({ year, month }: Period) => request<InvestmentMovement[]>(`/investments/movements?year=${year}&month=${month}`),
  createMovement: (data: InvestmentMovementCreate) =>
    request<InvestmentMovement>("/investments/movements", { method: "POST", body: JSON.stringify(data) }),
  removeMovement: (id: number) => request<{ message: string }>(`/investments/movements/${id}`, { method: "DELETE" }),
};

export const healthApi = {
  month: ({ year, month }: Period) =>
    request<SaudeDoMes>(`/months/${year}-${String(month).padStart(2, "0")}/health`),
};
