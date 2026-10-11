import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Modal from "../components/Modal";
import ConfirmDialog from "../components/ConfirmDialog";
import CategoryPicker from "../components/CategoryPicker";
import Segmentado from "../components/Segmentado";
import CompromissoForm from "../components/planejamento/CompromissoForm";
import ReservaForm from "../components/planejamento/ReservaForm";
import { nomeDoMes } from "../components/planejamento/comum";
import { OPCOES_FINALIDADE } from "../lib/finalidade";
import {
  useAddReconciliation,
  useCategories,
  useDeleteReconciliation,
  useLinkReconciliation,
  useReconciliation,
  useReconCommitment,
  useReconProvision,
  useReconTransaction,
  useUpdateReconciliation,
} from "../lib/queries";
import { usePeriod } from "../lib/period";
import { useAuth } from "../lib/auth";
import { ApiError } from "../lib/api";
import { formatDate, formatDiaMes, formatMoney, parseMoney, todayIso } from "../lib/format";
import type { Category, Finalidade } from "../lib/types";
import {
  CONFERENCIA_TIPO_LABEL,
  type Candidato,
  type CommitmentCreate,
  type ReconciliationItem,
  type ReconciliationKind,
} from "../lib/tiposPlanejamento";

/** Organizar o mês: revisar e aplicar, item a item.
 *
 *  Cada item é algo que talvez precise virar dado — "a entrada da moto já está
 *  lançada?", "o auxílio caiu?". Nada daqui entra em saldo, gasto ou
 *  planejamento enquanto você não decide. Não existe "importar tudo": o app
 *  mostra o que encontrou e o que parece corresponder, e cada criação é um
 *  toque seu. */

const ICONE: Record<ReconciliationKind, string> = {
  entrada: "↓", saida: "↑", obrigacao: "📄", reserva: "📌", saldo: "🏦", outro: "?",
};

export default function Organizar() {
  const navigate = useNavigate();
  const { period, label } = usePeriod();
  const { sessao } = useAuth();
  const podeEscrever = !sessao?.somenteLeitura;
  const { data, isLoading, error } = useReconciliation(period);
  const [aberto, setAberto] = useState<number | null>(null);
  const [adicionando, setAdicionando] = useState(false);

  const grupos = useMemo(() => {
    const itens = data?.items ?? [];
    return {
      pendentes: itens.filter((i) => i.status === "pendente" || i.link_missing),
      confirmar: itens.filter((i) => i.status === "confirmar" && !i.link_missing),
      resolvidos: itens.filter((i) => i.status === "resolvido" && !i.link_missing),
      ignorados: itens.filter((i) => i.status === "ignorado"),
    };
  }, [data]);

  const item = data?.items.find((i) => i.id === aberto) ?? null;
  const nome = nomeDoMes(period.year, period.month);

  return (
    <>
      <button className="btn btn-ghost btn-sm" onClick={() => navigate("/planejamento")} style={{ marginBottom: "var(--s3)" }}>
        ‹ Planejamento
      </button>

      <section className="hero">
        <div className="rot">Organizar {nome}</div>
        <div className="big tnum">{grupos.pendentes.length + grupos.confirmar.length}</div>
        <div className="delta">
          {grupos.pendentes.length + grupos.confirmar.length === 1 ? "item espera" : "itens esperam"} uma decisão sua
        </div>
        {data && (
          <div className="contagem">
            <span><b>{grupos.pendentes.length}</b> {grupos.pendentes.length === 1 ? "pendente" : "pendentes"}</span>
            <span><b>{grupos.confirmar.length}</b> a confirmar</span>
            <span><b>{grupos.resolvidos.length}</b> {grupos.resolvidos.length === 1 ? "resolvido" : "resolvidos"}</span>
            <span><b>{grupos.ignorados.length}</b> {grupos.ignorados.length === 1 ? "ignorado" : "ignorados"}</span>
          </div>
        )}
      </section>

      <div className="hint" style={{ marginTop: "var(--s3)" }}>
        Nada desta lista entra no saldo, no gasto ou no planejamento até você decidir. "Parece"
        é sugestão, não vínculo.
      </div>

      {isLoading && <div className="skel" style={{ height: 260, marginTop: "var(--s4)" }} />}
      {error && <div className="error-box">{(error as ApiError).message}</div>}

      {data && data.items.length === 0 && (
        <div className="empty">
          <div className="big">🧾</div>
          <div className="tit">Nada pra organizar em {label}</div>
          <div>Adicione o que você precisa conferir: um gasto que não lançou, um valor que não sabe se caiu.</div>
        </div>
      )}

      <Grupo titulo="Esperando você" itens={grupos.pendentes} onAbrir={setAberto} />
      <Grupo titulo="Precisa confirmar" itens={grupos.confirmar} onAbrir={setAberto} />
      <Grupo titulo="Resolvidos" itens={grupos.resolvidos} onAbrir={setAberto} fechado />
      <Grupo titulo="Ignorados" itens={grupos.ignorados} onAbrir={setAberto} fechado />

      {podeEscrever && (
        <button className="btn btn-block" style={{ marginTop: "var(--s5)" }} onClick={() => setAdicionando(true)}>
          + Adicionar item
        </button>
      )}

      {item && <ItemSheet item={item} podeEscrever={podeEscrever} onClose={() => setAberto(null)} />}
      {adicionando && <NovoItem ano={period.year} mes={period.month} onClose={() => setAdicionando(false)} />}
    </>
  );
}

