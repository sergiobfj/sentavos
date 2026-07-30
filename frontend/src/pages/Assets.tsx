import { useMemo, useState } from "react";
import Modal from "../components/Modal";
import MoneyCell from "../components/MoneyCell";
import {
  useAssetSummary,
  useCreateAsset,
  useDeleteAsset,
  useSetAssetSnapshot,
  useUpdateAsset,
} from "../lib/queries";
import { usePeriod } from "../lib/period";
import { ApiError } from "../lib/api";
import { formatMoney, formatYm } from "../lib/format";
import {
  ASSET_CLASS_LABEL,
  ASSET_CLASS_ORDER,
  type Asset,
  type AssetClass,
  type AssetSummaryItem,
} from "../lib/types";

export default function Assets() {
  const { label, ym } = usePeriod();
  const { data, isLoading, error } = useAssetSummary();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<AssetSummaryItem | null>(null);

  const byClass = useMemo(() => {
    const groups = new Map<AssetClass, AssetSummaryItem[]>();
    for (const item of data?.items ?? []) {
      const list = groups.get(item.asset_class) ?? [];
      list.push(item);
      groups.set(item.asset_class, list);
    }
    return groups;
  }, [data]);

  const head = (
    <div className="page-head">
      <div>
        <div className="eyebrow">Estoque</div>
        <h1>Patrimônio</h1>
        <p>Tudo que você tem menos tudo que você deve, em {label}.</p>
      </div>
      {data && data.items.length > 0 && (
        <button className="btn btn-primary" onClick={() => setCreating(true)}>
          + Novo ativo
        </button>
      )}
    </div>
  );

  if (isLoading) {
    return (
      <>
        {head}
        <div className="panel">
          <div className="loading"><div className="spinner" />Carregando patrimônio…</div>
        </div>
      </>
    );
  }
  if (error) {
    return (
      <>
        {head}
        <div className="panel"><div className="error-box">{(error as ApiError).message}</div></div>
      </>
    );
  }

  if (!data || data.items.length === 0) {
    return (
      <>
        {head}
        <div className="panel">
          <div className="empty">
            <div className="big">🏦</div>
            Nenhum ativo cadastrado. Comece pela conta onde o dinheiro fica —
            depois entram renda fixa, investimentos, bens e dívidas.
            <div style={{ marginTop: 14 }}>
              <button className="btn btn-primary" onClick={() => setCreating(true)}>
                + Novo ativo
              </button>
            </div>
          </div>
        </div>
        {creating && <AssetForm onClose={() => setCreating(false)} />}
      </>
    );
  }

  const change = data.net_worth - data.previous_net_worth;

  return (
    <>
      {head}

      <div className="stat-grid">
        <Stat
          label="Patrimônio líquido"
          value={data.net_worth}
          tone={data.net_worth >= 0 ? "pos" : "neg"}
          sub="Ativos − dívidas"
        />
        <Stat label="Ativos" value={data.assets} tone="gold" />
        <Stat label="Dívidas" value={data.liabilities} tone="neg" />
        <Stat
          label="Variação no mês"
          value={change}
          tone={change >= 0 ? "pos" : "neg"}
          sub={`Contra ${formatMoney(data.previous_net_worth)} no mês anterior`}
          signed
        />
      </div>

      {ASSET_CLASS_ORDER.map((classe) => {
        const items = byClass.get(classe) ?? [];
        if (items.length === 0) return null;
        return (
          <ClassSection
            key={classe}
            classe={classe}
            items={items}
            ym={ym}
            onEdit={setEditing}
          />
        );
      })}

      {creating && <AssetForm onClose={() => setCreating(false)} />}
      {editing && (
        <AssetForm
          asset={{
            id: editing.asset_id,
            name: editing.name,
            asset_class: editing.asset_class,
            note: editing.note,
          }}
          onClose={() => setEditing(null)}
        />
      )}
    </>
  );
}

