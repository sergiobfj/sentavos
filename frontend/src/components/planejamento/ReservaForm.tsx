import { useState } from "react";
import Modal from "../Modal";
import ConfirmDialog from "../ConfirmDialog";
import Segmentado from "../Segmentado";
import {
  useCommitment,
  useCommitments,
  useCreateProvision,
  useDeleteProvision,
  useUpdateProvision,
} from "../../lib/queries";
import { ApiError } from "../../lib/api";
import { formatDate, formatMoney, parseMoney, todayIso } from "../../lib/format";
import type { Provision, ProvisionCreate } from "../../lib/tiposPlanejamento";

type Destino = "compromisso" | "objetivo";

/** "Este dinheiro existe, mas não quero tratá-lo como livre."
 *
 *  Reserva não é despesa e não sai do patrimônio. Pra um compromisso, ela se
 *  cumpre sozinha quando a ocorrência é paga — o dinheiro sai uma vez só, pela
 *  baixa. Pra um objetivo, ela fica até você liberar. */
export default function ReservaForm({
  reserva,
  inicial,
  aoSalvar,
  pendenteExterno = false,
  erroExterno = null,
  onClose,
}: {
  reserva?: Provision;
  inicial?: Partial<ProvisionCreate>;
  aoSalvar?: (dados: ProvisionCreate) => void;
  pendenteExterno?: boolean;
  erroExterno?: string | null;
  onClose: () => void;
}) {
  const editando = !!reserva;
  const base = reserva ?? inicial ?? {};
  const [destino, setDestino] = useState<Destino>(base.commitment_id != null ? "compromisso" : "objetivo");
  const [valor, setValor] = useState(base.amount != null ? String(base.amount).replace(".", ",") : "");
  const [descricao, setDescricao] = useState(base.description ?? "");
  const [desde, setDesde] = useState(base.created_on ?? todayIso());
  const [alvo, setAlvo] = useState(base.target_date ?? "");
  const [compromissoId, setCompromissoId] = useState<number | null>(base.commitment_id ?? null);
  const [numero, setNumero] = useState<number | null>(base.commitment_no ?? null);
  const [apagando, setApagando] = useState(false);

  const { data: compromissos } = useCommitments();
  const { data: escolhido } = useCommitment(destino === "compromisso" ? compromissoId : null);
  const criar = useCreateProvision();
  const atualizar = useUpdateProvision();
  const excluir = useDeleteProvision();

  const quantia = parseMoney(valor) ?? 0;
  const abertas = (escolhido?.schedule ?? []).filter((o) => o.status === "pendente" || o.status === "vencida").slice(0, 24);
  const saidasAtivas = (compromissos ?? []).filter((c) => c.direction === "saida" && c.status === "ativo");

  function enviar(e: React.FormEvent) {
    e.preventDefault();
    if (editando) {
      atualizar.mutate(
        {
          id: reserva!.id,
          data: { amount: quantia, description: descricao.trim() || reserva!.description, created_on: desde, target_date: alvo || null },
        },
        { onSuccess: onClose }
      );
      return;
    }
    const dados: ProvisionCreate = {
      amount: quantia,
      created_on: desde,
      description: descricao.trim() || null,
      ...(destino === "compromisso"
        ? { commitment_id: compromissoId, commitment_no: numero }
        : { target_date: alvo || null }),
    };
    if (aoSalvar) return aoSalvar(dados);
    criar.mutate(dados, { onSuccess: onClose });
  }

  const pronto =
    quantia > 0 &&
    (editando || (destino === "compromisso" ? compromissoId != null && numero != null : descricao.trim().length > 0));
  const pendente = pendenteExterno || criar.isPending || atualizar.isPending;
  const erro = erroExterno ?? ((criar.error || atualizar.error) as ApiError | null)?.message ?? null;

  return (
    <Modal
      title={editando ? "Reserva" : "Nova reserva"}
      onClose={onClose}
      footer={
        <>
          {editando ? (
            <button type="button" className="btn btn-danger" onClick={() => setApagando(true)}>Excluir</button>
          ) : (
            <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          )}
          <button type="submit" form="reserva-form" className="btn btn-primary" disabled={!pronto || pendente}>
            {pendente ? "Salvando…" : "Salvar"}
          </button>
        </>
      }
    >
      <form id="reserva-form" className="m-body" onSubmit={enviar}>
        <p className="hint" style={{ marginTop: 0 }}>
          Reservar não é gastar: o dinheiro continua na conta e no patrimônio. Ele só sai do
          "disponível".
        </p>

        {!editando && (
          <div className="field">
            <Segmentado
              rotulo="Pra quê"
              largo
              opcoes={[
                { valor: "compromisso", rotulo: "Um compromisso" },
                { valor: "objetivo", rotulo: "Um objetivo" },
              ]}
              valor={destino}
              aoEscolher={(v: Destino) => setDestino(v)}
            />
          </div>
        )}

        {!editando && destino === "compromisso" ? (
          <>
            <div className="field">
              <label htmlFor="r-comp">Compromisso</label>
              <select id="r-comp" value={compromissoId ?? ""} onChange={(e) => {
                setCompromissoId(e.target.value ? Number(e.target.value) : null);
                setNumero(null);
              }}>
                <option value="">Escolher…</option>
                {saidasAtivas.map((c) => (
                  <option key={c.id} value={c.id}>{c.description}</option>
                ))}
              </select>
            </div>
            {compromissoId != null && (
              <div className="field">
                <label htmlFor="r-oc">Qual vencimento</label>
                <select id="r-oc" value={numero ?? ""} onChange={(e) => {
                  const n = e.target.value ? Number(e.target.value) : null;
                  setNumero(n);
                  const oc = abertas.find((o) => o.number === n);
                  if (oc && !valor) setValor(String(Math.max(oc.amount - oc.provisioned, 0)).replace(".", ","));
                }}>
                  <option value="">Escolher…</option>
                  {abertas.map((o) => (
                    <option key={o.number} value={o.number}>
                      {o.label ?? ""} {formatDate(o.due_date)} · {formatMoney(o.amount)}
                      {o.provisioned > 0 ? ` (já reservado ${formatMoney(o.provisioned)})` : ""}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </>
        ) : (
          <div className="field">
            <label htmlFor="r-desc">{editando ? "Descrição" : "Pra quê"}</label>
            <input id="r-desc" maxLength={80} placeholder="Ex.: Emergência, documentação da moto" value={descricao}
              onChange={(e) => setDescricao(e.target.value)} />
          </div>
        )}

        <div className="row2">
          <div className="field">
            <label htmlFor="r-valor">Valor</label>
            <input id="r-valor" inputMode="decimal" placeholder="0,00" value={valor} onChange={(e) => setValor(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="r-desde">Separado desde</label>
            <input id="r-desde" type="date" value={desde} onChange={(e) => setDesde(e.target.value)} />
          </div>
        </div>

        {(editando ? reserva!.commitment_id == null : destino === "objetivo") && (
          <div className="field">
            <label htmlFor="r-alvo">Pra quando (opcional)</label>
            <input id="r-alvo" type="date" value={alvo} onChange={(e) => setAlvo(e.target.value)} />
          </div>
        )}

        {editando && reserva!.status !== "cumprida" && (
          <div className="field">
            {reserva!.released_on ? (
              <button type="button" className="btn btn-sm" disabled={atualizar.isPending}
                onClick={() => atualizar.mutate({ id: reserva!.id, data: { released_on: null } }, { onSuccess: onClose })}>
                Voltar a reservar
              </button>
            ) : (
              <button type="button" className="btn btn-sm" disabled={atualizar.isPending}
                onClick={() => atualizar.mutate({ id: reserva!.id, data: { released_on: todayIso() } }, { onSuccess: onClose })}>
                Liberar este dinheiro
              </button>
            )}
            <span className="hint" style={{ display: "block" }}>
              Liberar devolve o valor ao disponível. Nada é lançado.
            </span>
          </div>
        )}

        {erro && <div className="error-box">{erro}</div>}
      </form>

      {apagando && reserva && (
        <ConfirmDialog
          title="Excluir reserva"
          itemName={`${reserva.description} · ${formatMoney(reserva.amount)}`}
          consequences={["O valor volta ao disponível do planejamento.", "Nenhum lançamento é tocado."]}
          pending={excluir.isPending}
          error={(excluir.error as ApiError | null)?.message ?? null}
          onCancel={() => setApagando(false)}
          onConfirm={() => excluir.mutate(reserva.id, { onSuccess: onClose })}
        />
      )}
    </Modal>
  );
}