function Grupo({
  titulo,
  itens,
  onAbrir,
  fechado = false,
}: {
  titulo: string;
  itens: ReconciliationItem[];
  onAbrir: (id: number) => void;
  fechado?: boolean;
}) {
  if (itens.length === 0) return null;
  const lista = (
    <div className="list">
      {itens.map((i) => <Linha key={i.id} item={i} onClick={() => onAbrir(i.id)} />)}
    </div>
  );
  if (fechado) {
    return (
      <details style={{ marginTop: "var(--s5)" }}>
        <summary className="grupo-rotulo" style={{ cursor: "pointer" }}>{titulo} ({itens.length})</summary>
        {lista}
      </details>
    );
  }
  return (
    <>
      <div className="sec-title"><h2>{titulo}</h2><span className="extra">{itens.length}</span></div>
      {lista}
    </>
  );
}

function Linha({ item, onClick }: { item: ReconciliationItem; onClick: () => void }) {
  const parece = item.candidates[0];
  return (
    <button className="row plano-row" onClick={onClick}>
      <div className="avatar avatar-fatura" aria-hidden>{ICONE[item.kind]}</div>
      <div className="mid">
        <div className="t">{item.description}</div>
        <div className="s">
          <span>{CONFERENCIA_TIPO_LABEL[item.kind]}</span>
          {item.link_missing && <span style={{ color: "var(--neg)" }}>o vínculo foi apagado</span>}
          {item.linked && <span>→ {item.linked.description}</span>}
          {!item.linked && parece && !parece.used && <span>parece: {parece.description}</span>}
          {!item.linked && !parece && item.question && <span>{item.question}</span>}
        </div>
      </div>
      <div className="amt tnum">{item.amount != null ? formatMoney(item.amount) : "—"}</div>
    </button>
  );
}

type Acao = null | "realizado" | "previsto" | "compromisso" | "reserva" | "confirmar" | "ignorar";

