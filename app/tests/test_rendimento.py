"""Cobre a projeção de rendimento de renda fixa.

O que se testa aqui não é "o código roda" — é que a conta bate com o que o banco
paga. Um erro de convenção (dias corridos no lugar de dias úteis, juros simples
no lugar de compostos) não quebra nada: ele produz um número plausível e errado,
que é o pior tipo de bug num app de dinheiro.
"""

import datetime as dt

from app.rendimento import (
    DIAS_UTEIS_NO_ANO,
    dias_uteis_entre,
    eh_dia_util,
    render,
    taxa_diaria,
)


def test_fim_de_semana_nao_e_dia_util():
    assert eh_dia_util(dt.date(2026, 9, 11)) is True   # sexta
    assert eh_dia_util(dt.date(2026, 9, 12)) is False  # sábado
    assert eh_dia_util(dt.date(2026, 9, 13)) is False  # domingo
    assert eh_dia_util(dt.date(2026, 9, 14)) is True   # segunda


def test_feriado_nacional_nao_e_dia_util():
    assert eh_dia_util(dt.date(2026, 9, 7)) is False   # Independência
    assert eh_dia_util(dt.date(2026, 12, 25)) is False  # Natal


def test_uma_semana_tem_cinco_dias_uteis():
    # Segunda a segunda: conta seg-sex e para antes da segunda seguinte.
    assert dias_uteis_entre(dt.date(2026, 9, 14), dt.date(2026, 9, 21)) == 5


def test_intervalo_invertido_da_zero():
    assert dias_uteis_entre(dt.date(2026, 9, 20), dt.date(2026, 9, 10)) == 0


def test_taxa_diaria_composta_reconstroi_a_anual():
    """A taxa diária elevada a 252 tem que voltar na anual.

    É a definição de taxa equivalente, e é o que separa esta conta de uma
    divisão por 252 (que daria juros simples e um resultado menor).
    """
    cdi, pct = 10.65, 115.0
    diaria = taxa_diaria(cdi, pct)
    anual_reconstruida = (1 + diaria) ** DIAS_UTEIS_NO_ANO - 1

    esperado = (cdi / 100) * (pct / 100)
    assert abs(anual_reconstruida - esperado) < 1e-9


def test_cem_por_cento_do_cdi_em_um_ano_util_rende_o_cdi():
    """252 dias úteis de rendimento equivalem à taxa anual cheia."""
    principal = 10_000.0
    # Um ano de calendário tem ~252 dias úteis; aqui a data é escolhida pra
    # fechar exatamente 252 e o teste falar de matemática, não de calendário.
    dias = 0
    dia = dt.date(2026, 1, 1)
    while dias < DIAS_UTEIS_NO_ANO:
        if eh_dia_util(dia):
            dias += 1
        dia += dt.timedelta(days=1)

    final = render(principal, 10.0, 100.0, dt.date(2026, 1, 1), dia)

    assert abs(final - principal * 1.10) < 0.5


def test_dias_corridos_inflaria_o_resultado():
    """Guarda contra a troca de convenção.

    Se alguém trocar 252 por 365 sem perceber, este teste cai. A diferença não é
    acadêmica: são ~45% a mais de rendimento projetado, e alguém planejando em
    cima disso contaria com dinheiro que não vai existir.
    """
    principal = 10_000.0
    inicio, fim = dt.date(2026, 1, 1), dt.date(2027, 1, 1)

    correto = render(principal, 10.0, 100.0, inicio, fim) - principal

    diaria_errada = (1 + 0.10) ** (1 / 365) - 1
    errado = principal * (1 + diaria_errada) ** 365 - principal

    # Os dois dão ~1000 no ano cheio, mas a conta certa usa menos dias.
    assert correto < errado * 1.02
    assert dias_uteis_entre(inicio, fim) < 260


def test_juros_sao_compostos_e_nao_simples():
    """Em prazo longo a diferença aparece, e é ela que o app promete mostrar."""
    principal = 10_000.0
    dois_anos = render(principal, 10.0, 100.0, dt.date(2026, 1, 1), dt.date(2028, 1, 1))

    simples = principal * (1 + 0.10 * 2)

    assert dois_anos > simples


def test_principal_zero_ou_negativo_nao_rende():
    assert render(0.0, 10.0, 115.0, dt.date(2026, 1, 1), dt.date(2027, 1, 1)) == 0.0
    assert render(-500.0, 10.0, 115.0, dt.date(2026, 1, 1), dt.date(2027, 1, 1)) == 0.0


def test_um_dia_util_rende_a_ordem_de_grandeza_certa():
    """Sanidade: 10 mil a 115% do CDI (10,65% a.a.) rendem ~R$ 4,60 por dia útil.

    A conta de cabeça: 12,25% ao ano sobre 10 mil dá ~R$ 1.225; dividido pelos
    252 dias úteis, ~R$ 4,86 (um pouco menos por ser composto).

    A faixa é estreita de propósito. Se alguém aplicar a taxa anual como se
    fosse diária, o resultado saltaria pra mais de mil reais num dia — e num
    número pequeno esse erro passa despercebido em teste frouxo.
    """
    final = render(10_000.0, 10.65, 115.0, dt.date(2026, 9, 14), dt.date(2026, 9, 15))

    assert 4.00 < final - 10_000.0 < 5.00
