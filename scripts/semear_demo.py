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

from app.cartao import competencia_da_parcela, dividir_em_parcelas  # noqa: E402
from app.database import engine  # noqa: E402
from app.faturas import fatura_da_parcela  # noqa: E402
from app.models import (  # noqa: E402
    Asset,
    AssetClass,
    AssetSnapshot,
    Budget,
    Card,
    Category,
    CategoryType,
    Finalidade,
    Invoice,
    InvoicePayment,
    PaymentMethod,
    Purchase,
    Transaction,
    User,
)

# Semente fixa: o demo precisa ser o mesmo toda vez que for recriado.
rnd = random.Random(20260913)

MESES = 12
FIM = dt.date(2026, 9, 1)

# (nome, tipo, cor, ícone, dia do mês, valor base, variação, orçado, finalidade)
#
# A variação é o que separa "planilha de exemplo" de "vida real": aluguel não
# muda, mercado muda todo mês. Sem isso o demo parece gerado — porque é.
#
# As cores são da paleta fechada do app (frontend/src/lib/paleta.ts), na ordem
# dela: a rosca do Início sai com fatias distinguíveis, e não com cinco tons de
# vermelho como a versão anterior.
#
# A finalidade mostra os três contextos: a casa e a escola são da família, o
# software é da empresa, o resto é pessoal. Receita e investimento não têm.
P, F, E = Finalidade.PESSOAL, Finalidade.FAMILIA, Finalidade.EMPRESA
CATEGORIAS = [
    ("Salário",        CategoryType.INCOME,     "#6aa84f", "💰",  5, 4500.00, 0.00, 4500, None),
    ("Freelance",      CategoryType.INCOME,     "#199e70", "💻", 20,  800.00, 0.45,  600, None),
    ("Aluguel",        CategoryType.EXPENSE,    "#3987e5", "🏠", 10, 1450.00, 0.00, 1450, F),
    ("Mercado",        CategoryType.EXPENSE,    "#d95926", "🛒",  8,  820.00, 0.18,  750, F),
    ("Restaurante",    CategoryType.EXPENSE,    "#199e70", "🍽️", 15,  310.00, 0.35,  250, P),
    ("Transporte",     CategoryType.EXPENSE,    "#c98500", "🚗", 12,  240.00, 0.25,  260, P),
    ("Escola",         CategoryType.EXPENSE,    "#9085e9", "🎓",  7,  690.00, 0.00,  690, F),
    ("Academia",       CategoryType.EXPENSE,    "#6aa84f", "🏋️", 10,  129.00, 0.00,  129, P),
    ("Assinaturas",    CategoryType.EXPENSE,    "#d55181", "📺",  3,   69.90, 0.10,   70, P),
    ("Farmácia",       CategoryType.EXPENSE,    "#e66767", "💊", 22,   85.00, 0.40,   80, F),
    ("Software",       CategoryType.EXPENSE,    "#1f94ad", "💼",  4,  189.00, 0.00,  190, E),
    ("Reserva",        CategoryType.INVESTMENT, "#3987e5", "🏦",  6,  600.00, 0.10,  600, None),
    ("Tesouro Selic",  CategoryType.INVESTMENT, "#9085e9", "📈",  6,  400.00, 0.15,  400, None),
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


# (nome, fecha, vence, finalidade) — um cartão por contexto, como na vida real
# de quem separa o cartão da família e o da empresa.
CARTOES = [
    ("Nubank", 25, 2, Finalidade.PESSOAL),
    ("Cartão Família", 5, 15, Finalidade.FAMILIA),
    ("Cartão Empresa", 25, 5, Finalidade.EMPRESA),
]

# (cartão, categoria, descrição, valor, parcelas, meses atrás, dia, finalidade)
#
# Uma compra parcelada atravessando os meses é o que faz o demo mostrar o que
# uma planilha não mostra bem: gasto que já aconteceu e dinheiro que ainda não
# saiu. A finalidade `None` herda a do cartão; o "Presente da sobrinha" é a
# exceção de propósito — compra da família no cartão pessoal.
COMPRAS = [
    ("Nubank",         "Restaurante", "Jantar de aniversário", 180.00, 1, 3, 12, None),
    ("Cartão Família", "Mercado",     "Compra do mês",         420.00, 1, 2, 8,  None),
    ("Nubank",         "Assinaturas", "Fone de ouvido",        899.90, 6, 2, 14, None),
    ("Nubank",         "Restaurante", "Almoço de domingo",      96.40, 1, 1, 9,  None),
    ("Cartão Família", "Mercado",     "Feira",                 138.20, 1, 1, 22, None),
    ("Cartão Família", "Farmácia",    "Remédio",                74.30, 1, 0, 6,  None),
    ("Nubank",         "Restaurante", "Pizza",                  89.90, 0, 0, 12, None),
    ("Nubank",         "Transporte",  "Pneus",                 760.00, 3, 2, 20, None),
    ("Nubank",         "Assinaturas", "Presente da sobrinha",  159.00, 1, 0, 9,  Finalidade.FAMILIA),
    ("Cartão Empresa", "Software",    "Notebook do trabalho", 4800.00, 10, 4, 3, None),
    ("Cartão Empresa", "Transporte",  "Uber para cliente",      64.50, 1, 0, 11, None),
]


def semear_cartoes(dono: User, s: Session, categorias: dict[str, Category]) -> dict:
    """Cartões, compras, faturas e pagamentos — tudo inventado.

    As faturas NÃO são montadas à mão: saem de `fatura_da_parcela`, a mesma
    função que a API usa. Calcular o ciclo aqui de outro jeito faria o demo
    mostrar um app que não existe, e o erro só apareceria pra quem abrisse o
    link.
    """
    contagem = {"cartoes": 0, "compras": 0, "parcelas": 0, "faturas": 0, "pagamentos": 0}

    cartoes: dict[str, Card] = {}
    for nome, fecha, vence, finalidade in CARTOES:
        c = Card(
            name=nome, closing_day=fecha, due_day=vence, finalidade=finalidade, user_id=dono.id
        )
        s.add(c)
        cartoes[nome] = c
        contagem["cartoes"] += 1
    s.commit()
    for c in cartoes.values():
        s.refresh(c)

    for nome_cartao, nome_cat, descricao, preco, parcelas, meses_atras, dia, finalidade in COMPRAS:
        # `parcelas == 0` no COMPRAS é atalho pra "1x"; mantido só pra a tabela
        # acima ficar legível com zeros alinhados.
        n = max(1, parcelas)
        ano, mes = periodos()[-1 - meses_atras]
        data = dt.date(ano, mes, min(dia, 28))

        compra = Purchase(
            user_id=dono.id,
            card_id=cartoes[nome_cartao].id,
            category_id=categorias[nome_cat].id,
            description=descricao,
            total_amount=preco,
            installments=n,
            purchase_date=data,
            # Mesma regra da API: sem escolha, a do cartão.
            finalidade=finalidade or cartoes[nome_cartao].finalidade,
        )
        s.add(compra)
        s.commit()
        s.refresh(compra)
        contagem["compras"] += 1

        for numero, parcela in enumerate(dividir_em_parcelas(preco, n), start=1):
            fatura = fatura_da_parcela(s, dono, cartoes[nome_cartao], data, numero)
            s.add(Transaction(
                user_id=dono.id,
                date=competencia_da_parcela(data, numero),
                description=descricao,
                amount_paid=parcela,
                category_id=categorias[nome_cat].id,
                finalidade=compra.finalidade,
                payment_method=PaymentMethod.CREDIT,
                purchase_id=compra.id,
                installment_no=numero,
                invoice_id=fatura.id,
            ))
            contagem["parcelas"] += 1
        s.commit()

    # As faturas já vencidas aparecem pagas; a que ainda vai vencer fica em
    # aberto. Um demo com tudo pago não mostraria o botão de pagar, e um com
    # tudo em aberto pareceria de alguém que nunca paga a fatura.
    hoje = dt.date.today()
    faturas = s.exec(select(Invoice).where(Invoice.user_id == dono.id)).all()
    contagem["faturas"] = len(faturas)

    for fatura in faturas:
        if fatura.due_date >= hoje:
            continue
        total = sum(
            t.amount_paid or 0.0
            for t in s.exec(
                select(Transaction).where(
                    Transaction.user_id == dono.id, Transaction.invoice_id == fatura.id
                )
            ).all()
        )
        if total <= 0:
            continue
        s.add(InvoicePayment(
            user_id=dono.id, invoice_id=fatura.id,
            date=fatura.due_date, amount=round(total, 2),
        ))
        contagem["pagamentos"] += 1

    s.commit()
    return contagem


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
        for nome, _tipo, _cor, _icone, dia, base, var, orcado, finalidade in CATEGORIAS:
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
                payment_method=PaymentMethod.CASH,
                finalidade=finalidade,
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
                # Avulso à vista sem escolha é pessoal — o padrão da API.
                finalidade=Finalidade.PESSOAL,
                # O demo nasce todo classificado: ele existe pra mostrar o app
                # funcionando, não o estado de quem ainda vai organizar o
                # histórico. O aviso de "sem forma de pagamento" não deve
                # aparecer pra quem abre o link.
                payment_method=PaymentMethod.CASH,
            ))
            contagem["lancamentos"] += 1

    s.commit()

    contagem.update(semear_cartoes(dono, s, categorias))

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
            # Pagamento aponta pra fatura, parcela aponta pra compra e pra
            # fatura, compra aponta pro cartao: o que depende sai primeiro.
            for modelo in (
                InvoicePayment, Transaction, Purchase, Invoice, Card,
                Budget, AssetSnapshot, Asset, Category,
            ):
                for linha in s.exec(select(modelo).where(modelo.user_id == dono.id)).all():
                    s.delete(linha)
                # Flush a cada modelo, e não um commit no fim. Sem `Relationship`
                # declarado em lugar nenhum deste projeto, não dá pra confiar que
                # o SQLAlchemy vá ordenar os DELETEs sozinho — e delete fora de
                # ordem passa batido no SQLite e estoura FK no Postgres. Foi
                # assim que um delete de ativo quebrou em produção uma vez.
                s.flush()
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
