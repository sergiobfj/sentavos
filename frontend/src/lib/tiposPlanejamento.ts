// Espelha app/planejamento.py e o bloco "Planejamento" de app/models.py.
//
// Quatro coisas que não se misturam: realizado (Transaction), compromisso
// (Commitment), reserva (Provision) e simulação (Scenario). A tela só desenha:
// toda conta vem pronta do servidor — refazê-la aqui seria a segunda cópia da
// regra, e duas cópias de uma regra de dinheiro discordam um dia.

import type { AssetClass, Finalidade } from "./types";

export type Certeza = "confirmado" | "estimado" | "hipotetico";
export type OrigemPlano = "cartao" | "parcelado" | "recorrente" | "previsto" | "cenario";

export const CERTEZA_LABEL: Record<Certeza, string> = {
  confirmado: "confirmado",
  estimado: "estimado",
  hipotetico: "hipotético",
};

export const ORIGEM_LABEL: Record<OrigemPlano, string> = {
  cartao: "Cartão",
  parcelado: "Parcelados",
  recorrente: "Recorrentes",
  previsto: "Previstos",
  cenario: "Hipóteses",
};

export interface PlanoItem {
  key: string;
  source: OrigemPlano;
  direction: "entrada" | "saida";
  description: string;
  detail: string | null;
  date: string;
  year: number;
  month: number;
  // O esperado; `remaining` é o que ainda conta na conta do mês.
  amount: number;
  remaining: number;
  certainty: Certeza;
  status: "pendente" | "vencido" | "pago";
  label: string | null;
  provisioned: number;
  // Mudado por um cenário: o valor de antes.
  original_amount: number | null;
  icon: string | null;
  color: string | null;
  commitment_id: number | null;
  commitment_no: number | null;
  invoice_id: number | null;
  transaction_id: number | null;
  scenario_item_id: number | null;
}

export interface PlanoReserva {
  key: string;
  source: "reserva" | "aporte" | "cenario";
  description: string;
  amount: number;
  certainty: Certeza;
  since: [number, number];
  target_key: string | null;
  target_label: string | null;
  original_amount: number | null;
  provision_id: number | null;
}

export interface PlanoMes {
  year: number;
  month: number;
  is_current: boolean;
  opening_source: "saldos" | "projecao";
  opening: number;
  income: number;
  expense: number;
  projected: number;
  reserved: number;
  available: number;
  by_certainty: Record<Certeza, number>;
  by_source: Record<OrigemPlano, number>;
  overdue: number;
  provisioned: number;
  still_needed: number;
  items: PlanoItem[];
  reserves: PlanoReserva[];
}

export interface ContaPlanejamento {
  // Uma das duas: a conta financeira (quem tem contas) ou o ativo (o jeito
  // anterior, pra quem ainda não cadastrou contas).
  asset_id: number | null;
  account_id?: number | null;
  name: string;
  asset_class: AssetClass | null;
  account_type?: string | null;
  restricted?: boolean;
  quality?: "reconciliado" | "calculado" | "desatualizado" | "sem_saldo" | null;
  observed_at?: string | null;
  maybe_incomplete?: boolean;
  included: boolean;
  value: number;
  as_of: string | null;
  observed_on: string | null;
  // Último saldo é de mês anterior: aparece, mas não entra no saldo de partida.
  stale?: boolean;
}

export interface MovimentoDepois {
  date: string;
  description: string;
  amount: number;
  tipo: "entrada" | "saida" | "fatura" | "investimento";
}

/** Por que o saldo de partida talvez não seja o de hoje. Nada daqui é aplicado. */
export interface AvisoSaldo {
  desatualizado: boolean;
  sem_dia: boolean;
  sem_contas: boolean;
  contas_sem_saldo: string[];
  contas_desatualizadas?: string[];
  desde: string | null;
  entradas: number;
  saidas: number;
  investimentos: number;
  quantidade: number;
  movimentos: MovimentoDepois[];
}

export interface PlanoResposta {
  today: string;
  scenario_id: number | null;
  scenario_name: string | null;
  accounts: ContaPlanejamento[];
  balance_warning: AvisoSaldo;
  months: PlanoMes[];
}

export interface Comparacao {
  scenario_id: number;
  scenario_name: string;
  base: PlanoMes;
  scenario: PlanoMes;
  diff: { projected: number; expense: number; income: number; reserved: number; available: number };
}

export type OccurrenceStatus = "pendente" | "vencida" | "paga" | "dispensada" | "cancelada" | "prevista";

export const OCORRENCIA_LABEL: Record<OccurrenceStatus, string> = {
  pendente: "a pagar",
  vencida: "vencida",
  paga: "paga",
  dispensada: "dispensada",
  cancelada: "cancelada",
  // Entrada que já está num lançamento só previsto: conta uma vez, por ele.
  prevista: "já prevista",
};

// Nota das dispensas criadas por "Pausar" (`planejamento.PAUSA`).
export const PAUSA = "Pausa";

export interface Ocorrencia {
  number: number;
  due_date: string;
  amount: number;
  status: OccurrenceStatus;
  label: string | null;
  transaction_id: number | null;
  paid_amount: number | null;
  paid_date: string | null;
  provisioned: number;
  skip_note: string | null;
  // Reconhecida num lançamento da mesma categoria perto do vencimento (não
  // vinculada à mão).
  matched?: boolean;
}

