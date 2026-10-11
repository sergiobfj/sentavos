import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Segmentado from "../components/Segmentado";
import { Cabecalho, LinhaPlano, nomeDoMes } from "../components/planejamento/comum";
import { usePlanningHorizon } from "../lib/queries";
import { ApiError } from "../lib/api";
import { formatMoney } from "../lib/format";
import type { PlanoMes } from "../lib/tiposPlanejamento";

const JANELAS = [
  { valor: "3", rotulo: "3 meses" },
  { valor: "6", rotulo: "6 meses" },
  { valor: "12", rotulo: "12 meses" },
] as const;

const CHAVE = "sentavos:horizonte";

function lerJanela(): "3" | "6" | "12" {
  try {
    const v = localStorage.getItem(CHAVE);
    if (v === "3" || v === "6" || v === "12") return v;
  } catch {
    /* armazenamento bloqueado: segue com o padrão */
  }
  return "6";
}

/** "Novembro já começa com quanto comprometido?" — um mês por bloco.
 *
 *  Cada mês diz o comprometido em destaque, quanto disso já está reservado e
 *  quanto ainda falta separar, e embaixo a lista do que compõe. O cronograma
 *  inteiro de um financiamento mora na tela dele, não aqui. */
export default function PlanejamentoProximos() {
  const [janela, setJanela] = useState<"3" | "6" | "12">(lerJanela);
  const { data, isLoading, error } = usePlanningHorizon(Number(janela));

  function escolher(v: "3" | "6" | "12") {
    setJanela(v);
    try {
      localStorage.setItem(CHAVE, v);
    } catch {
      /* segue sem lembrar */
    }
  }

  return (
    <>
      <Cabecalho titulo="Próximos meses" voltar="Planejamento" voltarPara="/planejamento" />
      <Segmentado rotulo="Horizonte" opcoes={[...JANELAS]} valor={janela} aoEscolher={escolher} largo />

      {isLoading && !data && <div className="skel" style={{ height: 320, marginTop: "var(--s4)" }} />}
      {error && <div className="error-box" style={{ marginTop: "var(--s4)" }}>{(error as ApiError).message}</div>}
      {data?.months.map((m) => <Mes key={`${m.year}-${m.month}`} mes={m} />)}
    </>
  );
}

function Mes({ mes }: { mes: PlanoMes }) {
  const navigate = useNavigate();
  const abertos = mes.items.filter((i) => i.status !== "pago");
  const saidas = abertos.filter((i) => i.direction === "saida");
  const entradas = abertos.filter((i) => i.direction === "entrada");
  const outroAno = mes.year !== new Date().getFullYear();

  return (
    <section className="mes-bloco">
      <div className="mes-cab">
        <h2>
          {nomeDoMes(mes.year, mes.month)}
          {outroAno && ` ${mes.year}`}
        </h2>
        <span className="tnum">sobra {formatMoney(mes.projected)}</span>
      </div>
      <div className="mes-numero">
        <b className="tnum">{formatMoney(mes.expense)}</b> comprometidos
      </div>
      {mes.expense > 0 && (
        <div className="mes-legenda">
          {mes.provisioned > 0
            ? mes.still_needed > 0
              ? <>{formatMoney(mes.provisioned)} reservado · {formatMoney(mes.still_needed)} ainda necessário</>
              : <>{formatMoney(mes.provisioned)} reservado · <span className="ok">✓ coberto</span></>
            : "nada reservado ainda"}
          {mes.overdue > 0 && <> · <span className="neg">{formatMoney(mes.overdue)} vencido</span></>}
        </div>
      )}

      {saidas.length > 0 && (
        <ul className="lista-compacta">
          {saidas.map((i) => (
            <LinhaPlano
              key={i.key}
              item={i}
              onClick={
                i.commitment_id != null
                  ? () => navigate(`/planejamento/compromissos?id=${i.commitment_id}`)
                  : i.invoice_id != null
                    ? () => navigate("/orcamento?aba=faturas")
                    : undefined
              }
            />
          ))}
        </ul>
      )}
      {entradas.length > 0 && (
        <div className="mes-legenda">
          entra {formatMoney(mes.income)} ({entradas.map((i) => i.description).join(", ")})
        </div>
      )}
      {saidas.length === 0 && entradas.length === 0 && <p className="hint">Nada a pagar ou receber.</p>}
    </section>
  );
}
