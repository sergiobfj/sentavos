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
import { formatMoney, formatYm, parseMoney } from "../lib/format";
import {
  ASSET_CLASS_LABEL,
  ASSET_CLASS_ORDER,
  type Asset,
  type AssetClass,
  type AssetSummaryItem,
} from "../lib/types";

// Só estas classes rendem juros. Conta corrente, imóvel e carro não rendem, e
// oferecer um campo de taxa neles seria convite a preencher errado.
const RENDEM: AssetClass[] = ["fixed_income", "equity", "crypto"];

export default function Assets() {
  const { ym } = usePeriod();
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

  if (isLoading) return <Esqueleto />;
  if (error) return <div className="error-box">{(error as ApiError).message}</div>;

  if (!data || data.items.length === 0) {
    return (
      <>
        <div className="empty">
          <div className="big">🏦</div>
          <div className="tit">Nenhum ativo cadastrado</div>
          <div>
            Comece pela conta onde o dinheiro fica — depois entram renda fixa,
            investimentos, bens e dívidas.
          </div>
          <div style={{ marginTop: "var(--s4)" }}>
            <button className="btn btn-primary" onClick={() => setCreating(true)}>
              Cadastrar ativo
            </button>
          </div>
        </div>
        {creating && <AssetForm onClose={() => setCreating(false)} />}
      </>
    );
  }

  const variacao = data.net_worth - data.previous_net_worth;
  const temDividas = data.liabilities > 0;

  return (
    <>
      <section className="hero">
        <div className="rot">Patrimônio líquido</div>
        <div className={`big tnum ${data.net_worth >= 0 ? "pos" : "neg"}`}>
          {formatMoney(data.net_worth)}
        </div>
        {Math.abs(variacao) >= 0.01 && (
          <div className={`delta ${variacao > 0 ? "pos" : "neg"}`}>
            <span aria-hidden>{variacao > 0 ? "↑" : "↓"}</span>
            {formatMoney(Math.abs(variacao))} no mês
          </div>
        )}
      </section>

      {/* A linha de dívidas só aparece quando existe dívida. Um "R$ 0,00" fixo
          ali ocuparia o mesmo espaço pra não informar nada. */}
      <div className="duo" style={{ gridTemplateColumns: temDividas ? "1fr 1fr" : "1fr" }}>
        <div className="card">
          <div className="rot">Tudo que você tem</div>
          <div className="val tnum">{formatMoney(data.assets)}</div>
        </div>
        {temDividas && (
          <div className="card">
            <div className="rot">Tudo que você deve</div>
            <div className="val neg tnum">{formatMoney(data.liabilities)}</div>
          </div>
        )}
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

      <button
        className="btn btn-block"
        style={{ marginTop: "var(--s5)" }}
        onClick={() => setCreating(true)}
      >
        + Novo ativo
      </button>

      {creating && <AssetForm onClose={() => setCreating(false)} />}
      {editing && (
        <AssetForm
          asset={{
            id: editing.asset_id,
            name: editing.name,
            asset_class: editing.asset_class,
            note: editing.note,
            cdi_percent: editing.cdi_percent,
          }}
          onClose={() => setEditing(null)}
        />
      )}
    </>
  );
}

function Esqueleto() {
  return (
    <>
      <div className="skel" style={{ height: 132, borderRadius: "var(--r-lg)" }} />
      <div className="duo" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <div className="skel" style={{ height: 72 }} />
        <div className="skel" style={{ height: 72 }} />
      </div>
      <div className="sec-title"><h2>Seus ativos</h2></div>
      <div className="skel" style={{ height: 200, borderRadius: "var(--r)" }} />
    </>
  );
}

