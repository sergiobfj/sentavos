import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import Modal from "../Modal";
import CompromissoForm from "./CompromissoForm";
import ReservaForm from "./ReservaForm";
import { Selo } from "./comum";
import {
  useCategories,
  useCommitment,
  useCommitments,
  useDesfazerDispensa,
  useDesvincularOcorrencia,
  useDispensarOcorrencia,
  usePagarOcorrencia,
  useProvisions,
  useVincularOcorrencia,
} from "../../lib/queries";
import { useAuth } from "../../lib/auth";
import { ApiError, transactionsApi } from "../../lib/api";
import { toYm } from "../../lib/period";
import { formatDate, formatDiaMes, formatMoney, formatYm, parseMoney, todayIso } from "../../lib/format";
import { fundoDaCor } from "../../lib/paleta";
import {
  OCORRENCIA_LABEL,
  type Commitment,
  type CommitmentDetail,
  type Ocorrencia,
  type Provision,
} from "../../lib/tiposPlanejamento";

const PERIODO_LABEL: Record<number, string> = {
  1: "mensal", 2: "bimestral", 3: "trimestral", 6: "semestral", 12: "anual",
};

/** Os compromissos fora do cartão e as reservas.
 *
 *  O compromisso aberto mora na URL (?id=), como a fatura aberta em Faturas:
 *  o "Próximos meses" linka direto pra ele, e o F5 não perde o lugar. */
export default function Compromissos() {
  const [params, setParams] = useSearchParams();
  const abertoId = Number(params.get("id")) || null;
  const { sessao } = useAuth();
  const podeEscrever = !sessao?.somenteLeitura;
  const { data: compromissos, isLoading, error } = useCommitments();
  const { data: reservas } = useProvisions();
  const [criando, setCriando] = useState(false);
  const [reservando, setReservando] = useState(false);
  const [reservaAberta, setReservaAberta] = useState<Provision | null>(null);

  function abrir(id: number | null) {
    setParams(
      (prev) => {
        const p = new URLSearchParams(prev);
        if (id == null) p.delete("id");
        else p.set("id", String(id));
        return p;
      },
      { replace: id == null }
    );
  }

  if (abertoId != null) {
    return <Detalhe id={abertoId} podeEscrever={podeEscrever} onVoltar={() => abrir(null)} />;
  }

  if (isLoading) return <div className="skel" style={{ height: 260, borderRadius: "var(--r)" }} />;
  if (error) return <div className="error-box">{(error as ApiError).message}</div>;

  const ativos = (compromissos ?? []).filter((c) => c.status === "ativo");
  const aPagar = ativos.filter((c) => c.direction === "saida");
  const aReceber = ativos.filter((c) => c.direction === "entrada");
  const encerrados = (compromissos ?? []).filter((c) => c.status !== "ativo");
  const reservasAtivas = (reservas ?? []).filter((r) => r.status === "ativa");
  const reservasPassadas = (reservas ?? []).filter((r) => r.status !== "ativa");

  return (
    <>
      {podeEscrever && (
        <div className="row2">
          <button className="btn btn-primary" onClick={() => setCriando(true)}>+ Compromisso</button>
          <button className="btn" onClick={() => setReservando(true)}>+ Reserva</button>
        </div>
      )}

      <Grupo titulo="A pagar" vazio="Nenhum compromisso fora do cartão. Financiamento, parcelado direto e contas recorrentes entram aqui; o cartão já está nas faturas.">
        {aPagar.map((c) => <LinhaCompromisso key={c.id} c={c} onClick={() => abrir(c.id)} />)}
      </Grupo>

      {aReceber.length > 0 && (
        <Grupo titulo="A receber">
          {aReceber.map((c) => <LinhaCompromisso key={c.id} c={c} onClick={() => abrir(c.id)} />)}
        </Grupo>
      )}

      <Grupo titulo="Reservas" vazio="Nenhum dinheiro separado.">
        {reservasAtivas.map((r) => (
          <LinhaReserva key={r.id} r={r} onClick={podeEscrever ? () => setReservaAberta(r) : undefined} />
        ))}
      </Grupo>

      {(encerrados.length > 0 || reservasPassadas.length > 0) && (
        <details style={{ marginTop: "var(--s5)" }}>
          <summary className="grupo-rotulo" style={{ cursor: "pointer" }}>
            Encerrados, quitados e reservas cumpridas ({encerrados.length + reservasPassadas.length})
          </summary>
          <div className="list">
            {encerrados.map((c) => <LinhaCompromisso key={c.id} c={c} onClick={() => abrir(c.id)} />)}
            {reservasPassadas.map((r) => (
              <LinhaReserva key={`r${r.id}`} r={r} onClick={podeEscrever ? () => setReservaAberta(r) : undefined} />
            ))}
          </div>
        </details>
      )}

      {criando && <CompromissoForm onClose={() => setCriando(false)} />}
      {reservando && <ReservaForm onClose={() => setReservando(false)} />}
      {reservaAberta && <ReservaForm reserva={reservaAberta} onClose={() => setReservaAberta(null)} />}
    </>
  );
}

