// Natureza do gasto (app/dominio/natureza.py): que evento econômico foi, não
// "com o quê". Gasto total soma as três; custo de vida é só o consumo.
// A natureza efetiva vem pronta do servidor — aqui só rótulo e preferência.

import { useState } from "react";
import type { Natureza } from "./types";

export const NATUREZA_LABEL: Record<Natureza, string> = {
  consumption: "Consumo",
  asset_acquisition: "Aquisição",
  financial: "Financeiro",
};

export const OPCOES_NATUREZA: { valor: Natureza; rotulo: string }[] = (
  ["consumption", "asset_acquisition", "financial"] as Natureza[]
).map((n) => ({ valor: n, rotulo: NATUREZA_LABEL[n] }));

export const NATUREZA_DICA: Record<Natureza, string> = {
  consumption: "Custo de vida: o consumo normal do mês.",
  asset_acquisition: "Compra de um bem (ex.: a entrada da moto). Conta no gasto total, fora do custo de vida.",
  financial: "Parcela de financiamento, juros, tarifa. Conta no gasto total, fora do custo de vida.",
};

// Gasto total ou custo de vida na rosca e na evolução do Início. Preferência
// de quem olha (localStorage), não dado: sem storage, volta pro total.
export type LeituraDoGasto = "total" | "vida";
const CHAVE = "sentavos:leitura-gasto";

function ler(): LeituraDoGasto {
  try {
    return localStorage.getItem(CHAVE) === "vida" ? "vida" : "total";
  } catch {
    return "total";
  }
}

export function useLeituraDoGasto(): [LeituraDoGasto, (l: LeituraDoGasto) => void] {
  const [leitura, setLeitura] = useState<LeituraDoGasto>(ler);
  return [
    leitura,
    (l) => {
      setLeitura(l);
      try {
        localStorage.setItem(CHAVE, l);
      } catch {
        /* segue sem lembrar */
      }
    },
  ];
}
