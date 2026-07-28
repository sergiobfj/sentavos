import { currentPeriod, usePeriod } from "../lib/period";

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

export default function MonthPicker() {
  const { period, setPeriod, shift, isCurrent, goToCurrent } = usePeriod();

  // Set garante que um ano vindo do localStorage fora da faixa ainda apareça
  // na lista — select com value fora das options faz o React reclamar.
  const thisYear = currentPeriod().year;
  const years = new Set<number>([period.year]);
  for (let y = thisYear - 5; y <= thisYear + 1; y++) years.add(y);

  return (
    <div className="month-picker">
      <button className="btn btn-ghost btn-sm" onClick={() => shift(-1)} aria-label="Mês anterior">
        ‹
      </button>

      <select
        aria-label="Mês"
        value={period.month}
        onChange={(e) => setPeriod({ ...period, month: Number(e.target.value) })}
      >
        {MESES.map((m, i) => (
          <option key={m} value={i + 1}>
            {m}
          </option>
        ))}
      </select>

      <select
        aria-label="Ano"
        value={period.year}
        onChange={(e) => setPeriod({ ...period, year: Number(e.target.value) })}
      >
        {[...years]
          .sort((a, b) => b - a)
          .map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
      </select>

      <button className="btn btn-ghost btn-sm" onClick={() => shift(1)} aria-label="Próximo mês">
        ›
      </button>

      {!isCurrent && (
        <button className="btn btn-ghost btn-sm" onClick={goToCurrent}>
          Hoje
        </button>
      )}
    </div>
  );
}
