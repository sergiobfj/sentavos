import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Modal from "../Modal";
import MoneyCell from "../MoneyCell";
import Segmentado from "../Segmentado";
import { LinhaPlano, nomeDoMes, sinal } from "./comum";
import {
  useAddScenarioItem,
  useCreateScenario,
  usePlanningHorizon,
  useSetAssetSnapshot,
  useSimular,
  useUpdateAsset,
  useUpdateAccount,
  useInformarSaldo,
} from "../../lib/queries";
import { estadoDaConta } from "../../lib/tiposContas";
import { ApiError } from "../../lib/api";
import { formatDiaMes, formatMoney, formatYm, parseMoney, todayIso } from "../../lib/format";
import type { Period } from "../../lib/period";
import type {
  AvisoSaldo,
  ContaPlanejamento,
  PlanoItem,
  PlanoMes,
  PlanoReserva,
  ScenarioItemKind,
} from "../../lib/tiposPlanejamento";

/* O que sai da primeira camada mora aqui: a conta inteira, as listas, as
 * contas do saldo e o simular. Cada folha responde UMA pergunta. */

// ---------- Ver cálculo ----------

export function CalculoSheet({
  mes,
  contas,
  onContas,
  onClose,
}: {
  mes: PlanoMes;
  contas: ContaPlanejamento[];
  onContas?: () => void;
  onClose: () => void;
}) {
  const incluidas = contas.filter((c) => c.included && !c.stale).length;
  return (
    <Modal title={`Cálculo de ${nomeDoMes(mes.year, mes.month)}`} onClose={onClose}>
      <div className="m-body">
        <ul className="conta-plano">
          <li>
            <span className="op" aria-hidden />
            <span className="rot">
              {mes.opening_source === "saldos" ? "Saldo atual" : "Começa o mês com"}
              <small>
                {mes.opening_source === "saldos"
                  ? `${incluidas} ${incluidas === 1 ? "conta" : "contas"}`
                  : "o que sobra do mês anterior"}
                {onContas && mes.opening_source === "saldos" && (
                  <> · <button type="button" className="link-inline" onClick={onContas}>editar</button></>
                )}
              </small>
            </span>
            <b className="v tnum">{formatMoney(mes.opening)}</b>
          </li>
          <li>
            <span className="op">+</span>
            <span className="rot">Entradas futuras</span>
            <b className="v tnum">{formatMoney(mes.income)}</b>
          </li>
          <li>
            <span className="op">−</span>
            <span className="rot">Compromissos</span>
            <b className="v tnum">{formatMoney(mes.expense)}</b>
          </li>
          <li className="parcial">
            <span className="op">=</span>
            <span className="rot">Saldo projetado</span>
            <b className="v tnum">{formatMoney(mes.projected)}</b>
          </li>
          <li>
            <span className="op">−</span>
            <span className="rot">Reservado</span>
            <b className="v tnum">{formatMoney(mes.reserved)}</b>
          </li>
          <li className="total">
            <span className="op">=</span>
            <span className="rot">Disponível</span>
            <b className="v tnum">{formatMoney(mes.available)}</b>
          </li>
        </ul>
        <p className="nota">
          O que já entrou ou saiu está no saldo atual e não é somado de novo. Reservar não é
          gastar: o dinheiro reservado continua no patrimônio.
        </p>
      </div>
    </Modal>
  );
}

// ---------- A receber / comprometido ----------