function Grupo({ titulo, vazio, children }: { titulo: string; vazio?: string; children: React.ReactNode[] }) {
  return (
    <>
      <div className="sec-title"><h2>{titulo}</h2></div>
      {children.length === 0 ? (
        vazio ? <div className="hint">{vazio}</div> : null
      ) : (
        <div className="list">{children}</div>
      )}
    </>
  );
}

function resumoDoCompromisso(c: Commitment): string {
  const partes: string[] = [];
  if (c.kind === "parcelado") {
    partes.push(c.total_count === 1 ? "conta única" : `${c.paid_count}/${c.total_count} pagas`);
  } else {
    partes.push(PERIODO_LABEL[c.interval_months] ?? `a cada ${c.interval_months} meses`);
  }
  if (c.status !== "ativo") partes.push(c.status);
  else if (c.next) partes.push(`${c.direction === "entrada" ? "próxima" : "próximo"} ${formatDiaMes(c.next.due_date)}`);
  if (c.institution) partes.push(c.institution);
  return partes.join(" · ");
}

function LinhaCompromisso({ c, onClick }: { c: Commitment; onClick: () => void }) {
  return (
    <button className="row plano-row" onClick={onClick}>
      <div className="avatar" style={{ background: fundoDaCor(c.color, 22) }}>{c.icon}</div>
      <div className="mid">
        <div className="t">{c.description}</div>
        <div className="s">
          <Selo certeza={c.confirmed ? "confirmado" : "estimado"} situacao={c.overdue_count > 0 ? "vencido" : undefined}
            entrada={c.direction === "entrada"} />
          <span>{resumoDoCompromisso(c)}</span>
        </div>
      </div>
      <div className={`amt tnum ${c.direction === "entrada" ? "pos" : ""}`}>
        {formatMoney(c.amount)}
        {c.overdue_count > 0 && <span className="sub">{c.overdue_count} vencida{c.overdue_count > 1 ? "s" : ""}</span>}
      </div>
    </button>
  );
}

function LinhaReserva({ r, onClick }: { r: Provision; onClick?: () => void }) {
  const corpo = (
    <>
      <div className="avatar avatar-fatura" aria-hidden>📌</div>
      <div className="mid">
        <div className="t">{r.description}</div>
        <div className="s">
          <span className={`selo ${r.status === "ativa" ? "confirmado" : "estimado"}`}>
            {r.status === "ativa" ? "reservada" : r.status}
          </span>
          {r.occurrence_due && <span>pra {formatDiaMes(r.occurrence_due)}</span>}
          {!r.occurrence_due && r.target_date && <span>até {formatDiaMes(r.target_date)}</span>}
          <span>desde {formatDiaMes(r.created_on)}</span>
        </div>
      </div>
      <div className="amt tnum">{formatMoney(r.amount)}</div>
    </>
  );
  return onClick ? (
    <button className="row plano-row" onClick={onClick}>{corpo}</button>
  ) : (
    <div className="row plano-row">{corpo}</div>
  );
}

// ---------- O compromisso por dentro ----------

