import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import Modal from "../Modal";
import ConfirmDialog from "../ConfirmDialog";
import MoneyCell from "../MoneyCell";
import Segmentado from "../Segmentado";
import { LinhaPlano, nomeDoMes, sinal } from "./comum";
import {
  useAddScenarioItem,
  useComparacao,
  useCreateScenario,
  useDeleteScenario,
  useDuplicateScenario,
  usePlanningMonth,
  useRemoveScenarioItem,
  useScenarios,
  useSetAssetSnapshot,
  useSimular,
  useUpdateAsset,
  useUpdateScenario,
} from "../../lib/queries";
import { currentPeriod, usePeriod, type Period } from "../../lib/period";
import { useAuth } from "../../lib/auth";
import { ApiError } from "../../lib/api";
import { formatDiaMes, formatMoney, formatYm, parseMoney } from "../../lib/format";
import type {
  AvisoSaldo,
  ContaPlanejamento,
  PlanoItem,
  PlanoMes,
  PlanoReserva,
  Scenario,
  ScenarioItemKind,
} from "../../lib/tiposPlanejamento";

/** "Simular mês": quanto tenho, quanto entra, quanto sai, quanto sobra e quanto
 *  disso está livre. A conta inteira vem do servidor; aqui ela só é desenhada.
 *
 *  O cenário escolhido mora na URL (?cenario=) pra sobreviver ao F5 e ao
 *  vaivém entre as abas do planejamento. */
export default function SimularMes() {
  const { period, setPeriod } = usePeriod();
  const atual = currentPeriod();
  const passado = period.year * 12 + period.month < atual.year * 12 + atual.month;
  const [params, setParams] = useSearchParams();
  const cenarioId = Number(params.get("cenario")) || null;

  function escolherCenario(id: number | null) {
    setParams(
      (prev) => {
        const p = new URLSearchParams(prev);
        if (id == null) p.delete("cenario");
        else p.set("cenario", String(id));
        return p;
      },
      { replace: true }
    );
  }

  if (passado) {
    return (
      <div className="empty">
        <div className="big">🗓️</div>
        <div className="tit">O planejamento olha pra frente</div>
        <div>
          {nomeDoMes(period.year, period.month, true)} já passou: o que aconteceu nele está em
          Lançamentos. O planejamento começa no mês atual.
        </div>
        <div style={{ marginTop: "var(--s4)" }}>
          <button className="btn btn-primary" onClick={() => setPeriod(atual)}>
            Ir para {nomeDoMes(atual.year, atual.month)}
          </button>
        </div>
      </div>
    );
  }

  return <Mes period={period} cenarioId={cenarioId} escolherCenario={escolherCenario} />;
}

