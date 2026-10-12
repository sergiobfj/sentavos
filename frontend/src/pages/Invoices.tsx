import { useState } from "react";
import { Link } from "react-router-dom";
import Modal from "../components/Modal";
import ConfirmDialog from "../components/ConfirmDialog";
import { IconeCartao, MarcaEditavel } from "../components/TransactionList";
import {
  useCandidatosAPagamento,
  useInvoice,
  useInvoicesSummary,
  usePayInvoice,
  useReconcile,
  useUndoPayment,
} from "../lib/queries";
import { useAuth } from "../lib/auth";
import { ApiError } from "../lib/api";
import { formatDate, formatDiaMes, formatMoney, parseMoney, todayIso } from "../lib/format";
import {
  INVOICE_STATUS_LABEL,
  type CardInvoices,
  type Invoice,
  type InvoiceStatus,
} from "../lib/types";

// A cor do selo segue o que ele pede de você: vermelho só quando já venceu.
// "Aberta" não é problema — é o estado normal de uma fatura que ainda vai
// fechar, e pintá-la de alerta faria o app parecer sempre em apuro.
const COR_STATUS: Record<InvoiceStatus, string> = {
  aberta: "var(--text-dim)",
  // Parcial é informação, não ação: texto claro, sem o dourado que agora é só
  // de botão e seleção.
  parcial: "var(--text)",
  paga: "var(--pos)",
  atrasada: "var(--neg)",
};

export default function Invoices() {
  const [abertaId, setAbertaId] = useState<number | null>(null);
  const { data, isLoading, error } = useInvoicesSummary();

  if (abertaId != null) {
    return <DetalheFatura id={abertaId} onVoltar={() => setAbertaId(null)} />;
  }

  if (isLoading) {
    return <div className="skel" style={{ height: 200, borderRadius: "var(--r)" }} />;
  }
  if (error) return <div className="error-box">{(error as ApiError).message}</div>;

  if (!data || data.cards.length === 0) {
    return (
      <div className="empty">
        <div className="big">💳</div>
        <div className="tit">Nenhum cartão cadastrado</div>
        <div>
          Com um cartão, a compra vira gasto agora e só sai da conta quando você
          pagar a fatura.
        </div>
        <div style={{ marginTop: "var(--s4)" }}>
          <Link className="btn btn-primary" to="/configuracoes">
            Cadastrar cartão
          </Link>
        </div>
      </div>
    );
  }

  return (
    <>
      {data.open_total > 0 && (
        <section className="hero">
          <div className="rot">Em aberto nas faturas</div>
          <div className="big tnum">{formatMoney(data.open_total)}</div>
          <div className="delta">
            Dinheiro que já foi gasto e ainda vai sair da conta
          </div>
        </section>
      )}

      {data.cards.map((c) => (
        <CartaoNaLista key={c.card_id} cartao={c} onAbrir={setAbertaId} />
      ))}

      {data.payments.length > 0 && (
        <>
          <div className="sec-title">
            <h2>Pagamentos do mês</h2>
          </div>
          <div className="list">
            {data.payments.map((p) => (
              <button key={p.id} className="row" onClick={() => setAbertaId(p.invoice_id)}>
                <div className="avatar avatar-fatura" aria-hidden>
                  <IconeCartao />
                </div>
                <div className="mid">
                  <div className="t">Fatura {p.card_name}</div>
                  <div className="s">{formatDiaMes(p.date)} · pagamento de fatura</div>
                </div>
                <div className="amt tnum">−{formatMoney(p.amount)}</div>
                <MarcaEditavel />
              </button>
            ))}
          </div>
        </>
      )}
    </>
  );
}

