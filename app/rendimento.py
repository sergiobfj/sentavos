"""Projeção de rendimento de renda fixa atrelada ao CDI.

Existe porque a aba de Investimento só sabia comparar saldos lançados à mão, e
o "rendimento" que ela calculava era sempre a diferença entre dois números que o
próprio dono digitou — ou seja, zero informação nova. Com a taxa declarada, dá
pra dizer quanto a aplicação *deveria* render, e comparar com o que de fato
rendeu.

## Por que dias úteis

O CDI é uma taxa **ao ano em dias úteis**, e o mercado brasileiro convenciona
252 dias úteis por ano. Um CDB que rende "115% do CDI" com CDI a 10,65% a.a.
não rende 12,25% em 365 dias corridos: ele rende a taxa diária equivalente, e
só nos dias em que há pregão.

    taxa_diaria = (1 + taxa_anual) ** (1 / 252) - 1

Usar dias corridos inflaria o resultado em mais de 40% do que a aplicação
realmente paga — o tipo de erro que faz alguém planejar em cima de dinheiro que
não vai existir.

## O que isto NÃO faz

Não desconta imposto de renda nem IOF. A tabela regressiva de IR (22,5% até 180
dias, caindo a 15% depois de 720) morde bastante o resultado de curto prazo, e
fingir que não existe seria pior do que não projetar. A projeção é **bruta**, e
quem chama precisa dizer isso na tela.
"""

import datetime as dt

# Convenção do mercado brasileiro. Não é o número exato de dias úteis de um ano
# específico — é a base que a própria taxa usa, então a conta tem que usar a
# mesma ou o resultado não bate com o extrato do banco.
DIAS_UTEIS_NO_ANO = 252

# Feriados nacionais fixos, sem os móveis (Carnaval, Sexta-Feira Santa, Corpus
# Christi). O erro de ignorar os três é de ~1% no ano, bem abaixo da imprecisão
# de o CDI ser digitado à mão — e a alternativa seria carregar uma tabela de
# feriados que envelhece e ninguém lembra de atualizar.
FERIADOS_FIXOS = {(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (12, 25)}


def eh_dia_util(data: dt.date) -> bool:
    if data.weekday() >= 5:  # sábado e domingo
        return False
    return (data.month, data.day) not in FERIADOS_FIXOS


def dias_uteis_entre(inicio: dt.date, fim: dt.date) -> int:
    """Dias úteis no intervalo [inicio, fim). Zero se fim <= inicio."""
    if fim <= inicio:
        return 0
    total = 0
    dia = inicio
    while dia < fim:
        if eh_dia_util(dia):
            total += 1
        dia += dt.timedelta(days=1)
    return total


def taxa_diaria(cdi_anual: float, percentual_do_cdi: float) -> float:
    """Taxa diária equivalente de uma aplicação que rende X% do CDI.

    `cdi_anual` e `percentual_do_cdi` vêm em porcentagem (10.65 e 115.0), não em
    fração — é como o banco mostra, e converter na fronteira evita que alguém
    passe 0.1065 achando que é a mesma coisa.
    """
    anual = (cdi_anual / 100.0) * (percentual_do_cdi / 100.0)
    if anual <= -1:
        return 0.0
    return (1 + anual) ** (1 / DIAS_UTEIS_NO_ANO) - 1


def render(
    principal: float,
    cdi_anual: float,
    percentual_do_cdi: float,
    inicio: dt.date,
    fim: dt.date,
) -> float:
    """Quanto `principal` vira no fim do período, com juros compostos.

    Composto e não simples porque é assim que renda fixa funciona: o rendimento
    de ontem rende hoje. Em um mês a diferença é pequena; em dois anos, não.
    """
    if principal <= 0:
        return max(principal, 0.0)
    dias = dias_uteis_entre(inicio, fim)
    if dias == 0:
        return principal
    return principal * (1 + taxa_diaria(cdi_anual, percentual_do_cdi)) ** dias


def rendimento_do_mes(
    principal: float, cdi_anual: float, percentual_do_cdi: float, ano: int, mes: int
) -> float:
    """Quanto a aplicação deveria render no mês — só a parte que já passou.

    Projetar o mês inteiro no dia 5 mostraria um rendimento que ainda não
    aconteceu, e a pessoa compararia com o saldo real achando que perdeu
    dinheiro. Até o fim do mês corrente, conta só até hoje.
    """
    inicio = dt.date(ano, mes, 1)
    proximo = dt.date(ano + 1, 1, 1) if mes == 12 else dt.date(ano, mes + 1, 1)
    hoje = dt.date.today()
    fim = min(proximo, hoje) if hoje > inicio else inicio
    return round(render(principal, cdi_anual, percentual_do_cdi, inicio, fim) - principal, 2)
