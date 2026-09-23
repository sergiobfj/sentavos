"""O ciclo da fatura e a divisão em parcelas, sem banco.

São as duas contas que, erradas, produzem um número plausível — e número
plausível e errado é o pior tipo de defeito num app de dinheiro, porque ninguém
desconfia dele. Por isso elas são funções puras e têm teste próprio.
"""

import datetime as dt

import pytest

from app.cartao import (
    avancar_meses,
    ciclo_da_parcela,
    competencia_da_parcela,
    dia_do_mes,
    dividir_em_parcelas,
    fechamento_da_compra,
    limites_do_mes,
    referencia,
    vencimento_apos,
)

# O cartão do dono: fecha 25, vence 02 do mês seguinte.
FECHA, VENCE = 25, 2


# ---------- O dia do fechamento ----------


@pytest.mark.parametrize(
    "compra,fechamento_esperado",
    [
        # Antes do fechamento: entra no ciclo que fecha neste mês.
        (dt.date(2026, 9, 24), dt.date(2026, 9, 25)),
        # NO dia do fechamento: ainda entra. É a convenção da maioria dos
        # bancos brasileiros, e a decisão está num lugar só (app/cartao.py).
        (dt.date(2026, 9, 25), dt.date(2026, 9, 25)),
        # Depois: vai pro ciclo seguinte.
        (dt.date(2026, 9, 26), dt.date(2026, 10, 25)),
        # Primeiro dia do mês, bem longe do fechamento.
        (dt.date(2026, 9, 1), dt.date(2026, 9, 25)),
    ],
)
def test_fechamento_em_volta_do_dia_de_corte(compra, fechamento_esperado):
    assert fechamento_da_compra(compra, FECHA) == fechamento_esperado


def test_virada_de_ano_no_fechamento():
    """Compra depois do fechamento de dezembro fecha em janeiro do ano seguinte."""
    assert fechamento_da_compra(dt.date(2026, 12, 26), FECHA) == dt.date(2027, 1, 25)


def test_fechamento_dia_31_em_fevereiro():
    """Cartão que fecha 31 fecha no último dia do mês curto.

    Sem o achatamento, `date(2027, 2, 31)` estoura — e fevereiro é justamente o
    mês em que ninguém testa.
    """
    assert fechamento_da_compra(dt.date(2027, 2, 10), 31) == dt.date(2027, 2, 28)
    assert dia_do_mes(2028, 2, 31) == dt.date(2028, 2, 29)  # bissexto


# ---------- O vencimento ----------


def test_vence_no_mes_seguinte_quando_o_dia_e_menor():
    """fecha 25, vence 02 → a fatura que fecha 25/09 vence 02/10."""
    assert vencimento_apos(dt.date(2026, 9, 25), VENCE) == dt.date(2026, 10, 2)


def test_vence_no_mesmo_mes_quando_o_dia_e_maior():
    """fecha 05, vence 15 → mesma competência, sem ramificar a regra."""
    assert vencimento_apos(dt.date(2026, 10, 5), 15) == dt.date(2026, 10, 15)


def test_referencia_e_o_mes_do_vencimento():
    """A fatura que fecha em setembro e vence em outubro é 'a de outubro'.

    É como o banco a chama e como se fala dela na hora de pagar — usar o mês do
    fechamento faria a tela discordar do aplicativo do banco.
    """
    _, vencimento = ciclo_da_parcela(dt.date(2026, 9, 23), FECHA, VENCE)
    assert vencimento == dt.date(2026, 10, 2)
    assert referencia(vencimento) == (2026, 10)


# ---------- Competência x cobrança ----------


def test_compra_depois_do_fechamento_continua_sendo_gasto_do_mes_da_compra():
    """O caso que motivou separar os quatro conceitos.

    Compra em 28/09 num cartão que fecha 25: é gasto de SETEMBRO (foi quando
    aconteceu) e é cobrada na fatura que vence em NOVEMBRO. Misturar os dois
    faria alguém "gastar" em novembro o que comeu em setembro.
    """
    compra = dt.date(2026, 9, 28)

    assert competencia_da_parcela(compra, 1).month == 9

    fechamento, vencimento = ciclo_da_parcela(compra, FECHA, VENCE, 1)
    assert fechamento == dt.date(2026, 10, 25)
    assert referencia(vencimento) == (2026, 11)


