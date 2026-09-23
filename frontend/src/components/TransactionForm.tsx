import { useMemo, useState } from "react";
import Modal from "./Modal";
import ConfirmDialog from "./ConfirmDialog";
import CategoryPicker from "./CategoryPicker";
import CardPicker from "./CardPicker";
import PurchaseForm from "./PurchaseForm";
import {
  useCards,
  useCreatePurchase,
  useCreateTransaction,
  useDefinirForma,
  useDeleteTransaction,
  useUpdateTransaction,
} from "../lib/queries";
import { usePeriod } from "../lib/period";
import { ApiError } from "../lib/api";
import {
  dividirEmParcelas,
  formatDiaMes,
  formatMesPorExtenso,
  formatMoney,
  parseMoney,
  todayIso,
} from "../lib/format";
import {
  ehParcela,
  type Category,
  type CategoryType,
  type PaymentMethod,
  type Transaction,
} from "../lib/types";

// Tres tipos, os mesmos que a categoria ja tinha. Os rotulos sao os do dia a
// dia -- "Saida" e nao "Despesa", porque e a palavra que se usa ao lancar.
const TIPOS: { valor: CategoryType; rotulo: string; cor: string }[] = [
  { valor: "expense", rotulo: "Saída", cor: "var(--neg)" },
  { valor: "income", rotulo: "Entrada", cor: "var(--pos)" },
  { valor: "investment", rotulo: "Investir", cor: "var(--inv)" },
];

// Até 12 cabem em duas fileiras de chips no celular; 18 e 24 existem porque
// aparecem em eletrônico e passagem, e sem eles a opção seria digitar.
const PARCELAS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 18, 24];

export default function TransactionForm({
  categories,
  transaction,
  onClose,
}: {
  categories: Category[];
  transaction?: Transaction;
  onClose: () => void;
}) {
  // Parcela não se edita sozinha: as N somam o valor da compra, e mexer numa
  // faria a fatura discordar do total. A tela abre a COMPRA, onde a alteração
  // tem o escopo certo — e as quatro telas que abrem este formulário não
  // precisam saber disso.
  if (transaction && ehParcela(transaction)) {
    return (
      <PurchaseForm
        purchaseId={transaction.purchase_id!}
        categories={categories}
        onClose={onClose}
      />
    );
  }
  return <Lancamento categories={categories} transaction={transaction} onClose={onClose} />;
}

