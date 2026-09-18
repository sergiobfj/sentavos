import { useEffect, useState } from "react";
import { parseMoney } from "../lib/format";
import Modal from "../components/Modal";
import ConfirmDialog from "../components/ConfirmDialog";
import {
  useCategories,
  useCreateCategory,
  useDeleteCategory,
  useUpdateCategory,
  usePerfil,
  useSetCdi,
} from "../lib/queries";
import { ApiError } from "../lib/api";
import { CATEGORY_TYPE_LABEL, type Category, type CategoryType } from "../lib/types";

const TYPES: CategoryType[] = ["expense", "income", "investment"];

const EMPTY = { name: "", type: "expense" as CategoryType, color: "#f5b301", icon: "💸" };

export default function Settings() {
  // Mostra as arquivadas também: é aqui que se desarquiva.
  const { data: categories, isLoading, error } = useCategories(true);
  const [editing, setEditing] = useState<Category | null>(null);
  const [creating, setCreating] = useState(false);

  return (
    <>
      <div className="sec-title" style={{ marginTop: 0 }}>
        <h2>Rendimento</h2>
      </div>
      <CdiCard />

      <div className="sec-title">
        <h2>Categorias</h2>
        <button className="link" onClick={() => setCreating(true)}>+ Nova</button>
      </div>

      {isLoading && <div className="skel" style={{ height: 200, borderRadius: "var(--r)" }} />}
      {error && <div className="error-box">{(error as ApiError).message}</div>}

      {categories && categories.length === 0 && (
        <div className="empty">
          <div className="big">🏷️</div>
          <div className="tit">Nenhuma categoria ainda</div>
          <div>Crie a primeira para começar a lançar.</div>
        </div>
      )}

      {categories && categories.length > 0 && (
        <div className="cat-grid">
          {categories.map((c) => (
            <CategoryCard
              key={c.id}
              category={c}
              todas={categories}
              onEdit={() => setEditing(c)}
            />
          ))}
        </div>
      )}

      {creating && <CategoryForm onClose={() => setCreating(false)} />}
      {editing && <CategoryForm category={editing} onClose={() => setEditing(null)} />}
    </>
  );
}

function CategoryCard({
  category,
  todas,
  onEdit,
}: {
  category: Category;
  todas: Category[];
  onEdit: () => void;
}) {
  const update = useUpdateCategory();
  const [excluindo, setExcluindo] = useState(false);
  return (
    <div className="cat-card" style={category.archived ? { opacity: 0.5 } : undefined}>
      <div className="top">
        <div className="cat-icon" style={{ background: withAlpha(category.color, 0.16), color: category.color }}>
          {category.icon || "•"}
        </div>
        <div>
          <div className="cname">{category.name}</div>
          <span className={`badge ${category.type}`}>{CATEGORY_TYPE_LABEL[category.type]}</span>
          {category.archived && <span className="badge" style={{ marginLeft: 6 }}>arquivada</span>}
        </div>
      </div>
      <div className="actions">
        <button className="btn btn-ghost btn-sm" onClick={onEdit}>Editar</button>
        {/* Arquivar e não excluir: os lançamentos antigos apontam pra esta
            categoria, e apagá-la levaria o histórico junto. Excluir continua
            existindo só para categoria que nunca foi usada — e nesse caso a
            API deixa, porque não há o que perder. */}
        <button
          className="btn btn-ghost btn-sm"
          disabled={update.isPending}
          onClick={() =>
            update.mutate({ id: category.id, data: { archived: !category.archived } })
          }
        >
          {category.archived ? "Desarquivar" : "Arquivar"}
        </button>
        <button
          className="btn btn-ghost btn-sm btn-danger"
          onClick={() => setExcluindo(true)}
        >
          Excluir
        </button>
      </div>

      {excluindo && (
        <ExcluirCategoria
          category={category}
          todas={todas}
          onDone={() => setExcluindo(false)}
        />
      )}
    </div>
  );
}

/** Excluir categoria, com a opção de entregar os lançamentos a outra.
 *
 * Mover é o caminho principal, não o alternativo: quase nunca se quer "apagar
 * UBER" — quer-se "UBER virou Transporte". Sem essa saída, reorganizar as
 * categorias herdadas da planilha exigia apagar lançamento por lançamento, que
 * é perder histórico pra arrumar nome.
 *
 * O seletor só oferece categorias do mesmo tipo. Mover uma despesa pra uma
 * categoria de receita inverteria o sinal do lançamento e faria o mês inteiro
 * mentir — a API recusa, e a tela nem chega a oferecer.
 */