function Mes({
  period,
  cenarioId,
  escolherCenario,
}: {
  period: Period;
  cenarioId: number | null;
  escolherCenario: (id: number | null) => void;
}) {
  const navigate = useNavigate();
  const { sessao } = useAuth();
  const podeEscrever = !sessao?.somenteLeitura;
  const { data: cenarios } = useScenarios();
  const cenario = cenarios?.find((s) => s.id === cenarioId) ?? null;
  const { data, isLoading, error } = usePlanningMonth(period, cenario ? cenario.id : null);
  const comparacao = useComparacao(period, cenario ? cenario.id : null);

  const [contasAbertas, setContasAbertas] = useState(false);
  const [simulando, setSimulando] = useState(false);
  const [novoCenario, setNovoCenario] = useState(false);
  const [editandoCenario, setEditandoCenario] = useState(false);
  const [hipotese, setHipotese] = useState(false);
  const [ajustando, setAjustando] = useState<PlanoItem | PlanoReserva | null>(null);

  if (isLoading && !data) {
    return (
      <>
        <div className="skel" style={{ height: 44, width: "70%", marginTop: "var(--s3)" }} />
        <div className="skel" style={{ height: 220, marginTop: "var(--s4)" }} />
      </>
    );
  }
  if (error) return <div className="error-box">{(error as ApiError).message}</div>;
  if (!data || data.months.length === 0) return null;

  const mes = data.months[0];
  const nome = nomeDoMes(mes.year, mes.month);
  const entradas = mes.items.filter((i) => i.direction === "entrada");
  const saidas = mes.items.filter((i) => i.direction === "saida");
  const contasNaConta = data.accounts.filter((c) => c.included);

  function tocarItem(item: PlanoItem) {
    // Com cenário, tocar ajusta o item SÓ no cenário. Sem cenário, leva ao
    // lugar onde ele de fato se resolve.
    if (cenario && podeEscrever) {
      if (item.status !== "pago") setAjustando(item);
      return;
    }
    if (item.commitment_id != null) navigate(`/planejamento?aba=compromissos&id=${item.commitment_id}`);
    else if (item.invoice_id != null) navigate("/orcamento?aba=faturas");
  }

  return (
    <>
      {/* ---------- Cenário ---------- */}
      <div className="cenarios">
        <div className="chip-linha" role="group" aria-label="Cenário">
          <button className={cenario == null ? "on" : ""} onClick={() => escolherCenario(null)}>
            Base
          </button>
          {(cenarios ?? []).map((s) => (
            <button
              key={s.id}
              className={cenario?.id === s.id ? "on" : ""}
              onClick={() => escolherCenario(s.id)}
            >
              {s.name}
            </button>
          ))}
          {podeEscrever && (
            <button className="novo" onClick={() => setNovoCenario(true)}>
              + Cenário
            </button>
          )}
        </div>
      </div>

      {/* ---------- Herói: o disponível ---------- */}
      <section className="hero" aria-labelledby="disp-rotulo">
        <div className="big tnum">{formatMoney(mes.available)}</div>
        <div className="rot" id="disp-rotulo">
          Disponível em {nome}
          {cenario ? ` · ${cenario.name}` : ""}
        </div>
        {cenario && comparacao.data && (
          <div className="delta">
            {sinal(comparacao.data.diff.available)} em relação à base (
            {formatMoney(comparacao.data.base.available)})
          </div>
        )}
      </section>

      {/* ---------- A conta ---------- */}
      <ul className="conta-plano">
        <li>
          <span className="op" aria-hidden />
          {mes.opening_source === "saldos" ? (
            <button className="rot" onClick={() => setContasAbertas(true)}>
              Saldo atual <span aria-hidden style={{ color: "var(--text-faint)" }}>›</span>
              <small>
                {contasNaConta.length === 0
                  ? "nenhuma conta escolhida"
                  : contasNaConta.map((c) => c.name).join(", ")}
              </small>
            </button>
          ) : (
            <span className="rot">
              Começa o mês com
              <small>o projetado do mês anterior</small>
            </span>
          )}
          <b className="v tnum">{formatMoney(mes.opening)}</b>
        </li>
        <li>
          <span className="op">+</span>
          <span className="rot">Entradas restantes</span>
          <b className="v tnum">{formatMoney(mes.income)}</b>
        </li>
        <li>
          <span className="op">−</span>
          <span className="rot">
            Saídas restantes
            {mes.expense > 0 && (
              <small>
                {[
                  mes.by_certainty.confirmado > 0 && `${formatMoney(mes.by_certainty.confirmado)} confirmado`,
                  mes.by_certainty.estimado > 0 && `${formatMoney(mes.by_certainty.estimado)} estimado`,
                  mes.by_certainty.hipotetico > 0 && `${formatMoney(mes.by_certainty.hipotetico)} hipotético`,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </small>
            )}
          </span>
          <b className="v tnum">{formatMoney(mes.expense)}</b>
        </li>
        <li className="parcial">
          <span className="op">=</span>
          <span className="rot">Saldo projetado no fim do mês</span>
          <b className="v tnum">{formatMoney(mes.projected)}</b>
        </li>
        <li>
          <span className="op">−</span>
          <span className="rot">
            Reservas
            <small>dinheiro que existe, mas já tem destino</small>
          </span>
          <b className="v tnum">{formatMoney(mes.reserved)}</b>
        </li>
        <li className="total">
          <span className="op">=</span>
          <span className="rot">Disponível</span>
          <b className="v tnum">{formatMoney(mes.available)}</b>
        </li>
      </ul>

      {mes.is_current && (
        <AvisoDoSaldo aviso={data.balance_warning} onAtualizar={() => setContasAbertas(true)} />
      )}

      <button
        className="btn btn-block"
        style={{ marginTop: "var(--s4)" }}
        onClick={() => setSimulando(true)}
      >
        + Simular gasto
      </button>

      {cenario && (
        <CenarioAtual
          cenario={cenario}
          podeEscrever={podeEscrever}
          onAdicionar={() => setHipotese(true)}
          onEditar={() => setEditandoCenario(true)}
        />
      )}

      {/* ---------- O que compõe ---------- */}
      <Secao titulo="Entradas" total={mes.income} vazio={`Nenhuma entrada prevista em ${nome}.`}>
        {entradas.map((i) => (
          <LinhaPlano key={i.key} item={i} onClick={() => tocarItem(i)} />
        ))}
      </Secao>

      <Secao titulo="Saídas" total={mes.expense} vazio={`Nada a pagar em ${nome}.`}>
        {saidas.map((i) => (
          <LinhaPlano key={i.key} item={i} onClick={() => tocarItem(i)} />
        ))}
      </Secao>
      {mes.still_needed > 0 && mes.provisioned > 0 && (
        <div className="nota">
          {formatMoney(mes.provisioned)} das saídas já estão reservados; faltam{" "}
          {formatMoney(mes.still_needed)}.
        </div>
      )}

      <Secao titulo="Reservas" total={mes.reserved} vazio="Nenhum dinheiro separado.">
        {mes.reserves.map((r) => (
          <LinhaReserva
            key={r.key}
            reserva={r}
            onClick={cenario && podeEscrever && r.source === "reserva" ? () => setAjustando(r) : undefined}
          />
        ))}
      </Secao>
      <div className="nota">
        Reserva não sai do patrimônio: ela só tira o dinheiro do disponível.{" "}
        {cenario
          ? "Toque num item pra mudá-lo só neste cenário."
          : "Compromissos e reservas se cadastram na aba Compromissos."}
      </div>

      {contasAbertas && (
        <ContasSheet
          contas={data.accounts}
          period={period}
          podeEscrever={podeEscrever}
          onClose={() => setContasAbertas(false)}
        />
      )}
      {simulando && (
        <SimularGasto
          mes={mes}
          cenario={cenario}
          podeEscrever={podeEscrever}
          onCriado={escolherCenario}
          onClose={() => setSimulando(false)}
        />
      )}
      {novoCenario && (
        <NovoCenario
          onCriado={(id) => {
            setNovoCenario(false);
            escolherCenario(id);
          }}
          onClose={() => setNovoCenario(false)}
        />
      )}
      {editandoCenario && cenario && (
        <EditarCenario
          cenario={cenario}
          onDuplicado={escolherCenario}
          onExcluido={() => escolherCenario(null)}
          onClose={() => setEditandoCenario(false)}
        />
      )}
      {hipotese && cenario && (
        <NovaHipotese cenario={cenario} mes={mes} onClose={() => setHipotese(false)} />
      )}
      {ajustando && cenario && (
        <AjustarNoCenario cenario={cenario} alvo={ajustando} onClose={() => setAjustando(null)} />
      )}
    </>
  );
}

function Secao({
  titulo,
  total,
  vazio,
  children,
}: {
  titulo: string;
  total: number;
  vazio: string;
  children: React.ReactNode[];
}) {
  return (
    <>
      <div className="sec-title">
        <h2>{titulo}</h2>
        <span className="extra tnum">{formatMoney(total)}</span>
      </div>
      {children.length === 0 ? <div className="hint">{vazio}</div> : <div className="list">{children}</div>}
    </>
  );
}

function LinhaReserva({ reserva, onClick }: { reserva: PlanoReserva; onClick?: () => void }) {
  const corpo = (
    <>
      <div className="avatar avatar-fatura" aria-hidden>
        {reserva.source === "aporte" ? "🏦" : reserva.source === "cenario" ? "✦" : "📌"}
      </div>
      <div className="mid">
        <div className="t">{reserva.description}</div>
        <div className="s">
          <span className={`selo ${reserva.certainty}`}>
            {reserva.source === "aporte"
              ? "aporte previsto"
              : reserva.source === "cenario"
                ? "hipotético"
                : "reservado"}
          </span>
          {reserva.target_label && reserva.target_label !== reserva.description && (
            <span>pra {reserva.target_label}</span>
          )}
        </div>
      </div>
      <div className="amt tnum">
        {reserva.original_amount != null && (
          <span className="riscado">{formatMoney(reserva.original_amount)}</span>
        )}
        {formatMoney(reserva.amount)}
      </div>
    </>
  );
  return onClick ? (
    <button className="row plano-row" onClick={onClick}>
      {corpo}
    </button>
  ) : (
    <div className="row plano-row">{corpo}</div>
  );
}

/** Por que o saldo de partida talvez não seja o de hoje. Lista, nunca aplica:
 *  o app não sabe de qual conta cada lançamento saiu. */
function AvisoDoSaldo({ aviso, onAtualizar }: { aviso: AvisoSaldo; onAtualizar: () => void }) {
  if (aviso.sem_contas) {
    return (
      <div className="aviso-box" style={{ marginTop: "var(--s4)" }}>
        <b>Nenhuma conta escolhida.</b> O planejamento parte do saldo das contas onde seu
        dinheiro está.{" "}
        <button className="btn btn-sm" style={{ marginTop: "var(--s2)" }} onClick={onAtualizar}>
          Escolher contas
        </button>
      </div>
    );
  }
  const temMovimento = aviso.quantidade > 0;
  if (!aviso.desatualizado && !aviso.sem_dia && !temMovimento && aviso.contas_sem_saldo.length === 0) {
    return null;
  }
  return (
    <div className="aviso-box" style={{ marginTop: "var(--s4)" }}>
      {aviso.contas_sem_saldo.length > 0 && (
        <div>
          <b>Sem saldo lançado:</b> {aviso.contas_sem_saldo.join(", ")}.
        </div>
      )}
      {aviso.sem_dia && (
        <div>
          Há saldo deste mês sem o dia da leitura: não dá pra saber se os lançamentos do mês já
          estão dentro dele.
        </div>
      )}
      {temMovimento && aviso.desde && (
        <>
          <div>
            <b>
              {aviso.desatualizado ? "Saldo desatualizado." : "Houve movimento depois do saldo."}
            </b>{" "}
            Depois de {formatDiaMes(aviso.desde)} o app registrou {aviso.quantidade}{" "}
            {aviso.quantidade === 1 ? "movimento" : "movimentos"}:
            {aviso.entradas > 0 && <> {formatMoney(aviso.entradas)} de entrada</>}
            {aviso.saidas > 0 && <> · {formatMoney(aviso.saidas)} de saída</>}
            {aviso.investimentos > 0 && <> · {formatMoney(aviso.investimentos)} pra investimento</>}.
            Eles não estão na conta acima.
          </div>
          <details style={{ marginTop: "var(--s2)" }}>
            <summary style={{ cursor: "pointer" }}>Ver movimentos</summary>
            <ul style={{ margin: "var(--s2) 0 0", paddingLeft: "var(--s4)" }}>
              {aviso.movimentos.map((m, i) => (
                <li key={i}>
                  {formatDiaMes(m.date)} · {m.description} · {m.tipo === "entrada" ? "+" : "−"}
                  {formatMoney(m.amount)}
                  {m.tipo === "investimento" && " (talvez transferência entre suas contas)"}
                </li>
              ))}
            </ul>
          </details>
        </>
      )}
      <button className="btn btn-sm" style={{ marginTop: "var(--s3)" }} onClick={onAtualizar}>
        Atualizar saldos
      </button>
    </div>
  );
}

/** As contas que entram no "quanto tenho agora", com o saldo deste mês. */
function ContasSheet({
  contas,
  period,
  podeEscrever,
  onClose,
}: {
  contas: ContaPlanejamento[];
  period: Period;
  podeEscrever: boolean;
  onClose: () => void;
}) {
  const atualizar = useUpdateAsset();
  const saldo = useSetAssetSnapshot();
  const ym = `${period.year}-${String(period.month).padStart(2, "0")}`;

  return (
    <Modal title="Saldo atual" onClose={onClose}>
      <div className="m-body">
        <p className="hint" style={{ marginTop: 0 }}>
          Marque onde seu dinheiro do dia a dia está. O valor é o saldo lançado em Patrimônio;
          digitar aqui lança o saldo de hoje.
        </p>
        {contas.length === 0 && (
          <div className="hint">Nenhuma conta cadastrada. Cadastre em Patrimônio.</div>
        )}
        <div className="list">
          {contas.map((c) => (
            <div key={c.asset_id} className="row asset-row">
              <label className="conta-toggle mid">
                <input
                  type="checkbox"
                  checked={c.included}
                  disabled={!podeEscrever || atualizar.isPending}
                  onChange={(e) =>
                    atualizar.mutate({ id: c.asset_id, data: { include_in_planning: e.target.checked } })
                  }
                />
                <span style={{ minWidth: 0 }}>
                  <span className="t" style={{ display: "block" }}>{c.name}</span>
                  <span className="s" style={{ display: "block" }}>
                    {c.as_of == null
                      ? "sem saldo"
                      : c.as_of === ym
                        ? c.observed_on
                          ? `lido em ${formatDiaMes(c.observed_on)}`
                          : "deste mês"
                        : `de ${formatYm(c.as_of)}`}
                  </span>
                </span>
              </label>
              <div className="saldo-input">
                {podeEscrever ? (
                  <MoneyCell
                    saved={c.as_of === ym ? c.value : null}
                    placeholder={c.as_of ? formatMoney(c.value) : "0,00"}
                    ariaLabel={`Saldo de ${c.name} hoje`}
                    pending={saldo.isPending}
                    onCommit={(valor) => {
                      if (valor == null) return;
                      saldo.mutate({ asset_id: c.asset_id, year: period.year, month: period.month, value: valor });
                    }}
                  />
                ) : (
                  <b className="tnum">{formatMoney(c.value)}</b>
                )}
              </div>
            </div>
          ))}
        </div>
        {(atualizar.error || saldo.error) && (
          <div className="error-box" style={{ marginTop: "var(--s3)" }}>
            {((atualizar.error || saldo.error) as ApiError).message}
          </div>
        )}
      </div>
    </Modal>
  );
}

const TIPOS_HIPOTESE: { valor: ScenarioItemKind; rotulo: string }[] = [
  { valor: "saida", rotulo: "Gastar" },
  { valor: "entrada", rotulo: "Receber" },
  { valor: "reserva", rotulo: "Guardar" },
];

function dataPadrao(mes: PlanoMes): string {
  const hoje = new Date();
  if (mes.is_current) {
    return `${hoje.getFullYear()}-${String(hoje.getMonth() + 1).padStart(2, "0")}-${String(hoje.getDate()).padStart(2, "0")}`;
  }
  return `${mes.year}-${String(mes.month).padStart(2, "0")}-15`;
}

/** "E se eu gastar 500?" — calcula no servidor e não grava. Guardar a
 *  hipótese num cenário é um segundo passo, explícito. */
function SimularGasto({
  mes,
  cenario,
  podeEscrever,
  onCriado,
  onClose,
}: {
  mes: PlanoMes;
  cenario: Scenario | null;
  podeEscrever: boolean;
  onCriado: (id: number) => void;
  onClose: () => void;
}) {
  const [tipo, setTipo] = useState<ScenarioItemKind>("saida");
  const [valor, setValor] = useState("");
  const [descricao, setDescricao] = useState("");
  const simular = useSimular();
  const criar = useCreateScenario();
  const adicionar = useAddScenarioItem();
  const numero = parseMoney(valor) ?? 0;
  const resultado = simular.data?.months[0];

  const hipotese = {
    kind: tipo,
    description: descricao.trim() || (tipo === "saida" ? "Gasto hipotético" : tipo === "entrada" ? "Entrada hipotética" : "Guardar"),
    amount: numero,
    date: dataPadrao(mes),
  };

  function calcular(e: React.FormEvent) {
    e.preventDefault();
    if (numero <= 0) return;
    simular.mutate({ year: mes.year, month: mes.month, scenario_id: cenario?.id ?? null, extras: [hipotese] });
  }

  function salvar() {
    if (cenario) {
      adicionar.mutate({ id: cenario.id, data: hipotese }, { onSuccess: onClose });
      return;
    }
    criar.mutate(
      { name: hipotese.description.slice(0, 60) },
      {
        onSuccess: (novo) =>
          adicionar.mutate(
            { id: novo.id, data: hipotese },
            { onSuccess: () => { onCriado(novo.id); onClose(); } }
          ),
      }
    );
  }

  const erro = (simular.error || criar.error || adicionar.error) as ApiError | null;

  return (
    <Modal
      title="Simular"
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose}>Fechar</button>
          <button type="submit" form="simular-form" className="btn btn-primary" disabled={numero <= 0 || simular.isPending}>
            {simular.isPending ? "Calculando…" : "Calcular"}
          </button>
        </>
      }
    >
      <form id="simular-form" className="m-body" onSubmit={calcular}>
        <div className="field">
          <Segmentado rotulo="Tipo da hipótese" opcoes={TIPOS_HIPOTESE} valor={tipo} aoEscolher={setTipo} largo />
        </div>
        <div className="row2">
          <div className="field">
            <label htmlFor="s-valor">Valor</label>
            <input id="s-valor" inputMode="decimal" autoFocus placeholder="0,00" value={valor}
              onChange={(e) => setValor(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="s-desc">O quê</label>
            <input id="s-desc" placeholder="Opcional" value={descricao} onChange={(e) => setDescricao(e.target.value)} />
          </div>
        </div>
        <p className="hint" style={{ marginTop: 0 }}>
          Nada é gravado: é só uma conta. {cenario ? `Parte do cenário "${cenario.name}".` : "Parte da base."}
        </p>

        {resultado && (
          <div className="resumo-compra" style={{ marginTop: "var(--s3)" }}>
            <div className="linha">
              <span>Disponível hoje</span>
              <b className="tnum">{formatMoney(mes.available)}</b>
            </div>
            <div className="linha">
              <span>Com a hipótese</span>
              <b className="tnum">{formatMoney(resultado.available)}</b>
            </div>
            <div className="linha">
              <span>Saldo projetado</span>
              <b className="tnum">{formatMoney(resultado.projected)}</b>
            </div>
            {resultado.available < 0 && (
              <div className="linha">
                <span style={{ color: "var(--neg)" }}>Faltaria dinheiro livre no fim do mês.</span>
              </div>
            )}
          </div>
        )}

        {resultado && podeEscrever && (
          <button type="button" className="btn btn-block" onClick={salvar}
            disabled={criar.isPending || adicionar.isPending}>
            {cenario ? `Guardar em "${cenario.name}"` : "Guardar como cenário"}
          </button>
        )}
        {erro && <div className="error-box" style={{ marginTop: "var(--s3)" }}>{erro.message}</div>}
      </form>
    </Modal>
  );
}

function CenarioAtual({
  cenario,
  podeEscrever,
  onAdicionar,
  onEditar,
}: {
  cenario: Scenario;
  podeEscrever: boolean;
  onAdicionar: () => void;
  onEditar: () => void;
}) {
  const remover = useRemoveScenarioItem();
  return (
    <>
      <div className="sec-title">
        <h2>Neste cenário</h2>
        {podeEscrever && (
          <button className="link" onClick={onEditar}>Editar</button>
        )}
      </div>
      {cenario.note && <div className="hint" style={{ marginBottom: "var(--s2)" }}>{cenario.note}</div>}
      {cenario.items.length === 0 ? (
        <div className="hint">Nenhuma hipótese ainda. Adicione uma, ou toque num item real pra mudá-lo só aqui.</div>
      ) : (
        <div className="list">
          {cenario.items.map((h) => (
            <div key={h.id} className="row plano-row">
              <div className="avatar avatar-fatura" aria-hidden>✦</div>
              <div className="mid">
                <div className="t">{h.description}</div>
                <div className="s">
                  <span className="selo hipotetico">
                    {h.ref ? (h.amount === 0 ? "removido" : "valor mudado") : h.kind === "saida" ? "gasto" : h.kind === "entrada" ? "entrada" : "guardar"}
                  </span>
                  <span>
                    {formatDiaMes(h.date)}
                    {h.repeat_months > 1 && ` · por ${h.repeat_months} meses`}
                  </span>
                </div>
              </div>
              <div className="amt tnum">{formatMoney(h.amount)}</div>
              {podeEscrever && (
                <button
                  className="row-editar"
                  aria-label={`Tirar ${h.description} do cenário`}
                  disabled={remover.isPending}
                  onClick={() => remover.mutate({ id: cenario.id, itemId: h.id })}
                >
                  ✕
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      {podeEscrever && (
        <button className="btn btn-ghost btn-sm btn-block" style={{ marginTop: "var(--s2)" }} onClick={onAdicionar}>
          + Hipótese
        </button>
      )}
    </>
  );
}

function NovoCenario({ onCriado, onClose }: { onCriado: (id: number) => void; onClose: () => void }) {
  const [nome, setNome] = useState("");
  const criar = useCreateScenario();
  return (
    <Modal
      title="Novo cenário"
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          <button type="submit" form="cenario-form" className="btn btn-primary" disabled={!nome.trim() || criar.isPending}>
            Criar
          </button>
        </>
      }
    >
      <form id="cenario-form" className="m-body" onSubmit={(e) => {
        e.preventDefault();
        criar.mutate({ name: nome.trim() }, { onSuccess: (s) => onCriado(s.id) });
      }}>
        <div className="field">
          <label htmlFor="c-nome">Nome</label>
          <input id="c-nome" autoFocus maxLength={60} placeholder="Ex.: Viagem, Outubro conservador" value={nome}
            onChange={(e) => setNome(e.target.value)} />
        </div>
        <p className="hint" style={{ marginTop: 0 }}>
          Um cenário é uma hipótese com nome. Ele nunca cria lançamento e nunca muda o que é real.
        </p>
        {criar.error && <div className="error-box">{(criar.error as ApiError).message}</div>}
      </form>
    </Modal>
  );
}

function EditarCenario({
  cenario,
  onDuplicado,
  onExcluido,
  onClose,
}: {
  cenario: Scenario;
  onDuplicado: (id: number) => void;
  onExcluido: () => void;
  onClose: () => void;
}) {
  const [nome, setNome] = useState(cenario.name);
  const [nota, setNota] = useState(cenario.note ?? "");
  const [apagando, setApagando] = useState(false);
  const atualizar = useUpdateScenario();
  const duplicar = useDuplicateScenario();
  const excluir = useDeleteScenario();
  const erro = (atualizar.error || duplicar.error) as ApiError | null;

  return (
    <Modal
      title="Cenário"
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-danger" onClick={() => setApagando(true)}>Excluir</button>
          <button type="submit" form="editar-cenario" className="btn btn-primary" disabled={!nome.trim() || atualizar.isPending}>
            Salvar
          </button>
        </>
      }
    >
      <form id="editar-cenario" className="m-body" onSubmit={(e) => {
        e.preventDefault();
        atualizar.mutate({ id: cenario.id, data: { name: nome.trim(), note: nota.trim() || null } }, { onSuccess: onClose });
      }}>
        <div className="field">
          <label htmlFor="e-nome">Nome</label>
          <input id="e-nome" maxLength={60} value={nome} onChange={(e) => setNome(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="e-nota">Observação</label>
          <textarea id="e-nota" placeholder="Opcional" value={nota} onChange={(e) => setNota(e.target.value)} />
        </div>
        <button type="button" className="btn btn-block" disabled={duplicar.isPending}
          onClick={() => duplicar.mutate({ id: cenario.id }, { onSuccess: (s) => { onDuplicado(s.id); onClose(); } })}>
          Duplicar cenário
        </button>
        {erro && <div className="error-box" style={{ marginTop: "var(--s3)" }}>{erro.message}</div>}
      </form>
      {apagando && (
        <ConfirmDialog
          title="Excluir cenário"
          itemName={cenario.name}
          consequences={[
            `${cenario.items.length} ${cenario.items.length === 1 ? "hipótese vai" : "hipóteses vão"} junto.`,
            "Nenhum lançamento, compromisso ou reserva é tocado.",
          ]}
          pending={excluir.isPending}
          error={(excluir.error as ApiError | null)?.message ?? null}
          onCancel={() => setApagando(false)}
          onConfirm={() => excluir.mutate(cenario.id, { onSuccess: () => { onExcluido(); onClose(); } })}
        />
      )}
    </Modal>
  );
}

function NovaHipotese({ cenario, mes, onClose }: { cenario: Scenario; mes: PlanoMes; onClose: () => void }) {
  const [tipo, setTipo] = useState<ScenarioItemKind>("saida");
  const [descricao, setDescricao] = useState("");
  const [valor, setValor] = useState("");
  const [data, setData] = useState(dataPadrao(mes));
  const [repetir, setRepetir] = useState("1");
  const adicionar = useAddScenarioItem();
  const numero = parseMoney(valor) ?? 0;

  return (
    <Modal
      title={`Hipótese em "${cenario.name}"`}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          <button type="submit" form="hipotese-form" className="btn btn-primary"
            disabled={numero <= 0 || !descricao.trim() || adicionar.isPending}>
            Adicionar
          </button>
        </>
      }
    >
      <form id="hipotese-form" className="m-body" onSubmit={(e) => {
        e.preventDefault();
        adicionar.mutate(
          { id: cenario.id, data: { kind: tipo, description: descricao.trim(), amount: numero, date: data,
            repeat_months: Math.max(1, Number(repetir) || 1) } },
          { onSuccess: onClose }
        );
      }}>
        <div className="field">
          <Segmentado rotulo="Tipo" opcoes={TIPOS_HIPOTESE} valor={tipo} aoEscolher={setTipo} largo />
        </div>
        <div className="field">
          <label htmlFor="h-desc">Descrição</label>
          <input id="h-desc" autoFocus placeholder="Ex.: Equipamento novo" value={descricao}
            onChange={(e) => setDescricao(e.target.value)} />
        </div>
        <div className="row2">
          <div className="field">
            <label htmlFor="h-valor">Valor</label>
            <input id="h-valor" inputMode="decimal" placeholder="0,00" value={valor} onChange={(e) => setValor(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="h-data">Data</label>
            <input id="h-data" type="date" value={data} onChange={(e) => setData(e.target.value)} />
          </div>
        </div>
        <div className="field">
          <label htmlFor="h-rep">Repetir por quantos meses</label>
          <input id="h-rep" inputMode="numeric" value={repetir} onChange={(e) => setRepetir(e.target.value)} />
          <span className="hint">1 = só uma vez. "Uma parcela nova de 10x" = 10.</span>
        </div>
        {adicionar.error && <div className="error-box">{(adicionar.error as ApiError).message}</div>}
      </form>
    </Modal>
  );
}

/** Mudar um item REAL só dentro do cenário: outro valor, ou fora. */
function AjustarNoCenario({
  cenario,
  alvo,
  onClose,
}: {
  cenario: Scenario;
  alvo: PlanoItem | PlanoReserva;
  onClose: () => void;
}) {
  const ehReserva = !("direction" in alvo);
  const chave = ehReserva && alvo.provision_id != null ? `reserva:${alvo.provision_id}` : alvo.key;
  const atual = ehReserva ? alvo.amount : (alvo as PlanoItem).remaining;
  const [valor, setValor] = useState(String(atual).replace(".", ","));
  const adicionar = useAddScenarioItem();
  const kind: ScenarioItemKind = ehReserva ? "reserva" : (alvo as PlanoItem).direction === "entrada" ? "entrada" : "saida";
  const data = ehReserva ? `${alvo.since[0]}-${String(alvo.since[1]).padStart(2, "0")}-01` : (alvo as PlanoItem).date;

  function aplicar(novo: number) {
    adicionar.mutate(
      { id: cenario.id, data: { kind, description: alvo.description, amount: novo, date: data, ref: chave } },
      { onSuccess: onClose }
    );
  }

  return (
    <Modal title="Só neste cenário" onClose={onClose}>
      <div className="m-body">
        <div className="resumo-compra">
          <div className="linha"><span>{alvo.description}</span><b className="tnum">{formatMoney(atual)}</b></div>
        </div>
        <p className="hint" style={{ marginTop: 0 }}>
          O item real não muda. O cenário "{cenario.name}" passa a considerar outro valor.
        </p>
        <div className="field">
          <label htmlFor="a-valor">Valor no cenário</label>
          <input id="a-valor" inputMode="decimal" value={valor} onChange={(e) => setValor(e.target.value)} />
        </div>
        <div className="acoes">
          <button className="btn btn-primary" disabled={adicionar.isPending || parseMoney(valor) == null}
            onClick={() => aplicar(parseMoney(valor) ?? 0)}>
            Usar este valor no cenário
          </button>
          <button className="btn" disabled={adicionar.isPending} onClick={() => aplicar(0)}>
            Tirar deste cenário
          </button>
        </div>
        {adicionar.error && <div className="error-box" style={{ marginTop: "var(--s3)" }}>{(adicionar.error as ApiError).message}</div>}
      </div>
    </Modal>
  );
}
