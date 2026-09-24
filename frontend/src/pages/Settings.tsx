import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { parseMoney } from "../lib/format";
import Modal from "../components/Modal";
import ConfirmDialog from "../components/ConfirmDialog";
import Segmentado from "../components/Segmentado";
import { IconeCartao, MarcaEditavel } from "../components/TransactionList";
import {
  useCards,
  useCategories,
  useCategoriesComUso,
  useCreateCard,
  useCreateCategory,
  useDeleteCard,
  useDeleteCategory,
  useUpdateCard,
  useUpdateCategory,
  usePerfil,
  useSetCdi,
} from "../lib/queries";
import { ApiError } from "../lib/api";
import { OPCOES_FINALIDADE } from "../lib/finalidade";
import {
  EMOJIS,
  PALETA_CATEGORIAS,
  ehCorDaPaleta,
  fundoDaCor,
  proximaCorLivre,
} from "../lib/paleta";
import {
  CATEGORY_TYPE_LABEL,
  FINALIDADE_LABEL,
  type Card as CardType,
  type Category,
  type CategoryComUso,
  type CategoryType,
  type Finalidade,
} from "../lib/types";

// A ordem das seções segue o uso: despesa é o que se cria e ajusta com mais
// frequência; investimento, o que menos muda.
const GRUPOS: { tipo: CategoryType; titulo: string }[] = [
  { tipo: "expense", titulo: "Despesas" },
  { tipo: "income", titulo: "Receitas" },
  { tipo: "investment", titulo: "Investimentos" },
];

const OPCOES_TIPO = GRUPOS.map((g) => ({ valor: g.tipo, rotulo: CATEGORY_TYPE_LABEL[g.tipo] }));

export default function Settings() {
  return (
    <>
      <div className="sec-title" style={{ marginTop: "var(--s2)" }}>
        <h2>Cartões</h2>
      </div>
      <Cartoes />

      <Categorias />

      <div className="sec-title">
        <h2>Rendimento</h2>
      </div>
      <CdiCard />
    </>
  );
}

// ---------- Cartões ----------

function Cartoes() {
  // Inclui arquivados: é aqui que se desarquiva, igual às categorias.
  const { data: cards, isLoading } = useCards(true);
  const { data: categories } = useCategories(true);
  const [editando, setEditando] = useState<CardType | null>(null);
  const [criando, setCriando] = useState(false);
  const arquivarCategoria = useUpdateCategory();

  // A categoria "Fatura do cartão" é o jeito antigo de registrar fatura. O app
  // OFERECE arquivá-la — não arquiva sozinho, e não toca no histórico dela.
  const legada = (categories ?? []).find(
    (c) => !c.archived && c.type === "expense" && /fatura/i.test(c.name)
  );

  if (isLoading) return <div className="skel" style={{ height: 90 }} />;

  return (
    <>
      {(cards ?? []).length === 0 ? (
        <div className="card card-pad">
          <div className="hint" style={{ margin: "0 0 var(--s3)" }}>
            Com um cartão cadastrado, a compra vira gasto no mês em que você
            comprou e só sai da conta quando você pagar a fatura.
          </div>
          <button className="btn btn-primary btn-block" onClick={() => setCriando(true)}>
            Cadastrar cartão
          </button>
        </div>
      ) : (
        <>
          <div className="list">
            {(cards ?? []).map((c) => (
              <button
                className="row"
                key={c.id}
                onClick={() => setEditando(c)}
                style={c.archived ? { opacity: 0.5 } : undefined}
              >
                <div className="avatar avatar-fatura" aria-hidden>
                  <IconeCartao />
                </div>
                <div className="mid">
                  <div className="t">{c.name}</div>
                  <div className="s">
                    {c.finalidade ? FINALIDADE_LABEL[c.finalidade] : (
                      // O único estado que pede ação: sem finalidade, as
                      // compras dele ficam fora dos filtros do Início.
                      <span style={{ color: "var(--text)" }}>Sem finalidade</span>
                    )}
                    {" · "}fecha {c.closing_day}, vence {c.due_day}
                    {c.archived && " · arquivado"}
                  </div>
                </div>
                <MarcaEditavel />
              </button>
            ))}
          </div>
          <button
            className="btn btn-ghost btn-sm btn-block"
            style={{ marginTop: "var(--s2)" }}
            onClick={() => setCriando(true)}
          >
            + Novo cartão
          </button>
        </>
      )}

      {(cards ?? []).length > 0 && legada && (
        <div className="aviso-box" style={{ marginTop: "var(--s3)" }}>
          A categoria <b>{legada.name}</b> é o jeito antigo de registrar fatura:
          uma despesa por mês, com o total. Com o cartão no app, usar os dois no
          mesmo mês conta o mesmo dinheiro duas vezes. Arquivar tira a categoria
          do formulário; os lançamentos antigos <b>não mudam</b>.
          <div style={{ marginTop: "var(--s3)" }}>
            <button
              className="btn btn-sm"
              disabled={arquivarCategoria.isPending}
              onClick={() => arquivarCategoria.mutate({ id: legada.id, data: { archived: true } })}
            >
              Arquivar {legada.name}
            </button>
          </div>
        </div>
      )}

      <Link className="link-seta" to="/rever" style={{ marginTop: "var(--s2)" }}>
        Revisar forma de pagamento dos lançamentos
      </Link>

      {criando && <CardForm onClose={() => setCriando(false)} />}
      {editando && <CardForm card={editando} onClose={() => setEditando(null)} />}
    </>
  );
}

