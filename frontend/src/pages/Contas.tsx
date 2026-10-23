import { useState } from "react";
import Modal from "../components/Modal";
import Segmentado from "../components/Segmentado";
import { Cabecalho, Linha } from "../components/planejamento/comum";
import {
  useAccountMovements,
  useAccountsSummary,
  useAceitarDiferenca,
  useCreateAccount,
  useCreateTransfer,
  useDeleteAccount,
  useDeleteTransfer,
  useDistribuir,
  useInformarSaldo,
  useTransfers,
  useUpdateAccount,
} from "../lib/queries";
import { useAuth } from "../lib/auth";
import { usePeriod } from "../lib/period";
import { ApiError } from "../lib/api";
import { formatDiaMes, formatMoney, parseMoney, todayIso } from "../lib/format";
import {
  ACCOUNT_TYPE_LABEL,
  ACCOUNT_TYPE_ORDER,
  estadoDaConta,
  instanteSeHoje,
  type AccountSnapshot,
  type AccountType,
  type FinancialAccount,
  type Transfer,
} from "../lib/tiposContas";

/** Contas e saldos: onde o dinheiro está, e quão confiável é cada número.
 *
 *  O saldo vem calculado do servidor (último saldo observado + movimentos
 *  da conta). A tela formata e oferece as três ações que mexem nele sem criar
 *  receita nem despesa: atualizar saldo, transferir e distribuir o agregado. */
export default function Contas() {
  const { data, isLoading, error } = useAccountsSummary();
  const { sessao } = useAuth();
  const podeEscrever = !sessao?.somenteLeitura;
  const [aberta, setAberta] = useState<FinancialAccount | null>(null);
  const [criando, setCriando] = useState(false);
  const [transferindo, setTransferindo] = useState(false);

  if (isLoading) return <div className="skel" style={{ height: 320 }} />;
  if (error) return <div className="error-box">{(error as ApiError).message}</div>;
  if (!data) return null;

  const agregado = data.accounts.find((c) => c.type === "reconciliation" && (c.balance ?? 0) > 0.005);
  const atual = aberta ? data.accounts.find((c) => c.id === aberta.id) ?? aberta : null;

  return (
    <>
      <Cabecalho titulo="Contas e saldos" voltar="Configurações" voltarPara="/configuracoes" />

      <section className="hero plano-hero">
        <div className="big tnum">{data.possible_overlap ? "—" : formatMoney(data.total)}</div>
        <div className="rot">
          em contas{data.restricted > 0 && <> · {formatMoney(data.free)} livres, {formatMoney(data.restricted)} restritos</>}
        </div>
        {data.without_balance_count > 0 && (
          <div className="nota">
            {data.without_balance_count} {data.without_balance_count === 1 ? "conta sem saldo" : "contas sem saldo"} — não
            entram no total até você informar.
          </div>
        )}
        {data.possible_overlap && <div className="nota">Confira a distribuição do saldo agregado: ele pode incluir o dinheiro das contas individuais.</div>}
        {data.maybe_incomplete && !data.possible_overlap && (
          <div className="nota">
            {data.unassigned_movements > 0 ? `${data.unassigned_movements} movimentos sem conta a conferir desde o saldo observado.` : "Movimentos do mesmo dia sem horário: confira se já estão incluídos no saldo observado."} O número pode estar incompleto.
          </div>
        )}
      </section>

      {agregado && (
        <button type="button" className="aviso-acao" onClick={() => setAberta(agregado)}>
          <div>
            <b className="tnum">{formatMoney(agregado.balance)}</b> no {agregado.name}, esperando divisão entre as contas
          </div>
          <span aria-hidden>›</span>
        </button>
      )}

      <div className="sec-title">
        <h2>Contas</h2>
        {podeEscrever && (
          <span className="titulo-acoes">
            <button className="link" onClick={() => setTransferindo(true)}>Transferir</button>
            <button className="link" onClick={() => setCriando(true)}>+ Conta</button>
          </span>
        )}
      </div>
      {data.accounts.length === 0 ? (
        <p className="nota">
          Nenhuma conta ainda. Cadastre onde o dinheiro fica — Nubank, Mercado Pago, carteira — e informe o saldo de hoje.
        </p>
      ) : (
        <ul className="lista-compacta">
          {data.accounts.map((c) => (
            <Linha
              key={c.id}
              rotulo={c.name}
              legenda={`${estadoDaConta(c)}${c.restricted ? " · restrita" : ""}`}
              tom={c.quality === "desatualizado" || c.quality === "sem_saldo" ? "neg" : undefined}
              valor={c.balance == null ? "—" : formatMoney(c.balance)}
              onClick={() => setAberta(c)}
            />
          ))}
        </ul>
      )}

      <Transferencias podeEscrever={podeEscrever} />

      {atual && (
        <ContaSheet conta={atual} todas={data.accounts} podeEscrever={podeEscrever} onClose={() => setAberta(null)} />
      )}
      {criando && <NovaConta onClose={() => setCriando(false)} />}
      {transferindo && <Transferir contas={data.accounts} onClose={() => setTransferindo(false)} />}
    </>
  );
}