const ICONE_CLASSE: Record<string, string> = {
  checking: "🏦", fixed_income: "📄", equity: "📊", crypto: "₿",
  real_estate: "🏠", vehicle: "🚗", debt: "💳",
};

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
  const ehDivida = classe === "debt";

  return (
    <>
      <div className="sec-title">
        <h2>{ASSET_CLASS_LABEL[classe]}</h2>
        <span
          className="tnum"
          style={{ fontSize: 13, color: ehDivida ? "var(--neg)" : "var(--text-dim)" }}
        >
          {formatMoney(total)}
        </span>
      </div>
      <div className="list">
        {items.map((item) => (
          <AssetRow
            key={item.asset_id}
            item={item}
            ym={ym}
            onEdit={() => onEdit(item)}
          />
        ))}
      </div>
    </>
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
  const herdado = item.snapshot_id == null && item.as_of != null;

  return (
    <div className="row asset-row">
      <button
        className="avatar"
        onClick={onEdit}
        aria-label={`Editar ${item.name}`}
        style={{
          border: 0, cursor: "pointer",
          background: `color-mix(in srgb, ${item.liability ? "var(--neg)" : "var(--gold)"} 20%, transparent)`,
        }}
      >
        {ICONE_CLASSE[item.asset_class] ?? "💰"}
      </button>

      <div className="mid">
        <div className="t">{item.name}</div>
        <div className="s">
          {/* O estado do saldo vira texto curto em vez de coluna própria. Num
              celular, "de mai/2026" ao lado do nome diz o mesmo que uma coluna
              "Referência" e não custa um quinto da largura da tela. */}
          {item.as_of == null
            ? "sem saldo"
            : item.as_of === ym
              ? "atualizado neste mês"
              : `de ${formatYm(item.as_of)}`}
          {item.change !== 0 && item.as_of != null && (
            <span style={{ color: changeColor(item) }}>
              {" · "}{formatSigned(item.change)}
            </span>
          )}
        </div>
      </div>

      <div className="saldo-input">
        <MoneyCell
          saved={item.snapshot_id != null ? item.value : null}
          ariaLabel={`Saldo de ${item.name}`}
          placeholder={herdado ? formatMoney(item.value) : "0,00"}
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
      </div>
    </div>
  );
}

function DeleteAssetButton({
  id,
  name,
  onDone,
}: {
  id: number;
  name: string;
  onDone: () => void;
}) {
  const del = useDeleteAsset();
  return (
    <button
      type="button"
      className="btn btn-danger"
      disabled={del.isPending}
      onClick={() => {
        if (confirm(`Excluir "${name}"? O histórico de saldos vai junto.`)) {
          del.mutate(id, { onSuccess: onDone });
        }
      }}
    >
      {del.isPending ? "Excluindo…" : "Excluir"}
    </button>
  );
}

const EMPTY = {
  name: "",
  asset_class: "checking" as AssetClass,
  note: null as string | null,
};

function AssetForm({ asset, onClose }: { asset?: Asset; onClose: () => void }) {
  const isEdit = !!asset;
  const [form, setForm] = useState({
    name: asset?.name ?? EMPTY.name,
    asset_class: asset?.asset_class ?? EMPTY.asset_class,
    note: asset?.note ?? "",
    cdi_percent: asset?.cdi_percent?.toString() ?? "",
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
      // Vazio vira null, e não zero: "não sei a taxa" e "a taxa é zero" são
      // coisas diferentes, e só a segunda deveria projetar rendimento zero.
      cdi_percent: parseMoney(form.cdi_percent),
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
          {isEdit ? (
            <DeleteAssetButton id={asset!.id} name={asset!.name} onDone={onClose} />
          ) : (
            <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          )}
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
        {RENDEM.includes(form.asset_class) && (
          <div className="field">
            <label htmlFor="a-cdi">Rende quanto do CDI?</label>
            <input
              id="a-cdi"
              inputMode="decimal"
              value={form.cdi_percent}
              placeholder="Ex.: 115"
              onChange={(e) => setForm({ ...form, cdi_percent: e.target.value })}
            />
            <span className="hint">
              Em porcentagem, como o banco mostra: 115 para "115% do CDI". Deixe
              vazio se não render juros.
            </span>
          </div>
        )}

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

// Dívida que cresce é ruim, ativo que cresce é bom — a cor segue isso.
function changeColor(item: AssetSummaryItem): string {
  if (item.change === 0) return "var(--text-faint)";
  const good = item.liability ? item.change < 0 : item.change > 0;
  return good ? "var(--income)" : "var(--expense)";
}

function formatSigned(value: number): string {
  return `${value > 0 ? "+" : ""}${formatMoney(value)}`;
}
