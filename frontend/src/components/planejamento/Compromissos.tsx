import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import Modal from "../Modal";
import CompromissoForm from "./CompromissoForm";
import ReservaForm from "./ReservaForm";
import { Cabecalho, Linha } from "./comum";
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
import {
  CERTEZA_LABEL,
  OCORRENCIA_LABEL,
  type Commitment,
  type CommitmentDetail,
  type Ocorrencia,
  type Provision,
} from "../../lib/tiposPlanejamento";

const PERIODO_LABEL: Record<number, string> = {
  1: "mensal", 2: "bimestral", 3: "trimestral", 6: "semestral", 12: "anual",
};

/** Compromissos fora do cartão e o dinheiro reservado.
 *
 *  Lista curta: nome, o próximo passo e o valor. Banco, entrada, valor total e
 *  o cronograma inteiro moram no detalhe de cada um (?id=), que é pra onde a
 *  visão de próximos meses linka. */
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

  const lista = compromissos ?? [];
  const ativos = lista.filter((c) => c.status === "ativo");
  const aPagar = ativos.filter((c) => c.direction === "saida");
  const aReceber = ativos.filter((c) => c.direction === "entrada");
  const encerrados = lista.filter((c) => c.status !== "ativo");
  const ativas = (reservas ?? []).filter((r) => r.status === "ativa");
  const passadas = (reservas ?? []).filter((r) => r.status !== "ativa");
  const porId = new Map(lista.map((c) => [c.id, c]));

  return (
    <>
      <Cabecalho titulo="Compromissos e reservas" voltar="Planejamento" voltarPara="/planejamento" />
      {podeEscrever && (
        <div className="acoes-linha">
          <button className="btn btn-sm" onClick={() => setCriando(true)}>+ Compromisso</button>
          <button className="btn btn-sm" onClick={() => setReservando(true)}>+ Reserva</button>
        </div>
      )}

      {isLoading && <div className="skel" style={{ height: 200 }} />}
      {error && <div className="error-box">{(error as ApiError).message}</div>}

      <div className="sec-title"><h2>A pagar</h2></div>
      {aPagar.length === 0 ? (
        <p className="hint">Nenhum. Financiamento, parcelado direto e conta recorrente entram aqui; o cartão já está nas faturas.</p>
      ) : (
        <ul className="lista-compacta">
          {aPagar.map((c) => <LinhaCompromisso key={c.id} c={c} onClick={() => abrir(c.id)} />)}
        </ul>
      )}

      {aReceber.length > 0 && (
        <>
          <div className="sec-title"><h2>A receber</h2></div>
          <ul className="lista-compacta">
            {aReceber.map((c) => <LinhaCompromisso key={c.id} c={c} onClick={() => abrir(c.id)} />)}
          </ul>
        </>
      )}

      <div className="sec-title"><h2>Reservado</h2></div>
      {ativas.length === 0 ? (
        <p className="hint">Nenhum dinheiro separado.</p>
      ) : (
        <ul className="lista-compacta">
          {ativas.map((r) => (
            <LinhaReserva key={r.id} r={r} reservas={ativas} compromisso={r.commitment_id ? porId.get(r.commitment_id) : undefined}
              onClick={podeEscrever ? () => setReservaAberta(r) : undefined} />
          ))}
        </ul>
      )}

      {(encerrados.length > 0 || passadas.length > 0) && (
        <details className="detalhe">
          <summary>Encerrados e reservas cumpridas ({encerrados.length + passadas.length})</summary>
          <ul className="lista-compacta">
            {encerrados.map((c) => <LinhaCompromisso key={c.id} c={c} onClick={() => abrir(c.id)} />)}
            {passadas.map((r) => (
              <Linha key={`r${r.id}`} rotulo={r.description} legenda={r.status} valor={formatMoney(r.amount)}
                onClick={podeEscrever ? () => setReservaAberta(r) : undefined} />
            ))}
          </ul>
        </details>
      )}

      {criando && <CompromissoForm onClose={() => setCriando(false)} />}
      {reservando && <ReservaForm onClose={() => setReservando(false)} />}
      {reservaAberta && <ReservaForm reserva={reservaAberta} onClose={() => setReservaAberta(null)} />}
    </>
  );
}

function LinhaCompromisso({ c, onClick }: { c: Commitment; onClick: () => void }) {
  const partes: string[] = [];
  if (c.overdue_count > 0) partes.push(`${c.overdue_count} vencida${c.overdue_count > 1 ? "s" : ""}`);
  else if (c.status !== "ativo") partes.push(c.status);
  else if (c.next) partes.push(`${c.next.label ? `${c.next.label} · ` : ""}${formatDiaMes(c.next.due_date)}`);
  if (c.kind === "recorrente") partes.push(PERIODO_LABEL[c.interval_months] ?? `a cada ${c.interval_months} meses`);
  if (!c.confirmed) partes.push(CERTEZA_LABEL.estimado);
  return (
    <Linha
      rotulo={c.description}
      legenda={partes.join(" · ")}
      tom={c.overdue_count > 0 ? "neg" : undefined}
      valor={`${c.direction === "entrada" ? "+" : ""}${formatMoney(c.amount)}`}
      onClick={onClick}
    />
  );
}

