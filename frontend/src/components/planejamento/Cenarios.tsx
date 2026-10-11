import { useState } from "react";
import Modal from "../Modal";
import ConfirmDialog from "../ConfirmDialog";
import Segmentado from "../Segmentado";
import { Linha, LinhaPlano, sinal } from "./comum";
import {
  useAddScenarioItem,
  useComparacao,
  useCreateScenario,
  useDeleteScenario,
  useDuplicateScenario,
  useUpdateScenario,
} from "../../lib/queries";
import { ApiError } from "../../lib/api";
import { formatMoney, parseMoney, todayIso } from "../../lib/format";
import type { Period } from "../../lib/period";
import type {
  PlanoItem,
  PlanoMes,
  PlanoReserva,
  Scenario,
  ScenarioItemKind,
} from "../../lib/tiposPlanejamento";

/* Simulações (cenários): hipóteses com nome que nunca tocam no dado real. */

const TIPOS: { valor: ScenarioItemKind; rotulo: string }[] = [
  { valor: "saida", rotulo: "Gastar" },
  { valor: "entrada", rotulo: "Receber" },
  { valor: "reserva", rotulo: "Guardar" },
];

export function dataDoMes(mes: PlanoMes): string {
  return mes.is_current ? todayIso() : `${mes.year}-${String(mes.month).padStart(2, "0")}-15`;
}

/** Uma simulação numa linha: o nome, quanto ela muda e o disponível dela. */
export function LinhaSimulacao({ cenario, period, to }: { cenario: Scenario; period: Period; to: string }) {
  const { data } = useComparacao(period, cenario.id);
  const diferenca = data ? data.diff.available : null;
  return (
    <Linha
      rotulo={cenario.name}
      legenda={diferenca == null ? "…" : Math.abs(diferenca) < 0.005 ? "nada muda neste mês" : `${sinal(diferenca)} no disponível`}
      tom={diferenca != null && diferenca < -0.005 ? "neg" : undefined}
      valor={data ? formatMoney(data.scenario.available) : undefined}
      legendaValor={data ? "disponível" : undefined}
      to={to}
    />
  );
}

export function NovoCenario({ onCriado, onClose }: { onCriado: (id: number) => void; onClose: () => void }) {
  const [nome, setNome] = useState("");
  const criar = useCreateScenario();
  return (
    <Modal
      title="Nova simulação"
      onClose={onClose}
      footer={
        <button type="submit" form="cenario-form" className="btn btn-primary" disabled={!nome.trim() || criar.isPending}>
          Criar
        </button>
      }
    >
      <form id="cenario-form" className="m-body" onSubmit={(e) => {
        e.preventDefault();
        criar.mutate({ name: nome.trim() }, { onSuccess: (s) => onCriado(s.id) });
      }}>
        <div className="field">
          <label htmlFor="c-nome">Nome</label>
          <input id="c-nome" autoFocus maxLength={60} placeholder="Ex.: Viagem, Outubro conservador" value={nome}
            onChange={(e) => setNome(e.target.value)} />
        </div>
        <p className="nota">Uma simulação nunca cria lançamento nem muda o que é real.</p>
        {criar.error && <div className="error-box">{(criar.error as ApiError).message}</div>}
      </form>
    </Modal>
  );
}

