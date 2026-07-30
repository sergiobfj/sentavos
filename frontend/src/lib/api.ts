import { accessToken, supabase } from "./supabase";
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
  Category,
  CategoryCreate,
  CategoryUpdate,
  Transaction,
  TransactionCreate,
  TransactionUpdate,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  // Toda chamada passa por aqui, então o token entra num lugar só — não tem
  // como uma rota nova esquecer de mandar.
  const token = await accessToken();

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

  // Token venceu ou foi revogado: derruba a sessão pra a tela de login aparecer,
  // em vez de deixar o app mostrando erro em toda aba.
  if (res.status === 401) {
    await supabase.auth.signOut();
    throw new ApiError(401, "Sua sessão expirou. Entre de novo.");
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

// ---------- Categorias ----------
export const categoriesApi = {
  list: () => request<Category[]>("/categories"),
  get: (id: number) => request<Category>(`/categories/${id}`),
  create: (data: CategoryCreate) =>
    request<Category>("/categories", { method: "POST", body: JSON.stringify(data) }),
  update: (id: number, data: CategoryUpdate) =>
    request<Category>(`/categories/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  remove: (id: number) => request<{ message: string }>(`/categories/${id}`, { method: "DELETE" }),
};