function ItemSheet({ item, podeEscrever, onClose }: { item: ReconciliationItem; podeEscrever: boolean; onClose: () => void }) {
  const [acao, setAcao] = useState<Acao>(null);
  const [nota, setNota] = useState(item.note ?? "");
  const [apagando, setApagando] = useState(false);
  const vincular = useLinkReconciliation();
  const atualizar = useUpdateReconciliation();
  const excluir = useDeleteReconciliation();
  const criarCompromisso = useReconCommitment();
  const criarReserva = useReconProvision();
  const { data: categorias } = useCategories();
  const aberto = item.status === "pendente" || item.status === "confirmar" || item.link_missing;
  const erro = (vincular.error || atualizar.error) as ApiError | null;

  function escolherCandidato(c: Candidato) {
    if (c.kind === "fatura") {
      // Fatura não é lançamento nem compromisso: o vínculo é a anotação.
      atualizar.mutate(
        { id: item.id, data: { status: "resolvido", note: `Corresponde à ${c.description} (vence ${formatDiaMes(c.date!)}).` } },
        { onSuccess: onClose }
      );
      return;
    }
    vincular.mutate(
      { id: item.id, data: c.kind === "compromisso" ? { commitment_id: c.id } : { transaction_id: c.id } },
      { onSuccess: onClose }
    );
  }

  if (acao === "realizado" || acao === "previsto") {
    return <LancamentoDoItem item={item} previsto={acao === "previsto"} onClose={onClose} />;
  }
  if (acao === "compromisso") {
    const p = item.prefill ?? {};
    const inicial: Partial<CommitmentCreate> & { direction?: "saida" | "entrada" } = {
      description: (p.description as string) ?? item.description,
      amount: (p.amount as number) ?? item.amount ?? undefined,
      first_due: (p.first_due as string) ?? item.date ?? undefined,
      installments: (p.installments as number) ?? 1,
      interval_months: (p.interval_months as number) ?? 1,
      confirmed: (p.confirmed as boolean) ?? true,
      finalidade: (p.finalidade as Finalidade) ?? null,
      institution: (p.institution as string) ?? null,
      total_amount: (p.total_amount as number) ?? null,
      down_payment: (p.down_payment as number) ?? null,
      note: (p.note as string) ?? null,
      category_id: categoriaSugerida(categorias ?? [], item.category_hint, item.kind === "entrada" ? "income" : "expense")?.id,
      direction: item.kind === "entrada" ? "entrada" : "saida",
    };
    return (
      <CompromissoForm
        titulo="Criar compromisso"
        inicial={inicial}
        aoSalvar={(dados) => criarCompromisso.mutate({ id: item.id, data: dados }, { onSuccess: onClose })}
        pendenteExterno={criarCompromisso.isPending}
        erroExterno={(criarCompromisso.error as ApiError | null)?.message ?? null}
        onClose={onClose}
      />
    );
  }
  if (acao === "reserva") {
    return (
      <ReservaForm
        inicial={{ description: item.description, amount: item.amount ?? undefined }}
        aoSalvar={(dados) => criarReserva.mutate({ id: item.id, data: dados }, { onSuccess: onClose })}
        pendenteExterno={criarReserva.isPending}
        erroExterno={(criarReserva.error as ApiError | null)?.message ?? null}
        onClose={onClose}
      />
    );
  }

  const podeLancar = item.kind === "entrada" || item.kind === "saida" || item.kind === "outro";
  const podeComprometer = item.kind === "obrigacao" || item.kind === "saida" || item.kind === "entrada";
  const podeReservar = item.kind === "reserva" || item.kind === "outro";

  return (
    <Modal title={item.description} onClose={onClose}>
      <div className="m-body">
        <div className="resumo-compra">
          <div className="linha"><span>{CONFERENCIA_TIPO_LABEL[item.kind]}</span><b className="tnum">{item.amount != null ? formatMoney(item.amount) : "sem valor"}</b></div>
          {item.date && <div className="linha"><span>Data</span><b>{formatDate(item.date)}</b></div>}
          {item.suggestion && <div className="linha"><span>{item.suggestion}</span></div>}
          {item.question && <div className="linha"><b style={{ textAlign: "left" }}>{item.question}</b></div>}
          {item.category_hint && <div className="linha"><span>Categoria sugerida: {item.category_hint}</span></div>}
          {item.note && <div className="linha"><span>Nota: {item.note}</span></div>}
        </div>

        {item.linked && (
          <div className="aviso-box">
            Resolvido com <b>{item.linked.description}</b>
            {item.linked.amount != null && <> · {formatMoney(item.linked.amount)}</>}
            {item.linked.date && <> · {formatDiaMes(item.linked.date)}</>}.
          </div>
        )}
        {item.link_missing && (
          <div className="aviso-box">O que estava vinculado foi apagado depois. O item voltou a esperar uma decisão.</div>
        )}

        {aberto && item.kind === "saldo" && (
          <div className="aviso-box" style={{ marginTop: "var(--s3)" }}>
            Saldo observado não é lançamento: não vira receita nem despesa. Se quiser usá-lo,
            lance os saldos das contas em <Link to="/patrimonio">Patrimônio</Link> — sem ajuste pra fazer bater.
          </div>
        )}

        {aberto && item.candidates.length > 0 && (
          <>
            <div className="grupo-rotulo">Parece com</div>
            {item.candidates.map((c) => (
              <button key={`${c.kind}${c.id}`} className="sugestao" disabled={!podeEscrever || vincular.isPending || atualizar.isPending}
                onClick={() => escolherCandidato(c)}>
                <span className="t">
                  <span>{c.description}</span>
                  <span className="tnum">{c.amount != null ? formatMoney(c.amount) : ""}</span>
                </span>
                <span className="s">
                  {c.date && formatDiaMes(c.date)}
                  {c.detail && ` · ${c.detail}`}
                  {c.used && " · já usado em outro item"}
                </span>
                <span className="m">{c.reasons.join(" · ")}</span>
              </button>
            ))}
            {podeEscrever && <p className="hint">Tocar numa sugestão marca "já existe" — nada novo é criado.</p>}
          </>
        )}

        {podeEscrever && aberto && acao === null && (
          <div className="acoes">
            {podeLancar && (
              <button className="btn" onClick={() => setAcao("realizado")}>
                <span>Criar como realizado<small>Um lançamento com valor pago.</small></span>
              </button>
            )}
            {podeLancar && (
              <button className="btn" onClick={() => setAcao("previsto")}>
                <span>Criar como previsto<small>Só previsto: entra no planejamento, não no saldo.</small></span>
              </button>
            )}
            {podeComprometer && (
              <button className="btn" onClick={() => setAcao("compromisso")}>
                <span>Criar compromisso<small>Parcelado ou recorrente, sem lançar nada agora.</small></span>
              </button>
            )}
            {podeReservar && (
              <button className="btn" onClick={() => setAcao("reserva")}>
                <span>Criar reserva<small>Separa o dinheiro sem gastar.</small></span>
              </button>
            )}
            <button className="btn btn-ghost" onClick={() => setAcao("confirmar")}>
              <span>Precisa confirmar<small>Deixa anotado o que falta saber.</small></span>
            </button>
            <button className="btn btn-ghost" onClick={() => setAcao("ignorar")}>
              <span>Ignorar<small>Não é dado (cancelado, saldo, simulação).</small></span>
            </button>
          </div>
        )}

        {(acao === "confirmar" || acao === "ignorar") && (
          <form onSubmit={(e) => {
            e.preventDefault();
            atualizar.mutate(
              { id: item.id, data: { status: acao === "ignorar" ? "ignorado" : "confirmar", note: nota.trim() || null } },
              { onSuccess: onClose }
            );
          }}>
            <div className="field">
              <label htmlFor="i-nota">{acao === "ignorar" ? "Por quê (opcional)" : "O que falta saber"}</label>
              <input id="i-nota" value={nota} maxLength={500} onChange={(e) => setNota(e.target.value)} />
            </div>
            <button type="submit" className="btn btn-primary btn-block" disabled={atualizar.isPending}>
              {acao === "ignorar" ? "Ignorar" : "Marcar"}
            </button>
          </form>
        )}

        {podeEscrever && !aberto && (
          <button className="btn btn-block" style={{ marginTop: "var(--s3)" }} disabled={atualizar.isPending}
            onClick={() => atualizar.mutate({ id: item.id, data: { status: "pendente" } }, { onSuccess: onClose })}>
            Reabrir
          </button>
        )}
        {podeEscrever && !aberto && item.linked && (
          <p className="hint">Reabrir solta o vínculo, mas não apaga o que foi criado.</p>
        )}

        {podeEscrever && (
          <button className="btn btn-ghost btn-sm btn-block" style={{ marginTop: "var(--s3)" }} onClick={() => setApagando(true)}>
            Tirar da lista
          </button>
        )}

        {erro && <div className="error-box" style={{ marginTop: "var(--s3)" }}>{erro.message}</div>}
      </div>

      {apagando && (
        <ConfirmDialog
          title="Tirar da lista"
          itemName={item.description}
          consequences={["Só o item da conferência sai. Nada que ele vinculou é apagado."]}
          confirmLabel="Tirar"
          pending={excluir.isPending}
          error={(excluir.error as ApiError | null)?.message ?? null}
          onCancel={() => setApagando(false)}
          onConfirm={() => excluir.mutate(item.id, { onSuccess: onClose })}
        />
      )}
    </Modal>
  );
}

