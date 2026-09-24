import { useEffect, useState } from "react";
import Modal from "./Modal";
import ConfirmDialog from "./ConfirmDialog";
import CategoryPicker from "./CategoryPicker";
import Segmentado from "./Segmentado";
import { OPCOES_FINALIDADE } from "../lib/finalidade";
import { useDeletePurchase, usePurchase, useUpdatePurchase } from "../lib/queries";
import { ApiError } from "../lib/api";
import { formatDate, formatMoney } from "../lib/format";
import type { Category, Finalidade } from "../lib/types";

/** A compra no cartão, aberta a partir de qualquer uma das suas parcelas.
 *
 * Tocar na parcela 2 de 3 e poder mudar só ela pareceria natural e estaria
 * errado: as três somam R$ 900, e alterar uma faria a soma deixar de ser a
 * compra. Então a tela sobe um nível — o que se edita é a compra inteira, e
 * todas as parcelas andam juntas.
 *
 * Depois que uma fatura da compra é paga, valor, parcelas, cartão e data
 * travam. Não é zelo: mudar qualquer um deles reescreveria uma fatura que já
 * foi cobrada, e o extrato do banco não se reescreve junto. O que continua
 * livre é rótulo — descrição, categoria e observação não mexem em dinheiro.
 */
export default function PurchaseForm({
  purchaseId,
  categories,
  onClose,
}: {
  purchaseId: number;
  categories: Category[];
  onClose: () => void;
}) {
  const { data: compra, isLoading } = usePurchase(purchaseId);
  const update = useUpdatePurchase();
  const [confirmando, setConfirmando] = useState(false);

  const [form, setForm] = useState({
    description: "",
    category_id: 0,
    note: "",
    finalidade: null as Finalidade | null,
  });

  // O formulário só pode nascer depois que a compra chega. Sem isto, os campos
  // ficariam vazios e salvar apagaria a descrição.
  useEffect(() => {
    if (compra) {
      setForm({
        description: compra.description,
        category_id: compra.category_id,
        note: compra.note ?? "",
        finalidade: compra.finalidade,
      });
    }
  }, [compra]);

  if (isLoading || !compra) {
    return (
      <Modal title="Compra no cartão" onClose={onClose}>
        <div className="m-body">
          <div className="skel" style={{ height: 160 }} />
        </div>
      </Modal>
    );
  }

  const parcelado = compra.installments > 1;
  const restam = compra.installments - compra.paid_installments;

  return (
    <Modal
      title="Compra no cartão"
      onClose={onClose}
      footer={
        <>
          <ExcluirCompra
            compra={compra}
            onDone={onClose}
            confirmando={confirmando}
            setConfirmando={setConfirmando}
          />
          <button
            type="submit"
            form="compra-form"
            className="btn btn-primary"
            disabled={update.isPending || !form.description.trim()}
          >
            {update.isPending ? "Salvando…" : "Salvar"}
          </button>
        </>
      }
    >
      <form
        id="compra-form"
        className="m-body"
        onSubmit={(e) => {
          e.preventDefault();
          update.mutate(
            {
              id: compra.id,
              data: {
                description: form.description.trim(),
                category_id: form.category_id,
                note: form.note.trim() || null,
                // Todas as parcelas recebem a mesma — o servidor reescreve as N.
                ...(form.finalidade ? { finalidade: form.finalidade } : {}),
              },
            },
            { onSuccess: onClose }
          );
        }}
      >
        {/* O contexto primeiro: quem abriu uma parcela quer saber de que compra
            ela é antes de qualquer outra coisa. */}
        <div className="resumo-compra">
          <div className="linha">
            <span>Compra total</span>
            <b className="tnum">{formatMoney(compra.total_amount)}</b>
          </div>
          {parcelado && (
            <div className="linha">
              <span>Parcelas</span>
              <b className="tnum">
                {compra.installments}× de {formatMoney(compra.installment_amounts[1])}
              </b>
            </div>
          )}
          <div className="linha">
            <span>Cartão</span>
            <b>{compra.card_name}</b>
          </div>
          <div className="linha">
            <span>Data da compra</span>
            <b>{formatDate(compra.purchase_date)}</b>
          </div>
          {parcelado && (
            <div className="linha">
              <span>{compra.paid_installments > 0 ? "Já em fatura paga" : "Restam"}</span>
              <b>
                {compra.paid_installments > 0
                  ? `${compra.paid_installments} de ${compra.installments}`
                  : `${restam} parcela${restam > 1 ? "s" : ""}`}
              </b>
            </div>
          )}
        </div>

        {compra.locked && (
          <div className="aviso-box" style={{ marginBottom: "var(--s4)" }}>
            Uma fatura desta compra já foi paga, então <b>valor, parcelas, cartão
            e data não mudam mais</b> — alterar reescreveria uma fatura que já foi
            cobrada. Descrição, categoria e observação continuam livres.
            <div style={{ marginTop: "var(--s2)", color: "var(--text-faint)" }}>
              Se a compra não existiu mesmo, desfaça o pagamento da fatura primeiro.
            </div>
          </div>
        )}

        <div className="field">
          <label htmlFor="c-desc">Descrição</label>
          <input
            id="c-desc"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </div>

        <div className="field">
          <label>Categoria</label>
          <CategoryPicker
            categories={categories.filter((c) => !c.archived)}
            tipo="expense"
            valor={form.category_id}
            aoEscolher={(id) => setForm({ ...form, category_id: id })}
          />
        </div>

        {/* Finalidade é rótulo, como a categoria: continua editável depois
            da fatura paga, porque não muda quanto nenhuma fatura cobra. */}
        <div className="field">
          <span className="label">Finalidade</span>
          <Segmentado
            rotulo="Finalidade"
            opcoes={OPCOES_FINALIDADE}
            valor={form.finalidade}
            aoEscolher={(f) => setForm({ ...form, finalidade: f })}
            largo
          />
          {compra.installments > 1 && (
            <div className="hint">Vale para as {compra.installments} parcelas.</div>
          )}
        </div>

        <div className="field">
          <label htmlFor="c-note">Observação</label>
          <textarea
            id="c-note"
            value={form.note}
            placeholder="Opcional"
            onChange={(e) => setForm({ ...form, note: e.target.value })}
          />
        </div>

        {update.error && (
          <div className="error-box" style={{ padding: 0, textAlign: "left" }}>
            {(update.error as ApiError).message}
          </div>
        )}
      </form>
    </Modal>
  );
}

function ExcluirCompra({
  compra,
  onDone,
  confirmando,
  setConfirmando,
}: {
  compra: { id: number; description: string; installments: number; locked: boolean };
  onDone: () => void;
  confirmando: boolean;
  setConfirmando: (v: boolean) => void;
}) {
  const del = useDeletePurchase();

  const consequencias =
    compra.installments > 1
      ? [
          `As ${compra.installments} parcelas somem, em todos os meses em que aparecem.`,
          "As faturas que ficarem sem nenhum item saem junto.",
        ]
      : ["A parcela sai da fatura e do gasto do mês."];

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
          title="Excluir compra"
          itemName={compra.description}
          consequences={consequencias}
          pending={del.isPending}
          error={(del.error as ApiError | null)?.message ?? null}
          onCancel={() => setConfirmando(false)}
          onConfirm={() => del.mutate(compra.id, { onSuccess: onDone })}
        />
      )}
    </>
  );
}
