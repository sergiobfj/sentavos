import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import Modal from "../components/Modal";
import TransactionForm from "../components/TransactionForm";
import ContaPicker from "../components/ContaPicker";
import { MarcaEditavel } from "../components/TransactionList";
import { Rosca } from "../components/Graficos";
import {
  useCategories,
  useCreateMovement,
  useInvestmentMovements,
  useInvestmentSummary,
  usePerfil,
  useRemoveMovement,
  useTransactions,
} from "../lib/queries";
import { useAuth } from "../lib/auth";
import { usePeriod } from "../lib/period";
import { ApiError } from "../lib/api";
import { formatDiaMes, formatMoney, formatYm, parseMoney, todayIso } from "../lib/format";
import { PALETA_CATEGORIAS, fundoDaCor } from "../lib/paleta";
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

/** A cor de cada aplicação segue o ATIVO, não a posição no ranking. */
function corDoAtivo(itens: InvestmentAssetItem[], id: number): string {
  const ids = itens.map((i) => i.asset_id).sort((a, b) => a - b);
  return PALETA_CATEGORIAS[ids.indexOf(id) % PALETA_CATEGORIAS.length].cor;
}

export default function Investments() {
  const { label } = usePeriod();
  const resumo = useInvestmentSummary();
  const movimentos = useInvestmentMovements();
  const perfil = usePerfil();
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
  const comValor = itens.filter((i) => !i.stale && i.value > 0);
  const conciliacaoPendente = itens.some((i) => i.reconciliation_note);

  if (itens.length === 0) {
    return (
      <div className="empty">
        <div className="big">📈</div>
        <div className="tit">Nada investido ainda</div>
        <div>
          Esta aba lê os ativos de renda fixa, renda variável e cripto do Patrimônio.
          {r.contributed > 0 && (
            <> Você já aportou <b>{formatMoney(r.contributed)}</b> em {label} — cadastre onde esse dinheiro está.</>
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
        <div className="rot">Total investido</div>
        <div className="big tnum">{formatMoney(r.total)}</div>
        {r.variation != null && r.previous_total > 0 && Math.abs(r.variation) >= 0.01 && (
          <div className={`delta ${r.variation > 0 ? "pos" : "neg"}`}>
            <span className="seta" aria-hidden>{r.variation > 0 ? "↑" : "↓"}</span>
            {formatMoney(Math.abs(r.variation))} no mês
          </div>
        )}
        {r.stale_names.length > 0 && (
          <div className="nota">
            Não entra no total: {r.stale_names.join(", ")} ({formatMoney(r.stale_total)} no último saldo) — sem saldo de {label}.
          </div>
        )}
      </section>

      {/* Dois números em linha. O resgate é linha do aporte, não terceira
          coluna: três valores em dinheiro não cabem lado a lado em 360px. */}
      <div className="metricas">
        <div className="metrica">
          <div className="rot">Aportado</div>
          <div className="val tnum">{formatMoney(r.contributed)}</div>
          {r.redeemed > 0 ? (
            <div className="s">resgatado <span className="tnum">{formatMoney(r.redeemed)}</span></div>
          ) : (
            conciliacaoPendente && <div className="s">resgate não conciliado</div>
          )}
        </div>
        <div className="metrica">
          <div className="rot">Rendeu</div>
          {r.yield_status === "apurado" && r.yield_amount != null ? (
            <div className="val tnum">{r.yield_amount > 0 ? "+" : ""}{formatMoney(r.yield_amount)}</div>
          ) : (
            <>
              <div className="val fraco">—</div>
              <div className="s">{r.yield_status === "sem_base" ? "sem mês anterior" : "não apurado"}</div>
            </>
          )}
          {r.expected_yield != null && (
            <div className="s">esperado <span className="tnum">{formatMoney(r.expected_yield)}</span></div>
          )}
        </div>
      </div>
      {/* O motivo "falta o saldo de X" vem por último; quando há outro motivo,
          ele já está dito embaixo do total e não se repete aqui. */}
      {r.yield_status === "nao_apurado" && r.reasons.length > 0 && (
        <p className="nota">
          Rendimento de {label} não apurado:{" "}
          {(r.stale_names.length && r.reasons.length > 1 ? r.reasons.slice(0, -1) : r.reasons).join(" ")}
        </p>
      )}

      {perfil.data && perfil.data.cdi_annual == null && itens.some((i) => i.cdi_percent != null) && (
        <div className="aviso-box" style={{ marginTop: "var(--s4)" }}>
          Você marcou a taxa das aplicações, mas falta informar o <b>CDI atual</b> para calcular o rendimento.{" "}
          <Link to="/configuracoes">Informar agora</Link>
        </div>
      )}

      <div className="sec-title">
        <h2>Onde está</h2>
        <Link to="/patrimonio">Editar</Link>
      </div>

      {comValor.length >= 2 && (
        <div style={{ marginBottom: "var(--s4)" }}>
          <Rosca semLegenda total={r.total} rotuloCentro="investido"
            fatias={comValor.map((i) => ({
              id: String(i.asset_id), nome: i.name, cor: corDoAtivo(itens, i.asset_id), valor: i.value,
              pct: (i.share ?? 0) * 100,
            }))} />
        </div>
      )}

      <div className="list">
        {itens.map((item) => (
          <Link className={`row${item.stale ? " desatualizado" : ""}`} key={item.asset_id} to="/patrimonio">
            <div className="avatar" style={{ background: fundoDaCor(corDoAtivo(itens, item.asset_id), 26) }} aria-hidden>
              {item.asset_class === "crypto" ? "₿" : item.asset_class === "equity" ? "📊" : "🏦"}
            </div>
            <div className="mid">
              <div className="t">{item.name}</div>
              <div className="s">
                {item.stale ? (
                  <span className="aviso-txt">não atualizado · {item.as_of ? formatYm(item.as_of) : ""}</span>
                ) : item.reconciliation_note ? (
                  "ajuste de conferência"
                ) : item.yield_status === "apurado" && item.yield_amount != null ? (
                  <>rendeu {item.yield_amount >= 0 ? "+" : ""}{formatMoney(item.yield_amount)}</>
                ) : (
                  <>
                    {ASSET_CLASS_LABEL[item.asset_class]}
                    {item.cdi_percent != null && <> · {item.cdi_percent}% do CDI</>}
                  </>
                )}
              </div>
            </div>
            <div className="amt tnum">
              {formatMoney(item.value)}
              {item.share != null && <span className="sub">{Math.round(item.share * 100)}%</span>}
            </div>
            <MarcaEditavel />
          </Link>
        ))}
      </div>

      <div className="sec-title">
        {/* Sem o mês no título: ele já está no topo, e com as duas ações ao
            lado o título longo quebrava em 360px. */}
        <h2>{r.redeemed > 0 ? "Aportes e resgates" : "Aportes"}</h2>
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
                <div className="avatar" style={{ background: fundoDaCor("#93a6dc", 18) }} aria-hidden>🏦</div>
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
