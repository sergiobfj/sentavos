import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

// Mês selecionado no app. Vive acima do <Outlet/> pra sobreviver à navegação
// entre abas, e no localStorage pra sobreviver ao F5.

const STORAGE_KEY = "sentavos:period";

export interface Period {
  year: number;
  month: number; // 1-12, como o backend espera
}

export function currentPeriod(): Period {
  const now = new Date();
  return { year: now.getFullYear(), month: now.getMonth() + 1 };
}

export function toYm({ year, month }: Period): string {
  return `${year}-${String(month).padStart(2, "0")}`;
}

// Converte pra índice absoluto de meses, soma, e volta — evita as armadilhas
// de fim de mês que aparecem quando se usa Date.setMonth.
export function shiftPeriod({ year, month }: Period, delta: number): Period {
  const i = year * 12 + (month - 1) + delta;
  return { year: Math.floor(i / 12), month: (i % 12) + 1 };
}

export function formatPeriod({ year, month }: Period): string {
  return new Date(year, month - 1, 1).toLocaleDateString("pt-BR", {
    month: "long",
    year: "numeric",
  });
}

function readStored(): Period {
  try {
    const [y, m] = (localStorage.getItem(STORAGE_KEY) ?? "").split("-").map(Number);
    if (y && m >= 1 && m <= 12) return { year: y, month: m };
  } catch {
    /* localStorage pode estar bloqueado */
  }
  return currentPeriod();
}

interface PeriodValue {
  period: Period;
  ym: string;
  label: string;
  isCurrent: boolean;
  setPeriod: (p: Period) => void;
  shift: (delta: number) => void;
  goToCurrent: () => void;
}

const PeriodContext = createContext<PeriodValue | null>(null);

export function PeriodProvider({ children }: { children: ReactNode }) {
  const [period, setState] = useState<Period>(readStored);

  const value = useMemo<PeriodValue>(() => {
    function setPeriod(p: Period) {
      setState(p);
      try {
        localStorage.setItem(STORAGE_KEY, toYm(p));
      } catch {
        /* segue sem persistir */
      }
    }

    const now = currentPeriod();
    return {
      period,
      setPeriod,
      ym: toYm(period),
      label: formatPeriod(period),
      isCurrent: period.year === now.year && period.month === now.month,
      shift: (delta) => setPeriod(shiftPeriod(period, delta)),
      goToCurrent: () => setPeriod(now),
    };
  }, [period]);

  return <PeriodContext.Provider value={value}>{children}</PeriodContext.Provider>;
}

export function usePeriod(): PeriodValue {
  const ctx = useContext(PeriodContext);
  if (!ctx) throw new Error("usePeriod precisa estar dentro de <PeriodProvider>");
  return ctx;
}
