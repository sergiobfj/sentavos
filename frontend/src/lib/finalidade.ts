import { useState } from "react";
import { FINALIDADE_LABEL, FINALIDADES, type Finalidade, type FiltroFinalidade } from "./types";

// O filtro é lembrado entre aberturas: quem olha "Pessoal" quer continuar
// olhando "Pessoal" amanhã. Preferência de quem está vendo, não dado — por
// isso localStorage, e por isso a tela funciona igual se ele falhar.
const CHAVE = "sentavos:finalidade";

export const OPCOES_FINALIDADE: { valor: Finalidade; rotulo: string }[] = FINALIDADES.map((f) => ({
  valor: f,
  rotulo: FINALIDADE_LABEL[f],
}));

export const OPCOES_FILTRO: { valor: FiltroFinalidade; rotulo: string }[] = [
  ...FINALIDADES.map((f) => ({ valor: f as FiltroFinalidade, rotulo: FINALIDADE_LABEL[f] })),
  { valor: "todos", rotulo: "Todos" },
];

// Adjetivo no plural, pra frase "R$ 1.240 gastos pessoais em setembro".
export const FRASE_FILTRO: Record<FiltroFinalidade, string> = {
  pessoal: "gastos pessoais",
  familia: "gastos da família",
  empresa: "gastos da empresa",
  todos: "gastos no total",
};

function ler(): FiltroFinalidade {
  try {
    const v = localStorage.getItem(CHAVE);
    if (v === "pessoal" || v === "familia" || v === "empresa" || v === "todos") return v;
  } catch {
    /* armazenamento bloqueado: segue com o padrão */
  }
  // Todos por padrão: é o único filtro que não esconde nada, inclusive os
  // lançamentos antigos sem finalidade.
  return "todos";
}

export function useFiltroFinalidade(): [FiltroFinalidade, (f: FiltroFinalidade) => void] {
  const [filtro, setFiltro] = useState<FiltroFinalidade>(ler);
  return [
    filtro,
    (f) => {
      setFiltro(f);
      try {
        localStorage.setItem(CHAVE, f);
      } catch {
        /* segue sem lembrar */
      }
    },
  ];
}