function Detalhe({ id, podeEscrever, onVoltar }: { id: number; podeEscrever: boolean; onVoltar: () => void }) {
  const { data: c, isLoading, error } = useCommitment(id);
  const [editando, setEditando] = useState(false);
  const [ocorrencia, setOcorrencia] = useState<Ocorrencia | null>(null);
  const [todas, setTodas] = useState(false);

  // Excluído (ou de outra conta): volta pra lista em vez de prender a tela num erro.
  useEffect(() => {
    if (error && (error as ApiError).status === 404) onVoltar();
  }, [error, onVoltar]);

  if (isLoading) return <div className="skel" style={{ height: 320, borderRadius: "var(--r)" }} />;
  if (error) return <div className="error-box">{(error as ApiError).message}</div>;
  if (!c) return null;

  const hoje = todayIso();
  // Parcelado longo: abre nas próximas 12, com o resto a um toque.
  const inicio = Math.max(0, c.schedule.findIndex((o) => o.due_date >= hoje || o.status === "vencida") - 2);
  const visiveis = todas ? c.schedule : c.schedule.slice(inicio, inicio + 12);
  const entrada = c.direction === "entrada";

  return (
    <>
      <button className="btn btn-ghost btn-sm" onClick={onVoltar} style={{ marginBottom: "var(--s3)" }}>
        ‹ Compromissos
      </button>

      <section className="hero">
        <div className="rot">
          {c.description}
          {c.institution && ` · ${c.institution}`}
        </div>
        <div className="big tnum">
          {c.kind === "parcelado" && c.total_count && c.total_count > 1 ? `${c.total_count} × ` : ""}
          {formatMoney(c.amount)}
        </div>
        <div className="delta">
          <Selo certeza={c.confirmed ? "confirmado" : "estimado"} />
          <span>
            {c.kind === "parcelado"
              ? `1ª em ${formatDate(c.first_due)}`
              : `${PERIODO_LABEL[c.interval_months] ?? ""} desde ${formatDate(c.first_due)}`}
            {c.end_date && ` · até ${formatDate(c.end_date)}`}
            {c.cancelled_on && ` · cancelado em ${formatDate(c.cancelled_on)}`}
          </span>
        </div>
      </section>

      <div className="metricas">
        {c.kind === "parcelado" ? (
          <>
            <div className="metrica">
              <div className="rot">{entrada ? "Recebidas" : "Pagas"}</div>
              <div className="val tnum">{c.paid_count}/{c.total_count}</div>
            </div>
            <div className="metrica">
              <div className="rot">Restam</div>
              <div className="val tnum">{c.remaining_count}</div>
            </div>
          </>
        ) : (
          <div className="metrica">
            <div className="rot">{entrada ? "Recebidas" : "Pagas"}</div>
            <div className="val tnum">{c.paid_count}</div>
          </div>
        )}
        <div className="metrica">
          <div className="rot">Próximo</div>
          <div className={`val tnum${c.next ? "" : " fraco"}`}>{c.next ? formatDiaMes(c.next.due_date) : "—"}</div>
        </div>
      </div>

      <ul className="conta-plano">
        {c.remaining_nominal != null && c.remaining_nominal > 0 && (
          <li>
            <span className="op" aria-hidden />
            <span className="rot">
              Soma das parcelas que faltam
              <small>Nominal: não é o saldo devedor do banco, que desconta juros na quitação.</small>
            </span>
            <b className="v tnum">{formatMoney(c.remaining_nominal)}</b>
          </li>
        )}
        {c.overdue_count > 0 && (
          <li>
            <span className="op" aria-hidden />
            <span className="rot" style={{ color: "var(--neg)" }}>Vencidas sem baixa ({c.overdue_count})</span>
            <b className="v tnum">{formatMoney(c.overdue_amount)}</b>
          </li>
        )}
        {c.down_payment != null && (
          <li>
            <span className="op" aria-hidden />
            <span className="rot">Entrada<small>informação — já é um lançamento à parte</small></span>
            <b className="v tnum">{formatMoney(c.down_payment)}</b>
          </li>
        )}
        {c.total_amount != null && (
          <li>
            <span className="op" aria-hidden />
            <span className="rot">Valor total / financiado<small>informação — não entra em conta</small></span>
            <b className="v tnum">{formatMoney(c.total_amount)}</b>
          </li>
        )}
      </ul>
      {c.note && <div className="hint" style={{ marginTop: "var(--s2)" }}>{c.note}</div>}

      <div className="sec-title">
        <h2>Cronograma</h2>
        {podeEscrever && <button className="link" onClick={() => setEditando(true)}>Editar</button>}
      </div>
      <ul className="cronograma">
        {visiveis.map((o) => (
          <li key={o.number} className={o.status === "paga" || o.status === "dispensada" || o.status === "cancelada" ? "passada" : ""}>
            <span className="n">{o.label ?? formatYm(o.due_date.slice(0, 7))}</span>
            <button className="d" onClick={() => setOcorrencia(o)}>
              {formatDate(o.due_date)}
              <small>
                {o.status === "paga" && o.paid_date
                  ? `${entrada ? "recebida" : "paga"} em ${formatDiaMes(o.paid_date)}`
                  : o.status === "dispensada"
                    ? `dispensada${o.skip_note ? ` · ${o.skip_note}` : ""}`
                    : o.provisioned > 0
                      ? `${formatMoney(o.provisioned)} reservado`
                      : OCORRENCIA_LABEL[o.status]}
              </small>
            </button>
            <span className="fim">
              <b className="tnum">{formatMoney(o.paid_amount ?? o.amount)}</b>
              <span className={`selo ${o.status === "paga" ? "pago" : o.status === "vencida" ? "vencido" : "estimado"}`}>
                {o.status === "pendente" ? (entrada ? "a receber" : "a pagar") : OCORRENCIA_LABEL[o.status]}
              </span>
            </span>
          </li>
        ))}
      </ul>
      {!todas && c.schedule.length > visiveis.length && (
        <button className="btn btn-ghost btn-sm btn-block" onClick={() => setTodas(true)}>
          Ver as {c.schedule.length} ocorrências
        </button>
      )}

      {editando && <CompromissoForm compromisso={c} onClose={() => setEditando(false)} />}
      {ocorrencia && (
        <OcorrenciaSheet
          c={c}
          o={c.schedule.find((x) => x.number === ocorrencia.number) ?? ocorrencia}
          podeEscrever={podeEscrever}
          onClose={() => setOcorrencia(null)}
        />
      )}
    </>
  );
}

