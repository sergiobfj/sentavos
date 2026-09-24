import { lazy, Suspense } from "react";
import { formatMoney } from "../lib/format";
import type { PontoEvolucao } from "./graficos/EvolucaoSvg";

/* ===========================================================================
   Gráficos do Sentavos
   ===========================================================================

   Dois só: a rosca (composição de UM total) e a linha (um valor ao longo do
   tempo). As barras de "Previsto × pago" e "Fluxo" saíram do Início — a
   segunda somava entrou + gastou + investido como partes de um mesmo todo, o
   que não tem significado financeiro nenhum.

   O Recharts carrega num pedaço separado do bundle (`lazy`). O número herói e
   as legendas aparecem na hora; o desenho chega um instante depois, no mesmo
   espaço reservado, sem a tela pular.
   =========================================================================== */

const RoscaSvg = lazy(() => import("./graficos/RoscaSvg"));
const EvolucaoSvg = lazy(() => import("./graficos/EvolucaoSvg"));

export type { PontoEvolucao };

export interface Fatia {
  id: string;
  nome: string;
  icone?: string;
  cor: string;
  valor: number;
  // Sobre o total real do filtro, já calculado pelo servidor.
  pct: number;
}

/** Percentual pra leitura: inteiro, com "<1%" em vez de um "0%" que mente. */
export function formatPct(pct: number): string {
  if (pct > 0 && pct < 1) return "<1%";
  return `${Math.round(pct)}%`;
}

/** Rosca com o total no centro e a legenda-tabela ao lado (ou embaixo).
 *
 * A legenda não é enfeite: ela é a tabela dos números e o que torna a cor
 * dispensável. Nenhum texto vai dentro das fatias — em 400px ele não cabe.
 */
export function Rosca({
  fatias,
  total,
  rotuloCentro,
  tamanho = 184,
  semLegenda = false,
}: {
  fatias: Fatia[];
  total: number;
  rotuloCentro: string;
  tamanho?: number;
  // Quando a lista da própria tela já faz o papel de legenda (Investir), uma
  // segunda legenda repetiria os mesmos nomes e valores logo abaixo.
  semLegenda?: boolean;
}) {
  const descricao = fatias
    .map((f) => `${f.nome} ${formatMoney(f.valor)} (${formatPct(f.pct)})`)
    .join("; ");

  return (
    <div className={semLegenda ? "rosca so" : "rosca"}>
      <div
        className="rosca-grafico"
        style={{ width: tamanho, height: tamanho }}
        role="img"
        aria-label={`${rotuloCentro}: ${formatMoney(total)}. ${descricao}`}
      >
        <Suspense fallback={<div className="skel" style={{ width: "100%", height: "100%", borderRadius: "50%" }} />}>
          <RoscaSvg fatias={fatias} tamanho={tamanho} />
        </Suspense>
        <div className="rosca-centro" aria-hidden>
          <b className="tnum">{formatMoney(total)}</b>
          <span>{rotuloCentro}</span>
        </div>
      </div>

      {!semLegenda && (
      <ul className="legenda">
        {fatias.map((f) => (
          <li key={f.id}>
            <i className="cor" style={{ background: f.cor }} aria-hidden />
            <span className="nome">
              {f.icone && <span className="ic" aria-hidden>{f.icone}</span>}
              {f.nome}
            </span>
            <span className="v tnum">{formatMoney(f.valor)}</span>
            <span className="p tnum">{formatPct(f.pct)}</span>
          </li>
        ))}
      </ul>
      )}
    </div>
  );
}

export function Evolucao({ pontos }: { pontos: PontoEvolucao[] }) {
  const resumo = pontos
    .map((p) => `${p.mesLongo}: ${p.valor == null ? "sem dado" : formatMoney(p.valor)}`)
    .join("; ");
  return (
    <div className="evolucao" role="img" aria-label={`Evolução dos gastos. ${resumo}`}>
      <Suspense fallback={<div className="skel" style={{ height: "100%" }} />}>
        <EvolucaoSvg pontos={pontos} />
      </Suspense>
    </div>
  );
}