function CardForm({ card, onClose }: { card?: CardType; onClose: () => void }) {
  const criar = useCreateCard();
  const atualizar = useUpdateCard();
  const [excluindo, setExcluindo] = useState(false);
  const [form, setForm] = useState({
    name: card?.name ?? "",
    closing_day: String(card?.closing_day ?? 25),
    due_day: String(card?.due_day ?? 2),
    // Cartão novo começa em Pessoal (a escolha fica visível); cartão antigo sem
    // finalidade começa sem nada marcado, pra a pessoa escolher de propósito.
    finalidade: (card ? card.finalidade : "pessoal") as Finalidade | null,
  });

  const pendente = criar.isPending || atualizar.isPending;
  const erro = (criar.error || atualizar.error) as ApiError | null;
  const fecha = Number(form.closing_day);
  const vence = Number(form.due_day);
  const valido =
    form.name.trim() && fecha >= 1 && fecha <= 31 && vence >= 1 && vence <= 31 && form.finalidade;
  const classificando = card && card.finalidade == null && form.finalidade != null;

  return (
    <Modal
      title={card ? "Editar cartão" : "Novo cartão"}
      onClose={onClose}
      footer={
        <>
          {card ? (
            <button type="button" className="btn btn-danger" onClick={() => setExcluindo(true)}>
              Excluir
            </button>
          ) : (
            <button type="button" className="btn btn-ghost" onClick={onClose}>
              Cancelar
            </button>
          )}
          <button type="submit" form="card-form" className="btn btn-primary" disabled={pendente || !valido}>
            {pendente ? "Salvando…" : "Salvar"}
          </button>
        </>
      }
    >
      <form
        id="card-form"
        className="m-body"
        onSubmit={(e) => {
          e.preventDefault();
          const dados = {
            name: form.name.trim(),
            closing_day: fecha,
            due_day: vence,
            finalidade: form.finalidade!,
          };
          if (card) atualizar.mutate({ id: card.id, data: dados }, { onSuccess: onClose });
          else criar.mutate(dados, { onSuccess: onClose });
        }}
      >
        <div className="field">
          <label htmlFor="cd-nome">Nome</label>
          <input
            id="cd-nome"
            value={form.name}
            autoFocus={!card}
            placeholder="Ex.: Nubank"
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </div>

        <div className="field">
          <span className="label">Finalidade</span>
          <Segmentado
            rotulo="Finalidade do cartão"
            opcoes={OPCOES_FINALIDADE}
            valor={form.finalidade}
            aoEscolher={(f) => setForm({ ...form, finalidade: f })}
            largo
          />
          <div className="hint">
            {classificando
              ? "As compras deste cartão que ainda não têm finalidade passam a ter esta. As que já têm continuam como estão."
              : "Compra neste cartão vem com esta finalidade, e dá pra trocar compra a compra."}
          </div>
        </div>

        <div className="field row2">
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="cd-fecha">Fecha dia</label>
            <input
              id="cd-fecha"
              inputMode="numeric"
              value={form.closing_day}
              onChange={(e) => setForm({ ...form, closing_day: e.target.value })}
            />
          </div>
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="cd-vence">Vence dia</label>
            <input
              id="cd-vence"
              inputMode="numeric"
              value={form.due_day}
              onChange={(e) => setForm({ ...form, due_day: e.target.value })}
            />
          </div>
        </div>

        <div className="hint" style={{ marginBottom: "var(--s4)" }}>
          Compra feita <b>até</b> o dia do fechamento entra na fatura que fecha
          nesse dia. Depois disso, vai pra próxima.
        </div>

        {card && (
          <div className="field">
            <button
              type="button"
              className="btn btn-sm"
              disabled={atualizar.isPending}
              onClick={() =>
                atualizar.mutate({ id: card.id, data: { archived: !card.archived } }, { onSuccess: onClose })
              }
            >
              {card.archived ? "Desarquivar cartão" : "Arquivar cartão"}
            </button>
            <div className="hint">
              Arquivado, ele some do formulário de lançamento sem levar as
              compras e faturas antigas junto.
            </div>
          </div>
        )}

        {erro && <div className="error-box">{erro.message}</div>}
      </form>

      {excluindo && card && (
        <ExcluirCartao card={card} onDone={onClose} onCancel={() => setExcluindo(false)} />
      )}
    </Modal>
  );
}

