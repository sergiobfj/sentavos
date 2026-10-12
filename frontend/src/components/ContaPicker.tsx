import { useAccounts } from "../lib/queries";
import type { FinancialAccount } from "../lib/tiposContas";

/** De qual conta saiu (ou em qual entrou). Botões lado a lado, como o cartão:
 *  são poucas contas, de nome curto. "Sem conta" é uma resposta válida — o
 *  lançamento continua valendo, só não entra no saldo de conta nenhuma.
 *
 *  O saldo agregado (conta de reconciliação) não aparece: ele é um total
 *  esperando divisão, não um lugar onde se gasta. */
export default function ContaPicker({
  valor,
  aoEscolher,
  rotulo = "Conta",
}: {
  valor: number | null;
  aoEscolher: (id: number | null) => void;
  rotulo?: string;
}) {
  const { data } = useAccounts();
  const contas = (data ?? []).filter((c: FinancialAccount) => c.type !== "reconciliation");
  if (contas.length === 0) return null;
  return (
    <div className="field">
      <span className="label">{rotulo}</span>
      <div className="chip-linha" role="group" aria-label={rotulo}>
        {contas.map((c) => (
          <button
            type="button"
            key={c.id}
            className={c.id === valor ? "on" : ""}
            onClick={() => aoEscolher(c.id)}
            aria-pressed={c.id === valor}
          >
            {c.name}
          </button>
        ))}
        <button type="button" className={valor == null ? "on" : ""} onClick={() => aoEscolher(null)} aria-pressed={valor == null}>
          Sem conta
        </button>
      </div>
    </div>
  );
}
