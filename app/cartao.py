"""O ciclo do cartão de crédito: que fatura cobra o quê, e como parcelar.

Existe porque o app tratava "tive uma despesa" e "o dinheiro saiu da conta" como
o mesmo evento. Isso vale pra PIX, débito e dinheiro. No cartão são dois eventos
separados por até quase dois meses, e misturá-los faz a Carteira mentir.

Tudo aqui é função pura sobre datas e centavos — sem banco, sem sessão. É o mesmo
arranjo de `app/rendimento.py`, e pelo mesmo motivo: a regra que dá erro caro é a
que precisa ser testável sozinha, sem montar um cenário inteiro pra exercitá-la.

## As quatro datas que não podem se misturar

    compra 28/09  ->  gasto de SETEMBRO  ->  fatura que vence 02/11  ->  paga 02/11
    ^data da compra   ^competência           ^cobrança                  ^saída de caixa

Uma compra feita depois do fechamento continua sendo gasto do mês em que foi
feita — o que muda é só em qual fatura ela é cobrada. Confundir os dois é o que
faz alguém "gastar" em novembro o que comeu em setembro.

## A convenção do fechamento

O ciclo é **(fechamento anterior, fechamento atual]**: a compra feita no próprio
dia do fechamento entra na fatura que fecha naquele dia. É a regra da maioria dos
bancos brasileiros, e a decisão está aqui num lugar só porque é o tipo de coisa
que, espalhada, passa a valer diferente em cada tela.
"""

import calendar
import datetime as dt


def ultimo_dia(ano: int, mes: int) -> int:
    return calendar.monthrange(ano, mes)[1]


def dia_do_mes(ano: int, mes: int, dia: int) -> dt.date:
    """A data pedida, achatada no último dia quando o mês é curto.

    Cartão que fecha dia 31 fecha 28 em fevereiro. Sem isto, `date(2026, 2, 31)`
    estoura — e fevereiro é justamente o mês em que ninguém testa.
    """
    return dt.date(ano, mes, min(dia, ultimo_dia(ano, mes)))


def avancar_meses(ano: int, mes: int, passos: int) -> tuple[int, int]:
    """(ano, mês) deslocado, sem as armadilhas de virada de ano."""
    i = ano * 12 + (mes - 1) + passos
    return i // 12, (i % 12) + 1


def limites_do_mes(ano: int, mes: int) -> tuple[dt.date, dt.date]:
    """Intervalo semiaberto [início, fim) do mês. Dezembro vira janeiro seguinte.

    Mora aqui, e não em cada arquivo que precisa dele, porque "o que é o mês de
    setembro" é a pergunta que todo número deste app responde — e duas
    definições dela é o começo de dois totais diferentes pro mesmo mês.
    """
    inicio = dt.date(ano, mes, 1)
    proximo_ano, proximo_mes = avancar_meses(ano, mes, 1)
    return inicio, dt.date(proximo_ano, proximo_mes, 1)


def fechamento_da_compra(compra: dt.date, dia_fechamento: int) -> dt.date:
    """A data de fechamento do ciclo que contém esta compra.

    Compra NO dia do fechamento entra no ciclo que fecha naquele dia; a partir do
    dia seguinte, vai pro próximo.
    """
    candidato = dia_do_mes(compra.year, compra.month, dia_fechamento)
    if compra <= candidato:
        return candidato
    ano, mes = avancar_meses(compra.year, compra.month, 1)
    return dia_do_mes(ano, mes, dia_fechamento)


def vencimento_apos(fechamento: dt.date, dia_vencimento: int) -> dt.date:
    """O primeiro dia de vencimento que cai em cima ou depois do fechamento.

    Uma regra só cobre os dois arranjos, em vez de ramificar em "vence antes ou
    depois do fechamento":

        fecha 25, vence 02  ->  fecha 25/09, vence 02/10 (mês seguinte)
        fecha 05, vence 15  ->  fecha 05/10, vence 15/10 (mesmo mês)

    Ela também sobrevive ao achatamento de mês curto, que é onde comparar
    `dia_vencimento` com `dia_fechamento` daria a resposta errada.
    """
    candidato = dia_do_mes(fechamento.year, fechamento.month, dia_vencimento)
    if candidato < fechamento:
        ano, mes = avancar_meses(fechamento.year, fechamento.month, 1)
        candidato = dia_do_mes(ano, mes, dia_vencimento)
    return candidato


def ciclo_da_parcela(
    compra: dt.date, dia_fechamento: int, dia_vencimento: int, numero: int = 1
) -> tuple[dt.date, dt.date]:
    """(fechamento, vencimento) da fatura que cobra a parcela `numero` (1-based).

    A parcela 2 é cobrada na fatura seguinte à da parcela 1, e assim por diante —
    o ciclo anda junto com a competência do gasto, um mês por parcela.
    """
    base = fechamento_da_compra(compra, dia_fechamento)
    ano, mes = avancar_meses(base.year, base.month, numero - 1)
    fechamento = dia_do_mes(ano, mes, dia_fechamento)
    return fechamento, vencimento_apos(fechamento, dia_vencimento)


def referencia(vencimento: dt.date) -> tuple[int, int]:
    """(ano, mês) pelo qual a fatura é conhecida.

    É o mês do VENCIMENTO, não o do fechamento: a fatura que fecha 25/09 e vence
    02/10 é "a fatura de outubro" pra quem vai pagá-la — e é assim que o banco a
    chama.
    """
    return vencimento.year, vencimento.month


def competencia_da_parcela(compra: dt.date, numero: int) -> dt.date:
    """O dia que representa o mês em que a parcela `numero` conta como gasto.

    A primeira parcela é sempre no mês da compra. As seguintes andam um mês por
    vez, com o mesmo achatamento de mês curto do resto do arquivo: compra em
    31/01 parcelada tem a segunda parcela em 28/02, não em 03/03.
    """
    ano, mes = avancar_meses(compra.year, compra.month, numero - 1)
    return dia_do_mes(ano, mes, compra.day)


def dividir_em_parcelas(total: float, parcelas: int) -> list[float]:
    """Divide o total em parcelas que somam EXATAMENTE o total.

    A conta é feita em centavos inteiros porque float não fecha:
    `100 / 3 * 3` não dá 100. O que sobra vai na PRIMEIRA parcela —
    R$ 100,00 em 3x são 33,34 + 33,33 + 33,33.

    Na primeira e não na última de propósito: é a que aparece no mês da compra,
    onde a pessoa ainda lembra quanto gastou e pode conferir contra o extrato.
    """
    if parcelas < 1:
        raise ValueError("Uma compra tem pelo menos uma parcela.")

    centavos = round(total * 100)
    base, resto = divmod(centavos, parcelas)
    return [(base + resto) / 100] + [base / 100] * (parcelas - 1)