function ClassSection({
  classe,
  items,
  ym,
  onEdit,
}: {
  classe: AssetClass;
  items: AssetSummaryItem[];
  ym: string;
  onEdit: (item: AssetSummaryItem) => void;
}) {
  const total = items.reduce((acc, i) => acc + i.value, 0);
  const isDebt = classe === "debt";

  return (
    <div className="panel" style={{ marginTop: 16 }}>
      <div className="panel-head">
        <div>
          <h2>{ASSET_CLASS_LABEL[classe]}</h2>
          {isDebt && (
            <div className="hint" style={{ marginTop: 3 }}>
              Sai subtraindo do patrimônio líquido
            </div>
          )}
        </div>
        <div className="num" style={{ fontSize: 13.5, color: isDebt ? "var(--expense)" : "var(--text-dim)" }}>
          {formatMoney(total)}
        </div>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Ativo</th>
              <th style={{ width: 150 }}>Saldo</th>
              <th>Referência</th>
              <th className="num">Variação</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <AssetRow key={item.asset_id} item={item} ym={ym} onEdit={() => onEdit(item)} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AssetRow({
  item,
  ym,
  onEdit,
}: {
  item: AssetSummaryItem;
  ym: string;
  onEdit: () => void;
}) {
  const { period } = usePeriod();
  const setSnapshot = useSetAssetSnapshot();
  // Valor herdado de mês anterior não é editável aqui: o input fica vazio e o
  // saldo antigo vira placeholder, pra não parecer que o mês já foi preenchido.
  const inherited = item.snapshot_id == null && item.as_of != null;

  return (
    <tr>
      <td>
        <div style={{ fontWeight: 600 }}>{item.name}</div>
        {item.note && (
          <div style={{ fontSize: 12.5, color: "var(--text-faint)" }}>{item.note}</div>
        )}
      </td>
      <td>
        <MoneyCell
          saved={item.snapshot_id != null ? item.value : null}
          ariaLabel={`Saldo de ${item.name}`}
          placeholder={inherited ? formatMoney(item.value) : "0,00"}
          pending={setSnapshot.isPending}
          onCommit={(amount) =>
            setSnapshot.mutate({
              asset_id: item.asset_id,
              year: period.year,
              month: period.month,
              value: amount ?? 0,
            })
          }
        />
      </td>
      <td>
        {item.as_of == null ? (
          <span style={{ fontSize: 12.5, color: "var(--text-faint)" }}>sem saldo</span>
        ) : item.as_of === ym ? (
          <span className="badge income">deste mês</span>
        ) : (
          <span className="badge" style={{ color: "var(--text-dim)", background: "var(--surface-3)" }}>
            de {formatYm(item.as_of)}
          </span>
        )}
      </td>
      <td className="num" style={{ fontWeight: 650, color: changeColor(item) }}>
        {item.change === 0 ? "—" : formatSigned(item.change)}
      </td>
      <td>
        <div className="row-actions">
          <button className="btn btn-ghost btn-sm" onClick={onEdit}>Editar</button>
          <DeleteAssetButton id={item.asset_id} name={item.name} />
        </div>
      </td>
    </tr>
  );
}

function DeleteAssetButton({ id, name }: { id: number; name: string }) {
  const del = useDeleteAsset();
  return (
    <button
      className="btn btn-ghost btn-sm btn-danger"
      disabled={del.isPending}
      onClick={() => {
        if (confirm(`Excluir "${name}"? O histórico de saldos vai junto.`)) del.mutate(id);
      }}
    >
      Excluir
    </button>
  );
}

const EMPTY = { name: "", asset_class: "checking" as AssetClass, note: null as string | null };

function AssetForm({ asset, onClose }: { asset?: Asset; onClose: () => void }) {
  const isEdit = !!asset;
  const [form, setForm] = useState({
    name: asset?.name ?? EMPTY.name,
    asset_class: asset?.asset_class ?? EMPTY.asset_class,
    note: asset?.note ?? "",
  });
  const create = useCreateAsset();
  const update = useUpdateAsset();
  const pending = create.isPending || update.isPending;
  const err = (create.error || update.error) as ApiError | null;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const payload = {
      name: form.name.trim(),
      asset_class: form.asset_class,
      note: form.note.trim() || null,
    };
    if (isEdit) {
      update.mutate({ id: asset!.id, data: payload }, { onSuccess: onClose });
    } else {
      create.mutate(payload, { onSuccess: onClose });
    }
  }

  return (
    <Modal
      title={isEdit ? "Editar ativo" : "Novo ativo"}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          <button
            type="submit"
            form="asset-form"
            className="btn btn-primary"
            disabled={pending || !form.name.trim()}
          >
            {pending ? "Salvando…" : "Salvar"}
          </button>
        </>
      }
    >
      <form id="asset-form" className="m-body" onSubmit={submit}>
        <div className="field">
          <label htmlFor="a-name">Nome</label>
          <input
            id="a-name"
            value={form.name}
            autoFocus
            placeholder="Ex.: Nubank, Tesouro Selic, Apartamento"
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </div>
        <div className="field">
          <label htmlFor="a-class">Classe</label>
          <select
            id="a-class"
            value={form.asset_class}
            onChange={(e) => setForm({ ...form, asset_class: e.target.value as AssetClass })}
          >
            {ASSET_CLASS_ORDER.map((c) => (
              <option key={c} value={c}>{ASSET_CLASS_LABEL[c]}</option>
            ))}
          </select>
          <span className="hint">
            Dívida subtrai do patrimônio líquido. Renda fixa, renda variável e cripto
            são o que a aba de Investimento vai olhar.
          </span>
        </div>
        <div className="field">
          <label htmlFor="a-note">Observação</label>
          <textarea
            id="a-note"
            value={form.note}
            placeholder="Opcional"
            onChange={(e) => setForm({ ...form, note: e.target.value })}
          />
        </div>
        {err && <div className="error-box" style={{ padding: 0, textAlign: "left" }}>{err.message}</div>}
      </form>
    </Modal>
  );
}

function Stat({
  label,
  value,
  tone,
  sub,
  signed,
}: {
  label: string;
  value: number;
  tone: "pos" | "neg" | "gold";
  sub?: string;
  signed?: boolean;
}) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className={`value ${tone}`}>{signed ? formatSigned(value) : formatMoney(value)}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

// Dívida que cresce é ruim, ativo que cresce é bom — a cor segue isso.
function changeColor(item: AssetSummaryItem): string {
  if (item.change === 0) return "var(--text-faint)";
  const good = item.liability ? item.change < 0 : item.change > 0;
  return good ? "var(--income)" : "var(--expense)";
}

function formatSigned(value: number): string {
  return `${value > 0 ? "+" : ""}${formatMoney(value)}`;
}
