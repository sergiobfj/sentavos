import { useMemo, useState } from "react";
import Modal from "./Modal";
import ConfirmDialog from "./ConfirmDialog";
import CategoryPicker from "./CategoryPicker";
import {
  useCreateTransaction,
  useDeleteTransaction,
  useUpdateTransaction,
} from "../lib/queries";
import { usePeriod } from "../lib/period";
import { ApiError } from "../lib/api";
import { formatDiaMes, formatMoney, parseMoney, todayIso } from "../lib/format";
import type { Category, CategoryType, Transaction } from "../lib/types";

// Tres tipos, os mesmos que a categoria ja tinha. Os rotulos sao os do dia a
// dia -- "Saida" e nao "Despesa", porque e a palavra que se usa ao lancar.
const TIPOS: { valor: CategoryType; rotulo: string; cor: string }[] = [
  { valor: "expense", rotulo: "Saída", cor: "var(--neg)" },
  { valor: "income", rotulo: "Entrada", cor: "var(--pos)" },
  { valor: "investment", rotulo: "Investir", cor: "var(--inv)" },
];

export default function TransactionForm({
  categories,
  transaction,
  onClose,
}: {
  categories: Category[];
  transaction?: Transaction;
  onClose: () => void;
}) {
  const isEdit = !!transaction;

  // Editando, o tipo vem da categoria que ja estava no lancamento. Criando, o
  // padrao e saida: e o que se lanca dez vezes mais que entrada.
  const tipoInicial: CategoryType =
    categories.find((c) => c.id === transaction?.category_id)?.type ?? "expense";
  const [tipo, setTipo] = useState<CategoryType>(tipoInicial);

  const [form, setForm] = useState({
    date: transaction?.date ?? todayIso(),
    description: transaction?.description ?? "",
    category_id: (transaction?.category_id ?? null) as number | null,
    amount_planned: transaction?.amount_planned?.toString() ?? "",
    amount_paid: transaction?.amount_paid?.toString() ?? "",
    note: transaction?.note ?? "",
  });

  const ativas = useMemo(() => categories.filter((c) => !c.archived), [categories]);

  // Trocar de tipo limpa a categoria escolhida se ela nao pertence ao novo
  // tipo. Sem isso daria pra sair com "Saida" selecionado e a categoria
  // "Salario" salva -- um lancamento que contaria como receita e apareceria
  // como despesa na tela.
  function trocarTipo(novo: CategoryType) {
    setTipo(novo);
    const atual = categories.find((c) => c.id === form.category_id);
    if (!atual || atual.type !== novo) {
      const primeira = ativas.find((c) => c.type === novo);
      setForm((f) => ({ ...f, category_id: primeira?.id ?? null }));
    }
  }
  const { setPeriod } = usePeriod();
  const create = useCreateTransaction();
  const update = useUpdateTransaction();
  const pending = create.isPending || update.isPending;
  const err = (create.error || update.error) as ApiError | null;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const payload = {
      date: form.date,
      description: form.description.trim(),
      category_id: Number(form.category_id),
      amount_planned: parseMoney(form.amount_planned),
      amount_paid: parseMoney(form.amount_paid),
      note: form.note.trim() || null,
    };
    // Salvar um lançamento de outro mês some da lista e parece que falhou;
    // então o app acompanha a data que foi salva.
    function onSaved() {
      const [y, m] = payload.date.split("-").map(Number);
      if (y && m) setPeriod({ year: y, month: m });
      onClose();
    }

    if (isEdit) {
      update.mutate({ id: transaction!.id, data: payload }, { onSuccess: onSaved });
    } else {
      create.mutate(payload, { onSuccess: onSaved });
    }
  }

  return (
    <Modal
      title={isEdit ? "Editar transação" : "Nova transação"}
      onClose={onClose}
      footer={
        <>
          {/* Editando, o "Cancelar" dá lugar ao "Excluir". Ele saiu da linha da
              lista porque lá ficava a um toque do próprio lançamento — e no
              celular, um botão de apagar encostado no alvo que se quer tocar é
              um acidente esperando acontecer. Fechar, aqui, é tocar fora. */}
          {isEdit ? (
            <ExcluirTransacao transacao={transaction!} onDone={onClose} />
          ) : (
            <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          )}
          <button type="submit" form="tx-form" className="btn btn-primary" disabled={pending || !form.description.trim() || !form.category_id}>
            {pending ? "Salvando…" : "Salvar"}
          </button>
        </>
      }
    >
      <form id="tx-form" className="m-body" onSubmit={submit}>
        {/* O tipo vem primeiro porque ele estreita todo o resto: escolhido
            "Saida", o seletor de categoria ja abre so com as de saida. Pedir a
            categoria antes obrigaria a procurar "Mercado" numa lista que
            tambem tem "Salario". */}
        <div className="field">
          <label>Tipo</label>
          <div className="tipo-toggle" role="group" aria-label="Tipo do lançamento">
            {TIPOS.map(({ valor, rotulo, cor }) => (
              <button
                type="button"
                key={valor}
                className={tipo === valor ? "on" : ""}
                style={tipo === valor ? { color: cor, borderColor: cor } : undefined}
                onClick={() => trocarTipo(valor)}
                aria-pressed={tipo === valor}
              >
                {rotulo}
              </button>
            ))}
          </div>
        </div>

        <div className="field">
          <label htmlFor="t-desc">Descrição</label>
          <input id="t-desc" value={form.description} autoFocus placeholder="Ex.: Conta de luz"
            onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </div>

        <div className="field">
          <label>Categoria</label>
          <CategoryPicker
            categories={ativas}
            tipo={tipo}
            valor={form.category_id}
            aoEscolher={(id) => setForm({ ...form, category_id: id })}
          />
        </div>

        <div className="field">
          <label htmlFor="t-date">Data</label>
          <input id="t-date" type="date" value={form.date}
            onChange={(e) => setForm({ ...form, date: e.target.value })} />
        </div>
        <div className="field row2">
          <div className="field">
            <label htmlFor="t-planned">Previsto</label>
            <input id="t-planned" inputMode="decimal" value={form.amount_planned} placeholder="0,00"
              onChange={(e) => setForm({ ...form, amount_planned: e.target.value })} />
          </div>
          <div className="field">
            <label htmlFor="t-paid">{tipo === "income" ? "Recebido" : "Pago"}</label>
            <input id="t-paid" inputMode="decimal" value={form.amount_paid} placeholder="0,00"
              onChange={(e) => setForm({ ...form, amount_paid: e.target.value })} />
          </div>
        </div>
        <div className="field">
          <label htmlFor="t-note">Observação</label>
          <textarea id="t-note" value={form.note} placeholder="Opcional"
            onChange={(e) => setForm({ ...form, note: e.target.value })} />
        </div>
        {err && <div className="error-box" style={{ padding: 0, textAlign: "left" }}>{err.message}</div>}
      </form>
    </Modal>
  );
}

