// Espelha os modelos do backend (app/models.py)

export type CategoryType = "expense" | "income" | "investment";

export interface Category {
  id: number;
  name: string;
  type: CategoryType;
  color: string;
  icon: string;
  // Arquivada some do formulário de lançamento mas continua no banco: os
  // lançamentos antigos apontam pra ela.
  archived: boolean;
}

export type CategoryCreate = Omit<Category, "id" | "archived">;
export type CategoryUpdate = Partial<CategoryCreate> & { archived?: boolean };

// Como o dinheiro sai (ou não sai) da conta.
//
// `null` é um terceiro estado e é de propósito: os lançamentos anteriores ao
// cartão não têm essa informação, e inventá-la seria pior que admitir que ela
// falta. A Carteira conta esses como saída — é como já eram contados — e a tela
// avisa quantos ainda estão sem resposta.
export type PaymentMethod = "cash" | "credit";

export const PAYMENT_METHOD_LABEL: Record<PaymentMethod, string> = {
  cash: "À vista",
  credit: "Cartão",
};

export interface Transaction {
  id: number;
  date: string; // ISO date (YYYY-MM-DD) — a competência: o mês em que isto conta
  description: string;
  amount_planned: number | null;
  amount_paid: number | null;
  note: string | null;
  category_id: number;
  payment_method: PaymentMethod | null;

  // ---------- Só em parcela de compra no cartão ----------
  // Vêm calculados do backend pra a linha da lista poder dizer
  // "Notebook · Compras · Nubank 2/3" sem uma chamada por linha.
  purchase_id?: number | null;
  installment_no?: number | null;
  invoice_id?: number | null;
  installments?: number | null;
  purchase_total?: number | null;
  purchase_date?: string | null;
  card_id?: number | null;
  card_name?: string | null;
}

export type TransactionCreate = Omit<
  Transaction,
  | "id" | "purchase_id" | "installment_no" | "invoice_id" | "installments"
  | "purchase_total" | "purchase_date" | "card_id" | "card_name"
>;
export type TransactionUpdate = Partial<TransactionCreate>;

/** Parcela não é lançamento solto: as N somam o valor da compra. Editar ou
 *  apagar uma sozinha quebraria esse total, então a API recusa (409) e a tela
 *  manda pra compra. */
export function ehParcela(t: Transaction): boolean {
  return t.purchase_id != null;
}

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
  archived: boolean;
  budget_id: number | null;
  // O teto do mês. Zero (ou budget_id nulo) é categoria sem teto — gastar nela
  // continua valendo, só não há régua pra comparar.
  //
  // Existiu aqui a caixinha acumulativa (has_envelope, carried_in, available):
  // o que sobrava num mês virava saldo do seguinte. Saiu porque o número
  // dependia de todo o passado — uma meta esquecida em janeiro voltava como
  // dívida em setembro. Cada mês agora se explica sozinho.
  budgeted: number;
  planned: number;
  paid: number;
}

export interface BudgetSummaryTotals {
  budgeted: number;
  planned: number;
  paid: number;
}

/** Os dois eixos do mês, que eram o mesmo número até o cartão existir.
 *
 *  Gastei 1.200 (500 à vista + 700 no cartão) e saiu da conta 500 — o cartão sai
 *  quando a fatura for paga. Vem junto do resumo de orçamento porque a tela de
 *  Início já pede esse resumo: uma chamada a mais ali seria espera por nada. */
export interface Caixa {
  // Dinheiro de verdade
  entrou: number;
  saiu_a_vista: number;
  investido: number;
  faturas_pagas: number;
  carteira: number;
  // O que foi consumido — é o número das metas
  gasto_total: number;
  no_cartao: number;
  // Transição: despesa anterior ao cartão, ainda sem forma de pagamento
  sem_forma_definida: number;
  sem_forma_definida_qtd: number;
  // Compromisso
  faturas_do_mes: number;
  faturas_em_aberto: number;
  apos_faturas: number;
}

export interface BudgetSummary {
  year: number;
  month: number;
  items: BudgetSummaryItem[];
  // Continua medindo GASTO: compra no cartão consome a meta no mês da parcela,
  // mesmo sem ter saído da conta.
  totals: Record<CategoryType, BudgetSummaryTotals>;
  caixa: Caixa;
}

// ---------- Cartão de crédito ----------

export interface Card {
  id: number;
  name: string;
  closing_day: number;
  due_day: number;
  archived: boolean;
}

export type CardCreate = Omit<Card, "id" | "archived">;
export type CardUpdate = Partial<CardCreate> & { archived?: boolean };

export type InvoiceStatus = "aberta" | "parcial" | "paga" | "atrasada";

export const INVOICE_STATUS_LABEL: Record<InvoiceStatus, string> = {
  aberta: "Aberta",
  parcial: "Parcial",
  paga: "Paga",
  atrasada: "Atrasada",
};

export interface Invoice {
  id: number;
  card_id: number;
  card_name: string;
  // Referência = mês do VENCIMENTO, que é como o banco chama a fatura.
  year: number;
  month: number;
  closing_date: string;
  due_date: string;
  total: number;
  paid: number;
  remaining: number;
  status: InvoiceStatus;
  item_count: number;
}

