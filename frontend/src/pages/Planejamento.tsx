import { useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { Linha, nomeDoMes, sinal } from "../components/planejamento/comum";
import {
  CalculoSheet,
  ContasSheet,
  ItensSheet,
  ReservasSheet,
  SimularGastoSheet,
} from "../components/planejamento/Folhas";
import {
  useComparacao,
  usePlanningHorizon,
  usePlanningMonth,
  useReconciliation,
  useScenarios,
} from "../lib/queries";
import { currentPeriod, usePeriod, type Period } from "../lib/period";
import { useAuth } from "../lib/auth";
import { ApiError } from "../lib/api";
import { formatMoney } from "../lib/format";
import type { PlanoMes, PlanoResposta, Scenario } from "../lib/tiposPlanejamento";

/* Planejamento — a tela responde, primeiro, "quanto eu posso usar?".
 *
 * Primeira camada: o disponível, quanto ainda entra e quanto já está
 * comprometido. Todo o resto — a conta inteira, as listas, as contas do saldo,
 * as reservas — fica a um toque, em folhas. É a mesma informação correta da
 * versão anterior, com o detalhe atrás do resumo em vez de ao lado dele.
 *
 * Fica fora da barra de abas (planejar é semanal, não diário). A porta é a
 * linha "Disponível" do Início e o item na lateral do desktop. */

type Folha = null | "calculo" | "movimento" | "saidas" | "reservas" | "contas" | "simular";

export default function Planejamento() {
  const [params] = useSearchParams();
  const { period, setPeriod } = usePeriod();
  const atual = currentPeriod();

  // Endereços da versão com sub-abas continuam valendo.
  const aba = params.get("aba");
  if (aba === "proximos") return <Navigate to="/planejamento/proximos" replace />;
  if (aba === "compromissos") {
    const id = params.get("id");
    return <Navigate to={`/planejamento/compromissos${id ? `?id=${id}` : ""}`} replace />;
  }

  if (period.year * 12 + period.month < atual.year * 12 + atual.month) {
    return (
      <div className="empty">
        <div className="big">🗓️</div>
        <div className="tit">O planejamento olha pra frente</div>
        <div>{nomeDoMes(period.year, period.month, true)} já passou; o que aconteceu nele está em Lançamentos.</div>
        <div style={{ marginTop: "var(--s4)" }}>
          <button className="btn btn-primary" onClick={() => setPeriod(atual)}>
            Ir para {nomeDoMes(atual.year, atual.month)}
          </button>
        </div>
      </div>
    );
  }
  return <Inicio period={period} />;
}

function Inicio({ period }: { period: Period }) {
  const { sessao } = useAuth();
  const podeEscrever = !sessao?.somenteLeitura;
  const navigate = useNavigate();
  const { data, isLoading, error } = usePlanningMonth(period, null);
  const [folha, setFolha] = useState<Folha>(null);

  if (isLoading && !data) return <Esqueleto />;
  if (error) return <div className="error-box">{(error as ApiError).message}</div>;
  if (!data || data.months.length === 0) return null;

  const mes = data.months[0];
  const nome = nomeDoMes(mes.year, mes.month);

  return (
    <div className="plano-home">
      <div className="plano-col">
        <h1 className="pagina-titulo">Planejamento</h1>

        {/* ---------- Herói: só o que responde "quanto posso usar?" ---------- */}
        <section className="hero plano-hero" aria-labelledby="disp-rotulo">
          <div className="big tnum">{formatMoney(mes.available)}</div>
          <div className="rot" id="disp-rotulo">Disponível até o fim de {nome}</div>
          <button type="button" className="hero-linhas" onClick={() => setFolha("movimento")}
            aria-label={`${formatMoney(mes.income)} a receber e ${formatMoney(mes.expense)} comprometidos. Ver a lista.`}>
            <span><b className="tnum">+ {formatMoney(mes.income)}</b> a receber</span>
            <span><b className="tnum">− {formatMoney(mes.expense)}</b> comprometidos</span>
          </button>
          <button type="button" className="link-seta" onClick={() => setFolha("calculo")}>Ver cálculo</button>
        </section>

        <EsteMes resposta={data} mes={mes} onFolha={setFolha} />

        <button type="button" className="btn btn-primary btn-block plano-acao" onClick={() => setFolha("simular")}>
          + Simular gasto
        </button>
      </div>

      <div className="plano-col">
        <Simulacoes period={period} mes={mes} />
        <ProximosMeses />
        <Mais period={period} />
      </div>

      {folha === "calculo" && (
        <CalculoSheet mes={mes} contas={data.accounts} onContas={() => setFolha("contas")} onClose={() => setFolha(null)} />
      )}
      {(folha === "movimento" || folha === "saidas") && (
        <ItensSheet mes={mes} direcao={folha === "saidas" ? "saida" : undefined} onClose={() => setFolha(null)} />
      )}
      {folha === "reservas" && <ReservasSheet mes={mes} onClose={() => setFolha(null)} />}
      {folha === "contas" && (
        <ContasSheet contas={data.accounts} aviso={data.balance_warning} period={period}
          podeEscrever={podeEscrever} onClose={() => setFolha(null)} />
      )}
      {folha === "simular" && (
        <SimularGastoSheet mes={mes} podeEscrever={podeEscrever}
          onSalvo={(id) => navigate(`/planejamento/simulacoes?id=${id}`)} onClose={() => setFolha(null)} />
      )}
    </div>
  );
}

/** Até três linhas: de onde a conta parte, o que já tem destino e o que
 *  venceu. "Comprometido" e "livre" não se repetem aqui: já estão no herói. */
function EsteMes({ resposta, mes, onFolha }: { resposta: PlanoResposta; mes: PlanoMes; onFolha: (f: Folha) => void }) {
  // Só conta com saldo deste mês entra; a de saldo antigo fica fora e é dita.
  const contas = resposta.accounts.filter((c) => c.included && !c.stale);
  const aviso = resposta.balance_warning;
  const fora = aviso.contas_desatualizadas ?? [];
  const desatualizado = mes.is_current && (fora.length > 0 || aviso.sem_contas || aviso.contas_sem_saldo.length > 0);
  const legendaSaldo = aviso.sem_contas
    ? "nenhuma conta escolhida"
    : [
        contas.length ? `${contas.length} ${contas.length === 1 ? "conta" : "contas"}` : "sem saldo deste mês",
        fora.length ? `${fora.length} sem saldo de ${nomeDoMes(mes.year, mes.month)}, fora` : "",
      ].filter(Boolean).join(" · ");

  return (
    <>
      <div className="sec-title"><h2>Este mês</h2></div>
      <ul className="lista-compacta">
        {mes.opening_source === "saldos" && (
          <Linha
            rotulo="Saldo considerado"
            legenda={legendaSaldo}
            tom={desatualizado ? "neg" : undefined}
            valor={formatMoney(mes.opening)}
            onClick={() => onFolha("contas")}
          />
        )}
        <Linha
          rotulo="Reservado"
          legenda={
            mes.reserves.length === 0
              ? "nada separado"
              : `${mes.reserves.length} ${mes.reserves.length === 1 ? "reserva" : "reservas"}`
          }
          valor={formatMoney(mes.reserved)}
          onClick={() => onFolha("reservas")}
        />
        {mes.overdue > 0 && (
          <Linha rotulo="Vencido sem baixa" legenda="continua contando até ser pago" tom="neg"
            valor={formatMoney(mes.overdue)} onClick={() => onFolha("saidas")} />
        )}
      </ul>
    </>
  );
}

/** As simulações salvas, no máximo três, cada uma com o disponível dela. */
function Simulacoes({ period, mes }: { period: Period; mes: PlanoMes }) {
  const { data: cenarios } = useScenarios();
  const lista = cenarios ?? [];
  return (
    <>
      <div className="sec-title">
        <h2>Simulações</h2>
        {lista.length > 0 && <Link to="/planejamento/simulacoes">Ver todas</Link>}
      </div>
      {lista.length === 0 ? (
        <p className="hint">Nenhuma simulação salva. Use "Simular gasto" e salve a que quiser comparar.</p>
      ) : (
        <ul className="lista-compacta">
          {lista.slice(0, 3).map((s) => <LinhaSimulacao key={s.id} cenario={s} period={period} base={mes} />)}
        </ul>
      )}
    </>
  );
}

function LinhaSimulacao({ cenario, period, base }: { cenario: Scenario; period: Period; base: PlanoMes }) {
  const { data } = useComparacao(period, cenario.id);
  const disponivel = data?.scenario.available;
  const diferenca = data ? data.diff.available : null;
  return (
    <Linha
      rotulo={cenario.name}
      legenda={diferenca == null ? "…" : Math.abs(diferenca) < 0.005 ? "nada muda neste mês" : `${sinal(diferenca)} no disponível`}
      valor={disponivel != null ? formatMoney(disponivel) : formatMoney(base.available)}
      legendaValor="disponível"
      to={`/planejamento/simulacoes?id=${cenario.id}`}
    />
  );
}

/** Prévia: só o comprometido de cada um dos três meses seguintes. */
function ProximosMeses() {
  const { data } = usePlanningHorizon(4);
  const meses = (data?.months ?? []).slice(1);
  return (
    <>
      <div className="sec-title">
        <h2>Próximos meses</h2>
        <Link to="/planejamento/proximos">Ver 6 meses</Link>
      </div>
      {meses.length === 0 ? (
        <div className="skel" style={{ height: 132 }} />
      ) : (
        <ul className="lista-compacta">
          {meses.map((m) => (
            <Linha
              key={`${m.year}-${m.month}`}
              rotulo={<span style={{ textTransform: "capitalize" }}>{nomeDoMes(m.year, m.month)}</span>}
              legenda={
                m.provisioned > 0
                  ? m.still_needed > 0 ? `${formatMoney(m.provisioned)} reservado · faltam ${formatMoney(m.still_needed)}` : "coberto pelas reservas"
                  : m.expense > 0 ? "nada reservado ainda" : undefined
              }
              valor={formatMoney(m.expense)}
              legendaValor="comprometido"
              to="/planejamento/proximos"
            />
          ))}
        </ul>
      )}
    </>
  );
}

function Mais({ period }: { period: Period }) {
  const { data } = useReconciliation(period);
  const abertos = data ? data.counts.pendente + data.counts.confirmar : 0;
  return (
    <ul className="lista-compacta plano-mais">
      {abertos > 0 && (
        <Linha rotulo={`Organizar ${nomeDoMes(period.year, period.month)}`}
          legenda={`${abertos} ${abertos === 1 ? "item" : "itens"} pra revisar`} to="/organizar" />
      )}
      <Linha rotulo="Compromissos e reservas" legenda="financiamentos, contas recorrentes, dinheiro separado"
        to="/planejamento/compromissos" />
    </ul>
  );
}

function Esqueleto() {
  return (
    <>
      <div className="skel" style={{ height: 22, width: "40%" }} />
      <div className="skel" style={{ height: 44, width: "65%", marginTop: "var(--s4)" }} />
      <div className="skel" style={{ height: 16, width: "45%", marginTop: "var(--s2)" }} />
      <div className="skel" style={{ height: 120, marginTop: "var(--s5)" }} />
    </>
  );
}
