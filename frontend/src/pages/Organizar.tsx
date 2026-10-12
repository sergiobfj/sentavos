import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Modal from "../components/Modal";
import ConfirmDialog from "../components/ConfirmDialog";
import CategoryPicker from "../components/CategoryPicker";
import Segmentado from "../components/Segmentado";
import CompromissoForm from "../components/planejamento/CompromissoForm";
import ReservaForm from "../components/planejamento/ReservaForm";
import { Cabecalho, Linha, nomeDoMes } from "../components/planejamento/comum";
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
  useMonthHealth,
} from "../lib/queries";
import { usePeriod } from "../lib/period";
import { useAuth } from "../lib/auth";
import { ApiError } from "../lib/api";
import { formatDate, formatDiaMes, formatMoney, parseMoney, todayIso } from "../lib/format";
import type { Pendencia } from "../lib/tiposPlanejamento";
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
 *  A lista é uma linha por item — o que é, uma pista curta e o valor. A
 *  pergunta, as correspondências e as ações ficam na folha do item. Nada
 *  daqui entra em saldo, gasto ou planejamento até o dono decidir. */

type Filtro = "pendentes" | "resolvidos" | "ignorados" | "todos";

export default function Organizar() {
  const { period, label } = usePeriod();
  const { sessao } = useAuth();
  const podeEscrever = !sessao?.somenteLeitura;
  const { data, isLoading, error } = useReconciliation(period);
  const [filtro, setFiltro] = useState<Filtro>("pendentes");
  const [aberto, setAberto] = useState<number | null>(null);
  const [adicionando, setAdicionando] = useState(false);

  const grupos = useMemo(() => {
    const itens = data?.items ?? [];
    return {
      pendentes: itens.filter((i) => i.status === "pendente" || i.status === "confirmar" || i.link_missing),
      resolvidos: itens.filter((i) => i.status === "resolvido" && !i.link_missing),
      ignorados: itens.filter((i) => i.status === "ignorado"),
      todos: itens,
    };
  }, [data]);

  const item = data?.items.find((i) => i.id === aberto) ?? null;
  const lista = grupos[filtro];

  return (
    <>
      <Cabecalho titulo={`Conferir ${nomeDoMes(period.year, period.month)}`} voltar="Planejamento" voltarPara="/planejamento" />

      {/* O estado do mês e o que impede ele de ser confiável — derivado no
          servidor, agrupado ("6 lançamentos sem conta", não seis alertas).
          Os itens anotados à mão (a lista abaixo) são uma das pendências. */}
      <SaudeDoMesBloco />

      {data && data.items.length > 0 && <div className="sec-title"><h2>Itens anotados</h2></div>}
      {data && data.items.length > 0 && (
        <Segmentado
          rotulo="Filtro"
          largo
          valor={filtro}
          aoEscolher={setFiltro}
          opcoes={[
            { valor: "pendentes", rotulo: `Pendentes ${grupos.pendentes.length}` },
            { valor: "resolvidos", rotulo: `Resolvidos ${grupos.resolvidos.length}` },
            { valor: "ignorados", rotulo: `Ignorados ${grupos.ignorados.length}` },
            { valor: "todos", rotulo: "Todos" },
          ]}
        />
      )}
      <p className="nota">Nada desta lista entra no saldo ou no gasto até você decidir. "Parece" é sugestão, não vínculo.</p>

      {isLoading && <div className="skel" style={{ height: 260 }} />}
      {error && <div className="error-box">{(error as ApiError).message}</div>}

      {data && data.items.length === 0 && (
        <div className="empty">
          <div className="big">🧾</div>
          <div className="tit">Nada pra organizar em {label}</div>
          <div>Adicione o que precisa conferir: um gasto que não lançou, um valor que não sabe se caiu.</div>
        </div>
      )}
      {data && data.items.length > 0 && lista.length === 0 && <p className="hint">Nenhum item aqui.</p>}

      {lista.length > 0 && (
        <ul className="lista-compacta">
          {lista.map((i) => <LinhaItem key={i.id} item={i} onClick={() => setAberto(i.id)} />)}
        </ul>
      )}

      {podeEscrever && (
        <button className="btn btn-ghost btn-sm btn-block" style={{ marginTop: "var(--s3)" }} onClick={() => setAdicionando(true)}>
          + Adicionar item
        </button>
      )}

      {item && <ItemSheet item={item} podeEscrever={podeEscrever} onClose={() => setAberto(null)} />}
      {adicionando && <NovoItem ano={period.year} mes={period.month} onClose={() => setAdicionando(false)} />}
    </>
  );
}