function ExcluirCategoria({
  category,
  todas,
  onDone,
}: {
  category: Category;
  todas: Category[];
  onDone: () => void;
}) {
  const del = useDeleteCategory();
  const [destino, setDestino] = useState<string>("");

  const candidatas = todas.filter(
    (c) => c.id !== category.id && c.type === category.type
  );

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
      onCancel={onDone}
      onConfirm={() =>
        del.mutate(
          { id: category.id, moverPara: destino ? Number(destino) : null },
          { onSuccess: onDone }
        )
      }
    >
      {candidatas.length > 0 && (
        <div className="field">
          <label htmlFor="mover-para">Mover os lançamentos para</label>
          <select
            id="mover-para"
            value={destino}
            onChange={(e) => setDestino(e.target.value)}
          >
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

function CategoryForm({ category, onClose }: { category?: Category; onClose: () => void }) {
  const isEdit = !!category;
  const [form, setForm] = useState(category ?? EMPTY);
  const create = useCreateCategory();
  const update = useUpdateCategory();
  const pending = create.isPending || update.isPending;
  const err = (create.error || update.error) as ApiError | null;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const payload = { name: form.name.trim(), type: form.type, color: form.color, icon: form.icon.trim() || "•" };
    if (isEdit) {
      update.mutate({ id: category!.id, data: payload }, { onSuccess: onClose });
    } else {
      create.mutate(payload, { onSuccess: onClose });
    }
  }

  return (
    <Modal
      title={isEdit ? "Editar categoria" : "Nova categoria"}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          <button type="submit" form="cat-form" className="btn btn-primary" disabled={pending || !form.name.trim()}>
            {pending ? "Salvando…" : "Salvar"}
          </button>
        </>
      }
    >
      <form id="cat-form" className="m-body" onSubmit={submit}>
        <div className="field">
          <label htmlFor="c-name">Nome</label>
          <input id="c-name" value={form.name} autoFocus placeholder="Ex.: Mercado"
            onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </div>
        <div className="field row2">
          <div className="field">
            <label htmlFor="c-type">Tipo</label>
            <select id="c-type" value={form.type}
              onChange={(e) => setForm({ ...form, type: e.target.value as CategoryType })}>
              {TYPES.map((t) => (
                <option key={t} value={t}>{CATEGORY_TYPE_LABEL[t]}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="c-color">Cor</label>
            <input id="c-color" type="color" value={form.color}
              onChange={(e) => setForm({ ...form, color: e.target.value })} />
          </div>
        </div>
        <div className="field">
          <label htmlFor="c-icon">Ícone</label>
          <input id="c-icon" value={form.icon} placeholder="Um emoji, ex.: 🛒" maxLength={4}
            onChange={(e) => setForm({ ...form, icon: e.target.value })} />
          <span className="hint">Use um emoji para reconhecer a categoria de relance.</span>
        </div>
        {err && <div className="error-box" style={{ padding: 0, textAlign: "left" }}>{err.message}</div>}
      </form>
    </Modal>
  );
}

// converte #rrggbb + alpha em rgba() para os fundos suaves
function withAlpha(hex: string, alpha: number): string {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  if (!m) return hex;
  const r = parseInt(m[1], 16);
  const g = parseInt(m[2], 16);
  const b = parseInt(m[3], 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}


/** Onde se informa a taxa CDI atual.
 *
 * Um lugar só pro país inteiro, e não um campo por aplicação: repetido em cada
 * ativo, atualizar a Selic viraria editar cinco lugares e esquecer o sexto.
 *
 * O valor é digitado à mão de propósito — buscar automático exigiria uma
 * chamada a serviço externo, que a CSP do app bloqueia e que quebraria calada
 * no dia em que o serviço saísse do ar. Um número que muda poucas vezes por ano
 * não justifica essa dependência.
 */
function CdiCard() {
  const perfil = usePerfil();
  const salvar = useSetCdi();
  const [valor, setValor] = useState("");

  // Sincroniza quando o dado chega: o estado inicial nasce vazio porque a
  // query ainda não respondeu na primeira renderização.
  useEffect(() => {
    if (perfil.data?.cdi_annual != null) setValor(String(perfil.data.cdi_annual));
  }, [perfil.data?.cdi_annual]);

  const atual = perfil.data?.cdi_annual;
  const mudou = valor.trim() !== (atual != null ? String(atual) : "");

  return (
    <div className="card card-pad">
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
    </div>
  );
}
