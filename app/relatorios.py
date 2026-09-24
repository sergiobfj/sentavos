"""As somas que os relatórios mostram, agregadas no banco e não no navegador.

Duas perguntas, uma consulta cada:

  - **como o mês evoluiu** (`serie_mensal`): gasto, entrada, investimento e saldo
    do mês, para N meses de uma vez — uma ida ao banco para o ano inteiro, e não
    doze chamadas de `/budgets/summary`.
  - **para onde o gasto foi** (`distribuicao`): gasto por categoria, com o
    percentual calculado sobre o TOTAL do filtro. A versão anterior dividia pela
    soma só das categorias visíveis, e com o top 5 na tela "Alimentação 20%"
    virava 31%.

## Os dois eixos, e qual deles a finalidade filtra

Mesma separação do cartão (ver `app/faturas.py`):

  - GASTO, por competência — compra no cartão entra no mês da parcela. É o eixo
    que a finalidade filtra: "quanto a família gastou em setembro".
  - CAIXA — entrou, investiu, faturas pagas e o saldo do mês. **Nunca** é
    filtrado por finalidade. Se a compra da família saiu da minha conta, ela
    mexeu no meu caixa; finalidade responde "quem consumiu", não "de onde saiu".

## Uma regra só para o saldo

`somas_por_mes` é o mesmo agrupamento que `resumo_de_caixa` usa para a Carteira
(agora "Saldo do mês") de um mês só. Os dois partem daqui, e é isso que garante
que a série e o Início nunca discordem sobre o mesmo mês.
"""

import datetime as dt

from sqlmodel import Session, func, select

from app.cartao import avancar_meses, limites_do_mes
from app.models import (
    Category,
    CategoryType,
    Finalidade,
    InvoicePayment,
    PaymentMethod,
    Transaction,
    User,
)

# Chave de uma soma: (tipo de categoria, forma de pagamento, finalidade), com
# nulo como valor legítimo nas duas últimas — é o estado dos lançamentos antigos.
Chave = tuple[str, str | None, str | None]


def _ano_mes():
    """Ano e mês da competência, como inteiros, em SQLite e Postgres.

    `extract` compila pra `strftime` no SQLite e pra `EXTRACT` no Postgres; um
    `to_char` ou `strftime` escrito à mão funcionaria em um banco só.
    """
    return (
        func.extract("year", Transaction.date).label("ano"),
        func.extract("month", Transaction.date).label("mes"),
    )


def somas_por_mes(
    session: Session, dono: User, inicio: dt.date, fim: dt.date
) -> dict[tuple[int, int], dict[Chave, float]]:
    """{(ano, mês): {(tipo, forma, finalidade): soma de amount_paid}} em [início, fim).

    Agrupado por forma de pagamento e finalidade e resolvido em Python pelo
    mesmo motivo de sempre: `forma != 'credit'` em SQL descarta o NULL, e NULL é
    justamente o estado dos lançamentos anteriores ao cartão.
    """
    ano, mes = _ano_mes()
    linhas = session.exec(
        select(
            ano,
            mes,
            Category.type,
            Transaction.payment_method,
            Transaction.finalidade,
            func.coalesce(func.sum(Transaction.amount_paid), 0.0),
        )
        .join(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.user_id == dono.id,
            Transaction.date >= inicio,
            Transaction.date < fim,
        )
        .group_by(ano, mes, Category.type, Transaction.payment_method, Transaction.finalidade)
    ).all()

    saida: dict[tuple[int, int], dict[Chave, float]] = {}
    for a, m, tipo, forma, finalidade, soma in linhas:
        chave = (
            CategoryType(tipo).value,
            PaymentMethod(forma).value if forma else None,
            Finalidade(finalidade).value if finalidade else None,
        )
        bucket = saida.setdefault((int(a), int(m)), {})
        bucket[chave] = bucket.get(chave, 0.0) + float(soma or 0.0)
    return saida


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
        for (t, forma, fin), valor in somas.items()
        if t == tipo
        and (formas is None or forma in formas)
        and (finalidade is None or fin == finalidade)
    )


