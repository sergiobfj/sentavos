import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import Modal from "../components/Modal";
import TransactionForm from "../components/TransactionForm";
import ContaPicker from "../components/ContaPicker";
import { MarcaEditavel } from "../components/TransactionList";
import {
  useCategories,
  useCreateMovement,
  useInvestmentMovements,
  useInvestmentSummary,
  useRemoveMovement,
  useTransactions,
} from "../lib/queries";
import { useAuth } from "../lib/auth";
import { currentPeriod, formatPeriod, usePeriod } from "../lib/period";
import { ApiError } from "../lib/api";
import { formatDiaMes, formatMoney, formatYm, parseMoney, todayIso } from "../lib/format";
import { ASSET_CLASS_LABEL, type Transaction } from "../lib/types";
import {
  instanteSeHoje,
  lembrarConta,
  ultimaConta,
  type InvestmentAssetItem,
  type InvestmentMovement,
  type MovementType,
} from "../lib/tiposContas";

// Os números desta aba vêm prontos do servidor (app/dominio/investimentos.py):
// total atualizado, variação, aportado, resgatado e o rendimento — com o motivo
// quando ele não é apurável. A tela formata; não recalcula nada.

export default function Investments() {
  const { label } = usePeriod();
  const resumo = useInvestmentSummary(currentPeriod());
  const fluxo = useInvestmentSummary();
  const movimentos = useInvestmentMovements();
  const transactions = useTransactions();
  const categories = useCategories();
  const { sessao } = useAuth();
  const podeEscrever = !sessao?.somenteLeitura;
  const [editando, setEditando] = useState<Transaction | null>(null);
  const [aberto, setAberto] = useState<Transaction | null>(null);
  const [novo, setNovo] = useState<MovementType | null>(null);

  // Os lançamentos de investimento do mês (o lado caixa) — cada um com o
  // ativo dele, quando ligado.
  const aportes = useMemo(() => {
    const investCats = new Set((categories.data ?? []).filter((c) => c.type === "investment").map((c) => c.id));
    return (transactions.data ?? [])
      .filter((t) => investCats.has(t.category_id) && t.amount_paid != null)
      .sort((a, b) => b.date.localeCompare(a.date));
  }, [transactions.data, categories.data]);
  const porLancamento = useMemo(() => {
    const m = new Map<number, InvestmentMovement>();
    for (const mv of movimentos.data ?? []) if (mv.transaction_id != null) m.set(mv.transaction_id, mv);
    return m;
  }, [movimentos.data]);

  if (resumo.isLoading || transactions.isLoading) return <Esqueleto />;
  if (resumo.error) return <div className="error-box">{(resumo.error as ApiError).message}</div>;
  const r = resumo.data!;
  const itens = r.items;
  const conciliacaoPendente = itens.some((i) => i.reconciliation_note);
  const doMes = fluxo.data;

  if (itens.length === 0) {
    return (
      <div className="empty">
        <div className="big">📈</div>
        <div className="tit">Nada investido ainda</div>
        <div>
          Esta aba lê os ativos de renda fixa, renda variável e cripto do Patrimônio.
          {(fluxo.data?.contributed ?? 0) > 0 && (
            <> Você já aportou <b>{formatMoney(fluxo.data!.contributed)}</b> em {label} — cadastre onde esse dinheiro está.</>
          )}
        </div>
        <div style={{ marginTop: "var(--s4)" }}>
          <Link className="btn btn-primary" to="/patrimonio">Ir para patrimônio</Link>
        </div>
      </div>
    );
  }

  return (
    <>
      <section className="hero">
        <div className="rot">{r.stale_names.length ? "Saldo conhecido em investimentos" : "Total guardado agora"}</div>
        <div className="big tnum">{r.total===0 && r.stale_names.length ? "—" : formatMoney(r.total)}</div>
        {r.stale_names.length > 0 && (
          <div className="nota">
            Não entra no total: {r.stale_names.join(", ")} ({formatMoney(r.stale_total)} no último saldo) — sem saldo de {formatPeriod(currentPeriod())}.
          </div>
        )}
      </section>

      <div className="sec-title">
        <h2>Onde está</h2>
        <Link to="/patrimonio">Editar</Link>
      </div>

      <div className="list">
        {itens.map((item) => (
          <Link className={`row${item.stale ? " desatualizado" : ""}`} key={item.asset_id} to="/patrimonio">
            <div className="mid">
              <div className="t">{item.name}</div>
              <div className="s">
                {item.stale ? (
                  <span className="aviso-txt">não atualizado · {item.as_of ? formatYm(item.as_of) : ""}</span>
                ) : item.reconciliation_note ? (
                  "ajuste de conferência"
                ) : ASSET_CLASS_LABEL[item.asset_class]}
              </div>
            </div>
            <div className="amt tnum">
              {formatMoney(item.value)}
            </div>
            <MarcaEditavel />
          </Link>
        ))}
      </div>

      <div className="e-investment-flow"><div><span>Aportado em {label}</span><b className="tnum">{doMes ? formatMoney(doMes.contributed) : "—"}</b></div><div><span>Resgatado</span><b className="tnum">{doMes ? formatMoney(doMes.redeemed) : "—"}</b></div><div><span>Rendimento</span><b className="tnum">{doMes?.yield_status === "apurado" && doMes.yield_amount != null ? formatMoney(doMes.yield_amount) : "Não apurado"}</b></div></div>
      {conciliacaoPendente && <p className="nota">Há movimento a conferir; redução de saldo não é prejuízo.</p>}
      {doMes?.yield_status === "nao_apurado" && doMes.reasons.length > 0 && <p className="nota">{doMes.reasons.join(" ")}</p>}

      <div className="sec-title">
        {/* Sem o mês no título: ele já está no topo, e com as duas ações ao
            lado o título longo quebrava em 360px. */}
        <h2>{(doMes?.redeemed ?? 0) > 0 ? "Aportes e resgates" : "Aportes"}</h2>
        {podeEscrever && (
          <span className="titulo-acoes">
            <button className="link" onClick={() => setNovo("redemption")}>Resgate</button>
            <button className="link" onClick={() => setNovo("contribution")}>+ Aporte</button>
          </span>
        )}
      </div>
      {aportes.length === 0 ? (
        <p className="nota">Nenhum aporte ou resgate em {label}.</p>
      ) : (
        <div className="list">
          {aportes.map((t) => {
            const mv = porLancamento.get(t.id);
            return (
              <button className="row" key={t.id} onClick={() => setAberto(t)}>
                <div className="mid">
                  <div className="t">{t.description}</div>
                  <div className="s">
                    {formatDiaMes(t.date)} · {mv ? mv.asset_name : <span className="aviso-txt">sem ativo</span>}
                  </div>
                </div>
                <div className="amt tnum">{formatMoney(t.amount_paid)}</div>
                <MarcaEditavel />
              </button>
            );
          })}
        </div>
      )}

      {aberto && (
        <MovimentoSheet t={aberto} mov={porLancamento.get(aberto.id) ?? null} itens={itens} podeEscrever={podeEscrever}
          onEditar={() => { setEditando(aberto); setAberto(null); }} onClose={() => setAberto(null)} />
      )}
      {novo && <NovoMovimento tipo={novo} itens={itens} onClose={() => setNovo(null)} />}
      {editando && categories.data && (
        <TransactionForm categories={categories.data} transaction={editando} onClose={() => setEditando(null)} />
      )}
    </>
  );
}