/** Uma pista só, a mais útil: o vínculo, a sugestão, ou o tipo. */
function LinhaItem({ item, onClick }: { item: ReconciliationItem; onClick: () => void }) {
  const parece = item.candidates.find((c) => !c.used);
  let legenda: string;
  let tom: "neg" | undefined;
  if (item.link_missing) {
    legenda = "o vínculo foi apagado";
    tom = "neg";
  } else if (item.linked) {
    legenda = `→ ${item.linked.description}`;
  } else if (item.status === "ignorado") {
    legenda = "ignorado";
  } else if (item.status === "confirmar") {
    legenda = "precisa confirmar";
  } else if (parece) {
    legenda = `parece: ${parece.description}`;
  } else {
    legenda = CONFERENCIA_TIPO_LABEL[item.kind];
  }
  return (
    <Linha
      rotulo={item.description}
      legenda={legenda}
      tom={tom}
      valor={item.amount != null ? formatMoney(item.amount) : "—"}
      onClick={onClick}
    />
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
        <div className="folha-total">
          <b className="tnum">{item.amount != null ? formatMoney(item.amount) : "sem valor"}</b>
          <span>
            {CONFERENCIA_TIPO_LABEL[item.kind]}
            {item.date && <> · {formatDate(item.date)}</>}
            {item.category_hint && <> · categoria sugerida: {item.category_hint}</>}
          </span>
        </div>
        {item.question && <p className="pergunta">{item.question}</p>}
        {item.suggestion && <p className="nota" style={{ marginTop: 0 }}>{item.suggestion}</p>}
        {item.note && <p className="nota">Nota: {item.note}</p>}

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
            <div className="rotulo-secao">Parece com</div>
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
          </div>
        )}
        {podeEscrever && aberto && acao === null && (
          <div className="acoes-linha">
            <button className="btn btn-ghost btn-sm" onClick={() => setAcao("confirmar")}>Precisa confirmar</button>
            <button className="btn btn-ghost btn-sm" onClick={() => setAcao("ignorar")}>Ignorar</button>
            <button className="btn btn-ghost btn-sm" onClick={() => setApagando(true)}>Tirar da lista</button>
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

        {podeEscrever && !aberto && (
          <button className="btn btn-ghost btn-sm btn-block" style={{ marginTop: "var(--s2)" }} onClick={() => setApagando(true)}>
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


function SaudeDoMesBloco() {
  const { data } = useMonthHealth();
  const navigate = useNavigate();
  const [aberta, setAberta] = useState<Pendencia | null>(null);
  if (!data) return null;
  const outras = data.issues.filter((i) => i.code !== "REVIEW_ITEMS");
  return (
    <>
      <div className="folha-total">
        <b>{data.state === "conciliado" ? "Mês conciliado" : data.state === "parcial" ? "Conciliado em parte" : "Precisa revisar"}</b>
        <span>
          {data.issues.length === 0
            ? "nada pendente: os números deste mês são confiáveis"
            : `${data.to_review} pra revisar · ${data.warnings} ${data.warnings === 1 ? "aviso" : "avisos"}`}
        </span>
      </div>
      {outras.length > 0 && (
        <ul className="lista-compacta">
          {outras.map((p) => (
            <Linha key={p.code + p.title} rotulo={p.title}
              legenda={p.detail ?? (p.amount != null ? formatMoney(p.amount) : undefined)}
              tom={p.severity === "revisar" ? "neg" : undefined}
              valor={p.amount != null && p.detail ? formatMoney(p.amount) : ""}
              onClick={() => (p.items.length ? setAberta(p) : p.where && navigate(p.where))} />
          ))}
        </ul>
      )}
      {aberta && (
        <Modal title={aberta.title} onClose={() => setAberta(null)}>
          <div className="m-body">
            {aberta.detail && <p className="hint" style={{ marginTop: 0 }}>{aberta.detail}</p>}
            <ul className="lista-compacta">
              {aberta.items.map((i, n) => (
                <Linha key={n} rotulo={i.label} legenda={i.date ? formatDiaMes(i.date) : undefined}
                  valor={i.amount != null ? formatMoney(i.amount) : ""} />
              ))}
            </ul>
            {aberta.where && (
              <button className="btn btn-block" onClick={() => navigate(aberta.where!)}>Abrir onde se resolve</button>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}
