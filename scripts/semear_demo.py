"""Preenche a conta de demonstração com uma vida financeira fictícia.

    uv run python -m scripts.semear_demo demo@sentavos.app

Gera 12 meses coerentes: salário que cai todo dia 5, aluguel que não muda,
mercado que oscila, uma categoria estourando o orçamento, patrimônio subindo e
um financiamento encolhendo. A ideia é que quem abrir o link entenda o app em
dez segundos, sem precisar imaginar como ficaria com dado de verdade.

Nada aqui vem dos seus lançamentos. É tudo inventado, e de propósito: num link
que vai pro LinkedIn, "quase anonimizado" é o tipo de coisa que se descobre ter
falhado depois que já foi visto.

O gerador é determinístico (semente fixa). Rodar duas vezes produz exatamente o
mesmo demo, então dá pra recriar a conta sem ela mudar de cara.
"""

import argparse
import datetime as dt
import os
import random
import sys

from sqlmodel import Session, select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine  # noqa: E402
from app.models import (  # noqa: E402
    Asset,
    AssetClass,
    AssetSnapshot,
    Budget,
    Category,
    CategoryType,
    Transaction,
    User,
)

# Semente fixa: o demo precisa ser o mesmo toda vez que for recriado.
rnd = random.Random(20260913)

MESES = 12
FIM = dt.date(2026, 9, 1)

# (nome, tipo, cor, ícone, dia do mês, valor base, variação, orçado)
#
# A variação é o que separa "planilha de exemplo" de "vida real": aluguel não
# muda, mercado muda todo mês. Sem isso o demo parece gerado — porque é.
CATEGORIAS = [
    ("Salário",        CategoryType.INCOME,     "#3ecf8e", "💰",  5, 4500.00, 0.00, 4500),
    ("Freelance",      CategoryType.INCOME,     "#48c47d", "💻", 20,  800.00, 0.45,  600),
    ("Aluguel",        CategoryType.EXPENSE,    "#ef5350", "🏠", 10, 1450.00, 0.00, 1450),
    ("Mercado",        CategoryType.EXPENSE,    "#e07a5f", "🛒",  8,  820.00, 0.18,  750),
    ("Restaurante",    CategoryType.EXPENSE,    "#d64550", "🍽️", 15,  310.00, 0.35,  250),
    ("Transporte",     CategoryType.EXPENSE,    "#c9705a", "🚗", 12,  240.00, 0.25,  260),
    ("Internet",       CategoryType.EXPENSE,    "#f07470", "🌐", 18,   99.90, 0.00,  100),
    ("Academia",       CategoryType.EXPENSE,    "#ef5350", "🏋️", 10,  129.00, 0.00,  129),
    ("Assinaturas",    CategoryType.EXPENSE,    "#e07a5f", "📺",  3,   69.90, 0.10,   70),
    ("Farmácia",       CategoryType.EXPENSE,    "#d64550", "💊", 22,   85.00, 0.40,   80),
    ("Reserva",        CategoryType.INVESTMENT, "#7c9bff", "🏦",  6,  600.00, 0.10,  600),
    ("Tesouro Selic",  CategoryType.INVESTMENT, "#5a78e8", "📈",  6,  400.00, 0.15,  400),
]

# (nome, classe, nota, valor inicial, crescimento mensal)
#
# O financiamento encolhe (crescimento negativo): é dívida, e é o que faz o
# patrimônio líquido subir mais rápido que a soma dos ativos — que é
# exatamente a coisa que uma planilha não mostra bem.
ATIVOS = [
    ("Conta corrente",      AssetClass.CHECKING,     "Onde o salário cai",        2400.0,   40.0),
    ("Reserva de emergência", AssetClass.FIXED_INCOME, "CDB de liquidez diária", 8500.0,  640.0),
    ("Tesouro Selic",       AssetClass.FIXED_INCOME, "Aposentadoria",            12000.0,  430.0),
    ("Ações",               AssetClass.EQUITY,       "Carteira de longo prazo",   6200.0,  180.0),
    ("Financiamento do carro", AssetClass.DEBT,      "Restam 28 parcelas",       31000.0, -780.0),
]