/** A categoria cujo nome bate com a sugestão ("Moto", "Saúde"). Sem certeza,
 *  nenhuma: a escolha fica com quem está criando. */
function categoriaSugerida(categorias: Category[], dica: string | null, tipo: "income" | "expense"): Category | undefined {
  if (!dica) return undefined;
  const alvo = dica.toLocaleLowerCase("pt-BR");
  return categorias.find((c) => c.type === tipo && !c.archived && c.name.toLocaleLowerCase("pt-BR") === alvo);
}

function dataDoItem(item: ReconciliationItem): string {
  if (item.date) return item.date;
  const hoje = todayIso();
  const doMes = `${item.year}-${String(item.month).padStart(2, "0")}`;
  return hoje.startsWith(doMes) ? hoje : `${doMes}-15`;
}

function LancamentoDoItem({ item, previsto, onClose }: { item: ReconciliationItem; previsto: boolean; onClose: () => void }) {
  const { data: categorias } = useCategories();
  const [tipo, setTipo] = useState<"expense" | "income">(item.kind === "entrada" ? "income" : "expense");
  const [descricao, setDescricao] = useState(item.description);
  const [valor, setValor] = useState(item.amount != null ? String(item.amount).replace(".", ",") : "");
  const [data, setData] = useState(dataDoItem(item));
  const [categoria, setCategoria] = useState<number | null>(
    categoriaSugerida(categorias ?? [], item.category_hint, item.kind === "entrada" ? "income" : "expense")?.id ?? null
  );
  const [finalidade, setFinalidade] = useState<Finalidade>("pessoal");
  const criar = useReconTransaction();
  const numero = parseMoney(valor) ?? 0;

  return (
    <Modal
      title={previsto ? "Criar como previsto" : "Criar como realizado"}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          <button type="submit" form="item-lanc" className="btn btn-primary"
            disabled={!descricao.trim() || categoria == null || numero <= 0 || criar.isPending}>
            {criar.isPending ? "Salvando…" : "Criar"}
          </button>
        </>
      }
    >
      <form id="item-lanc" className="m-body" onSubmit={(e) => {
        e.preventDefault();
        criar.mutate(
          {
            id: item.id,
            data: {
              date: data,
              description: descricao.trim(),
              category_id: categoria!,
              amount_paid: previsto ? null : numero,
              amount_planned: previsto ? numero : null,
              note: null,
              payment_method: "cash",
              finalidade: tipo === "expense" ? finalidade : null,
            },
          },
          { onSuccess: onClose }
        );
      }}>
        <p className="hint" style={{ marginTop: 0 }}>
          {previsto
            ? "Previsto não é dinheiro: entra no planejamento do mês, não no saldo nem no gasto."
            : "Realizado: entra no saldo do mês e, se for saída, no gasto. Compra no cartão se lança pelo formulário de compra; depois use \"já existe\"."}
        </p>
        <div className="field">
          <div className="tipo-toggle" role="group" aria-label="Tipo">
            {(["expense", "income"] as const).map((t) => (
              <button type="button" key={t} className={tipo === t ? "on" : ""} aria-pressed={tipo === t}
                onClick={() => { setTipo(t); setCategoria(null); }}>
                {t === "expense" ? "Saída" : "Entrada"}
              </button>
            ))}
          </div>
        </div>
        <div className="field">
          <label htmlFor="l-desc">Descrição</label>
          <input id="l-desc" value={descricao} onChange={(e) => setDescricao(e.target.value)} />
        </div>
        <div className="row2">
          <div className="field">
            <label htmlFor="l-valor">Valor</label>
            <input id="l-valor" inputMode="decimal" value={valor} onChange={(e) => setValor(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="l-data">Data</label>
            <input id="l-data" type="date" value={data} onChange={(e) => setData(e.target.value)} />
          </div>
        </div>
        <div className="field">
          <label>Categoria</label>
          <CategoryPicker categories={categorias ?? []} tipo={tipo} valor={categoria} aoEscolher={setCategoria} />
          {item.category_hint && <span className="hint">Sugestão do item: {item.category_hint}</span>}
        </div>
        {tipo === "expense" && (
          <div className="field">
            <label>Finalidade</label>
            <Segmentado rotulo="Finalidade" opcoes={OPCOES_FINALIDADE} valor={finalidade} aoEscolher={setFinalidade} largo />
          </div>
        )}
        {criar.error && <div className="error-box">{(criar.error as ApiError).message}</div>}
      </form>
    </Modal>
  );
}

const TIPOS_ITEM: { valor: ReconciliationKind; rotulo: string }[] = [
  { valor: "saida", rotulo: "Saída" },
  { valor: "entrada", rotulo: "Entrada" },
  { valor: "obrigacao", rotulo: "Compromisso" },
  { valor: "reserva", rotulo: "Reserva" },
];

function NovoItem({ ano, mes, onClose }: { ano: number; mes: number; onClose: () => void }) {
  const [tipo, setTipo] = useState<ReconciliationKind>("saida");
  const [descricao, setDescricao] = useState("");
  const [valor, setValor] = useState("");
  const [pergunta, setPergunta] = useState("");
  const adicionar = useAddReconciliation();

  return (
    <Modal
      title="Adicionar item"
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          <button type="submit" form="novo-item" className="btn btn-primary" disabled={!descricao.trim() || adicionar.isPending}>
            Adicionar
          </button>
        </>
      }
    >
      <form id="novo-item" className="m-body" onSubmit={(e) => {
        e.preventDefault();
        adicionar.mutate(
          { year: ano, month: mes, description: descricao.trim(), amount: parseMoney(valor), kind: tipo, question: pergunta.trim() || null },
          { onSuccess: onClose }
        );
      }}>
        <p className="hint" style={{ marginTop: 0 }}>
          Um item é uma pergunta, não um lançamento. Ele não entra em conta nenhuma até você decidir o que ele é.
        </p>
        <div className="field">
          <Segmentado rotulo="Tipo" opcoes={TIPOS_ITEM} valor={tipo} aoEscolher={setTipo} largo />
        </div>
        <div className="field">
          <label htmlFor="n-desc">Descrição</label>
          <input id="n-desc" autoFocus value={descricao} onChange={(e) => setDescricao(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="n-valor">Valor (se souber)</label>
          <input id="n-valor" inputMode="decimal" value={valor} onChange={(e) => setValor(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="n-perg">O que falta saber</label>
          <input id="n-perg" placeholder="Ex.: já foi pago?" value={pergunta} onChange={(e) => setPergunta(e.target.value)} />
        </div>
        {adicionar.error && <div className="error-box">{(adicionar.error as ApiError).message}</div>}
      </form>
    </Modal>
  );
}
