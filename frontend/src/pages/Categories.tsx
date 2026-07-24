import { useState } from "react";
import Modal from "../components/Modal";
import {
  useCategories,
  useCreateCategory,
  useDeleteCategory,
  useUpdateCategory,
} from "../lib/queries";
import { ApiError } from "../lib/api";
import { CATEGORY_TYPE_LABEL, type Category, type CategoryType } from "../lib/types";

const TYPES: CategoryType[] = ["expense", "income", "investment"];

const EMPTY = { name: "", type: "expense" as CategoryType, color: "#f5b301", icon: "💸" };

export default function Categories() {
  const { data: categories, isLoading, error } = useCategories();
  const [editing, setEditing] = useState<Category | null>(null);
  const [creating, setCreating] = useState(false);

  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">Organização</div>
          <h1>Categorias</h1>
          <p>Os potes onde cada centavo é separado.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setCreating(true)}>+ Nova categoria</button>
      </div>

      {isLoading && <div className="panel"><div className="loading"><div className="spinner" />Carregando…</div></div>}
      {error && <div className="panel"><div className="error-box">{(error as ApiError).message}</div></div>}

      {categories && categories.length === 0 && (
        <div className="panel">
          <div className="empty">
            <div className="big">🏷️</div>
            Nenhuma categoria ainda. Crie a primeira para começar a lançar transações.
          </div>
        </div>
      )}

      {categories && categories.length > 0 && (
        <div className="cat-grid">
          {categories.map((c) => (
            <CategoryCard key={c.id} category={c} onEdit={() => setEditing(c)} />
          ))}
        </div>
      )}

      {creating && <CategoryForm onClose={() => setCreating(false)} />}
      {editing && <CategoryForm category={editing} onClose={() => setEditing(null)} />}
    </>
  );
}

function CategoryCard({ category, onEdit }: { category: Category; onEdit: () => void }) {
  const del = useDeleteCategory();
  return (
    <div className="cat-card">
      <div className="top">
        <div className="cat-icon" style={{ background: withAlpha(category.color, 0.16), color: category.color }}>
          {category.icon || "•"}
        </div>
        <div>
          <div className="cname">{category.name}</div>
          <span className={`badge ${category.type}`}>{CATEGORY_TYPE_LABEL[category.type]}</span>
        </div>
      </div>
      <div className="actions">
        <button className="btn btn-ghost btn-sm" onClick={onEdit}>Editar</button>
        <button
          className="btn btn-ghost btn-sm btn-danger"
          disabled={del.isPending}
          onClick={() => {
            if (confirm(`Excluir a categoria "${category.name}"?`)) del.mutate(category.id);
          }}
        >
          Excluir
        </button>
      </div>
    </div>
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
