import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Segmentado from "../Segmentado";
import { LinhaPlano, nomeDoMes } from "./comum";
import { usePlanningHorizon } from "../../lib/queries";
import { ApiError } from "../../lib/api";
import { formatMoney } from "../../lib/format";
import { ORIGEM_LABEL, type OrigemPlano, type PlanoMes } from "../../lib/tiposPlanejamento";

const JANELAS = [
  { valor: "3", rotulo: "3 meses" },
  { valor: "6", rotulo: "6 meses" },
  { valor: "12", rotulo: "12 meses" },
] as const;

const CHAVE_JANELA = "sentavos:horizonte";

function lerJanela(): "3" | "6" | "12" {
  try {
    const v = localStorage.getItem(CHAVE_JANELA);
    if (v === "3" || v === "6" || v === "12") return v;
  } catch {
    /* armazenamento bloqueado: segue com o padrão */
  }
  return "6";
}

/** "Novembro já começa com quanto comprometido?" — um mês por bloco.
 *
 *  Fechado, o bloco responde as três perguntas (quanto devo, quanto já separei,
 *  quanto falta separar). Aberto, mostra de onde vem cada real. Um financiamento
 *  de 48 meses aparece aqui só nos meses da janela; o cronograma inteiro mora
 *  na tela do compromisso. */
export default function ProximosMeses() {
  const [janela, setJanela] = useState<"3" | "6" | "12">(lerJanela);
  const { data, isLoading, error } = usePlanningHorizon(Number(janela));

  function escolher(v: "3" | "6" | "12") {
    setJanela(v);
    try {
      localStorage.setItem(CHAVE_JANELA, v);
    } catch {
      /* segue sem lembrar */
    }
  }

  return (
    <>
      <Segmentado rotulo="Horizonte" opcoes={[...JANELAS]} valor={janela} aoEscolher={escolher} largo />

      {isLoading && !data && <div className="skel" style={{ height: 320, marginTop: "var(--s4)" }} />}
      {error && <div className="error-box" style={{ marginTop: "var(--s4)" }}>{(error as ApiError).message}</div>}

      {data && (
        <>
          <p className="hint" style={{ margin: "var(--s4) 0 var(--s3)" }}>
            Cartão vem das faturas; parcelados e recorrentes, dos compromissos; previstos, dos
            lançamentos sem valor pago. O saldo de cada mês parte do projetado do anterior.
          </p>
          {data.months.map((m, i) => (
            <BlocoDoMes key={`${m.year}-${m.month}`} mes={m} aberto={i === 0} />
          ))}
        </>
      )}
    </>
  );
}

const ORDEM: OrigemPlano[] = ["cartao", "parcelado", "recorrente", "previsto", "cenario"];

function BlocoDoMes({ mes, aberto }: { mes: PlanoMes; aberto: boolean }) {
  const navigate = useNavigate();
  const origens = ORDEM.filter((o) => mes.by_source[o] > 0);
  const ativos = mes.items.filter((i) => i.status !== "pago");

  return (
    <details className="mes-plano" open={aberto}>
      <summary>
        <div className="cab">
          <span className="n">
            {nomeDoMes(mes.year, mes.month)}
            {mes.year !== new Date().getFullYear() && ` ${mes.year}`}
          </span>
          <span className="p">
            sobra <b className="tnum">{formatMoney(mes.projected)}</b>
            {mes.reserved > 0 && (
              <>
                <br />
                livre <b className="tnum">{formatMoney(mes.available)}</b>
              </>
            )}
          </span>
        </div>
        <div className="tres">
          <Numero rotulo="Comprometido" valor={mes.expense} />
          <Numero rotulo="Provisionado" valor={mes.provisioned} />
          <Numero rotulo="Ainda falta" valor={mes.still_needed} />
        </div>
        {(origens.length > 0 || mes.income > 0) && (
          <div className="origens">
            {origens.map((o) => `${ORIGEM_LABEL[o]} ${formatMoney(mes.by_source[o])}`).join(" · ")}
            {mes.by_certainty.estimado > 0 && ` · ${formatMoney(mes.by_certainty.estimado)} estimado`}
            {mes.income > 0 && ` · entra ${formatMoney(mes.income)}`}
          </div>
        )}
      </summary>

      <div className="corpo">
        {ativos.length === 0 ? (
          <div className="hint">Nada a pagar ou receber.</div>
        ) : (
          <div className="list">
            {ativos.map((i) => (
              <LinhaPlano
                key={i.key}
                item={i}
                onClick={
                  i.commitment_id != null
                    ? () => navigate(`/planejamento?aba=compromissos&id=${i.commitment_id}`)
                    : i.invoice_id != null
                      ? () => navigate("/orcamento?aba=faturas")
                      : undefined
                }
              />
            ))}
          </div>
        )}
        {mes.overdue > 0 && (
          <div className="nota">
            {formatMoney(mes.overdue)} venceram e não têm baixa. Vencido não é pago: continua
            contando até ser pago ou dispensado.
          </div>
        )}
      </div>
    </details>
  );
}

function Numero({ rotulo, valor }: { rotulo: string; valor: number }) {
  return (
    <div>
      <div className="r">{rotulo}</div>
      <div className={`v tnum${valor === 0 ? " zero" : ""}`}>{formatMoney(valor)}</div>
    </div>
  );
}