function ExcluirTransacao({
  transacao,
  onDone,
}: {
  transacao: Transaction;
  onDone: () => void;
}) {
  const [confirmando, setConfirmando] = useState(false);
  const del = useDeleteTransaction();

  // O valor entra na confirmação porque é ele que identifica o lançamento
  // quando a descrição se repete — três "Futebol" no mês, só um de R$ 26,00.
  const valor = transacao.amount_paid ?? transacao.amount_planned;
  const consequencias = [
    // Com o sinal, não em módulo: num lançamento de −R$ 500 (a retirada que
    // anula um aporte), dizer "R$ 500,00 sai das somas" inverte o efeito —
    // apagá-lo faz o total SUBIR 500.
    valor != null
      ? `O lançamento de ${formatMoney(valor)} em ${formatDiaMes(transacao.date)} deixa de contar.`
      : "O lançamento sai da lista do mês.",
  ];

  return (
    <>
      <button
        type="button"
        className="btn btn-danger"
        disabled={del.isPending}
        onClick={() => setConfirmando(true)}
      >
        Excluir
      </button>

      {confirmando && (
        <ConfirmDialog
          title="Excluir lançamento"
          itemName={transacao.description}
          consequences={consequencias}
          pending={del.isPending}
          error={(del.error as ApiError | null)?.message ?? null}
          onCancel={() => setConfirmando(false)}
          onConfirm={() => del.mutate(transacao.id, { onSuccess: onDone })}
        />
      )}
    </>
  );
}