/** "R$ 618 de R$ 618 reservado · ✓ coberto" — ou quanto ainda falta. */
function LinhaReserva({
  r,
  reservas,
  compromisso,
  onClick,
}: {
  r: Provision;
  reservas: Provision[];
  compromisso?: Commitment;
  onClick?: () => void;
}) {
  let legenda: React.ReactNode = r.target_date ? `objetivo até ${formatDiaMes(r.target_date)}` : "objetivo";
  if (compromisso && r.commitment_no != null) {
    const total = reservas
      .filter((x) => x.commitment_id === r.commitment_id && x.commitment_no === r.commitment_no)
      .reduce((s, x) => s + x.amount, 0);
    const falta = Math.max(compromisso.amount - total, 0);
    legenda = (
      <>
        {formatMoney(total)} de {formatMoney(compromisso.amount)}
        {r.occurrence_due && <> · vence {formatDiaMes(r.occurrence_due)}</>} ·{" "}
        {falta < 0.005 ? <span className="ok">✓ coberto</span> : `faltam ${formatMoney(falta)}`}
      </>
    );
  }
  return <Linha rotulo={r.description} legenda={legenda} valor={formatMoney(r.amount)} onClick={onClick} />;
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

  if (isLoading) return <div className="skel" style={{ height: 320 }} />;
  if (error) return <div className="error-box">{(error as ApiError).message}</div>;
  if (!c) return null;

  const hoje = todayIso();
  // Abre no que interessa agora: a próxima em aberto, com duas antes de contexto.
  const inicio = Math.max(0, c.schedule.findIndex((o) => o.due_date >= hoje || o.status === "vencida") - 2);
  const visiveis = todas ? c.schedule : c.schedule.slice(inicio, inicio + 6);
  const entrada = c.direction === "entrada";
  const multiplas = c.kind === "parcelado" && c.total_count != null && c.total_count > 1;

  return (
    <>
      <div className="cabecalho-sec">
        <button type="button" className="voltar" onClick={onVoltar}>‹ Compromissos</button>
        <h1>{c.description}</h1>
      </div>

      <section className="hero plano-hero">
        <div className="big tnum">{multiplas ? `${c.total_count} × ` : ""}{formatMoney(c.amount)}</div>
        <div className="rot">
          {c.institution ? `${c.institution} · ` : ""}
          {c.kind === "parcelado" ? `1ª em ${formatDate(c.first_due)}` : `${PERIODO_LABEL[c.interval_months] ?? ""} desde ${formatDate(c.first_due)}`}
          {!c.confirmed && " · estimado"}
          {c.cancelled_on && ` · cancelado em ${formatDate(c.cancelled_on)}`}
        </div>
      </section>

      <div className="metricas">
        <div className="metrica">
          <div className="rot">{entrada ? "Recebidas" : "Pagas"}</div>
          <div className="val tnum">{multiplas ? `${c.paid_count}/${c.total_count}` : c.paid_count}</div>
        </div>
        {multiplas && (
          <div className="metrica">
            <div className="rot">Restam</div>
            <div className="val tnum">{c.remaining_count}</div>
          </div>
        )}
        <div className="metrica">
          <div className="rot">Próximo</div>
          <div className={`val tnum${c.next ? "" : " fraco"}`}>{c.next ? formatDiaMes(c.next.due_date) : "—"}</div>
        </div>
      </div>
      {c.overdue_count > 0 && (
        <p className="nota neg">{c.overdue_count} vencida{c.overdue_count > 1 ? "s" : ""} sem baixa · {formatMoney(c.overdue_amount)}</p>
      )}

      <details className="detalhe">
        <summary>Detalhes do contrato</summary>
        <ul className="lista-compacta">
          {c.remaining_nominal != null && c.remaining_nominal > 0 && (
            <Linha rotulo="Soma das parcelas que faltam" legenda="nominal — não é o saldo devedor do banco"
              valor={formatMoney(c.remaining_nominal)} />
          )}
          {c.down_payment != null && <Linha rotulo="Entrada" legenda="já é um lançamento à parte" valor={formatMoney(c.down_payment)} />}
          {c.total_amount != null && <Linha rotulo="Valor total / financiado" legenda="só informação" valor={formatMoney(c.total_amount)} />}
          <Linha rotulo="Categoria" valor={c.category_name} />
          {c.payment_hint && <Linha rotulo="Como paga" valor={c.payment_hint} />}
        </ul>
        {c.note && <p className="nota">{c.note}</p>}
      </details>

      <div className="sec-title">
        <h2>Cronograma</h2>
        {podeEscrever && <button className="link" onClick={() => setEditando(true)}>Editar</button>}
      </div>
      <ul className="lista-compacta">
        {visiveis.map((o) => (
          <Linha
            key={o.number}
            rotulo={<>{o.label ? `${o.label} · ` : ""}{formatDate(o.due_date)}</>}
            legenda={
              o.status === "paga" && o.paid_date
                ? `${entrada ? "recebida" : "paga"} em ${formatDiaMes(o.paid_date)}`
                : o.status === "dispensada"
                  ? `dispensada${o.skip_note ? ` · ${o.skip_note}` : ""}`
                  : o.provisioned > 0
                    ? `${formatMoney(o.provisioned)} reservado`
                    : o.status === "pendente" ? undefined : OCORRENCIA_LABEL[o.status]
            }
            tom={o.status === "vencida" ? "neg" : undefined}
            valor={formatMoney(o.paid_amount ?? o.amount)}
            onClick={() => setOcorrencia(o)}
          />
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
        <div className="folha-total">
          <b className="tnum">{formatMoney(o.paid_amount ?? o.amount)}</b>
          <span>
            {o.status === "paga" && o.paid_date
              ? `${entrada ? "recebida" : "paga"} em ${formatDate(o.paid_date)}`
              : `${OCORRENCIA_LABEL[o.status]} · vence ${formatDate(o.due_date)}`}
            {o.provisioned > 0 && aberta && ` · ${formatMoney(o.provisioned)} reservado`}
          </span>
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
