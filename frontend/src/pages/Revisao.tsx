import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import TransactionForm from "../components/TransactionForm";
import CardPicker from "../components/CardPicker";
import { ApiError, transactionsApi } from "../lib/api";
import { useCards, useCategories, useDefinirFormaEmLote } from "../lib/queries";
import { usePeriod } from "../lib/period";
import { formatDiaMes, formatMoney } from "../lib/format";
import { PAYMENT_METHOD_LABEL, type PaymentMethod, type Transaction } from "../lib/types";

/** Responder a forma de pagamento dos lançamentos que já existiam.
 *
 * O app passou a separar gasto de saída de caixa, mas os lançamentos anteriores
 * não têm essa informação. A migração NÃO os marcou como "à vista": parte deles
 * foi no cartão, e chutar seria inventar dado financeiro. Eles ficam contando
 * como saída de caixa — que é como já eram contados, então nenhum número do
 * passado mudou — e esta tela é onde o nulo vira resposta.
 *
 * Nada aqui adivinha por descrição ou por categoria. Uma categoria chamada
 * "Fatura do cartão" é uma pista boa e ainda assim é palpite sobre o dinheiro de
 * outra pessoa: quem sabe o que cada linha foi é quem a lançou.
 */

type Filtro = "sem-forma" | "mes" | "todos";

const FILTROS: { id: Filtro; rotulo: string }[] = [
  { id: "sem-forma", rotulo: "Sem pagamento" },
  { id: "mes", rotulo: "Este mês" },
  { id: "todos", rotulo: "Todos" },
];