export function EditarCenario({
  cenario,
  onDuplicado,
  onExcluido,
  onClose,
}: {
  cenario: Scenario;
  onDuplicado: (id: number) => void;
  onExcluido: () => void;
  onClose: () => void;
}) {
  const [nome, setNome] = useState(cenario.name);
  const [nota, setNota] = useState(cenario.note ?? "");
  const [apagando, setApagando] = useState(false);
  const atualizar = useUpdateScenario();
  const duplicar = useDuplicateScenario();
  const excluir = useDeleteScenario();
  const erro = (atualizar.error || duplicar.error) as ApiError | null;

  return (
    <Modal
      title="Simulação"
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-danger" onClick={() => setApagando(true)}>Excluir</button>
          <button type="submit" form="editar-cenario" className="btn btn-primary" disabled={!nome.trim() || atualizar.isPending}>
            Salvar
          </button>
        </>
      }
    >
      <form id="editar-cenario" className="m-body" onSubmit={(e) => {
        e.preventDefault();
        atualizar.mutate({ id: cenario.id, data: { name: nome.trim(), note: nota.trim() || null } }, { onSuccess: onClose });
      }}>
        <div className="field">
          <label htmlFor="e-nome">Nome</label>
          <input id="e-nome" maxLength={60} value={nome} onChange={(e) => setNome(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="e-nota">Observação</label>
          <textarea id="e-nota" placeholder="Opcional" value={nota} onChange={(e) => setNota(e.target.value)} />
        </div>
        <button type="button" className="btn btn-sm" disabled={duplicar.isPending}
          onClick={() => duplicar.mutate({ id: cenario.id }, { onSuccess: (s) => { onDuplicado(s.id); onClose(); } })}>
          Duplicar
        </button>
        {erro && <div className="error-box" style={{ marginTop: "var(--s3)" }}>{erro.message}</div>}
      </form>
      {apagando && (
        <ConfirmDialog
          title="Excluir simulação"
          itemName={cenario.name}
          consequences={[
            `${cenario.items.length} ${cenario.items.length === 1 ? "hipótese vai" : "hipóteses vão"} junto.`,
            "Nenhum lançamento, compromisso ou reserva é tocado.",
          ]}
          pending={excluir.isPending}
          error={(excluir.error as ApiError | null)?.message ?? null}
          onCancel={() => setApagando(false)}
          onConfirm={() => excluir.mutate(cenario.id, { onSuccess: () => { onExcluido(); onClose(); } })}
        />
      )}
    </Modal>
  );
}

export function NovaHipotese({ cenario, mes, onClose }: { cenario: Scenario; mes: PlanoMes; onClose: () => void }) {
  const [tipo, setTipo] = useState<ScenarioItemKind>("saida");
  const [descricao, setDescricao] = useState("");
  const [valor, setValor] = useState("");
  const [data, setData] = useState(dataDoMes(mes));
  const [repetir, setRepetir] = useState("1");
  const adicionar = useAddScenarioItem();
  const numero = parseMoney(valor) ?? 0;

  return (
    <Modal
      title="Nova hipótese"
      onClose={onClose}
      footer={
        <button type="submit" form="hipotese-form" className="btn btn-primary"
          disabled={numero <= 0 || !descricao.trim() || adicionar.isPending}>
          Adicionar
        </button>
      }
    >
      <form id="hipotese-form" className="m-body" onSubmit={(e) => {
        e.preventDefault();
        adicionar.mutate(
          { id: cenario.id, data: { kind: tipo, description: descricao.trim(), amount: numero, date: data,
            repeat_months: Math.max(1, Number(repetir) || 1) } },
          { onSuccess: onClose }
        );
      }}>
        <div className="row2">
          <div className="field">
            <label htmlFor="h-desc">Descrição</label>
            <input id="h-desc" autoFocus placeholder="Ex.: Equipamento" value={descricao} onChange={(e) => setDescricao(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="h-valor">Valor</label>
            <input id="h-valor" inputMode="decimal" placeholder="0,00" value={valor} onChange={(e) => setValor(e.target.value)} />
          </div>
        </div>
        <details className="detalhe">
          <summary>Mais opções</summary>
          <div className="field" style={{ marginTop: "var(--s3)" }}>
            <Segmentado rotulo="Tipo" opcoes={TIPOS} valor={tipo} aoEscolher={setTipo} largo />
          </div>
          <div className="row2">
            <div className="field">
              <label htmlFor="h-data">Data</label>
              <input id="h-data" type="date" value={data} onChange={(e) => setData(e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="h-rep">Por quantos meses</label>
              <input id="h-rep" inputMode="numeric" value={repetir} onChange={(e) => setRepetir(e.target.value)} />
            </div>
          </div>
        </details>
        {adicionar.error && <div className="error-box">{(adicionar.error as ApiError).message}</div>}
      </form>
    </Modal>
  );
}

/** Escolher um item real do mês pra mudar só nesta simulação. */
export function EscolherItemReal({
  mes,
  onEscolher,
  onClose,
}: {
  mes: PlanoMes;
  onEscolher: (alvo: PlanoItem | PlanoReserva) => void;
  onClose: () => void;
}) {
  const itens = mes.items.filter((i) => i.status !== "pago" && i.source !== "cenario");
  const reservas = mes.reserves.filter((r) => r.source === "reserva");
  return (
    <Modal title="Mudar um item real" onClose={onClose}>
      <div className="m-body">
        <p className="nota" style={{ marginTop: 0 }}>O item real não muda: só esta simulação passa a considerar outro valor.</p>
        {itens.length + reservas.length === 0 ? (
          <p className="hint">Nada em aberto neste mês.</p>
        ) : (
          <ul className="lista-compacta">
            {itens.map((i) => <LinhaPlano key={i.key} item={i} onClick={() => onEscolher(i)} />)}
            {reservas.map((r) => (
              <Linha key={r.key} rotulo={r.description} legenda="reserva" valor={formatMoney(r.amount)} onClick={() => onEscolher(r)} />
            ))}
          </ul>
        )}
      </div>
    </Modal>
  );
}

export function AjustarNoCenario({
  cenario,
  alvo,
  onClose,
}: {
  cenario: Scenario;
  alvo: PlanoItem | PlanoReserva;
  onClose: () => void;
}) {
  const ehReserva = !("direction" in alvo);
  const chave = ehReserva && alvo.provision_id != null ? `reserva:${alvo.provision_id}` : alvo.key;
  const atual = ehReserva ? alvo.amount : (alvo as PlanoItem).remaining;
  const [valor, setValor] = useState(String(atual).replace(".", ","));
  const adicionar = useAddScenarioItem();
  const kind: ScenarioItemKind = ehReserva ? "reserva" : (alvo as PlanoItem).direction === "entrada" ? "entrada" : "saida";
  const data = ehReserva ? `${alvo.since[0]}-${String(alvo.since[1]).padStart(2, "0")}-01` : (alvo as PlanoItem).date;

  function aplicar(novo: number) {
    adicionar.mutate(
      { id: cenario.id, data: { kind, description: alvo.description, amount: novo, date: data, ref: chave } },
      { onSuccess: onClose }
    );
  }

  return (
    <Modal title={alvo.description} onClose={onClose}>
      <div className="m-body">
        <div className="folha-total">
          <b className="tnum">{formatMoney(atual)}</b>
          <span>valor real · só esta simulação muda</span>
        </div>
        <div className="field">
          <label htmlFor="a-valor">Valor nesta simulação</label>
          <input id="a-valor" inputMode="decimal" value={valor} onChange={(e) => setValor(e.target.value)} />
        </div>
        <div className="acoes">
          <button className="btn btn-primary" disabled={adicionar.isPending || parseMoney(valor) == null}
            onClick={() => aplicar(parseMoney(valor) ?? 0)}>
            Usar este valor
          </button>
          <button className="btn" disabled={adicionar.isPending} onClick={() => aplicar(0)}>
            Tirar desta simulação
          </button>
        </div>
        {adicionar.error && <div className="error-box" style={{ marginTop: "var(--s3)" }}>{(adicionar.error as ApiError).message}</div>}
      </div>
    </Modal>
  );
}