/** Um aporte/resgate do mês: de qual ativo, e o lançamento por trás. */
function MovimentoSheet({
  t, mov, itens, podeEscrever, onEditar, onClose,
}: {
  t: Transaction; mov: InvestmentMovement | null; itens: InvestmentAssetItem[]; podeEscrever: boolean;
  onEditar: () => void; onClose: () => void;
}) {
  const criar = useCreateMovement();
  const remover = useRemoveMovement();
  const resgate = (t.amount_paid ?? 0) < 0;
  const erro = (criar.error || remover.error) as ApiError | null;
  return (
    <Modal title={t.description} onClose={onClose}>
      <div className="m-body">
        <div className="folha-total">
          <b className="tnum">{formatMoney(Math.abs(t.amount_paid ?? 0))}</b>
          <span>{resgate ? "resgate" : "aporte"} · {formatDiaMes(t.date)}{t.account_name ? ` · ${t.account_name}` : ""}</span>
        </div>
        {mov ? (
          <p className="hint">{resgate ? "Saiu de" : "Foi para"} <b>{mov.asset_name}</b>. Não é gasto, nem receita, nem rendimento.</p>
        ) : (
          <p className="hint">Este {resgate ? "resgate" : "aporte"} ainda não diz de qual ativo é — o rendimento por ativo fica sem conta até ligar.</p>
        )}
        {podeEscrever && !mov && (
          <div className="field">
            <span className="label">Ligar ao ativo</span>
            <div className="chip-linha" role="group" aria-label="Ativo">
              {itens.map((i) => (
                <button type="button" key={i.asset_id} disabled={criar.isPending}
                  onClick={() => criar.mutate({
                    asset_id: i.asset_id, type: resgate ? "redemption" : "contribution",
                    amount: Math.abs(t.amount_paid ?? 0), date: t.date, transaction_id: t.id,
                  }, { onSuccess: onClose })}>
                  {i.name}
                </button>
              ))}
            </div>
          </div>
        )}
        {podeEscrever && (
          <div className="acoes-linha">
            {mov && (
              <button className="link" disabled={remover.isPending} onClick={() => remover.mutate(mov.id, { onSuccess: onClose })}>
                Desvincular do ativo
              </button>
            )}
            <button className="link" onClick={onEditar}>Editar lançamento</button>
          </div>
        )}
        {erro && <div className="error-box">{erro.message}</div>}
      </div>
    </Modal>
  );
}