function CartaoNaLista({
  cartao,
  onAbrir,
}: {
  cartao: CardInvoices;
  onAbrir: (id: number) => void;
}) {
  // A fatura do mês selecionado é a que se paga agora; a próxima é a que ainda
  // está acumulando. Mostrar as duas responde "quanto devo" e "quanto já
  // comprei do mês que vem" sem trocar de tela.
  return (
    <div className="card card-pad" style={{ marginTop: "var(--s3)" }}>
      <div className="fatura-cabeca">
        <div>
          <div className="t">{cartao.name}</div>
          <div className="s">
            fecha dia {cartao.closing_day} · vence dia {cartao.due_day}
            {cartao.archived && " · arquivado"}
          </div>
        </div>
        {cartao.open_total > 0 && (
          <div className="tnum" style={{ color: "var(--text-dim)", fontSize: "var(--fs-small)" }}>
            {formatMoney(cartao.open_total)} em aberto
          </div>
        )}
      </div>

      {cartao.current ? (
        <FaturaResumida fatura={cartao.current} rotulo="Fatura atual" onAbrir={onAbrir} />
      ) : (
        <div className="hint" style={{ marginTop: "var(--s3)" }}>
          Nenhuma fatura vence neste mês.
        </div>
      )}

      {cartao.next && (
        <FaturaResumida fatura={cartao.next} rotulo="Próxima fatura" onAbrir={onAbrir} />
      )}
    </div>
  );
}

function FaturaResumida({
  fatura,
  rotulo,
  onAbrir,
}: {
  fatura: Invoice;
  rotulo: string;
  onAbrir: (id: number) => void;
}) {
  return (
    <button className="fatura-linha" onClick={() => onAbrir(fatura.id)}>
      <div className="mid">
        <div className="rot">{rotulo}</div>
        <div className="big tnum">{formatMoney(fatura.total)}</div>
        <div className="s">
          vence {formatDiaMes(fatura.due_date)} · {fatura.item_count}{" "}
          {fatura.item_count === 1 ? "compra" : "compras"}
          {fatura.paid > 0 && <> · {formatMoney(fatura.paid)} pago</>}
        </div>
      </div>
      <div className="fim">
        <span className="chip" style={{ color: COR_STATUS[fatura.status] }}>
          {INVOICE_STATUS_LABEL[fatura.status]}
        </span>
        <span className="ver">Ver fatura ›</span>
      </div>
    </button>
  );
}

// ---------- A fatura por dentro ----------

function DetalheFatura({ id, onVoltar }: { id: number; onVoltar: () => void }) {
  const { data: fatura, isLoading, error } = useInvoice(id);
  const { sessao } = useAuth();
  const [pagando, setPagando] = useState(false);
  const [reconciliando, setReconciliando] = useState(false);

  if (isLoading) {
    return <div className="skel" style={{ height: 320, borderRadius: "var(--r)" }} />;
  }
  if (error) return <div className="error-box">{(error as ApiError).message}</div>;
  if (!fatura) return null;

  const podeEscrever = !sessao?.somenteLeitura;

  return (
    <>
      <button className="btn btn-ghost btn-sm" onClick={onVoltar} style={{ marginBottom: "var(--s3)" }}>
        ‹ Faturas
      </button>

      <section className="hero">
        <div className="rot">
          {fatura.card_name} · fatura de {mesPorExtenso(fatura.year, fatura.month)}
        </div>
        <div className="big tnum">{formatMoney(fatura.total)}</div>
        <div className="delta">
          <span className="chip" style={{ color: COR_STATUS[fatura.status] }}>
            {INVOICE_STATUS_LABEL[fatura.status]}
          </span>
          {" "}vence {formatDate(fatura.due_date)}
        </div>
      </section>

      <div className="sec-title">
        <h2>Compras</h2>
        <span className="extra tnum">fecha {formatDiaMes(fatura.closing_date)}</span>
      </div>

      {fatura.items.length === 0 ? (
        <div className="empty">
          <div className="tit">Nenhuma compra nesta fatura</div>
        </div>
      ) : (
        <div className="list">
          {fatura.items.map((item) => (
            <div className="row" key={item.transaction_id}>
              <div
                className="avatar"
                style={{ background: `color-mix(in srgb, ${item.color} 22%, transparent)` }}
              >
                {item.icon}
              </div>
              <div className="mid">
                <div className="t">{item.description}</div>
                <div className="s">
                  {formatDiaMes(item.purchase_date)} · {item.category_name}
                  {item.installments && (
                    <>
                      {" · "}
                      {item.installment_no}/{item.installments} de{" "}
                      {formatMoney(item.purchase_total)}
                    </>
                  )}
                </div>
              </div>
              <div className="amt tnum">{formatMoney(item.amount)}</div>
            </div>
          ))}
        </div>
      )}

      <div className="card card-pad" style={{ marginTop: "var(--s4)" }}>
        <div className="fatura-total">
          <span>Total</span>
          <b className="tnum">{formatMoney(fatura.total)}</b>
        </div>
        <div className="fatura-total">
          <span>Pago</span>
          <b className="tnum">{formatMoney(fatura.paid)}</b>
        </div>
        <div className="fatura-total destaque">
          <span>Restante</span>
          <b className="tnum">{formatMoney(fatura.remaining)}</b>
        </div>

        {podeEscrever && fatura.remaining > 0 && (
          <>
            <button
              className="btn btn-primary btn-block"
              style={{ marginTop: "var(--s4)" }}
              onClick={() => setPagando(true)}
            >
              Pagar fatura
            </button>
            {/* A porta da reconciliação fica aqui, e não escondida em
                Configurações: é aqui que a pessoa percebe que já lançou esse
                pagamento à mão, olhando a fatura que ela acabou de reconstruir. */}
            <button
              className="btn btn-ghost btn-sm btn-block"
              style={{ marginTop: "var(--s2)" }}
              onClick={() => setReconciliando(true)}
            >
              Já lancei este pagamento como despesa
            </button>
          </>
        )}
      </div>

      {fatura.payments.length > 0 && (
        <>
          <div className="sec-title">
            <h2>Pagamentos</h2>
          </div>
          <div className="list">
            {fatura.payments.map((p) => (
              <div className="row" key={p.id}>
                <div className="avatar avatar-fatura" aria-hidden>
                  <IconeCartao />
                </div>
                <div className="mid">
                  <div className="t">{formatDate(p.date)}</div>
                  {p.note && <div className="s">{p.note}</div>}
                </div>
                <div className="amt tnum">{formatMoney(p.amount)}</div>
                {podeEscrever && <DesfazerPagamento id={p.id} valor={p.amount} />}
              </div>
            ))}
          </div>
        </>
      )}

      {pagando && <PagarFatura fatura={fatura} onClose={() => setPagando(false)} />}
      {reconciliando && (
        <Reconciliar fatura={fatura} onClose={() => setReconciliando(false)} />
      )}
    </>
  );
}