type Acao = null | "pagar" | "vincular" | "dispensar" | "reservar";

function OcorrenciaSheet({
  c,
  o,
  podeEscrever,
  onClose,
}: {
  c: CommitmentDetail;
  o: Ocorrencia;
  podeEscrever: boolean;
  onClose: () => void;
}) {
  const [acao, setAcao] = useState<Acao>(null);
  const [valor, setValor] = useState(String(o.amount).replace(".", ","));
  const [data, setData] = useState(o.due_date <= todayIso() ? o.due_date : todayIso());
  const [nota, setNota] = useState("");
  const pagar = usePagarOcorrencia();
  const vincular = useVincularOcorrencia();
  const desvincular = useDesvincularOcorrencia();
  const dispensar = useDispensarOcorrencia();
  const desfazer = useDesfazerDispensa();
  const entrada = c.direction === "entrada";
  const titulo = `${c.description}${o.label ? ` ${o.label}` : ""}`;
  const erro = (pagar.error || vincular.error || desvincular.error || dispensar.error || desfazer.error) as ApiError | null;
  const aberta = o.status === "pendente" || o.status === "vencida";

  if (acao === "reservar") {
    return (
      <ReservaForm
        inicial={{
          commitment_id: c.id,
          commitment_no: o.number,
          amount: Math.max(o.amount - o.provisioned, 0),
        }}
        onClose={onClose}
      />
    );
  }

  return (
    <Modal title={titulo} onClose={onClose}>
      <div className="m-body">
        <div className="resumo-compra">
          <div className="linha"><span>Vencimento</span><b>{formatDate(o.due_date)}</b></div>
          <div className="linha"><span>Valor previsto</span><b className="tnum">{formatMoney(o.amount)}</b></div>
          <div className="linha"><span>Situação</span><b>{OCORRENCIA_LABEL[o.status]}</b></div>
          {o.paid_amount != null && (
            <div className="linha">
              <span>{entrada ? "Recebido" : "Pago"}</span>
              <b className="tnum">{formatMoney(o.paid_amount)} em {formatDate(o.paid_date!)}</b>
            </div>
          )}
          {o.provisioned > 0 && aberta && (
            <div className="linha"><span>Reservado</span><b className="tnum">{formatMoney(o.provisioned)}</b></div>
          )}
        </div>

        {!podeEscrever && <p className="hint">Modo demonstração: dá pra ver, não alterar.</p>}

        {podeEscrever && aberta && acao === null && (
          <div className="acoes">
            <button className="btn btn-primary" onClick={() => setAcao("pagar")}>
              <span>{entrada ? "Recebi" : "Paguei agora"}<small>Cria o lançamento já vinculado — um toque só.</small></span>
            </button>
            <button className="btn" onClick={() => setAcao("vincular")}>
              <span>Já está lançado<small>Escolher o lançamento que {entrada ? "recebeu" : "pagou"} esta.</small></span>
            </button>
            {!entrada && (
              <button className="btn" onClick={() => setAcao("reservar")}>
                <span>Reservar dinheiro pra ela<small>Tira do disponível agora, sem lançar nada.</small></span>
              </button>
            )}
            <button className="btn btn-ghost" onClick={() => setAcao("dispensar")}>
              <span>Dispensar<small>Não vai ser {entrada ? "recebida" : "paga"} (não cobrou, renegociou).</small></span>
            </button>
          </div>
        )}

        {acao === "pagar" && (
          <form onSubmit={(e) => {
            e.preventDefault();
            pagar.mutate({ id: c.id, numero: o.number, date: data, amount: parseMoney(valor) ?? undefined }, { onSuccess: onClose });
          }}>
            <div className="row2">
              <div className="field">
                <label htmlFor="o-valor">Valor {entrada ? "recebido" : "pago"}</label>
                <input id="o-valor" inputMode="decimal" value={valor} onChange={(e) => setValor(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="o-data">Data</label>
                <input id="o-data" type="date" value={data} onChange={(e) => setData(e.target.value)} />
              </div>
            </div>
            <p className="hint" style={{ marginTop: 0 }}>
              Vira um lançamento {entrada ? "de entrada" : "à vista"} em {c.category_name}, com o previsto e o pago.
            </p>
            <button type="submit" className="btn btn-primary btn-block" disabled={pagar.isPending || (parseMoney(valor) ?? 0) <= 0}>
              {pagar.isPending ? "Registrando…" : "Confirmar"}
            </button>
          </form>
        )}

        {acao === "vincular" && (
          <EscolherLancamento c={c} o={o} pendente={vincular.isPending}
            onEscolher={(tid) => vincular.mutate({ id: c.id, numero: o.number, transactionId: tid }, { onSuccess: onClose })} />
        )}

        {acao === "dispensar" && (
          <form onSubmit={(e) => {
            e.preventDefault();
            dispensar.mutate({ id: c.id, numero: o.number, note: nota.trim() || null }, { onSuccess: onClose });
          }}>
            <div className="field">
              <label htmlFor="o-nota">Por quê (opcional)</label>
              <input id="o-nota" maxLength={200} placeholder="Ex.: não cobrou este mês" value={nota} onChange={(e) => setNota(e.target.value)} />
            </div>
            <button type="submit" className="btn btn-block" disabled={dispensar.isPending}>Dispensar esta ocorrência</button>
          </form>
        )}

        {podeEscrever && o.status === "paga" && (
          <>
            <p className="hint">
              Pra desfazer o pagamento, apague o lançamento em Lançamentos: a ocorrência volta a ficar em aberto.
              Desvincular mantém o lançamento e só desfaz a ligação.
            </p>
            <button className="btn btn-block" disabled={desvincular.isPending}
              onClick={() => desvincular.mutate({ id: c.id, numero: o.number }, { onSuccess: onClose })}>
              Desvincular o lançamento
            </button>
          </>
        )}

        {podeEscrever && o.status === "dispensada" && (
          <button className="btn btn-block" disabled={desfazer.isPending}
            onClick={() => desfazer.mutate({ id: c.id, numero: o.number }, { onSuccess: onClose })}>
            Desfazer a dispensa
          </button>
        )}

        {erro && <div className="error-box" style={{ marginTop: "var(--s3)" }}>{erro.message}</div>}
      </div>
    </Modal>
  );
}

/** Os lançamentos do mês do vencimento que podem ser esta baixa: mesmo tipo,
 *  já pagos, fora do cartão e sem vínculo. O mais parecido com o valor primeiro. */
function EscolherLancamento({
  c,
  o,
  pendente,
  onEscolher,
}: {
  c: CommitmentDetail;
  o: Ocorrencia;
  pendente: boolean;
  onEscolher: (transactionId: number) => void;
}) {
  const [ano, mes] = o.due_date.split("-").map(Number);
  const periodo = { year: ano, month: mes };
  const { data: lancamentos, isLoading } = useQuery({
    queryKey: ["transactions", toYm(periodo)],
    queryFn: () => transactionsApi.list(periodo),
  });
  const { data: categorias } = useCategories(true);
  const tipo = c.direction === "entrada" ? "income" : "expense";
  const tipos = new Map((categorias ?? []).map((x) => [x.id, x.type]));
  const candidatos = (lancamentos ?? [])
    .filter((t) => t.amount_paid != null && t.purchase_id == null && t.commitment_id == null && tipos.get(t.category_id) === tipo)
    .sort((a, b) => Math.abs((a.amount_paid ?? 0) - o.amount) - Math.abs((b.amount_paid ?? 0) - o.amount))
    .slice(0, 12);

  if (isLoading) return <div className="skel" style={{ height: 120 }} />;
  if (candidatos.length === 0) {
    return <div className="hint">Nenhum lançamento disponível em {formatYm(o.due_date.slice(0, 7))}. Use "Paguei agora".</div>;
  }
  return (
    <div>
      {candidatos.map((t) => (
        <button key={t.id} className="sugestao" disabled={pendente} onClick={() => onEscolher(t.id)}>
          <span className="t"><span>{t.description}</span><span className="tnum">{formatMoney(t.amount_paid)}</span></span>
          <span className="s">{formatDiaMes(t.date)}</span>
        </button>
      ))}
    </div>
  );
}
