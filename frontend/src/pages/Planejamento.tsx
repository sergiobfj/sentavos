import { Link, useSearchParams } from "react-router-dom";
import SimularMes from "../components/planejamento/SimularMes";
import ProximosMeses from "../components/planejamento/ProximosMeses";
import Compromissos from "../components/planejamento/Compromissos";
import { useReconciliation } from "../lib/queries";
import { currentPeriod } from "../lib/period";
import { nomeDoMes } from "../components/planejamento/comum";

/* Planejamento fica FORA da barra de abas, de propósito.
 *
 * As quatro abas do polegar são as de todo dia. Planejar é o que se faz uma ou
 * duas vezes por semana — e uma quinta aba encolheria as outras quatro na faixa
 * que a mão alcança. A porta é uma linha no Início ("Disponível em outubro"),
 * que é onde a pergunta "quanto posso gastar?" aparece, e um item na lateral
 * do desktop. */

type Aba = "mes" | "proximos" | "compromissos";

const ABAS: { id: Aba; rotulo: string }[] = [
  { id: "mes", rotulo: "Simular mês" },
  { id: "proximos", rotulo: "Próximos" },
  { id: "compromissos", rotulo: "Compromissos" },
];

export default function Planejamento() {
  const [params, setParams] = useSearchParams();
  const pedida = params.get("aba");
  const aba: Aba = pedida === "proximos" || pedida === "compromissos" ? pedida : "mes";
  const atual = currentPeriod();
  const { data: conferencia } = useReconciliation(atual);
  const abertos = conferencia ? conferencia.counts.pendente + conferencia.counts.confirmar : 0;

  function escolher(id: Aba) {
    setParams(
      (prev) => {
        const p = new URLSearchParams();
        // O cenário sobrevive ao vaivém entre abas; o compromisso aberto não.
        const cenario = prev.get("cenario");
        if (cenario) p.set("cenario", cenario);
        if (id !== "mes") p.set("aba", id);
        return p;
      },
      { replace: true }
    );
  }

  return (
    <>
      <div className="subtabs" role="tablist">
        {ABAS.map(({ id, rotulo }) => (
          <button key={id} role="tab" aria-selected={aba === id} className={aba === id ? "active" : ""}
            onClick={() => escolher(id)}>
            {rotulo}
          </button>
        ))}
      </div>

      {abertos > 0 && (
        <Link className="aviso-acao" to="/organizar" style={{ marginTop: 0, marginBottom: "var(--s4)" }}>
          <div>
            <b>Organizar {nomeDoMes(atual.year, atual.month)}</b> · {abertos}{" "}
            {abertos === 1 ? "item espera" : "itens esperam"} confirmação
          </div>
          <span aria-hidden>›</span>
        </Link>
      )}

      {aba === "mes" && <SimularMes />}
      {aba === "proximos" && <ProximosMeses />}
      {aba === "compromissos" && <Compromissos />}
    </>
  );
}
