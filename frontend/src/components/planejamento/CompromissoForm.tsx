import { useMemo, useState } from "react";
import Modal from "../Modal";
import ConfirmDialog from "../ConfirmDialog";
import CategoryPicker from "../CategoryPicker";
import Segmentado from "../Segmentado";
import { OPCOES_FINALIDADE } from "../../lib/finalidade";
import { NATUREZA_DICA, OPCOES_NATUREZA } from "../../lib/natureza";
import {
  useCategories,
  useCreateCommitment,
  useDeleteCommitment,
  useUpdateCommitment,
} from "../../lib/queries";
import { ApiError } from "../../lib/api";
import { formatMesPorExtenso, formatMoney, parseMoney, todayIso } from "../../lib/format";
import type { Finalidade, Natureza } from "../../lib/types";
import type { CommitmentCreate, CommitmentDetail } from "../../lib/tiposPlanejamento";

const PERIODOS = [
  { valor: "1", rotulo: "Mensal" },
  { valor: "2", rotulo: "Bimestral" },
  { valor: "3", rotulo: "Trimestral" },
  { valor: "6", rotulo: "Semestral" },
  { valor: "12", rotulo: "Anual" },
];

type Repeticao = "parcelado" | "recorrente";

/** Cadastra ou edita um compromisso fora do cartão.
 *
 *  Parcelado (financiamento, parcelado direto, conta única) ou recorrente
 *  (academia, internet, o salário). O cronograma é calculado no servidor; a
 *  prévia aqui só ajuda a conferir antes de salvar.
 *
 *  `aoSalvar` existe pra conferência do mês: ela usa o mesmo formulário, mas
 *  cria o compromisso e resolve o item numa chamada só. */