def saldo_do_mes(somas: dict[Chave, float], faturas_pagas: float) -> dict[str, float]:
    """Os números de caixa de um mês. A regra de sempre, num lugar só:

        saldo = entrou − despesa à vista (inclui forma nula) − investido − faturas pagas

    Compra no cartão não entra: ela sai da conta quando a fatura é paga. A
    forma nula conta como à vista porque é assim que ela já era contada antes
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


def faturas_pagas_por_mes(
    session: Session, dono: User, inicio: dt.date, fim: dt.date
) -> dict[tuple[int, int], float]:
    ano = func.extract("year", InvoicePayment.date)
    mes = func.extract("month", InvoicePayment.date)
    return {
        (int(a), int(m)): float(soma or 0.0)
        for a, m, soma in session.exec(
            select(ano, mes, func.coalesce(func.sum(InvoicePayment.amount), 0.0))
            .where(
                InvoicePayment.user_id == dono.id,
                InvoicePayment.date >= inicio,
                InvoicePayment.date < fim,
            )
            .group_by(ano, mes)
        ).all()
    }


def meses_entre(de: tuple[int, int], ate: tuple[int, int]) -> list[tuple[int, int]]:
    """Todos os meses de `de` até `ate`, inclusive, atravessando a virada do ano."""
    total = (ate[0] * 12 + ate[1]) - (de[0] * 12 + de[1])
    return [avancar_meses(de[0], de[1], i) for i in range(total + 1)]


def serie_mensal(
    session: Session,
    dono: User,
    de: tuple[int, int],
    ate: tuple[int, int],
    finalidade: Finalidade | None,
) -> list[dict]:
    """Um ponto por mês, INCLUSIVE os meses vazios.

    Mês sem lançamento vem com zero, e não some: numa linha do tempo, pular
    julho faria junho e agosto parecerem vizinhos e a queda sumir do desenho.
    """
    meses = meses_entre(de, ate)
    inicio = limites_do_mes(*meses[0])[0]
    fim = limites_do_mes(*meses[-1])[1]

    somas = somas_por_mes(session, dono, inicio, fim)
    pagas = faturas_pagas_por_mes(session, dono, inicio, fim)
    fin = finalidade.value if finalidade else None

    serie = []
    for ano, mes in meses:
        do_mes = somas.get((ano, mes), {})
        caixa = saldo_do_mes(do_mes, pagas.get((ano, mes), 0.0))
        gasto_total = caixa["gasto_total"]
        gasto = gasto_total if fin is None else somar(do_mes, "expense", finalidade=fin)
        serie.append(
            {
                "year": ano,
                "month": mes,
                # Eixo do gasto — o único que o filtro de finalidade estreita.
                "expense": round(gasto, 2),
                "expense_total": round(gasto_total, 2),
                "expense_sem_finalidade": round(
                    somar(do_mes, "expense") - sum(
                        somar(do_mes, "expense", finalidade=f.value) for f in Finalidade
                    ),
                    2,
                ),
                # Eixo do caixa — sempre global.
                "income": round(caixa["entrou"], 2),
                "investment": round(caixa["investido"], 2),
                "invoice_payments": round(pagas.get((ano, mes), 0.0), 2),
                "cash_flow": round(caixa["saldo"], 2),
            }
        )
    return serie


def distribuicao(
    session: Session,
    dono: User,
    ano: int,
    mes: int,
    finalidade: Finalidade | None,
    top: int,
) -> dict:
    """Gasto do mês por categoria: as `top` maiores e o resto em "Outras".

    O percentual é sobre o total do filtro, sempre. Dividir pela soma só das
    categorias exibidas faria a fatia mudar de tamanho conforme o top escolhido.
    Vai sem arredondar: a soma dos percentuais fecha 100 aqui, e arredondar é
    trabalho da tela, que sabe quantas casas mostrar.

    Categoria arquivada entra normalmente: arquivar tira do formulário, não
    apaga o que foi gasto nela naquele mês.
    """
    inicio, fim = limites_do_mes(ano, mes)
    query = (
        select(
            Category.id,
            Category.name,
            Category.icon,
            Category.color,
            Category.archived,
            func.coalesce(func.sum(Transaction.amount_paid), 0.0),
        )
        .join(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.user_id == dono.id,
            Transaction.date >= inicio,
            Transaction.date < fim,
            Category.type == CategoryType.EXPENSE,
        )
        .group_by(Category.id, Category.name, Category.icon, Category.color, Category.archived)
    )
    if finalidade is not None:
        query = query.where(Transaction.finalidade == finalidade)

    linhas = [
        {
            "category_id": cid,
            "name": nome,
            "icon": icone,
            "color": cor,
            "archived": bool(arquivada),
            "value": round(float(soma or 0.0), 2),
        }
        for cid, nome, icone, cor, arquivada, soma in session.exec(query).all()
    ]
    # Só gasto positivo desenha fatia. Estorno maior que o gasto deixaria uma
    # categoria negativa, que não tem fatia possível numa rosca.
    linhas = [l for l in linhas if l["value"] > 0]
    linhas.sort(key=lambda l: (-l["value"], l["name"]))

    total = sum(l["value"] for l in linhas)
    for l in linhas:
        l["pct"] = (l["value"] / total * 100) if total else 0.0

    visiveis, resto = linhas[:top], linhas[top:]
    # Uma "Outras" de uma categoria só é pior que mostrar a categoria: o nome
    # dela cabe no mesmo espaço e diz mais.
    if len(resto) == 1:
        visiveis, resto = linhas, []

    outras = None
    if resto:
        valor = round(sum(l["value"] for l in resto), 2)
        outras = {
            "value": valor,
            "pct": (valor / total * 100) if total else 0.0,
            "count": len(resto),
        }

    # Quanto do mês não tem finalidade — o que um filtro não-Todos deixa de fora.
    # É o que permite a tela dizer isso em vez de apresentar um total parcial
    # como se fosse o completo.
    sem = session.exec(
        select(func.count(Transaction.id), func.coalesce(func.sum(Transaction.amount_paid), 0.0))
        .join(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.user_id == dono.id,
            Transaction.date >= inicio,
            Transaction.date < fim,
            Category.type == CategoryType.EXPENSE,
            Transaction.finalidade.is_(None),
            Transaction.amount_paid.is_not(None),
        )
    ).one()

    return {
        "year": ano,
        "month": mes,
        "finalidade": finalidade.value if finalidade else None,
        "total": round(total, 2),
        "categories": visiveis,
        "others": outras,
        "sem_finalidade": {"count": int(sem[0] or 0), "value": round(float(sem[1] or 0.0), 2)},
    }
