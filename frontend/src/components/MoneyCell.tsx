import { useEffect, useState } from "react";
import { parseMoney } from "../lib/format";

// Campo de dinheiro editável dentro de uma tabela: digita, sai do campo, salva.
// Usado pela meta do Orçamento e pelo saldo do Patrimônio — as duas telas têm
// a mesma armadilha (trocar o mês tem que recarregar o valor salvo), então ela
// fica resolvida num lugar só.

export default function MoneyCell({
  saved,
  ariaLabel,
  placeholder = "0,00",
  pending = false,
  onCommit,
}: {
  // Valor já gravado, ou null quando não existe registro para este período.
  saved: number | null;
  ariaLabel: string;
  placeholder?: string;
  pending?: boolean;
  onCommit: (amount: number | null) => void;
}) {
  const savedText = saved != null ? String(saved).replace(".", ",") : "";
  const [value, setValue] = useState(savedText);

  // Trocar de mês remonta a linha com outro valor salvo; sem isso o input
  // continuaria mostrando o que foi digitado no mês anterior.
  useEffect(() => setValue(savedText), [savedText]);

  function commit() {
    const amount = parseMoney(value);
    // Campo vazio e nada gravado: não há o que salvar.
    if (amount === null && saved == null) {
      setValue("");
      return;
    }
    if (amount === saved) return;
    onCommit(amount);
  }

  return (
    <input
      className="money-cell"
      inputMode="decimal"
      placeholder={placeholder}
      aria-label={ariaLabel}
      value={value}
      disabled={pending}
      onChange={(e) => setValue(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
        if (e.key === "Escape") setValue(savedText);
      }}
    />
  );
}