function DesfazerPagamento({ id, valor }: { id: number; valor: number }) {
  const [confirmando, setConfirmando] = useState(false);
  const undo = useUndoPayment();

  return (
    <>
      <button
        className="row-editar"
        onClick={() => setConfirmando(true)}
        aria-label="Desfazer pagamento"
      >
        ✕
      </button>
      {confirmando && (
        <ConfirmDialog
          title="Desfazer pagamento"
          itemName={formatMoney(valor)}
          consequences={[
            "A fatura volta a ficar em aberto por este valor.",
            "O dinheiro volta para o saldo do mês em que foi pago.",
          ]}
          confirmLabel="Desfazer"
          pending={undo.isPending}
          error={(undo.error as ApiError | null)?.message ?? null}
          onCancel={() => setConfirmando(false)}
          onConfirm={() => undo.mutate(id, { onSuccess: () => setConfirmando(false) })}
        />
      )}
    </>
  );
}

function PagarFatura({
  fatura,
  onClose,
}: {
  fatura: { id: number; remaining: number; total: number; due_date: string };
  onClose: () => void;
}) {
  // Já vem com o restante preenchido: no uso normal a fatura é paga inteira, e
  // fazer a pessoa digitar de novo um número que o app já sabe é pedágio.
  const [valor, setValor] = useState(String(fatura.remaining).replace(".", ","));
  const [data, setData] = useState(todayIso());
  const pagar = usePayInvoice();

  const numero = parseMoney(valor) ?? 0;
  const sobra = Math.round((fatura.remaining - numero) * 100) / 100;

  return (
    <Modal
      title="Pagar fatura"
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Cancelar
          </button>
          <button
            type="submit"
            form="pagar-form"
            className="btn btn-primary"
            disabled={pagar.isPending || numero <= 0}
          >
            {pagar.isPending ? "Pagando…" : "Confirmar"}
          </button>
        </>
      }
    >
      <form
        id="pagar-form"
        className="m-body"
        onSubmit={(e) => {
          e.preventDefault();
          pagar.mutate(
            { id: fatura.id, amount: numero, date: data },
            { onSuccess: onClose }
          );
        }}
      >
        <div className="resumo-compra">
          <div className="linha">
            <span>Total da fatura</span>
            <b className="tnum">{formatMoney(fatura.total)}</b>
          </div>
          <div className="linha">
            <span>Restante</span>
            <b className="tnum">{formatMoney(fatura.remaining)}</b>
          </div>
          <div className="linha">
            <span>Vencimento</span>
            <b>{formatDate(fatura.due_date)}</b>
          </div>
        </div>

        <div className="field">
          <label htmlFor="p-valor">Valor pago</label>
          <input
            id="p-valor"
            inputMode="decimal"
            value={valor}
            autoFocus
            onChange={(e) => setValor(e.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="p-data">Data do pagamento</label>
          <input
            id="p-data"
            type="date"
            value={data}
            onChange={(e) => setData(e.target.value)}
          />
        </div>

        {numero > 0 && sobra > 0 && (
          <div className="aviso-box">
            Pagamento parcial: sobram <b>{formatMoney(sobra)}</b> nesta fatura.
          </div>
        )}

        <div className="hint">
          Isto sai do saldo do mês e <b>não</b> conta como gasto novo — o
          gasto já foi contado quando cada compra foi lançada.
        </div>

        {pagar.error && (
          <div className="error-box" style={{ padding: 0, textAlign: "left" }}>
            {(pagar.error as ApiError).message}
          </div>
        )}
      </form>
    </Modal>
  );
}

// ---------- Reconciliar com o jeito antigo ----------

function Reconciliar({
  fatura,
  onClose,
}: {
  fatura: { id: number; remaining: number };
  onClose: () => void;
}) {
  const { data: candidatos, isLoading } = useCandidatosAPagamento(fatura.id);
  const reconciliar = useReconcile();
  const [escolhido, setEscolhido] = useState<number | null>(null);

  const alvo = candidatos?.find((c) => c.id === escolhido) ?? null;

  return (
    <>
      <Modal
        title="Associar um lançamento"
        onClose={onClose}
        footer={
          <button type="button" className="btn btn-ghost btn-block" onClick={onClose}>
            Fechar
          </button>
        }
      >
        <div className="m-body">
          <div className="hint">
            Se você já lançou o pagamento desta fatura como uma despesa (por
            exemplo numa categoria "Fatura do cartão"), escolha o lançamento
            abaixo. Ele <b>deixa de contar como gasto</b> e passa a ser o
            pagamento desta fatura — assim o mesmo dinheiro não é contado duas
            vezes.
          </div>

          {isLoading && <div className="skel" style={{ height: 120 }} />}

          {candidatos && candidatos.length === 0 && (
            <div className="empty" style={{ padding: "var(--s5) 0" }}>
              <div className="tit">Nenhum lançamento por perto</div>
              <div>
                A lista traz despesas já pagas com data próxima do vencimento.
              </div>
            </div>
          )}

          {candidatos && candidatos.length > 0 && (
            <div className="list" style={{ marginTop: "var(--s3)" }}>
              {candidatos.map((c) => (
                <button className="row" key={c.id} onClick={() => setEscolhido(c.id)}>
                  <div className="mid">
                    <div className="t">{c.description}</div>
                    <div className="s">
                      {formatDiaMes(c.date)} · {c.category_name}
                    </div>
                  </div>
                  <div className="amt tnum">{formatMoney(c.amount)}</div>
                  <span className="row-editar" aria-hidden>
                    ›
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      </Modal>

      {alvo && (
        <ConfirmDialog
          title="Associar como pagamento"
          itemName={`${alvo.description} — ${formatMoney(alvo.amount)}`}
          consequences={[
            "Este lançamento deixa de existir como despesa e some do gasto do mês.",
            `Vira um pagamento de ${formatMoney(alvo.amount)} nesta fatura, na mesma data.`,
            "O dinheiro continua saindo do saldo uma vez só.",
          ]}
          confirmLabel="Associar"
          pending={reconciliar.isPending}
          error={(reconciliar.error as ApiError | null)?.message ?? null}
          onCancel={() => setEscolhido(null)}
          onConfirm={() =>
            reconciliar.mutate(
              { id: fatura.id, transactionId: alvo.id },
              {
                onSuccess: () => {
                  setEscolhido(null);
                  onClose();
                },
              }
            )
          }
        />
      )}
    </>
  );
}

function mesPorExtenso(ano: number, mes: number): string {
  const nome = new Date(ano, mes - 1, 1).toLocaleDateString("pt-BR", { month: "long" });
  return `${nome} de ${ano}`;
}