export interface CommitmentCreate {
  description: string;
  category_id: number;
  amount: number;
  first_due: string;
  installments?: number | null;
  interval_months?: number;
  end_date?: string | null;
  confirmed?: boolean;
  finalidade?: Finalidade | null;
  institution?: string | null;
  total_amount?: number | null;
  down_payment?: number | null;
  payment_hint?: string | null;
  note?: string | null;
}

export type CommitmentUpdate = Partial<CommitmentCreate> & { cancelled_on?: string | null };

export interface Commitment {
  id: number;
  description: string;
  category_id: number;
  amount: number;
  first_due: string;
  installments: number | null;
  interval_months: number;
  end_date: string | null;
  confirmed: boolean;
  finalidade: Finalidade | null;
  institution: string | null;
  total_amount: number | null;
  down_payment: number | null;
  payment_hint: string | null;
  note: string | null;
  cancelled_on: string | null;
  kind: "parcelado" | "recorrente";
  direction: "saida" | "entrada";
  category_name: string;
  color: string;
  icon: string;
  status: "ativo" | "quitado" | "encerrado" | "cancelado";
  paid_count: number;
  skipped_count: number;
  overdue_count: number;
  overdue_amount: number;
  total_count: number | null;
  remaining_count: number | null;
  // Soma NOMINAL do que falta — não é saldo devedor.
  remaining_nominal: number | null;
  next: Ocorrencia | null;
  // Última ocorrência futura dispensada por pausa.
  paused_until?: string | null;
}

export interface CommitmentDetail extends Commitment {
  schedule: Ocorrencia[];
}

export interface Provision {
  id: number;
  description: string;
  amount: number;
  created_on: string;
  commitment_id: number | null;
  commitment_no: number | null;
  target_date: string | null;
  note: string | null;
  released_on: string | null;
  status: "ativa" | "cumprida" | "liberada";
  commitment_description: string | null;
  occurrence_label: string | null;
  occurrence_due: string | null;
}

export interface ProvisionCreate {
  description?: string | null;
  amount: number;
  created_on?: string | null;
  commitment_id?: number | null;
  commitment_no?: number | null;
  target_date?: string | null;
  note?: string | null;
}

export type ProvisionUpdate = Partial<
  Pick<Provision, "description" | "amount" | "created_on" | "target_date" | "note" | "released_on">
>;

export type ScenarioItemKind = "entrada" | "saida" | "reserva";

export interface ScenarioItem {
  id: number;
  scenario_id: number;
  kind: ScenarioItemKind;
  description: string;
  amount: number;
  date: string;
  repeat_months: number;
  ref: string | null;
}

export interface ScenarioItemCreate {
  kind: ScenarioItemKind;
  description: string;
  amount: number;
  date: string;
  repeat_months?: number;
  ref?: string | null;
}

export interface Scenario {
  id: number;
  name: string;
  note: string | null;
  created_at: string;
  items: ScenarioItem[];
}

// ---------- Conferência do mês ----------

export type ReconciliationKind = "entrada" | "saida" | "obrigacao" | "reserva" | "saldo" | "outro";
export type ReconciliationStatus = "pendente" | "confirmar" | "resolvido" | "ignorado";

export const CONFERENCIA_TIPO_LABEL: Record<ReconciliationKind, string> = {
  entrada: "Entrada",
  saida: "Saída",
  obrigacao: "Compromisso",
  reserva: "Reserva",
  saldo: "Saldo observado",
  outro: "Pergunta",
};

export interface Candidato {
  kind: "lancamento" | "parcela" | "previsto" | "fatura" | "compromisso";
  id: number;
  description: string;
  amount: number | null;
  date: string | null;
  detail: string | null;
  score: number;
  reasons: string[];
  // Já vinculado a outro item desta conferência.
  used: boolean;
}

export interface ReconciliationItem {
  id: number;
  year: number;
  month: number;
  description: string;
  amount: number | null;
  date: string | null;
  kind: ReconciliationKind;
  status: ReconciliationStatus;
  suggestion: string | null;
  question: string | null;
  category_hint: string | null;
  prefill: Record<string, unknown> | null;
  note: string | null;
  source: string;
  transaction_id: number | null;
  commitment_id: number | null;
  provision_id: number | null;
  linked: {
    kind: "lancamento" | "compromisso" | "reserva";
    id: number;
    description: string;
    amount: number | null;
    date: string | null;
  } | null;
  link_missing: boolean;
  candidates: Candidato[];
}

export interface ReconciliationList {
  year: number;
  month: number;
  counts: Record<ReconciliationStatus, number>;
  items: ReconciliationItem[];
}

export interface ReconciliationItemCreate {
  year: number;
  month: number;
  description: string;
  amount?: number | null;
  date?: string | null;
  kind?: ReconciliationKind;
  question?: string | null;
}

// ---------- Conferir mês (app/dominio/saude.py) ----------
// Derivado no servidor: nada é gravado. Pendências agrupadas por tipo.

export type EstadoDoMes = "conciliado" | "parcial" | "precisa_revisar";

export interface Pendencia {
  code: string;
  severity: "revisar" | "aviso";
  title: string;
  detail: string | null;
  count: number;
  amount: number | null;
  where: string | null;
  items: { label: string; date: string | null; amount: number | null; ref: number | null }[];
}

export interface SaudeDoMes {
  year: number;
  month: number;
  state: EstadoDoMes;
  issues: Pendencia[];
  to_review: number;
  warnings: number;
  trustworthy_balance: boolean;
}

export const ESTADO_DO_MES_LABEL: Record<EstadoDoMes, string> = {
  conciliado: "conciliado",
  parcial: "parcial",
  precisa_revisar: "precisa revisar",
};