def test_primeira_parcela_sempre_no_mes_da_compra():
    compra = dt.date(2026, 9, 23)
    assert competencia_da_parcela(compra, 1) == compra


def test_parcelas_seguintes_andam_um_mes_por_vez():
    compra = dt.date(2026, 9, 23)
    assert competencia_da_parcela(compra, 2) == dt.date(2026, 10, 23)
    assert competencia_da_parcela(compra, 3) == dt.date(2026, 11, 23)


def test_parcelamento_atravessando_o_ano():
    """Compra em novembro/2026 em 3x: gasto em nov, dez e jan; faturas dez, jan, fev."""
    compra = dt.date(2026, 11, 15)

    competencias = [competencia_da_parcela(compra, n) for n in (1, 2, 3)]
    assert competencias == [
        dt.date(2026, 11, 15),
        dt.date(2026, 12, 15),
        dt.date(2027, 1, 15),
    ]

    refs = [referencia(ciclo_da_parcela(compra, FECHA, VENCE, n)[1]) for n in (1, 2, 3)]
    assert refs == [(2026, 12), (2027, 1), (2027, 2)]


def test_competencia_de_compra_no_dia_31():
    """Compra em 31/01 parcelada: a segunda cai em 28/02, não em 03/03.

    E a terceira volta pro dia 31 — o achatamento é do mês curto, não uma
    mudança permanente na data da parcela.
    """
    compra = dt.date(2026, 1, 31)
    assert competencia_da_parcela(compra, 2) == dt.date(2026, 2, 28)
    assert competencia_da_parcela(compra, 3) == dt.date(2026, 3, 31)


# ---------- Centavos ----------


def test_cem_reais_em_tres_vezes():
    """O caso do enunciado: nunca pode somar diferente de R$ 100,00."""
    parcelas = dividir_em_parcelas(100.0, 3)
    assert parcelas == [33.34, 33.33, 33.33]
    assert round(sum(parcelas), 2) == 100.00


def test_o_resto_vai_na_primeira_parcela():
    """Na primeira e não na última: é a que aparece no mês da compra, quando a
    pessoa ainda lembra quanto gastou e pode conferir contra o extrato."""
    parcelas = dividir_em_parcelas(10.0, 3)
    assert parcelas[0] > parcelas[1]


@pytest.mark.parametrize(
    "total,n",
    [
        (100.0, 3), (0.01, 3), (0.03, 2), (7.0, 3), (1000.0, 12), (1234.56, 7),
        (89.9, 2), (2499.99, 24), (0.02, 3), (33.33, 3), (19.99, 6), (5.0, 4),
    ],
)
def test_a_soma_das_parcelas_e_sempre_o_total(total, n):
    """A invariante que não pode falhar em nenhuma combinação.

    Comparação em centavos inteiros, e não em float: `33.34 + 33.33 + 33.33`
    pode dar 100.00000000000001, e o que importa é que o banco cobre cem reais.
    """
    parcelas = dividir_em_parcelas(total, n)
    assert len(parcelas) == n
    assert round(sum(parcelas) * 100) == round(total * 100)


def test_uma_parcela_e_o_valor_inteiro():
    assert dividir_em_parcelas(1200.0, 1) == [1200.0]


def test_parcela_zero_e_recusada():
    with pytest.raises(ValueError):
        dividir_em_parcelas(100.0, 0)


# ---------- Deslocamento de mês ----------


def test_avancar_meses_atravessa_o_ano():
    assert avancar_meses(2026, 11, 3) == (2027, 2)
    assert avancar_meses(2026, 1, -1) == (2025, 12)


def test_limites_do_mes_em_dezembro():
    assert limites_do_mes(2026, 12) == (dt.date(2026, 12, 1), dt.date(2027, 1, 1))
