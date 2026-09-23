import { EVENTO_SESSAO_EXPIRADA } from "./auth";
import { carregarSessao, limparSessao } from "./session";
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
  CategoryCreate,
  CategoryUpdate,
  Invoice,
  InvoiceDetail,
  InvoicesSummary,
  PaymentMethod,
  Purchase,
  PurchaseCreate,
  PurchaseUpdate,
  Transaction,
  TransactionCreate,
  TransactionUpdate,
} from "./types";

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
  pay: (id: number, data: { amount: number; date: string }) =>
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