def periodos() -> list[tuple[int, int]]:
    """Os 12 meses até FIM, do mais antigo pro mais novo."""
    fim = FIM.year * 12 + (FIM.month - 1)
    return [((fim - i) // 12, ((fim - i) % 12) + 1) for i in range(MESES - 1, -1, -1)]


def valor(base: float, variacao: float) -> float:
    if variacao == 0:
        return base
    return round(base * (1 + rnd.uniform(-variacao, variacao)), 2)


def semear(dono: User, s: Session) -> dict:
    contagem = {"categorias": 0, "lancamentos": 0, "metas": 0, "ativos": 0, "saldos": 0}

    categorias: dict[str, Category] = {}
    for nome, tipo, cor, icone, *_ in CATEGORIAS:
        c = Category(name=nome, type=tipo, color=cor, icon=icone, user_id=dono.id)
        s.add(c)
        categorias[nome] = c
        contagem["categorias"] += 1
    s.commit()
    for c in categorias.values():
        s.refresh(c)

    for ano, mes in periodos():
        for nome, _tipo, _cor, _icone, dia, base, var, orcado in CATEGORIAS:
            cat = categorias[nome]

            # O mês corrente entra parcialmente: o demo é aberto "hoje", e um
            # mês atual já fechado denunciaria que o dado é de mentira.
            if (ano, mes) == (FIM.year, FIM.month) and dia > 14:
                pago = None
            else:
                pago = valor(base, var)

            s.add(Transaction(
                user_id=dono.id,
                date=dt.date(ano, mes, min(dia, 28)),
                description=nome,
                amount_planned=round(base, 2),
                amount_paid=pago,
                category_id=cat.id,
            ))
            contagem["lancamentos"] += 1

            s.add(Budget(
                user_id=dono.id, category_id=cat.id,
                year=ano, month=mes, amount=float(orcado),
            ))
            contagem["metas"] += 1

        # Uns poucos gastos avulsos por mês, pra a lista não parecer um carimbo.
        for _ in range(rnd.randint(2, 4)):
            nome, cat = rnd.choice(
                [(n, categorias[n]) for n, t, *_ in CATEGORIAS if t == CategoryType.EXPENSE]
            )
            s.add(Transaction(
                user_id=dono.id,
                date=dt.date(ano, mes, rnd.randint(2, 27)),
                description=rnd.choice(
                    ["Padaria", "Uber", "Livraria", "Presente", "Cinema",
                     "Barbearia", "Feira", "Café", "Estacionamento"]
                ),
                amount_paid=round(rnd.uniform(18, 140), 2),
                category_id=cat.id,
            ))
            contagem["lancamentos"] += 1

    s.commit()

    for nome, classe, nota, inicial, passo in ATIVOS:
        ativo = Asset(name=nome, asset_class=classe, note=nota, user_id=dono.id)
        s.add(ativo)
        s.commit()
        s.refresh(ativo)
        contagem["ativos"] += 1

        for i, (ano, mes) in enumerate(periodos()):
            bruto = inicial + passo * i
            # Um tremidinho nas aplicações de risco; conta e dívida andam retas.
            if classe in (AssetClass.EQUITY, AssetClass.CRYPTO):
                bruto *= 1 + rnd.uniform(-0.04, 0.05)
            s.add(AssetSnapshot(
                user_id=dono.id, asset_id=ativo.id,
                year=ano, month=mes, value=round(max(bruto, 0.0), 2),
            ))
            contagem["saldos"] += 1

    s.commit()
    return contagem


def main() -> int:
    p = argparse.ArgumentParser(description="Popula a conta de demonstração.")
    p.add_argument("email", help="e-mail da conta demo")
    p.add_argument("--limpar", action="store_true",
                   help="apaga o que a conta já tem antes de semear")
    args = p.parse_args()

    with Session(engine) as s:
        dono = s.exec(select(User).where(User.email == args.email.strip().lower())).first()
        if dono is None:
            print(f"Não existe conta para {args.email}. "
                  "Crie com: uv run python -m app.criar_usuario", file=sys.stderr)
            return 1

        if not dono.read_only:
            # Aviso e não erro: pode ser proposital semear uma conta de teste
            # comum. Mas se for o demo público, read_only é o que impede o
            # primeiro visitante de apagar tudo.
            print(f"Atenção: {dono.email} NÃO é somente-leitura. "
                  "Como conta de demonstração pública, ela deveria ser.\n")

        if args.limpar:
            # Ordem importa: o que aponta pra outro sai primeiro, senão a chave
            # estrangeira barra o delete.
            for modelo in (Transaction, Budget, AssetSnapshot, Asset, Category):
                for linha in s.exec(select(modelo).where(modelo.user_id == dono.id)).all():
                    s.delete(linha)
            s.commit()
            print("Conta limpa.")

        # Guardado antes de fechar a sessão: depois do `with`, o objeto está
        # desanexado e ler qualquer atributo estoura DetachedInstanceError.
        email_dono = dono.email
        contagem = semear(dono, s)

    print(f"Demo semeada em {email_dono}:")
    for chave, qtd in contagem.items():
        print(f"   {chave:14} {qtd}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