function ExcluirCartao({
  card,
  onDone,
  onCancel,
}: {
  card: CardType;
  onDone: () => void;
  onCancel: () => void;
}) {
  const del = useDeleteCard();
  return (
    <ConfirmDialog
      title="Excluir cartão"
      itemName={card.name}
      consequences={[
        "Só dá para excluir cartão sem nenhuma compra registrada.",
        "Com histórico, a API recusa e o caminho é arquivar.",
      ]}
      pending={del.isPending}
      error={(del.error as ApiError | null)?.message ?? null}
      onCancel={onCancel}
      onConfirm={() => del.mutate(card.id, { onSuccess: onDone })}
    />
  );
}

// ---------- Categorias ----------

/** Agrupadas por tipo, uma linha curta por categoria.
 *
 * A versão anterior era uma grade de 23 cards, cada um com Editar, Arquivar e
 * Excluir — 69 botões pra uma tela que se abre uma vez por mês. Agora a linha
 * abre a folha da categoria, e tudo que se faz com ela mora lá.
 */
function Categorias() {
  const { data: categorias, isLoading, error } = useCategoriesComUso();
  const [editando, setEditando] = useState<CategoryComUso | null>(null);
  const [criando, setCriando] = useState<CategoryType | null>(null);
  const [verArquivadas, setVerArquivadas] = useState(false);

  const ativas = (categorias ?? []).filter((c) => !c.archived);
  const arquivadas = (categorias ?? []).filter((c) => c.archived);

  return (
    <>
      <div className="sec-title">
        <h2>Categorias</h2>
        <button className="link" onClick={() => setCriando("expense")}>+ Nova</button>
      </div>

      {isLoading && <div className="skel" style={{ height: 200 }} />}
      {error && <div className="error-box">{(error as ApiError).message}</div>}

      {GRUPOS.map(({ tipo, titulo }) => {
        const doTipo = ativas.filter((c) => c.type === tipo);
        if (doTipo.length === 0) return null;
        return (
          <section key={tipo} aria-label={titulo}>
            <div className="grupo-rotulo">{titulo} · {doTipo.length}</div>
            <div className="list cat-lista">
              {doTipo.map((c) => (
                <LinhaCategoria key={c.id} c={c} onAbrir={() => setEditando(c)} />
              ))}
            </div>
          </section>
        );
      })}

      {arquivadas.length > 0 && (
        <>
          <button
            className="btn btn-ghost btn-sm btn-block"
            style={{ marginTop: "var(--s3)" }}
            onClick={() => setVerArquivadas((v) => !v)}
            aria-expanded={verArquivadas}
          >
            {verArquivadas ? "Esconder arquivadas" : `Ver ${arquivadas.length} arquivada${arquivadas.length > 1 ? "s" : ""}`}
          </button>
          {verArquivadas && (
            <div className="list cat-lista" style={{ marginTop: "var(--s2)", opacity: 0.7 }}>
              {arquivadas.map((c) => (
                <LinhaCategoria key={c.id} c={c} onAbrir={() => setEditando(c)} />
              ))}
            </div>
          )}
        </>
      )}

      {criando && (
        <CategoryForm
          tipoInicial={criando}
          todas={categorias ?? []}
          onClose={() => setCriando(null)}
        />
      )}
      {editando && (
        <CategoryForm
          category={editando}
          todas={categorias ?? []}
          onClose={() => setEditando(null)}
        />
      )}
    </>
  );
}