function Lancamento({
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

  // Criando, o padrão é à vista. Editando um lançamento antigo (sem forma
  // definida), nada vem marcado: marcar "à vista" sozinho seria responder por
  // ele uma pergunta que o app não sabe responder.
  const [forma, setForma] = useState<PaymentMethod | null>(
    isEdit ? transaction!.payment_method : "cash"
  );
  const [cardId, setCardId] = useState<number | null>(null);
  const [parcelas, setParcelas] = useState(1);

  const [form, setForm] = useState({
    date: transaction?.date ?? todayIso(),
    description: transaction?.description ?? "",
    category_id: (transaction?.category_id ?? null) as number | null,
    amount_planned: transaction?.amount_planned?.toString() ?? "",
    amount_paid: transaction?.amount_paid?.toString() ?? "",
    note: transaction?.note ?? "",
  });

  const ativas = useMemo(() => categories.filter((c) => !c.archived), [categories]);
  const { data: cards } = useCards();

  // Trocar de tipo limpa a categoria escolhida se ela nao pertence ao novo
  // tipo. Sem isso dava pra sair com "Saida" selecionado e a categoria
  // "Salario" salva -- um lancamento que contaria como receita e apareceria
  // como despesa na tela.
  function trocarTipo(novo: CategoryType) {
    setTipo(novo);
    // Cartão só existe pra saída: entrada e investimento não passam por fatura.
    if (novo !== "expense" && forma === "credit") setForma("cash");
    const atual = categories.find((c) => c.id === form.category_id);
    if (!atual || atual.type !== novo) {
      const primeira = ativas.find((c) => c.type === novo);
      setForm((f) => ({ ...f, category_id: primeira?.id ?? null }));
    }
  }

  const { setPeriod } = usePeriod();
  const create = useCreateTransaction();
  const update = useUpdateTransaction();
  const criarCompra = useCreatePurchase();
  const definirForma = useDefinirForma();

  const pending =
    create.isPending || update.isPending || criarCompra.isPending || definirForma.isPending;
  const err = (create.error ||
    update.error ||
    criarCompra.error ||
    definirForma.error) as ApiError | null;

  const noCartao = tipo === "expense" && forma === "credit";
  const valorDaCompra = parseMoney(form.amount_paid) ?? 0;

  // A prévia usa a mesma regra do servidor, mas quem decide é ele: o valor que
  // vale é o que volta depois de salvar.
  const previa = noCartao && valorDaCompra > 0 ? dividirEmParcelas(valorDaCompra, parcelas) : [];
  const [ano, mes] = form.date.split("-").map(Number);

  function irParaOMesSalvo(dataIso: string) {
    const [y, m] = dataIso.split("-").map(Number);
    if (y && m) setPeriod({ year: y, month: m });
    onClose();
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();

    // ---------- Compra nova no cartão ----------
    if (noCartao && !isEdit) {
      criarCompra.mutate(
        {
          card_id: cardId!,
          category_id: Number(form.category_id),
          description: form.description.trim(),
          total_amount: valorDaCompra,
          installments: parcelas,
          purchase_date: form.date,
          note: form.note.trim() || null,
        },
        { onSuccess: () => irParaOMesSalvo(form.date) }
      );
      return;
    }

    const payload = {
      date: form.date,
      description: form.description.trim(),
      category_id: Number(form.category_id),
      amount_planned: parseMoney(form.amount_planned),
      amount_paid: parseMoney(form.amount_paid),
      note: form.note.trim() || null,
      // Entrada e investimento são dinheiro que se move na hora; só despesa
      // pode ficar pendurada numa fatura.
      payment_method: (tipo === "expense" ? forma : "cash") as PaymentMethod | null,
    };

    if (!isEdit) {
      create.mutate(payload, { onSuccess: () => irParaOMesSalvo(payload.date) });
      return;
    }

    // ---------- Editando ----------
    // Passar um lançamento existente PRA o cartão não é um PATCH: ele precisa
    // virar compra, ganhar parcelas e entrar numa fatura. Quem faz isso é a
    // rota de forma de pagamento, e ela roda depois de o resto ser salvo.
    const viraCartao = noCartao && transaction!.payment_method !== "credit";
    update.mutate(
      { id: transaction!.id, data: viraCartao ? { ...payload, payment_method: undefined } : payload },
      {
        onSuccess: () => {
          if (!viraCartao) return irParaOMesSalvo(payload.date);
          definirForma.mutate(
            {
              id: transaction!.id,
              metodo: "credit",
              card_id: cardId!,
              installments: parcelas,
            },
            { onSuccess: () => irParaOMesSalvo(payload.date) }
          );
        },
      }
    );
  }

  const faltaCartao = noCartao && (cardId == null || valorDaCompra <= 0);

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
          <button
            type="submit"
            form="tx-form"
            className="btn btn-primary"
            disabled={pending || !form.description.trim() || !form.category_id || faltaCartao}
          >
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
          <label htmlFor="t-date">{noCartao ? "Data da compra" : "Data"}</label>
          <input id="t-date" type="date" value={form.date}
            onChange={(e) => setForm({ ...form, date: e.target.value })} />
        </div>

        {/* ---------- Forma de pagamento ----------
            Só pra saída: entrada e investimento não passam por fatura. Não se
            chama "Tipo" porque a palavra já é de Saída/Entrada/Investir, e ter
            dois "Tipo" na mesma tela é como não ter nenhum. */}
        {tipo === "expense" && (
          <div className="field">
            <label>Pagamento</label>
            <div className="tipo-toggle" role="group" aria-label="Forma de pagamento">
              <button
                type="button"
                className={forma === "cash" ? "on" : ""}
                onClick={() => setForma("cash")}
                aria-pressed={forma === "cash"}
              >
                À vista
              </button>
              <button
                type="button"
                className={forma === "credit" ? "on" : ""}
                onClick={() => setForma("credit")}
                aria-pressed={forma === "credit"}
              >
                Cartão
              </button>
            </div>
            {forma === null && (
              <div className="hint">
                Este lançamento é anterior ao cartão e ainda não tem forma de
                pagamento. Até você responder, ele conta como saída da conta.
              </div>
            )}
          </div>
        )}

        {noCartao && (
          <>
            <div className="field">
              <label>Cartão</label>
              <CardPicker cards={cards ?? []} valor={cardId} aoEscolher={setCardId} />
            </div>

            <div className="field">
              <label>Parcelas</label>
              <div className="chip-linha" role="group" aria-label="Número de parcelas">
                {PARCELAS.map((n) => (
                  <button
                    type="button"
                    key={n}
                    className={n === parcelas ? "on" : ""}
                    onClick={() => setParcelas(n)}
                    aria-pressed={n === parcelas}
                  >
                    {n}x
                  </button>
                ))}
              </div>
            </div>
          </>
        )}

        {/* No cartão, "Previsto" sai em vez de ficar cinza: compra já
            aconteceu, e um campo desabilitado ao lado do valor faz procurar o
            que se perdeu. O que sobra é o valor da compra, em largura inteira. */}
        <div className={noCartao ? "field" : "field row2"}>
          {!noCartao && (
            <div className="field">
              <label htmlFor="t-planned">Previsto</label>
              <input id="t-planned" inputMode="decimal" value={form.amount_planned} placeholder="0,00"
                onChange={(e) => setForm({ ...form, amount_planned: e.target.value })} />
            </div>
          )}
          <div className="field">
            <label htmlFor="t-paid">
              {noCartao ? "Valor total da compra" : tipo === "income" ? "Recebido" : "Pago"}
            </label>
            <input id="t-paid" inputMode="decimal" value={form.amount_paid} placeholder="0,00"
              onChange={(e) => setForm({ ...form, amount_paid: e.target.value })} />
          </div>
        </div>

        {/* A conta na frente de quem lança, antes de salvar: quanto fica cada
            parcela, quando começa e em qual fatura cai. */}
        {previa.length > 0 && ano && mes && (
          <div className="aviso-box">
            {parcelas === 1 ? (
              <>Uma parcela de <b>{formatMoney(previa[0])}</b> em {formatMesPorExtenso(ano, mes)}.</>
            ) : (
              <>
                {parcelas} parcelas de <b>{formatMoney(previa[1])}</b>
                {previa[0] !== previa[1] && <> (a 1ª de {formatMoney(previa[0])})</>}
                {" · "}1ª em {formatMesPorExtenso(ano, mes)}
              </>
            )}
            <div style={{ marginTop: "var(--s2)", color: "var(--text-faint)" }}>
              O dinheiro só sai da conta quando você pagar a fatura.
            </div>
          </div>
        )}

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
