import { formatDiaMes, formatMoney } from "../../lib/format";
import { fundoDaCor } from "../../lib/paleta";
import { CERTEZA_LABEL, type Certeza, type PlanoItem } from "../../lib/tiposPlanejamento";

export function nomeDoMes(ano: number, mes: number, comAno = false): string {
  return new Date(ano, mes - 1, 1).toLocaleDateString(
    "pt-BR",
    comAno ? { month: "long", year: "numeric" } : { month: "long" }
  );
}

/** O grau de certeza, pela forma do marcador e pela palavra. Sem cor: só o
 *  que pede ação (vencido) ou já aconteceu (pago) ganha tom. */
export function Selo({
  certeza,
  situacao,
  entrada = false,
}: {
  certeza: Certeza;
  situacao?: "pendente" | "vencido" | "pago";
  entrada?: boolean;
}) {
  if (situacao === "vencido") {
    return <span className="selo vencido">{entrada ? "atrasada" : "vencido"}</span>;
  }
  if (situacao === "pago") {
    return <span className="selo pago">{entrada ? "recebido" : "pago"}</span>;
  }
  return <span className={`selo ${certeza}`}>{CERTEZA_LABEL[certeza]}</span>;
}

/** Uma linha do mês planejado. O valor à direita é o que ainda CONTA; o que
 *  já foi pago aparece riscado e apagado, só como contexto. */
export function LinhaPlano({ item, onClick }: { item: PlanoItem; onClick?: () => void }) {
  const entrada = item.direction === "entrada";
  const pago = item.status === "pago";
  const quando = pago
    ? null
    : item.status === "vencido"
      ? `venceu ${formatDiaMes(item.date)}`
      : `${entrada ? "previsto" : "vence"} ${formatDiaMes(item.date)}`;
  const corpo = (
    <>
      <div
        className="avatar"
        aria-hidden
        style={{ background: fundoDaCor(item.color ?? "#5b5a56", 22) }}
      >
        {item.icon ?? (item.source === "cenario" ? "✦" : "•")}
      </div>
      <div className="mid">
        <div className="t">
          {item.description}
          {item.label && <> {item.label}</>}
        </div>
        <div className="s">
          <Selo certeza={item.certainty} situacao={item.status} entrada={entrada} />
          {quando && <span>{quando}</span>}
          {item.detail && <span>{item.detail}</span>}
          {item.provisioned > 0 && !pago && (
            <span>
              {item.provisioned >= item.remaining
                ? "reservado"
                : `${formatMoney(item.provisioned)} reservado`}
            </span>
          )}
        </div>
      </div>
      <div className={`amt tnum ${entrada && !pago ? "pos" : ""}`}>
        {item.original_amount != null && (
          <span className="riscado">{formatMoney(item.original_amount)}</span>
        )}
        {entrada ? "+" : "−"}
        {formatMoney(pago ? item.amount : item.remaining)}
      </div>
    </>
  );
  const classe = `row plano-row${pago ? " pago" : ""}`;
  return onClick ? (
    <button className={classe} onClick={onClick}>
      {corpo}
    </button>
  ) : (
    <div className={classe}>{corpo}</div>
  );
}

export function sinal(valor: number): string {
  if (Math.abs(valor) < 0.005) return formatMoney(0);
  return `${valor > 0 ? "+" : "−"}${formatMoney(Math.abs(valor))}`;
}
