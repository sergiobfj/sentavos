import { Link } from "react-router-dom";
import { formatDiaMes, formatMoney } from "../../lib/format";
import { CERTEZA_LABEL, type Certeza, type PlanoItem } from "../../lib/tiposPlanejamento";

/* Peças do Planejamento.
 *
 * Regra de densidade desta área (e das telas novas do Sentavos): uma métrica
 * herói por tela, no máximo três secundárias na primeira dobra, listas
 * resumidas com o detalhe atrás de um toque, e nenhum estado interno exposto
 * — "confirmado" e "estimado" aparecem como texto discreto, não como pílula. */

export function nomeDoMes(ano: number, mes: number, comAno = false): string {
  return new Date(ano, mes - 1, 1).toLocaleDateString(
    "pt-BR",
    comAno ? { month: "long", year: "numeric" } : { month: "long" }
  );
}

export function sinal(valor: number): string {
  if (Math.abs(valor) < 0.005) return formatMoney(0);
  return `${valor > 0 ? "+" : "−"}${formatMoney(Math.abs(valor))}`;
}

/** O que a linha diz sobre a certeza ou a situação — uma palavra, discreta.
 *  Só o vencido ganha tom: é o único que pede ação. */
export function Situacao({
  certeza,
  situacao,
  entrada = false,
}: {
  certeza: Certeza;
  situacao?: "pendente" | "vencido" | "pago";
  entrada?: boolean;
}) {
  if (situacao === "vencido") return <span className="situ vencido">{entrada ? "atrasada" : "vencido"}</span>;
  if (situacao === "pago") return <span className="situ">{entrada ? "recebido" : "pago"}</span>;
  // Confirmado é o caso normal: marcar toda linha com ele seria ruído.
  if (certeza === "confirmado") return null;
  return <span className={`situ ${certeza}`}>{CERTEZA_LABEL[certeza]}</span>;
}

/** Uma linha de compromisso, entrada ou hipótese: nome, quando, certeza, valor.
 *  Sem avatar e sem caixa — é lista, não card. */
export function LinhaPlano({ item, onClick }: { item: PlanoItem; onClick?: () => void }) {
  const entrada = item.direction === "entrada";
  const pago = item.status === "pago";
  const conteudo = (
    <>
      <span className="esq">
        <span className="n">
          {item.description}
          {item.label && <> {item.label}</>}
        </span>
        <span className="d">
          {formatDiaMes(item.date)}
          {(item.certainty !== "confirmado" || item.status !== "pendente") && (
            <> · <Situacao certeza={item.certainty} situacao={item.status} entrada={entrada} /></>
          )}
          {item.provisioned > 0 && !pago && (
            <> · {item.provisioned >= item.remaining ? "reservado" : `${formatMoney(item.provisioned)} reservado`}</>
          )}
        </span>
      </span>
      <span className={`v tnum${pago ? " apagado" : ""}`}>
        {item.original_amount != null && <s>{formatMoney(item.original_amount)}</s>}
        {entrada ? "+" : ""}
        {formatMoney(pago ? item.amount : item.remaining)}
      </span>
    </>
  );
  return (
    <li>
      {onClick ? (
        <button type="button" onClick={onClick}>{conteudo}</button>
      ) : (
        <div>{conteudo}</div>
      )}
    </li>
  );
}

/** Linha genérica de lista compacta: rótulo, legenda, valor e, se tocável, seta. */
export function Linha({
  rotulo,
  legenda,
  valor,
  legendaValor,
  tom,
  onClick,
  to,
}: {
  rotulo: React.ReactNode;
  legenda?: React.ReactNode;
  valor?: React.ReactNode;
  legendaValor?: React.ReactNode;
  tom?: "neg" | "pos";
  onClick?: () => void;
  to?: string;
}) {
  const conteudo = (
    <>
      <span className="esq">
        <span className="n">{rotulo}</span>
        {legenda && <span className={`d${tom ? ` ${tom}` : ""}`}>{legenda}</span>}
      </span>
      {(valor != null || legendaValor != null) && (
        <span className="v tnum">
          {valor}
          {legendaValor && <small>{legendaValor}</small>}
        </span>
      )}
      {(onClick || to) && <span className="seta" aria-hidden>›</span>}
    </>
  );
  return (
    <li>
      {to ? (
        <Link to={to}>{conteudo}</Link>
      ) : onClick ? (
        <button type="button" onClick={onClick}>{conteudo}</button>
      ) : (
        <div>{conteudo}</div>
      )}
    </li>
  );
}

/** Topo das telas de detalhe: voltar e título, numa linha. */
export function Cabecalho({ titulo, voltar, voltarPara }: { titulo: string; voltar: string; voltarPara: string }) {
  return (
    <div className="cabecalho-sec">
      <Link className="voltar" to={voltarPara}>‹ {voltar}</Link>
      <h1>{titulo}</h1>
    </div>
  );
}