export default function CompromissoForm({
  compromisso,
  inicial,
  titulo,
  aoSalvar,
  pendenteExterno = false,
  erroExterno = null,
  onClose,
}: {
  compromisso?: CommitmentDetail;
  inicial?: Partial<CommitmentCreate> & { direction?: "saida" | "entrada" };
  titulo?: string;
  aoSalvar?: (dados: CommitmentCreate) => void;
  pendenteExterno?: boolean;
  erroExterno?: string | null;
  onClose: () => void;
}) {
  const editando = !!compromisso;
  const base = compromisso ?? inicial ?? {};
  const { data: categorias } = useCategories();

  const [tipo, setTipo] = useState<"expense" | "income">(
    (compromisso?.direction ?? inicial?.direction) === "entrada" ? "income" : "expense"
  );
  const [descricao, setDescricao] = useState(base.description ?? "");
  const [categoria, setCategoria] = useState<number | null>(base.category_id ?? null);
  const [valor, setValor] = useState(base.amount != null ? String(base.amount).replace(".", ",") : "");
  const [repeticao, setRepeticao] = useState<Repeticao>(
    base.installments != null ? "parcelado" : editando || inicial?.installments === null ? "recorrente" : "parcelado"
  );
  const [parcelas, setParcelas] = useState(String(base.installments ?? 1));
  const [fim, setFim] = useState(base.end_date ?? "");
  const [primeira, setPrimeira] = useState(base.first_due ?? todayIso());
  const [intervalo, setIntervalo] = useState(String(base.interval_months ?? 1));
  const [confirmado, setConfirmado] = useState<"sim" | "nao">(base.confirmed === false ? "nao" : "sim");
  const [finalidade, setFinalidade] = useState<Finalidade>((base.finalidade as Finalidade) ?? "pessoal");
  // Nula = a da categoria. Financiamento é financeiro: fica fora do custo de vida.
  const [natureza, setNatureza] = useState<Natureza | null>((base.nature as Natureza | null) ?? null);
  const [instituicao, setInstituicao] = useState(base.institution ?? "");
  const [total, setTotal] = useState(base.total_amount != null ? String(base.total_amount).replace(".", ",") : "");
  const [entrada, setEntrada] = useState(base.down_payment != null ? String(base.down_payment).replace(".", ",") : "");
  const [meio, setMeio] = useState(base.payment_hint ?? "");
  const [nota, setNota] = useState(base.note ?? "");
  const [apagando, setApagando] = useState(false);

  const criar = useCreateCommitment();
  const atualizar = useUpdateCommitment();
  const excluir = useDeleteCommitment();

  const numero = parseMoney(valor) ?? 0;
  const n = Math.max(1, Math.floor(Number(parcelas) || 1));
  const passo = Number(intervalo) || 1;

  // A prévia do que o servidor vai calcular: quantas, quanto, até quando.
  const previa = useMemo(() => {
    if (repeticao !== "parcelado" || numero <= 0 || !primeira) return null;
    const [a, m] = primeira.split("-").map(Number);
    const i = a * 12 + (m - 1) + (n - 1) * passo;
    return {
      nominal: Math.round(numero * n * 100) / 100,
      ultima: formatMesPorExtenso(Math.floor(i / 12), (i % 12) + 1),
    };
  }, [repeticao, numero, primeira, n, passo]);

  function montar(): CommitmentCreate {
    return {
      description: descricao.trim(),
      category_id: categoria!,
      amount: numero,
      first_due: primeira,
      installments: repeticao === "parcelado" ? n : null,
      interval_months: passo,
      end_date: repeticao === "recorrente" && fim ? fim : null,
      confirmed: confirmado === "sim",
      finalidade: tipo === "expense" ? finalidade : null,
      nature: tipo === "expense" ? natureza : null,
      institution: instituicao.trim() || null,
      total_amount: parseMoney(total),
      down_payment: parseMoney(entrada),
      payment_hint: meio.trim() || null,
      note: nota.trim() || null,
    };
  }

  function enviar(e: React.FormEvent) {
    e.preventDefault();
    const dados = montar();
    if (aoSalvar) return aoSalvar(dados);
    if (editando) {
      atualizar.mutate({ id: compromisso!.id, data: dados }, { onSuccess: onClose });
    } else {
      criar.mutate(dados, { onSuccess: onClose });
    }
  }

  const pendente = pendenteExterno || criar.isPending || atualizar.isPending;
  const erro = erroExterno ?? ((criar.error || atualizar.error) as ApiError | null)?.message ?? null;
  const pronto = descricao.trim() && categoria != null && numero > 0 && primeira;

  return (
    <Modal
      title={titulo ?? (editando ? "Editar compromisso" : "Novo compromisso")}
      onClose={onClose}
      footer={
        <>
          {editando ? (
            <button type="button" className="btn btn-danger" onClick={() => setApagando(true)}>Excluir</button>
          ) : (
            <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          )}
          <button type="submit" form="compromisso-form" className="btn btn-primary" disabled={!pronto || pendente}>
            {pendente ? "Salvando…" : "Salvar"}
          </button>
        </>
      }
    >
      <form id="compromisso-form" className="m-body" onSubmit={enviar}>
        <div className="field">
          <div className="tipo-toggle" role="group" aria-label="Direção">
            {(["expense", "income"] as const).map((t) => (
              <button
                type="button"
                key={t}
                className={tipo === t ? "on" : ""}
                aria-pressed={tipo === t}
                onClick={() => {
                  setTipo(t);
                  const atual = categorias?.find((c) => c.id === categoria);
                  if (atual && atual.type !== t) setCategoria(null);
                }}
              >
                {t === "expense" ? "A pagar" : "A receber"}
              </button>
            ))}
          </div>
        </div>

        <div className="field">
          <label htmlFor="c-desc">Descrição</label>
          <input id="c-desc" autoFocus={!editando} maxLength={80} value={descricao}
            placeholder={tipo === "expense" ? "Ex.: Financiamento, Academia" : "Ex.: Salário"}
            onChange={(e) => setDescricao(e.target.value)} />
        </div>

        <div className="field">
          <label>Categoria</label>
          <CategoryPicker categories={categorias ?? []} tipo={tipo} valor={categoria} aoEscolher={setCategoria} />
        </div>

        <div className="row2">
          <div className="field">
            <label htmlFor="c-valor">{repeticao === "parcelado" ? "Valor da parcela" : "Valor de cada vez"}</label>
            <input id="c-valor" inputMode="decimal" placeholder="0,00" value={valor} onChange={(e) => setValor(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="c-primeira">{repeticao === "parcelado" ? "1ª parcela" : "Começa em"}</label>
            <input id="c-primeira" type="date" value={primeira} onChange={(e) => setPrimeira(e.target.value)} />
          </div>
        </div>

        <div className="field">
          <Segmentado
            rotulo="Repetição"
            largo
            opcoes={[
              { valor: "parcelado", rotulo: "Parcelado" },
              { valor: "recorrente", rotulo: "Recorrente" },
            ]}
            valor={repeticao}
            aoEscolher={(v: Repeticao) => setRepeticao(v)}
          />
        </div>

        {repeticao === "parcelado" ? (
          <div className="field">
            <label htmlFor="c-n">Quantas parcelas</label>
            <input id="c-n" inputMode="numeric" value={parcelas} onChange={(e) => setParcelas(e.target.value)} />
            {previa && (
              <span className="hint">
                {n} × {formatMoney(numero)} = {formatMoney(previa.nominal)} nominais · última em {previa.ultima}.
                {n > 1 && " Soma das parcelas, não saldo devedor."}
              </span>
            )}
          </div>
        ) : (
          <div className="field">
            <label htmlFor="c-fim">Até (opcional)</label>
            <input id="c-fim" type="date" value={fim} onChange={(e) => setFim(e.target.value)} />
            <span className="hint">Sem data, continua até você encerrar. Nada é lançado antes de acontecer.</span>
          </div>
        )}

        <div className="field">
          <label>Periodicidade</label>
          <div className="chip-linha">
            {PERIODOS.map((p) => (
              <button type="button" key={p.valor} className={intervalo === p.valor ? "on" : ""}
                onClick={() => setIntervalo(p.valor)}>
                {p.rotulo}
              </button>
            ))}
          </div>
        </div>

        <div className="field">
          <label>Certeza</label>
          <Segmentado
            rotulo="Certeza"
            largo
            opcoes={[
              { valor: "sim", rotulo: "Confirmado" },
              { valor: "nao", rotulo: "Estimado" },
            ]}
            valor={confirmado}
            aoEscolher={(v: "sim" | "nao") => setConfirmado(v)}
          />
          <span className="hint">Estimado: ainda não contratado, ou o valor varia.</span>
        </div>

        {tipo === "expense" && (
          <div className="field">
            <label>Finalidade</label>
            <Segmentado rotulo="Finalidade" opcoes={OPCOES_FINALIDADE} valor={finalidade} aoEscolher={setFinalidade} largo />
          </div>
        )}

        {tipo === "expense" && (() => {
          const daCategoria = categorias?.find((c) => c.id === categoria)?.default_nature ?? "consumption";
          const efetiva = natureza ?? daCategoria;
          return (
            <div className="field">
              <label>Natureza</label>
              <Segmentado rotulo="Natureza" opcoes={OPCOES_NATUREZA} valor={efetiva}
                aoEscolher={(n) => setNatureza(n === daCategoria ? null : n)} largo />
              <span className="hint">{NATUREZA_DICA[efetiva]}</span>
            </div>
          );
        })()}

        <details className="field">
          <summary style={{ cursor: "pointer", color: "var(--text-dim)", fontSize: "var(--fs-small)" }}>
            Detalhes do contrato
          </summary>
          <div style={{ marginTop: "var(--s3)" }}>
            <div className="field">
              <label htmlFor="c-inst">Instituição</label>
              <input id="c-inst" maxLength={80} placeholder="Ex.: banco, loja, academia" value={instituicao}
                onChange={(e) => setInstituicao(e.target.value)} />
            </div>
            <div className="row2">
              <div className="field">
                <label htmlFor="c-total">Valor total / financiado</label>
                <input id="c-total" inputMode="decimal" placeholder="Opcional" value={total} onChange={(e) => setTotal(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="c-entrada">Entrada</label>
                <input id="c-entrada" inputMode="decimal" placeholder="Opcional" value={entrada} onChange={(e) => setEntrada(e.target.value)} />
              </div>
            </div>
            <span className="hint" style={{ display: "block", marginBottom: "var(--s4)" }}>
              Só informação: não entram em conta nenhuma. A entrada já paga é um lançamento à parte.
            </span>
            <div className="field">
              <label htmlFor="c-meio">Como costuma pagar</label>
              <input id="c-meio" maxLength={40} placeholder="Ex.: Pix, boleto, débito automático" value={meio}
                onChange={(e) => setMeio(e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="c-nota">Observação</label>
              <textarea id="c-nota" placeholder="Opcional" value={nota} onChange={(e) => setNota(e.target.value)} />
            </div>
          </div>
        </details>

        {editando && (
          <div className="field">
            {compromisso!.cancelled_on ? (
              <button type="button" className="btn btn-sm" onClick={() =>
                atualizar.mutate({ id: compromisso!.id, data: { cancelled_on: null } }, { onSuccess: onClose })}>
                Reativar compromisso
              </button>
            ) : (
              <button type="button" className="btn btn-sm" onClick={() =>
                atualizar.mutate({ id: compromisso!.id, data: { cancelled_on: todayIso() } }, { onSuccess: onClose })}>
                Cancelar daqui pra frente
              </button>
            )}
            <span className="hint" style={{ display: "block" }}>
              Cancelar tira as próximas ocorrências da conta; o que venceu antes e não foi pago continua devido.
            </span>
          </div>
        )}

        {erro && <div className="error-box">{erro}</div>}
      </form>

      {apagando && compromisso && (
        <ConfirmDialog
          title="Excluir compromisso"
          itemName={compromisso.description}
          consequences={[
            "O cronograma some do planejamento.",
            "Reservas feitas pra ele continuam, soltas — o dinheiro segue separado até você liberar.",
            compromisso.paid_count > 0
              ? `Ele tem ${compromisso.paid_count} baixa(s): a exclusão será recusada. Cancele em vez de excluir.`
              : "Nenhum lançamento é apagado.",
          ]}
          pending={excluir.isPending}
          error={(excluir.error as ApiError | null)?.message ?? null}
          onCancel={() => setApagando(false)}
          onConfirm={() => excluir.mutate(compromisso.id, { onSuccess: onClose })}
        />
      )}
    </Modal>
  );
}
