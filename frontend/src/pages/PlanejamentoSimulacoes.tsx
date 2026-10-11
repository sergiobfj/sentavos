import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Cabecalho, nomeDoMes, sinal } from "../components/planejamento/comum";
import { CalculoSheet } from "../components/planejamento/Folhas";
import {
  AjustarNoCenario,
  EditarCenario,
  EscolherItemReal,
  LinhaSimulacao,
  NovaHipotese,
  NovoCenario,
} from "../components/planejamento/Cenarios";
import { useComparacao, usePlanningMonth, useRemoveScenarioItem, useScenarios } from "../lib/queries";
import { currentPeriod, usePeriod, type Period } from "../lib/period";
import { useAuth } from "../lib/auth";
import { ApiError } from "../lib/api";
import { formatDiaMes, formatMoney } from "../lib/format";
import type { PlanoItem, PlanoReserva, Scenario } from "../lib/tiposPlanejamento";

/** As simulações salvas. Sem ?id= é a lista; com ele, uma simulação aberta. */
export default function PlanejamentoSimulacoes() {
  const [params, setParams] = useSearchParams();
  const id = Number(params.get("id")) || null;
  const { period } = usePeriod();
  const atual = currentPeriod();
  // Simulação olha do mês corrente em diante, como o resto do planejamento.
  const mes = period.year * 12 + period.month < atual.year * 12 + atual.month ? atual : period;
  const { data: cenarios, isLoading } = useScenarios();
  const { sessao } = useAuth();
  const podeEscrever = !sessao?.somenteLeitura;
  const [criando, setCriando] = useState(false);

  function abrir(novo: number | null) {
    setParams(novo == null ? {} : { id: String(novo) }, { replace: novo == null });
  }

  const cenario = cenarios?.find((s) => s.id === id) ?? null;
  if (id != null && cenario) {
    return <Simulacao cenario={cenario} period={mes} podeEscrever={podeEscrever} onFechar={() => abrir(null)} onAbrir={abrir} />;
  }

  return (
    <>
      <Cabecalho titulo="Simulações" voltar="Planejamento" voltarPara="/planejamento" />
      <p className="nota" style={{ marginTop: 0 }}>
        Cada uma mostra o disponível de {nomeDoMes(mes.year, mes.month)} se a hipótese acontecer. Nada aqui é lançado.
      </p>
      {isLoading && <div className="skel" style={{ height: 160 }} />}
      {cenarios && cenarios.length === 0 && <p className="hint">Nenhuma simulação salva.</p>}
      {cenarios && cenarios.length > 0 && (
        <ul className="lista-compacta">
          {cenarios.map((s) => (
            <LinhaSimulacao key={s.id} cenario={s} period={mes} to={`/planejamento/simulacoes?id=${s.id}`} />
          ))}
        </ul>
      )}
      {podeEscrever && (
        <button className="btn btn-block" style={{ marginTop: "var(--s4)" }} onClick={() => setCriando(true)}>
          + Nova simulação
        </button>
      )}
      {criando && <NovoCenario onCriado={(novo) => { setCriando(false); abrir(novo); }} onClose={() => setCriando(false)} />}
    </>
  );
}

function Simulacao({
  cenario,
  period,
  podeEscrever,
  onFechar,
  onAbrir,
}: {
  cenario: Scenario;
  period: Period;
  podeEscrever: boolean;
  onFechar: () => void;
  onAbrir: (id: number) => void;
}) {
  const navigate = useNavigate();
  const { data, isLoading, error } = usePlanningMonth(period, cenario.id);
  const comparacao = useComparacao(period, cenario.id);
  const remover = useRemoveScenarioItem();
  const [folha, setFolha] = useState<null | "calculo" | "editar" | "hipotese" | "escolher">(null);
  const [alvo, setAlvo] = useState<PlanoItem | PlanoReserva | null>(null);

  if (isLoading && !data) return <div className="skel" style={{ height: 240 }} />;
  if (error) return <div className="error-box">{(error as ApiError).message}</div>;
  const mes = data?.months[0];
  if (!mes) return null;

  return (
    <>
      <div className="cabecalho-sec">
        <button type="button" className="voltar" onClick={onFechar}>‹ Simulações</button>
        <h1>{cenario.name}</h1>
      </div>

      <section className="hero plano-hero">
        <div className="big tnum">{formatMoney(mes.available)}</div>
        <div className="rot">Disponível em {nomeDoMes(mes.year, mes.month)} nesta simulação</div>
        {comparacao.data && (
          <div className="hero-linhas">
            <span style={{ display: "inline" }}>
              <b className="tnum">{sinal(comparacao.data.diff.available)}</b> em relação ao planejado (
              {formatMoney(comparacao.data.base.available)})
            </span>
          </div>
        )}
        <button type="button" className="link-seta" onClick={() => setFolha("calculo")}>Ver cálculo</button>
      </section>
      {cenario.note && <p className="nota">{cenario.note}</p>}

      <div className="sec-title">
        <h2>Hipóteses</h2>
        {podeEscrever && <button className="link" onClick={() => setFolha("editar")}>Editar</button>}
      </div>
      {cenario.items.length === 0 ? (
        <p className="hint">Nenhuma hipótese ainda.</p>
      ) : (
        <ul className="lista-compacta">
          {cenario.items.map((h) => (
            <li key={h.id}>
              <div>
                <span className="esq">
                  <span className="n">{h.description}</span>
                  <span className="d">
                    <span className="situ hipotetico">
                      {h.ref ? (h.amount === 0 ? "tirado da conta" : "valor mudado") : h.kind === "saida" ? "gasto" : h.kind === "entrada" ? "entrada" : "guardar"}
                    </span>
                    {" · "}{formatDiaMes(h.date)}
                    {h.repeat_months > 1 && ` · por ${h.repeat_months} meses`}
                  </span>
                </span>
                <span className="v tnum">{formatMoney(h.amount)}</span>
                {podeEscrever && (
                  <button type="button" className="tirar" aria-label={`Tirar ${h.description}`} disabled={remover.isPending}
                    onClick={() => remover.mutate({ id: cenario.id, itemId: h.id })}>✕</button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {podeEscrever && (
        <div className="acoes-linha">
          <button className="btn btn-sm" onClick={() => setFolha("hipotese")}>+ Hipótese</button>
          <button className="btn btn-sm" onClick={() => setFolha("escolher")}>Mudar um item real</button>
        </div>
      )}

      {folha === "calculo" && <CalculoSheet mes={mes} contas={data!.accounts} onClose={() => setFolha(null)} />}
      {folha === "editar" && (
        <EditarCenario cenario={cenario} onDuplicado={onAbrir} onExcluido={() => navigate("/planejamento/simulacoes")}
          onClose={() => setFolha(null)} />
      )}
      {folha === "hipotese" && <NovaHipotese cenario={cenario} mes={mes} onClose={() => setFolha(null)} />}
      {folha === "escolher" && (
        <EscolherItemReal mes={mes} onEscolher={(a) => { setAlvo(a); setFolha(null); }} onClose={() => setFolha(null)} />
      )}
      {alvo && <AjustarNoCenario cenario={cenario} alvo={alvo} onClose={() => setAlvo(null)} />}
    </>
  );
}
