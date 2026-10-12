"""A regra do caixa: o que sai e entra da conta.

Uma regra, duas formas de usar:

  - `saldo_do_mes` lê somas agrupadas (tipo, forma, finalidade) de um mês —
    é o "Saldo do mês" do Início e a série dos relatórios;
  - `efeito_no_caixa` lê um lançamento — é o saldo de uma conta e a lista de
    movimentos do planejamento.

As duas dizem a mesma coisa:

  - receita entra;
  - despesa à vista (ou sem forma, o histórico anterior ao cartão) sai;
  - compra no cartão NÃO sai agora: sai quando a fatura é paga;
  - aporte (investimento positivo) sai e resgate (investimento negativo)
    entra — e nenhum dos dois é gasto ou receita;
  - pagamento de fatura sai, e não é gasto (o gasto foi a compra).
"""

from app.models import CategoryType, PaymentMethod

# Chave de uma soma: (tipo de categoria, forma de pagamento, finalidade), com
# nulo como valor legítimo nas duas últimas — é o estado dos lançamentos antigos.
Chave = tuple[str, str | None, str | None]


def somar(
    somas: dict[Chave, float],
    tipo: str,
    formas: tuple[str | None, ...] | None = None,
    finalidade: str | None = None,
) -> float:
    """Soma o que casa com o filtro. `formas=None` = qualquer forma;
    `finalidade=None` = qualquer finalidade (inclusive nula)."""
    return sum(
        valor
        for (t, forma, fin, *_), valor in somas.items()
        if t == tipo
        and (formas is None or forma in formas)
        and (finalidade is None or fin == finalidade)
    )


def saldo_do_mes(somas: dict[Chave, float], faturas_pagas: float) -> dict[str, float]:
    """Os números de caixa de um mês:

        saldo = entrou − despesa à vista (inclui forma nula) − investido − faturas pagas

    A forma nula conta como à vista porque é assim que ela já era contada antes
    do cartão — tratá-la de outro jeito mudaria o saldo de todo mês passado.
    """
    entrou = somar(somas, "income")
    investido = somar(somas, "investment")
    sem_forma = somar(somas, "expense", (None,))
    a_vista = somar(somas, "expense", ("cash",)) + sem_forma
    no_cartao = somar(somas, "expense", ("credit",))
    return {
        "entrou": entrou,
        "investido": investido,
        "a_vista": a_vista,
        "sem_forma": sem_forma,
        "no_cartao": no_cartao,
        "gasto_total": a_vista + no_cartao,
        "saldo": entrou - a_vista - investido - faturas_pagas,
    }


def efeito_no_caixa(tipo: CategoryType | str, forma: PaymentMethod | str | None, valor_pago: float) -> float:
    """Quanto um lançamento PAGO muda o dinheiro da conta (+ entra, − sai)."""
    tipo = CategoryType(tipo)
    if tipo == CategoryType.INCOME:
        return valor_pago
    if tipo == CategoryType.INVESTMENT:
        # Aporte (+) sai da conta; resgate (−) volta pra ela.
        return -valor_pago
    if forma is not None and PaymentMethod(forma) == PaymentMethod.CREDIT:
        return 0.0
    return -valor_pago