export default function Revisao() {
  const navigate = useNavigate();
  const { ym, label } = usePeriod();
  const [filtro, setFiltro] = useState<Filtro>("sem-forma");
  const [marcados, setMarcados] = useState<Set<number>>(new Set());
  const [formaEscolhida, setFormaEscolhida] = useState<PaymentMethod | null>(null);
  const [cardId, setCardId] = useState<number | null>(null);
  const [editando, setEditando] = useState<Transaction | null>(null);

  // Sem período: aqui se olha o histórico inteiro, não o mês selecionado.
  const { data: todos, isLoading, error } = useQuery({
    queryKey: ["transactions", "revisao"],
    queryFn: () => transactionsApi.list(),
  });
  const { data: categories } = useCategories(true);
  const { data: cards } = useCards();
  const lote = useDefinirFormaEmLote();

  const catMap = useMemo(() => {
    const m = new Map<number, { name: string; type: string; icon: string; color: string }>();
    categories?.forEach((c) => m.set(c.id, c));
    return m;
  }, [categories]);

  const lista = useMemo(() => {
    const despesas = (todos ?? []).filter(
      // Só despesa: entrada e investimento não passam por fatura, então não há
      // pergunta a responder neles. Parcela também não — ela já é de uma compra.
      (t) => catMap.get(t.category_id)?.type === "expense" && t.purchase_id == null
    );
    const filtrada =
      filtro === "sem-forma"
        ? despesas.filter((t) => t.payment_method == null)
        : filtro === "mes"
          ? despesas.filter((t) => t.date.startsWith(ym))
          : despesas;
    return filtrada.sort((a, b) => b.date.localeCompare(a.date));
  }, [todos, catMap, filtro, ym]);

  const semForma = useMemo(
    () =>
      (todos ?? []).filter(
        (t) =>
          catMap.get(t.category_id)?.type === "expense" &&
          t.purchase_id == null &&
          t.payment_method == null
      ).length,
    [todos, catMap]
  );

  function alternar(id: number) {
    setMarcados((atual) => {
      const novo = new Set(atual);
      if (novo.has(id)) novo.delete(id);
      else novo.add(id);
      return novo;
    });
  }

  function marcarTodos() {
    setMarcados(
      marcados.size === lista.length ? new Set() : new Set(lista.map((t) => t.id))
    );
  }

  function aplicar() {
    if (!formaEscolhida || marcados.size === 0) return;
    lote.mutate(
      {
        ids: [...marcados],
        metodo: formaEscolhida,
        card_id: formaEscolhida === "credit" ? cardId ?? undefined : undefined,
      },
      {
        onSuccess: () => {
          setMarcados(new Set());
          setFormaEscolhida(null);
        },
      }
    );
  }

  const precisaDeCartao = formaEscolhida === "credit" && cardId == null;

  return (
    <>
      <button
        className="btn btn-ghost btn-sm"
        onClick={() => navigate(-1)}
        style={{ marginBottom: "var(--s3)" }}
      >
        ‹ Voltar
      </button>

      <section className="hero">
        <div className="rot">Organize seus lançamentos</div>
        <div className="big tnum">{semForma}</div>
        <div className="delta">
          {semForma === 1 ? "lançamento sem" : "lançamentos sem"} forma de pagamento
          definida
        </div>
      </section>

      <div className="hint" style={{ marginTop: "var(--s3)" }}>
        Estes lançamentos são anteriores ao cartão. Enquanto não forem
        respondidos, eles contam como <b>saída da conta</b> — que é como já
        contavam, então nenhum número do passado mudou. Marcar "Cartão" tira o
        valor do saldo do mês e joga numa fatura.
      </div>

      <div className="chip-linha" style={{ marginTop: "var(--s4)" }} role="tablist">
        {FILTROS.map(({ id, rotulo }) => (
          <button
            key={id}
            role="tab"
            aria-selected={filtro === id}
            className={filtro === id ? "on" : ""}
            onClick={() => {
              setFiltro(id);
              setMarcados(new Set());
            }}
          >
            {id === "mes" ? label : rotulo}
          </button>
        ))}
      </div>

      {isLoading && <div className="skel" style={{ height: 240, marginTop: "var(--s3)" }} />}
      {error && <div className="error-box">{(error as ApiError).message}</div>}

      {!isLoading && lista.length === 0 && (
        <div className="empty">
          <div className="big">✅</div>
          <div className="tit">Nada para revisar aqui</div>
          <div>Todos os lançamentos deste filtro já têm forma de pagamento.</div>
        </div>
      )}

      {lista.length > 0 && (
        <>
          <div className="sec-title">
            <h2>{lista.length} {lista.length === 1 ? "lançamento" : "lançamentos"}</h2>
            <button className="link" onClick={marcarTodos}>
              {marcados.size === lista.length ? "Desmarcar" : "Marcar todos"}
            </button>
          </div>

          <div className="list">
            {lista.map((t) => {
              const cat = catMap.get(t.category_id);
              const marcado = marcados.has(t.id);
              return (
                <div className={`row revisao-row ${marcado ? "on" : ""}`} key={t.id}>
                  {/* O alvo do toque é a etiqueta inteira, não só o quadradinho:
                      um checkbox de 20px no celular é errar duas em cada dez. */}
                  <label className="revisao-marca">
                    <input
                      type="checkbox"
                      checked={marcado}
                      onChange={() => alternar(t.id)}
                      aria-label={`Selecionar ${t.description}`}
                    />
                  </label>
                  <div className="mid" onClick={() => alternar(t.id)}>
                    <div className="t">{t.description}</div>
                    <div className="s">
                      {formatDiaMes(t.date)}
                      {cat && <> · {cat.name}</>}
                      {t.payment_method && (
                        <> · {PAYMENT_METHOD_LABEL[t.payment_method]}</>
                      )}
                    </div>
                  </div>
                  {/* "R$ 0,00" num lançamento só previsto lê como gasto de
                      zero reais. Ele é uma promessa, e a palavra diz isso — a
                      mesma marca que a lista de lançamentos usa. */}
                  <div className="amt tnum">
                    {formatMoney(t.amount_paid ?? t.amount_planned ?? 0)}
                    {t.amount_paid == null && <span className="sub">previsto</span>}
                  </div>
                  {/* Parcelamento e casos especiais saem daqui: o lote é sempre
                      1x, porque aplicar "3x" a dez linhas de uma vez inventaria
                      dado. Abrir a linha resolve uma por uma. */}
                  <button
                    className="row-editar"
                    onClick={() => setEditando(t)}
                    aria-label={`Abrir ${t.description}`}
                  >
                    ›
                  </button>
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* A barra de ação só aparece com algo marcado, e fica acima da pílula de
          navegação — no celular ela é o polegar que decide.
          O espaçador é irmão dela e não enfeite: sendo `fixed`, ela cobre o fim
          da lista, e sem ele as últimas linhas ficavam inalcançáveis por baixo
          dos botões. Visto na tela com 159 linhas. */}
      {marcados.size > 0 && <div className="espaco-barra" aria-hidden />}
      {marcados.size > 0 && (
        <div className="barra-acao">
          <div className="quantos">
            {marcados.size} {marcados.size === 1 ? "marcado" : "marcados"}
          </div>
          <div className="tipo-toggle" role="group" aria-label="Aplicar forma de pagamento">
            <button
              type="button"
              className={formaEscolhida === "cash" ? "on" : ""}
              onClick={() => setFormaEscolhida("cash")}
            >
              À vista
            </button>
            <button
              type="button"
              className={formaEscolhida === "credit" ? "on" : ""}
              onClick={() => setFormaEscolhida("credit")}
            >
              Cartão
            </button>
          </div>

          {formaEscolhida === "credit" && (
            <div style={{ marginTop: "var(--s3)" }}>
              <CardPicker cards={cards ?? []} valor={cardId} aoEscolher={setCardId} />
            </div>
          )}

          {formaEscolhida && (
            <button
              className="btn btn-primary btn-block"
              style={{ marginTop: "var(--s3)" }}
              disabled={lote.isPending || precisaDeCartao}
              onClick={aplicar}
            >
              {lote.isPending
                ? "Aplicando…"
                : `Marcar ${marcados.size} como ${formaEscolhida === "cash" ? "à vista" : "cartão"}`}
            </button>
          )}

          {lote.data && lote.data.ignorados.length > 0 && (
            <div className="aviso-box" style={{ marginTop: "var(--s3)" }}>
              {lote.data.ignorados.length} não puderam ser alterados:{" "}
              {lote.data.ignorados[0].motivo}.
            </div>
          )}
          {lote.error && (
            <div className="error-box" style={{ padding: 0, marginTop: "var(--s3)" }}>
              {(lote.error as ApiError).message}
            </div>
          )}
        </div>
      )}

      {editando && categories && (
        <TransactionForm
          categories={categories}
          transaction={editando}
          onClose={() => setEditando(null)}
        />
      )}
    </>
  );
}