export function ItensSheet({
  mes,
  direcao,
  onClose,
}: {
  mes: PlanoMes;
  /** Sem direção, as duas listas: o que entra e o que sai. */
  direcao?: "entrada" | "saida";
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const nome = nomeDoMes(mes.year, mes.month);

  function abrir(i: PlanoItem) {
    onClose();
    if (i.commitment_id != null) navigate(`/planejamento/compromissos?id=${i.commitment_id}`);
    else if (i.invoice_id != null) navigate("/orcamento?aba=faturas");
  }

  function Grupo({ lado }: { lado: "entrada" | "saida" }) {
    const doTipo = mes.items.filter((i) => i.direction === lado);
    const abertos = doTipo.filter((i) => i.status !== "pago");
    const pagos = doTipo.filter((i) => i.status === "pago");
    const total = lado === "entrada" ? mes.income : mes.expense;
    return (
      <section className="folha-grupo">
        <div className="folha-total">
          <b className="tnum">{lado === "entrada" ? "+ " : "− "}{formatMoney(total)}</b>
          <span>
            {lado === "entrada" ? "a receber" : "comprometidos"} · {abertos.length} {abertos.length === 1 ? "item" : "itens"}
            {lado === "saida" && mes.overdue > 0 && <> · {formatMoney(mes.overdue)} vencido</>}
          </span>
        </div>
        {abertos.length === 0 ? (
          <p className="hint">{lado === "entrada" ? "Nada previsto pra entrar." : "Nada a pagar."}</p>
        ) : (
          <ul className="lista-compacta">
            {abertos.map((i) => (
              <LinhaPlano key={i.key} item={i}
                onClick={i.commitment_id != null || i.invoice_id != null ? () => abrir(i) : undefined} />
            ))}
          </ul>
        )}
        {pagos.length > 0 && (
          <details className="detalhe">
            <summary>{pagos.length} já {lado === "entrada" ? "recebidos" : "pagos"} neste mês</summary>
            <ul className="lista-compacta">
              {pagos.map((i) => <LinhaPlano key={i.key} item={i} />)}
            </ul>
          </details>
        )}
      </section>
    );
  }

  return (
    <Modal title={direcao === "saida" ? `Comprometido em ${nome}` : `O que falta em ${nome}`} onClose={onClose}>
      <div className="m-body">
        {direcao !== "saida" && <Grupo lado="entrada" />}
        {direcao !== "entrada" && <Grupo lado="saida" />}
        <Link className="link-seta" to="/planejamento/compromissos" onClick={onClose}>
          Compromissos e reservas
        </Link>
      </div>
    </Modal>
  );
}

// ---------- Reservado ----------

/** Cada reserva dita como gente fala: "R$ 618 de R$ 618 reservado · coberto". */
export function ReservasSheet({ mes, onClose }: { mes: PlanoMes; onClose: () => void }) {
  const horizonte = usePlanningHorizon(12);
  const itens = new Map<string, PlanoItem>();
  for (const m of horizonte.data?.months ?? []) for (const i of m.items) itens.set(i.key, i);

  return (
    <Modal title={`Reservado em ${nomeDoMes(mes.year, mes.month)}`} onClose={onClose}>
      <div className="m-body">
        <div className="folha-total">
          <b className="tnum">{formatMoney(mes.reserved)}</b>
          <span>sai do disponível, continua no patrimônio</span>
        </div>
        {mes.reserves.length === 0 ? (
          <p className="hint">Nenhum dinheiro reservado.</p>
        ) : (
          <ul className="lista-compacta">
            {mes.reserves.map((r) => <LinhaReserva key={r.key} reserva={r} alvo={r.target_key ? itens.get(r.target_key) : undefined} />)}
          </ul>
        )}
        <Link className="link-seta" to="/planejamento/compromissos" onClick={onClose}>
          Gerenciar reservas
        </Link>
      </div>
    </Modal>
  );
}

function LinhaReserva({ reserva, alvo }: { reserva: PlanoReserva; alvo?: PlanoItem }) {
  let legenda: React.ReactNode;
  if (alvo) {
    const falta = Math.max(alvo.amount - alvo.provisioned, 0);
    legenda = (
      <>
        {formatMoney(alvo.provisioned)} de {formatMoney(alvo.amount)} · vence {formatDiaMes(alvo.date)} ·{" "}
        {falta < 0.005 ? <span className="ok">✓ coberto</span> : `faltam ${formatMoney(falta)}`}
      </>
    );
  } else {
    legenda =
      reserva.source === "aporte" ? "guardar previsto" : reserva.source === "cenario" ? "hipótese" : "objetivo";
  }
  return (
    <li>
      <div>
        <span className="esq">
          <span className="n">{reserva.target_label ?? reserva.description}</span>
          <span className="d">{legenda}</span>
        </span>
        <span className="v tnum">{formatMoney(reserva.amount)}</span>
      </div>
    </li>
  );
}

// ---------- Saldo considerado ----------

export function ContasSheet({
  contas,
  aviso,
  period,
  podeEscrever,
  onClose,
}: {
  contas: ContaPlanejamento[];
  aviso: AvisoSaldo;
  period: Period;
  podeEscrever: boolean;
  onClose: () => void;
}) {
  const atualizar = useUpdateAsset();
  const saldo = useSetAssetSnapshot();
  const atualizarConta = useUpdateAccount();
  const saldoDaConta = useInformarSaldo();
  const comContas = contas.some((c) => c.account_id != null);
  const ym = `${period.year}-${String(period.month).padStart(2, "0")}`;
  const total = contas.filter((c) => c.included && !c.stale).reduce((s, c) => s + c.value, 0);
  const erro = (atualizar.error || saldo.error) as ApiError | null;

  return (
    <Modal title="Saldo considerado" onClose={onClose}>
      <div className="m-body">
        <div className="folha-total">
          <b className="tnum">{formatMoney(total)}</b>
          <span>{comContas ? "as contas livres que entram no mês" : "marque onde está o dinheiro que você usa no mês"}</span>
        </div>
        <ul className="lista-compacta">
          {contas.map((c) =>
            c.account_id != null ? (
              // Conta financeira: o saldo é o calculado (observado + movimentos).
              // Digitar registra o saldo observado agora; restrita nunca entra.
              <li key={`conta-${c.account_id}`}>
                <div className="com-campo">
                  <label className="conta-toggle">
                    <input
                      type="checkbox"
                      checked={c.included}
                      disabled={!podeEscrever || atualizarConta.isPending || c.restricted}
                      onChange={(e) => atualizarConta.mutate({ id: c.account_id!, data: { include_in_planning: e.target.checked } })}
                    />
                    <span className="esq">
                      <span className="n">{c.name}</span>
                      <span className="d">
                        {c.restricted ? "restrita · " : ""}
                        {estadoDaConta({ quality: c.quality ?? "sem_saldo", observed_at: c.observed_at ?? null })}
                      </span>
                    </span>
                  </label>
                  <span className="saldo-input">
                    {podeEscrever ? (
                      <MoneyCell
                        saved={c.quality === "reconciliado" ? c.value : null}
                        placeholder={c.quality !== "sem_saldo" ? formatMoney(c.value) : "0,00"}
                        ariaLabel={`Saldo de ${c.name} agora`}
                        pending={saldoDaConta.isPending}
                        onCommit={(v) => {
                          if (v != null) saldoDaConta.mutate({ id: c.account_id!, balance: v });
                        }}
                      />
                    ) : (
                      <b className="tnum">{c.quality === "sem_saldo" ? "—" : formatMoney(c.value)}</b>
                    )}
                  </span>
                </div>
              </li>
            ) : (
            <li key={c.asset_id}>
              <div className="com-campo">
                <label className="conta-toggle">
                  <input
                    type="checkbox"
                    checked={c.included}
                    disabled={!podeEscrever || atualizar.isPending}
                    onChange={(e) => atualizar.mutate({ id: c.asset_id!, data: { include_in_planning: e.target.checked } })}
                  />
                  <span className="esq">
                    <span className="n">{c.name}</span>
                    <span className="d">
                      {c.as_of == null
                        ? "sem saldo"
                        : c.as_of === ym
                          ? c.observed_on ? `lido em ${formatDiaMes(c.observed_on)}` : "deste mês"
                          : c.stale && c.included
                            ? `de ${formatYm(c.as_of)} · fora até atualizar`
                            : `de ${formatYm(c.as_of)}`}
                    </span>
                  </span>
                </label>
                <span className="saldo-input">
                  {podeEscrever ? (
                    <MoneyCell
                      saved={c.as_of === ym ? c.value : null}
                      placeholder={c.as_of ? formatMoney(c.value) : "0,00"}
                      ariaLabel={`Saldo de ${c.name} hoje`}
                      pending={saldo.isPending}
                      onCommit={(v) => {
                        if (v != null) saldo.mutate({ asset_id: c.asset_id!, year: period.year, month: period.month, value: v });
                      }}
                    />
                  ) : (
                    <b className="tnum">{formatMoney(c.value)}</b>
                  )}
                </span>
              </div>
            </li>
          ))}
        </ul>
        {podeEscrever && (
          <p className="nota">
            {comContas
              ? "Digitar um valor registra o saldo observado agora — não vira lançamento."
              : "Digitar um valor lança o saldo de hoje em Patrimônio."}
          </p>
        )}

        {aviso.quantidade > 0 && aviso.desde && (
          <details className="detalhe">
            <summary>
              {aviso.quantidade} {aviso.quantidade === 1 ? "movimento" : "movimentos"} depois de {formatDiaMes(aviso.desde)} não
              {aviso.quantidade === 1 ? " está" : " estão"} no saldo
            </summary>
            <ul className="lista-compacta">
              {aviso.movimentos.map((m, i) => (
                <li key={i}>
                  <div>
                    <span className="esq">
                      <span className="n">{m.description}</span>
                      <span className="d">
                        {formatDiaMes(m.date)}
                        {m.tipo === "investimento" && " · talvez transferência entre suas contas"}
                      </span>
                    </span>
                    <span className="v tnum">{m.tipo === "entrada" ? "+" : "−"}{formatMoney(m.amount)}</span>
                  </div>
                </li>
              ))}
            </ul>
            <p className="nota">O app não sabe de qual conta cada um saiu, então não desconta sozinho: atualize os saldos acima.</p>
          </details>
        )}
        {erro && <div className="error-box">{erro.message}</div>}
      </div>
    </Modal>
  );
}

// ---------- Simular gasto ----------

const TIPOS: { valor: ScenarioItemKind; rotulo: string }[] = [
  { valor: "saida", rotulo: "Gastar" },
  { valor: "entrada", rotulo: "Receber" },
  { valor: "reserva", rotulo: "Guardar" },
];

function dataPadrao(mes: PlanoMes): string {
  return mes.is_current ? todayIso() : `${mes.year}-${String(mes.month).padStart(2, "0")}-15`;
}

/** "E se eu gastar isso?" — calcula enquanto digita e não grava nada. */
export function SimularGastoSheet({
  mes,
  cenarioId,
  podeEscrever,
  onSalvo,
  onClose,
}: {
  mes: PlanoMes;
  cenarioId?: number | null;
  podeEscrever: boolean;
  onSalvo?: (cenarioId: number) => void;
  onClose: () => void;
}) {
  const [descricao, setDescricao] = useState("");
  const [valor, setValor] = useState("");
  const [data, setData] = useState(dataPadrao(mes));
  const [tipo, setTipo] = useState<ScenarioItemKind>("saida");
  const simular = useSimular();
  const criar = useCreateScenario();
  const adicionar = useAddScenarioItem();
  const numero = parseMoney(valor) ?? 0;
  const ultimo = useRef(0);

  const hipotese = {
    kind: tipo,
    description: descricao.trim() || (tipo === "saida" ? "Gasto" : tipo === "entrada" ? "Entrada" : "Guardar"),
    amount: numero,
    date: data,
  };

  // Calcula sozinho, meio segundo depois de parar de digitar.
  useEffect(() => {
    if (numero <= 0) return;
    const pedido = ++ultimo.current;
    const t = setTimeout(() => {
      if (pedido === ultimo.current) {
        simular.mutate({ year: mes.year, month: mes.month, scenario_id: cenarioId ?? null, extras: [hipotese] });
      }
    }, 450);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [numero, data, tipo]);

  const depois = numero > 0 ? simular.data?.months[0]?.available : undefined;
  const diferenca = depois != null ? depois - mes.available : null;

  function salvar() {
    if (cenarioId) {
      adicionar.mutate({ id: cenarioId, data: hipotese }, { onSuccess: () => { onSalvo?.(cenarioId); onClose(); } });
      return;
    }
    criar.mutate(
      { name: hipotese.description.slice(0, 60) },
      {
        onSuccess: (novo) =>
          adicionar.mutate({ id: novo.id, data: hipotese }, { onSuccess: () => { onSalvo?.(novo.id); onClose(); } }),
      }
    );
  }

  const erro = (simular.error || criar.error || adicionar.error) as ApiError | null;

  return (
    <Modal
      title="Simular gasto"
      onClose={onClose}
      footer={
        podeEscrever && depois != null ? (
          <button type="button" className="btn" disabled={criar.isPending || adicionar.isPending} onClick={salvar}>
            {cenarioId ? "Guardar nesta simulação" : "Salvar como simulação"}
          </button>
        ) : undefined
      }
    >
      <div className="m-body">
        <div className="row2">
          <div className="field">
            <label htmlFor="sg-desc">Descrição</label>
            <input id="sg-desc" autoFocus placeholder="Ex.: Viagem" value={descricao} onChange={(e) => setDescricao(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="sg-valor">Valor</label>
            <input id="sg-valor" inputMode="decimal" placeholder="0,00" value={valor} onChange={(e) => setValor(e.target.value)} />
          </div>
        </div>

        <ul className="conta-plano compacta">
          <li>
            <span className="op" aria-hidden />
            <span className="rot">Disponível atual</span>
            <b className="v tnum">{formatMoney(mes.available)}</b>
          </li>
          <li>
            <span className="op" aria-hidden />
            <span className="rot">Depois da simulação</span>
            <b className="v tnum">{depois != null ? formatMoney(depois) : "—"}</b>
          </li>
          <li className="total">
            <span className="op" aria-hidden />
            <span className="rot">Diferença</span>
            <b className={`v tnum${diferenca != null && diferenca < 0 ? " neg" : ""}`}>
              {diferenca != null ? sinal(diferenca) : "—"}
            </b>
          </li>
        </ul>
        {depois != null && depois < 0 && <p className="nota neg">Faltaria dinheiro livre no fim do mês.</p>}

        <details className="detalhe">
          <summary>Mais opções</summary>
          <div className="field" style={{ marginTop: "var(--s3)" }}>
            <Segmentado rotulo="Tipo" opcoes={TIPOS} valor={tipo} aoEscolher={setTipo} largo />
          </div>
          <div className="field">
            <label htmlFor="sg-data">Data</label>
            <input id="sg-data" type="date" value={data} onChange={(e) => setData(e.target.value)} />
          </div>
        </details>
        <p className="nota">É só uma conta: nada é lançado.</p>
        {erro && <div className="error-box">{erro.message}</div>}
      </div>
    </Modal>
  );
}