export interface InvoiceItem {
  transaction_id: number;
  date: string;
  description: string;
  amount: number;
  category_id: number;
  category_name: string;
  color: string;
  icon: string;
  // Nulos em compra de uma parcela só: "1/1" não informa nada.
  installment_no: number | null;
  installments: number | null;
  purchase_id: number;
  purchase_total: number;
  purchase_date: string;
}

export interface InvoicePayment {
  id: number;
  invoice_id: number;
  date: string;
  amount: number;
  note: string | null;
  card_id: number;
  card_name: string;
  invoice_year: number;
  invoice_month: number;
}

export interface InvoiceDetail extends Invoice {
  items: InvoiceItem[];
  payments: InvoicePayment[];
}

export interface CardInvoices {
  card_id: number;
  name: string;
  closing_day: number;
  due_day: number;
  archived: boolean;
  current: Invoice | null;
  next: Invoice | null;
  open_total: number;
}

export interface InvoicesSummary {
  year: number;
  month: number;
  cards: CardInvoices[];
  payments: InvoicePayment[];
  due_this_month: number;
  paid_this_month: number;
  open_total: number;
}

export interface Purchase {
  id: number;
  card_id: number;
  card_name: string;
  category_id: number;
  category_name: string;
  color: string;
  icon: string;
  description: string;
  total_amount: number;
  installments: number;
  purchase_date: string;
  note: string | null;
  installment_amounts: number[];
  paid_installments: number;
  // Com fatura paga, valor/parcelas/cartão/data não mudam mais: mexer
  // reescreveria uma fatura que já foi cobrada.
  locked: boolean;
}

export interface PurchaseCreate {
  card_id: number;
  category_id: number;
  description: string;
  total_amount: number;
  installments: number;
  purchase_date: string;
  note?: string | null;
}

export type PurchaseUpdate = Partial<PurchaseCreate>;

export interface CandidatoAPagamento {
  id: number;
  date: string;
  description: string;
  amount: number;
  category_name: string;
  payment_method: PaymentMethod | null;
}

export const CATEGORY_TYPE_LABEL: Record<CategoryType, string> = {
  expense: "Despesa",
  income: "Receita",
  investment: "Investimento",
};

// ---------- Patrimônio ----------
// Transaction é fluxo; aqui é estoque — quanto cada coisa vale num mês.

export type AssetClass =
  | "checking"
  | "fixed_income"
  | "equity"
  | "crypto"
  | "real_estate"
  | "vehicle"
  | "debt";

export interface Asset {
  id: number;
  name: string;
  asset_class: AssetClass;
  note: string | null;
  // Quanto do CDI a aplicação paga (115 = 115% do CDI). Nulo = não rende, que
  // é o caso de conta corrente, imóvel e carro.
  cdi_percent: number | null;
}

export type AssetCreate = Omit<Asset, "id" | "cdi_percent"> & {
  cdi_percent?: number | null;
};
export type AssetUpdate = Partial<AssetCreate>;

export interface AssetSnapshotSet {
  asset_id: number;
  year: number;
  month: number;
  value: number;
}

export interface AssetSummaryItem {
  asset_id: number;
  name: string;
  asset_class: AssetClass;
  liability: boolean;
  note: string | null;
  cdi_percent: number | null;
  // Quanto a aplicação DEVERIA render no mês, pela taxa declarada. Bruto: não
  // desconta imposto de renda nem IOF. Null quando não há taxa, ou quando o
  // CDI ainda não foi informado nas configurações.
  expected_yield: number | null;
  // Null quando o valor foi herdado de um mês anterior: não há saldo deste
  // mês pra editar, então a tela mostra de quando ele é (as_of).
  snapshot_id: number | null;
  value: number;
  previous: number;
  change: number;
  as_of: string | null;
}

export interface AssetClassTotal {
  value: number;
  previous: number;
}

export interface AssetSummary {
  year: number;
  month: number;
  items: AssetSummaryItem[];
  by_class: Record<AssetClass, AssetClassTotal>;
  assets: number;
  liabilities: number;
  net_worth: number;
  previous_net_worth: number;
}

export const ASSET_CLASS_LABEL: Record<AssetClass, string> = {
  checking: "Conta",
  fixed_income: "Renda fixa",
  equity: "Renda variável",
  crypto: "Cripto",
  real_estate: "Imóvel",
  vehicle: "Veículo",
  debt: "Dívida",
};

// A ordem em que as classes aparecem na tela: líquido primeiro, dívida no fim.
export const ASSET_CLASS_ORDER: AssetClass[] = [
  "checking",
  "fixed_income",
  "equity",
  "crypto",
  "real_estate",
  "vehicle",
  "debt",
];

// Espelha INVESTMENT_CLASSES do backend — a aba de Investimento filtra por elas.
export const INVESTMENT_CLASSES: AssetClass[] = ["fixed_income", "equity", "crypto"];