/** Aporte ou resgate novo: ativo, conta, valor, data. Cria o lançamento (o lado
 *  caixa) e o movimento juntos. */
function NovoMovimento({ tipo, itens, onClose }: { tipo: MovementType; itens: InvestmentAssetItem[]; onClose: () => void }) {
  const criar = useCreateMovement();
  const categories = useCategories();
  const investCats = (categories.data ?? []).filter((c) => c.type === "investment" && !c.archived);
  const [ativo, setAtivo] = useState<number | null>(itens[0]?.asset_id ?? null);
  const [categoria, setCategoria] = useState<number | null>(null);
  const [conta, setConta] = useState<number | null>(ultimaConta());
  const [valor, setValor] = useState("");
  const [data, setData] = useState(todayIso());
  const numero = parseMoney(valor) ?? 0;
  const cat = categoria ?? investCats[0]?.id ?? null;
  const erro = criar.error as ApiError | null;
  const aporte = tipo === "contribution";
  return (
    <Modal title={aporte ? "Novo aporte" : "Novo resgate"} onClose={onClose}>
      <form className="m-body" onSubmit={(e) => {
        e.preventDefault();
        if (ativo == null || cat == null) return;
        lembrarConta(conta);
        criar.mutate({ asset_id: ativo, type: tipo, amount: numero, date: data, account_id: conta, category_id: cat,
          occurred_at: instanteSeHoje(data) }, { onSuccess: onClose });
      }}>
        <div className="field">
          <span className="label">{aporte ? "Para o ativo" : "Do ativo"}</span>
          <div className="chip-linha" role="group" aria-label="Ativo">
            {itens.map((i) => (
              <button type="button" key={i.asset_id} className={i.asset_id === ativo ? "on" : ""}
                aria-pressed={i.asset_id === ativo} onClick={() => setAtivo(i.asset_id)}>{i.name}</button>
            ))}
          </div>
        </div>
        <ContaPicker rotulo={aporte ? "Saiu de" : "Entrou em"} valor={conta} aoEscolher={setConta} />
        {investCats.length > 1 && (
          <div className="field">
            <span className="label">Categoria</span>
            <div className="chip-linha" role="group" aria-label="Categoria">
              {investCats.map((c) => (
                <button type="button" key={c.id} className={c.id === cat ? "on" : ""} aria-pressed={c.id === cat}
                  onClick={() => setCategoria(c.id)}>{c.name}</button>
              ))}
            </div>
          </div>
        )}
        <div className="row2">
          <div className="field">
            <label htmlFor="mv-valor">Valor</label>
            <input id="mv-valor" inputMode="decimal" placeholder="0,00" autoFocus value={valor} onChange={(e) => setValor(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="mv-data">Data</label>
            <input id="mv-data" type="date" value={data} onChange={(e) => setData(e.target.value)} />
          </div>
        </div>
        <p className="hint">
          {aporte ? "Sai da conta e entra no ativo: não é gasto." : "Sai do ativo e volta pra conta: não é receita nem rendimento."}
        </p>
        <button type="submit" className="btn btn-primary btn-block" disabled={criar.isPending || numero <= 0 || ativo == null || cat == null}>
          {aporte ? "Registrar aporte" : "Registrar resgate"}
        </button>
        {erro && <div className="error-box">{erro.message}</div>}
      </form>
    </Modal>
  );
}

function Esqueleto() {
  return (
    <>
      <div className="skel" style={{ height: 64, width: "60%", marginTop: "var(--s3)" }} />
      <div className="skel" style={{ height: 64, marginTop: "var(--s4)" }} />
      <div className="sec-title"><h2>Onde está</h2></div>
      <div className="skel" style={{ height: 160, borderRadius: "var(--r)" }} />
    </>
  );
}