function Transferencias({ podeEscrever }: { podeEscrever: boolean }) {
  const { label } = usePeriod();
  const { data } = useTransfers();
  const excluir = useDeleteTransfer();
  const [aberta, setAberta] = useState<Transfer | null>(null);
  if (!data || data.length === 0) return null;
  return (
    <>
      <div className="sec-title"><h2>Transferências de {label}</h2></div>
      <ul className="lista-compacta">
        {data.map((t) => (
          <Linha key={t.id} rotulo={`${t.from_name} → ${t.to_name}`}
            legenda={`${formatDiaMes(t.date)}${t.description ? ` · ${t.description}` : ""}`}
            valor={formatMoney(t.amount)} onClick={podeEscrever ? () => setAberta(t) : undefined} />
        ))}
      </ul>
      {aberta && (
        <Modal title="Transferência" onClose={() => setAberta(null)}>
          <div className="m-body">
            <div className="folha-total">
              <b className="tnum">{formatMoney(aberta.amount)}</b>
              <span>{aberta.from_name} → {aberta.to_name} · {formatDiaMes(aberta.date)}</span>
            </div>
            <p className="hint">Transferência só muda onde o dinheiro está: não é gasto, nem receita.</p>
            <button className="btn btn-block" disabled={excluir.isPending}
              onClick={() => excluir.mutate(aberta.id, { onSuccess: () => setAberta(null) })}>
              Excluir esta transferência
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}

type Acao = null | "saldo" | "movimentos" | "editar" | "distribuir";

function ContaSheet({
  conta,
  todas,
  podeEscrever,
  onClose,
}: {
  conta: FinancialAccount;
  todas: FinancialAccount[];
  podeEscrever: boolean;
  onClose: () => void;
}) {
  const ehAgregado = conta.type === "reconciliation";
  const [acao, setAcao] = useState<Acao>(ehAgregado && (conta.balance ?? 0) > 0 ? "distribuir" : null);

  return (
    <Modal title={conta.name} onClose={onClose}>
      <div className="m-body">
        <div className="folha-total">
          <b className="tnum">{conta.balance == null ? "—" : formatMoney(conta.balance)}</b>
          <span>
            {estadoDaConta(conta)}
            {conta.quality === "calculado" && conta.observed_balance != null && (
              <> · observado {formatMoney(conta.observed_balance)} + {conta.movements_after} {conta.movements_after === 1 ? "movimento" : "movimentos"}</>
            )}
          </span>
        </div>
        {conta.maybe_incomplete && (
          <p className="hint">Há lançamentos sem conta depois do último saldo — o número pode não ter visto um gasto.</p>
        )}
        {conta.restricted && <p className="hint">Conta restrita: entra no patrimônio, nunca no dinheiro livre.</p>}

        {podeEscrever && acao === null && (
          <div className="acoes">
            <button className="btn btn-primary" onClick={() => setAcao("saldo")}>
              <span>Atualizar saldo<small>O que o app do banco mostra agora. Não vira lançamento.</small></span>
            </button>
            {ehAgregado && (conta.balance ?? 0) > 0 && (
              <button className="btn" onClick={() => setAcao("distribuir")}>
                <span>Distribuir entre as contas<small>Diz onde este dinheiro está. Não é receita nem despesa.</small></span>
              </button>
            )}
            <button className="btn" onClick={() => setAcao("movimentos")}>
              <span>Movimentos<small>O que entrou e saiu desta conta.</small></span>
            </button>
            <button className="btn btn-ghost" onClick={() => setAcao("editar")}>
              <span>Editar<small>Nome, tipo, planejamento, arquivar.</small></span>
            </button>
          </div>
        )}
        {!podeEscrever && acao === null && (
          <button className="btn btn-block" onClick={() => setAcao("movimentos")}>Ver movimentos</button>
        )}

        {acao === "saldo" && <AtualizarSaldo conta={conta} aoRevisar={() => setAcao("movimentos")} onClose={onClose} />}
        {acao === "movimentos" && <Movimentos conta={conta} />}
        {acao === "editar" && <EditarConta conta={conta} onClose={onClose} />}
        {acao === "distribuir" && <Distribuir agregado={conta} todas={todas} onClose={onClose} />}
      </div>
    </Modal>
  );
}

function AtualizarSaldo({ conta, aoRevisar, onClose }: { conta: FinancialAccount; aoRevisar: () => void; onClose: () => void }) {
  const informar = useInformarSaldo();
  const aceitar = useAceitarDiferenca();
  const [valor, setValor] = useState("");
  const [resultado, setResultado] = useState<AccountSnapshot | null>(null);
  const erro = (informar.error || aceitar.error) as ApiError | null;
  const numero = parseMoney(valor);

  if (resultado && resultado.pending_difference != null) {
    const d = resultado.pending_difference;
    return (
      <div>
        <div className="aviso-box">
          Diferença de <b className="tnum">{formatMoney(Math.abs(d))}</b> {d < 0 ? "a menos" : "a mais"} do que o calculado.
          Pode ser um lançamento que faltou — ou um ajuste que não vale a pena rastrear.
        </div>
        <div className="acoes">
          <button className="btn" onClick={aoRevisar}>
            <span>Revisar movimentos<small>Lançar o que faltou resolve a diferença sozinho.</small></span>
          </button>
          <button className="btn btn-ghost" disabled={aceitar.isPending}
            onClick={() => aceitar.mutate({ id: conta.id, snapshotId: resultado.id }, { onSuccess: onClose })}>
            <span>Aceitar ajuste de conferência<small>Fica registrado. Não vira receita nem despesa.</small></span>
          </button>
        </div>
        {erro && <div className="error-box">{erro.message}</div>}
      </div>
    );
  }

  return (
    <form onSubmit={(e) => {
      e.preventDefault();
      if (numero == null) return;
      informar.mutate({ id: conta.id, balance: numero }, {
        onSuccess: (r) => (r.snapshot.pending_difference != null ? setResultado(r.snapshot) : onClose()),
      });
    }}>
      <div className="field">
        <label htmlFor="s-valor">Saldo agora</label>
        <input id="s-valor" inputMode="decimal" autoFocus placeholder={conta.balance != null ? formatMoney(conta.balance) : "0,00"}
          value={valor} onChange={(e) => setValor(e.target.value)} />
      </div>
      <button type="submit" className="btn btn-primary btn-block" disabled={informar.isPending || numero == null}>
        {informar.isPending ? "Salvando…" : "Salvar saldo"}
      </button>
      {erro && <div className="error-box">{erro.message}</div>}
    </form>
  );
}

function Movimentos({ conta }: { conta: FinancialAccount }) {
  const { data, isLoading } = useAccountMovements(conta.id);
  if (isLoading) return <div className="skel" style={{ height: 120 }} />;
  if (!data || data.length === 0) return <p className="hint">Nenhum movimento com esta conta ainda.</p>;
  return (
    <ul className="lista-compacta">
      {data.map((m) => (
        <Linha key={`${m.source}-${m.source_id}-${m.amount}`} rotulo={m.description}
          legenda={`${formatDiaMes(m.date)}${m.after_observation ? " · depois do saldo" : ""}`}
          valor={`${m.amount > 0 ? "+" : "−"}${formatMoney(Math.abs(m.amount))}`} />
      ))}
    </ul>
  );
}

const OPCOES_TIPO = ACCOUNT_TYPE_ORDER.map((t) => ({ valor: t, rotulo: ACCOUNT_TYPE_LABEL[t] }));

function EditarConta({ conta, onClose }: { conta: FinancialAccount; onClose: () => void }) {
  const atualizar = useUpdateAccount();
  const excluir = useDeleteAccount();
  const [nome, setNome] = useState(conta.name);
  const [tipo, setTipo] = useState<AccountType>(conta.type);
  const [planejamento, setPlanejamento] = useState(conta.include_in_planning);
  const [restrita, setRestrita] = useState(conta.restricted);
  const erro = (atualizar.error || excluir.error) as ApiError | null;
  return (
    <form onSubmit={(e) => {
      e.preventDefault();
      atualizar.mutate({ id: conta.id, data: { name: nome, type: tipo, include_in_planning: planejamento, restricted: restrita } },
        { onSuccess: onClose });
    }}>
      <div className="field">
        <label htmlFor="c-nome">Nome</label>
        <input id="c-nome" value={nome} onChange={(e) => setNome(e.target.value)} />
      </div>
      {conta.type !== "reconciliation" && (
        <div className="field">
          <span className="label">Tipo</span>
          <Segmentado rotulo="Tipo" opcoes={OPCOES_TIPO} valor={tipo} aoEscolher={(t) => t && setTipo(t)} largo />
        </div>
      )}
      <label className="conta-toggle">
        <input type="checkbox" checked={planejamento} onChange={(e) => setPlanejamento(e.target.checked)} />
        <span className="esq"><span className="n">Entra no planejamento</span><span className="d">conta no "quanto posso usar"</span></span>
      </label>
      <label className="conta-toggle">
        <input type="checkbox" checked={restrita} onChange={(e) => setRestrita(e.target.checked)} />
        <span className="esq"><span className="n">Restrita</span><span className="d">dinheiro com destino fixo, como vale-transporte</span></span>
      </label>
      <button type="submit" className="btn btn-primary btn-block" disabled={atualizar.isPending || !nome.trim()}>Salvar</button>
      <div className="acoes-linha">
        <button type="button" className="link" disabled={atualizar.isPending}
          onClick={() => atualizar.mutate({ id: conta.id, data: { archived: true } }, { onSuccess: onClose })}>
          Arquivar
        </button>
        <button type="button" className="link" disabled={excluir.isPending}
          onClick={() => excluir.mutate(conta.id, { onSuccess: onClose })}>
          Excluir
        </button>
      </div>
      {erro && <div className="error-box">{erro.message}</div>}
    </form>
  );
}

function Distribuir({ agregado, todas, onClose }: { agregado: FinancialAccount; todas: FinancialAccount[]; onClose: () => void }) {
  const distribuir = useDistribuir();
  const destinos = todas.filter((c) => c.id !== agregado.id && c.type !== "reconciliation" && !c.archived);
  const [valores, setValores] = useState<Record<number, string>>({});
  const total = agregado.balance ?? 0;
  const partes = destinos
    .map((c) => ({ account_id: c.id, amount: parseMoney(valores[c.id] ?? "") ?? 0 }))
    .filter((p) => p.amount > 0);
  const soma = Math.round(partes.reduce((s, p) => s + p.amount, 0) * 100) / 100;
  const falta = Math.round((total - soma) * 100) / 100;
  const erro = distribuir.error as ApiError | null;

  if (destinos.length === 0) {
    return <p className="hint">Cadastre as contas reais (Nubank, Mercado Pago, carteira) pra distribuir este saldo.</p>;
  }
  return (
    <form onSubmit={(e) => {
      e.preventDefault();
      distribuir.mutate({ id: agregado.id, destinos: partes }, { onSuccess: onClose });
    }}>
      <p className="hint" style={{ marginTop: 0 }}>
        Quanto dos {formatMoney(total)} está em cada conta. O total não muda: o agregado vai a zero e cada conta recebe a parte dela.
      </p>
      {destinos.map((c) => (
        <div className="field" key={c.id}>
          <label htmlFor={`d-${c.id}`}>{c.name}</label>
          <input id={`d-${c.id}`} inputMode="decimal" placeholder="0,00" value={valores[c.id] ?? ""}
            onChange={(e) => setValores({ ...valores, [c.id]: e.target.value })} />
        </div>
      ))}
      <div className="folha-total">
        <b className="tnum">{formatMoney(Math.abs(falta))}</b>
        <span>{Math.abs(falta) < 0.005 ? "fecha certinho" : falta > 0 ? "ainda falta distribuir" : "passou do total"}</span>
      </div>
      <button type="submit" className="btn btn-primary btn-block"
        disabled={distribuir.isPending || Math.abs(falta) >= 0.005 || partes.length === 0}>
        Distribuir
      </button>
      {erro && <div className="error-box">{erro.message}</div>}
    </form>
  );
}

function NovaConta({ onClose }: { onClose: () => void }) {
  const criar = useCreateAccount();
  const [nome, setNome] = useState("");
  const [tipo, setTipo] = useState<AccountType>("checking");
  const erro = criar.error as ApiError | null;
  return (
    <Modal title="Nova conta" onClose={onClose}>
      <form className="m-body" onSubmit={(e) => {
        e.preventDefault();
        criar.mutate({ name: nome.trim(), type: tipo }, { onSuccess: onClose });
      }}>
        <div className="field">
          <label htmlFor="n-nome">Nome</label>
          <input id="n-nome" autoFocus placeholder="Ex.: Nubank" value={nome} onChange={(e) => setNome(e.target.value)} />
        </div>
        <div className="field">
          <span className="label">Tipo</span>
          <Segmentado rotulo="Tipo" opcoes={OPCOES_TIPO} valor={tipo} aoEscolher={(t) => t && setTipo(t)} largo />
        </div>
        {tipo === "benefit" && <p className="hint">Benefício nasce restrito: não entra no dinheiro livre.</p>}
        <button type="submit" className="btn btn-primary btn-block" disabled={criar.isPending || !nome.trim()}>Criar conta</button>
        {erro && <div className="error-box">{erro.message}</div>}
      </form>
    </Modal>
  );
}

function Transferir({ contas, onClose }: { contas: FinancialAccount[]; onClose: () => void }) {
  const criar = useCreateTransfer();
  const ativas = contas.filter((c) => !c.archived && c.type !== "reconciliation");
  const [de, setDe] = useState<number | null>(ativas[0]?.id ?? null);
  const [para, setPara] = useState<number | null>(ativas[1]?.id ?? null);
  const [valor, setValor] = useState("");
  const [data, setData] = useState(todayIso());
  const [descricao, setDescricao] = useState("");
  const numero = parseMoney(valor) ?? 0;
  const erro = criar.error as ApiError | null;

  const escolha = (atual: number | null, setar: (id: number) => void, rotulo: string) => (
    <div className="field">
      <span className="label">{rotulo}</span>
      <div className="chip-linha" role="group" aria-label={rotulo}>
        {ativas.map((c) => (
          <button type="button" key={c.id} className={c.id === atual ? "on" : ""} aria-pressed={c.id === atual}
            onClick={() => setar(c.id)}>{c.name}</button>
        ))}
      </div>
    </div>
  );

  return (
    <Modal title="Transferir" onClose={onClose}>
      <form className="m-body" onSubmit={(e) => {
        e.preventDefault();
        if (de == null || para == null) return;
        criar.mutate({ from_account_id: de, to_account_id: para, amount: numero, date: data,
          occurred_at: instanteSeHoje(data), description: descricao.trim() || null }, { onSuccess: onClose });
      }}>
        {escolha(de, setDe, "De")}
        {escolha(para, setPara, "Para")}
        <div className="row2">
          <div className="field">
            <label htmlFor="t-valor">Valor</label>
            <input id="t-valor" inputMode="decimal" placeholder="0,00" value={valor} onChange={(e) => setValor(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="t-data">Data</label>
            <input id="t-data" type="date" value={data} onChange={(e) => setData(e.target.value)} />
          </div>
        </div>
        <div className="field">
          <label htmlFor="t-desc">Descrição (opcional)</label>
          <input id="t-desc" placeholder="Ex.: Pix pra caixinha" value={descricao} onChange={(e) => setDescricao(e.target.value)} />
        </div>
        <p className="hint">Muda onde o dinheiro está. Não é gasto, nem receita, nem muda o patrimônio.</p>
        <button type="submit" className="btn btn-primary btn-block"
          disabled={criar.isPending || de == null || para == null || de === para || numero <= 0}>
          Transferir
        </button>
        {erro && <div className="error-box">{erro.message}</div>}
      </form>
    </Modal>
  );
}