function LinhaCategoria({ c, onAbrir }: { c: CategoryComUso; onAbrir: () => void }) {
  const usos = c.transactions + c.purchases;
  return (
    <button className="row" onClick={onAbrir}>
      <div className="avatar" style={{ background: fundoDaCor(c.color, 24) }} aria-hidden>
        {c.icon || "•"}
      </div>
      <div className="mid">
        <div className="t">{c.name}</div>
      </div>
      <span className="uso tnum">
        {usos > 0 ? `${usos} lanç.` : "sem uso"}
      </span>
      <MarcaEditavel />
    </button>
  );
}

function CategoryForm({
  category,
  tipoInicial = "expense",
  todas,
  onClose,
}: {
  category?: CategoryComUso;
  tipoInicial?: CategoryType;
  todas: CategoryComUso[];
  onClose: () => void;
}) {
  const isEdit = !!category;
  const [form, setForm] = useState({
    name: category?.name ?? "",
    type: category?.type ?? tipoInicial,
    // Categoria nova sugere a primeira cor da paleta que ninguém usa ainda: é
    // o que evita a sexta categoria vermelha.
    color: category?.color ?? proximaCorLivre(todas.map((c) => c.color)),
    icon: category?.icon ?? "🛒",
  });
  const [outroEmoji, setOutroEmoji] = useState(false);
  const [excluindo, setExcluindo] = useState(false);

  const create = useCreateCategory();
  const update = useUpdateCategory();
  const pending = create.isPending || update.isPending;
  const err = (create.error || update.error) as ApiError | null;

  // Tipo travado com histórico: a API recusa (409), e a tela nem oferece.
  const usos = category ? category.transactions + category.purchases + category.budgets : 0;
  const tipoTravado = isEdit && usos > 0;

  const emojiNaGrade = EMOJIS.some((g) => g.itens.includes(form.icon));
  useEffect(() => {
    if (isEdit && !emojiNaGrade) setOutroEmoji(true);
    // Só na abertura: depois, a escolha da pessoa manda.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Cor que veio de antes da paleta fechada: aparece como opção "atual", pra
  // salvar outra coisa não trocar a cor sem a pessoa pedir.
  const corLegada = category && !ehCorDaPaleta(category.color) ? category.color : null;

  // Aviso de nome repetido já na tela, antes da API recusar.
  const repetida = useMemo(() => {
    const alvo = form.name.trim().replace(/\s+/g, " ").toLocaleLowerCase("pt-BR");
    if (!alvo) return null;
    return (
      todas.find(
        (c) =>
          c.id !== category?.id &&
          c.type === form.type &&
          c.name.trim().replace(/\s+/g, " ").toLocaleLowerCase("pt-BR") === alvo
      ) ?? null
    );
  }, [form.name, form.type, todas, category?.id]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const payload = {
      name: form.name.trim(),
      type: form.type,
      color: form.color,
      icon: form.icon.trim() || "•",
    };
    if (isEdit) update.mutate({ id: category!.id, data: payload }, { onSuccess: onClose });
    else create.mutate(payload, { onSuccess: onClose });
  }

  return (
    <Modal
      title={isEdit ? "Editar categoria" : "Nova categoria"}
      onClose={onClose}
      footer={
        <>
          {isEdit ? (
            <button type="button" className="btn btn-danger" onClick={() => setExcluindo(true)}>
              Excluir
            </button>
          ) : (
            <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          )}
          <button
            type="submit"
            form="cat-form"
            className="btn btn-primary"
            disabled={pending || !form.name.trim() || !!repetida}
          >
            {pending ? "Salvando…" : "Salvar"}
          </button>
        </>
      }
    >
      <form id="cat-form" className="m-body" onSubmit={submit}>
        {/* A prévia é a linha como ela vai aparecer nas listas. */}
        <div className="previa-cat" aria-hidden>
          <div className="avatar" style={{ background: fundoDaCor(form.color, 24) }}>
            {form.icon || "•"}
          </div>
          <div className="t">{form.name.trim() || "Nome da categoria"}</div>
        </div>

        <div className="field">
          <label htmlFor="c-name">Nome</label>
          <input
            id="c-name"
            value={form.name}
            autoFocus={!isEdit}
            maxLength={40}
            placeholder="Ex.: Mercado"
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          {repetida && (
            <div className="hint" style={{ color: "var(--neg)" }}>
              Já existe “{repetida.name}”{repetida.archived ? " (arquivada — desarquive-a)" : ""}.
            </div>
          )}
        </div>

        <div className="field">
          <span className="label">Tipo</span>
          {tipoTravado ? (
            <>
              <div className="badge">{CATEGORY_TYPE_LABEL[form.type]}</div>
              <div className="hint">
                Com {usos} {usos === 1 ? "registro" : "registros"}, o tipo não muda:
                trocar inverteria o sinal desse histórico.
              </div>
            </>
          ) : (
            <Segmentado
              rotulo="Tipo da categoria"
              opcoes={OPCOES_TIPO}
              valor={form.type}
              aoEscolher={(t) => setForm({ ...form, type: t })}
              largo
            />
          )}
        </div>

        <div className="field">
          <span className="label">Cor</span>
          <div className="paleta" role="radiogroup" aria-label="Cor da categoria">
            {corLegada && (
              <button
                type="button"
                role="radio"
                aria-checked={form.color === corLegada}
                aria-label="Cor atual"
                className={form.color === corLegada ? "on" : ""}
                style={{ background: corLegada }}
                onClick={() => setForm({ ...form, color: corLegada })}
              />
            )}
            {PALETA_CATEGORIAS.map((p) => (
              <button
                type="button"
                key={p.cor}
                role="radio"
                aria-checked={form.color === p.cor}
                aria-label={p.nome}
                title={p.nome}
                className={form.color.toLowerCase() === p.cor ? "on" : ""}
                style={{ background: p.cor }}
                onClick={() => setForm({ ...form, color: p.cor })}
              />
            ))}
          </div>
          {corLegada && (
            <div className="hint">A primeira é a cor de antes. As outras funcionam melhor juntas nos gráficos.</div>
          )}
        </div>

        <div className="field">
          <span className="label">Ícone</span>
          <div className="emoji-rolagem">
            {EMOJIS.map((g) => (
              <div key={g.grupo}>
                <div className="emoji-grupo">{g.grupo}</div>
                <div className="emoji-grade">
                  {g.itens.map((e) => (
                    <button
                      type="button"
                      key={e}
                      className={form.icon === e ? "on" : ""}
                      aria-label={`Ícone ${e}`}
                      aria-pressed={form.icon === e}
                      onClick={() => {
                        setForm({ ...form, icon: e });
                        setOutroEmoji(false);
                      }}
                    >
                      {e}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
          {outroEmoji ? (
            <input
              aria-label="Outro emoji"
              value={form.icon}
              placeholder="Cole um emoji"
              style={{ marginTop: "var(--s2)" }}
              onChange={(e) => setForm({ ...form, icon: primeiroGrafema(e.target.value) })}
            />
          ) : (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              style={{ marginTop: "var(--s2)" }}
              onClick={() => setOutroEmoji(true)}
            >
              Outro emoji…
            </button>
          )}
        </div>

        {isEdit && (
          <ArquivarCategoria category={category!} onDone={onClose} />
        )}

        {err && <div className="error-box">{err.message}</div>}
      </form>

      {excluindo && category && (
        <ExcluirCategoria category={category} todas={todas} onDone={onClose} onCancel={() => setExcluindo(false)} />
      )}
    </Modal>
  );
}

/** Fica só com o primeiro emoji colado. Por grafema, não por caractere: um
 *  `slice(0, 2)` cortaria 👨‍👩‍👧 no meio e gravaria meio rosto. */
function primeiroGrafema(texto: string): string {
  const limpo = texto.trim();
  if (!limpo) return "";
  const Seg = (Intl as unknown as { Segmenter?: new (l: string, o: object) => { segment: (s: string) => Iterable<{ segment: string }> } }).Segmenter;
  if (Seg) {
    for (const { segment } of new Seg("pt-BR", { granularity: "grapheme" }).segment(limpo)) return segment;
  }
  return Array.from(limpo).slice(0, 2).join("");
}

function ArquivarCategoria({ category, onDone }: { category: Category; onDone: () => void }) {
  const update = useUpdateCategory();
  return (
    <div className="field">
      <button
        type="button"
        className="btn btn-sm"
        disabled={update.isPending}
        onClick={() =>
          update.mutate({ id: category.id, data: { archived: !category.archived } }, { onSuccess: onDone })
        }
      >
        {category.archived ? "Desarquivar" : "Arquivar"}
      </button>
      <div className="hint">
        {category.archived
          ? "Volta a aparecer no formulário de lançamento."
          : "Some do formulário de lançamento. O histórico dela continua contando nos meses em que foi usada."}
      </div>
    </div>
  );
}

/** Excluir categoria, com a opção de entregar os lançamentos a outra.
 *
 * Mover é o caminho principal: quase nunca se quer "apagar UBER" — quer-se
 * "UBER virou Transporte". O seletor só oferece categorias do mesmo tipo;
 * mover despesa pra receita inverteria o sinal, e a API recusa.
 */
function ExcluirCategoria({
  category,
  todas,
  onDone,
  onCancel,
}: {
  category: Category;
  todas: Category[];
  onDone: () => void;
  onCancel: () => void;
}) {
  const del = useDeleteCategory();
  const [destino, setDestino] = useState<string>("");

  const candidatas = todas.filter((c) => c.id !== category.id && c.type === category.type);

  return (
    <ConfirmDialog
      title="Excluir categoria"
      itemName={category.name}
      consequences={[
        destino
          ? `Os lançamentos passam para "${todas.find((c) => String(c.id) === destino)?.name}".`
          : "Categoria com lançamento não é apagada — escolha para onde eles vão, ou arquive em vez de excluir.",
        "As metas desta categoria vão junto, em todos os meses.",
      ]}
      pending={del.isPending}
      error={(del.error as ApiError | null)?.message ?? null}
      onCancel={onCancel}
      onConfirm={() =>
        del.mutate({ id: category.id, moverPara: destino ? Number(destino) : null }, { onSuccess: onDone })
      }
    >
      {candidatas.length > 0 && (
        <div className="field">
          <label htmlFor="mover-para">Mover os lançamentos para</label>
          <select id="mover-para" value={destino} onChange={(e) => setDestino(e.target.value)}>
            <option value="">— não mover —</option>
            {candidatas.map((c) => (
              <option key={c.id} value={c.id}>
                {c.icon} {c.name}
                {c.archived ? " (arquivada)" : ""}
              </option>
            ))}
          </select>
          <span className="hint">
            Só categorias de {CATEGORY_TYPE_LABEL[category.type].toLowerCase()}: mover
            para outro tipo trocaria o sinal dos lançamentos.
          </span>
        </div>
      )}
    </ConfirmDialog>
  );
}

/** Onde se informa a taxa CDI atual — um lugar só pro país inteiro. Digitado à
 *  mão: buscar automático exigiria um serviço externo que a CSP bloqueia. */
function CdiCard() {
  const perfil = usePerfil();
  const salvar = useSetCdi();
  const [valor, setValor] = useState("");

  useEffect(() => {
    if (perfil.data?.cdi_annual != null) setValor(String(perfil.data.cdi_annual));
  }, [perfil.data?.cdi_annual]);

  const atual = perfil.data?.cdi_annual;
  const mudou = valor.trim() !== (atual != null ? String(atual) : "");

  return (
    <div className="field" style={{ marginBottom: 0 }}>
      <label htmlFor="cdi">CDI hoje (% ao ano)</label>
      <div style={{ display: "flex", gap: "var(--s2)" }}>
        <input
          id="cdi"
          inputMode="decimal"
          value={valor}
          placeholder="Ex.: 10,65"
          onChange={(e) => setValor(e.target.value)}
        />
        <button
          className="btn btn-primary"
          disabled={!mudou || salvar.isPending}
          onClick={() => salvar.mutate(parseMoney(valor))}
        >
          {salvar.isPending ? "…" : "Salvar"}
        </button>
      </div>
      <span className="hint">
        Usado para calcular quanto suas aplicações devem render. A projeção é
        bruta — não desconta imposto de renda.
      </span>
    </div>
  );
}
