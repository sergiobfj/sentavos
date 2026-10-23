"""Preenche a conta de demonstração com uma vida financeira fictícia.

    uv run python -m scripts.semear_demo --usuario demo@sentavos.app                  # seco
    uv run python -m scripts.semear_demo --usuario demo@sentavos.app --limpar --apply # grava

Gera 12 meses coerentes: salário que cai todo dia 5, aluguel que não muda,
mercado que oscila, uma categoria estourando o orçamento, patrimônio subindo e
um financiamento encolhendo. A ideia é que quem abrir o link entenda o app em
dez segundos, sem precisar imaginar como ficaria com dado de verdade.

Nada aqui vem dos seus lançamentos. É tudo inventado, e de propósito: num link
que vai pro LinkedIn, "quase anonimizado" é o tipo de coisa que se descobre ter
falhado depois que já foi visto.

O gerador é determinístico (semente fixa). Rodar duas vezes produz exatamente o
mesmo demo, então dá pra recriar a conta sem ela mudar de cara.

Do mês corrente em diante o demo mostra a Foundation V3: duas contas com saldo
observado no dia 1 e calculado desde então, uma transferência entre elas, um
aporte e um resgate ligados aos ativos, o financiamento como compromisso
financeiro e uma aquisição de bem fora do custo de vida.
"""

import datetime as dt
import os
import random
import sys

from sqlmodel import Session, select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.cartao import avancar_meses, competencia_da_parcela, dia_do_mes, dividir_em_parcelas  # noqa: E402
from app.database import engine  # noqa: E402
from app.dominio import investimentos  # noqa: E402
from app.dominio.tempo import FUSO, hoje_local  # noqa: E402
from app.faturas import fatura_da_parcela  # noqa: E402
from app.models import (  # noqa: E402
    AccountBalanceSnapshot,
    AccountType,
    Asset,
    AssetClass,
    AssetSnapshot,
    Budget,
    Card,
    Category,
    CategoryType,
    Commitment,
    CommitmentSkip,
    Finalidade,
    FinancialAccount,
    Invoice,
    InvoicePayment,
    InvestmentMovement,
    InvestmentMovementCreate,
    InvestmentMovementType,
    PaymentMethod,
    Provision,
    Purchase,
    ReconciliationItem,
    ReconciliationKind,
    ReconciliationStatus,
    Scenario,
    ScenarioItem,
    ScenarioItemKind,
    SnapshotSource,
    Transaction,
    TransactionNature,
    Transfer,
    User,
)
from scripts._admin import argumentos, cabecalho  # noqa: E402

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


def meses_ate_hoje() -> list[tuple[int, int]]:
    """Os meses depois de FIM até o corrente (vazio se FIM já é o corrente)."""
    hoje = hoje_local()
    fim = FIM.year * 12 + (FIM.month - 1)
    agora = hoje.year * 12 + (hoje.month - 1)
    return [(i // 12, i % 12 + 1) for i in range(fim + 1, agora + 1)]


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
    hoje = hoje_local()
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

        # O histórico vai até FIM; o saldo segue na mesma reta até o mês
        # corrente. Do mês corrente em diante, saldo de mês anterior não soma
        # no patrimônio — sem isto o demo abriria com quase tudo "não
        # atualizado". Sem `rnd` aqui: o resto do demo continua idêntico.
        for k, (ano, mes) in enumerate(meses_ate_hoje(), start=len(periodos())):
            s.add(AssetSnapshot(
                user_id=dono.id, asset_id=ativo.id,
                year=ano, month=mes, value=round(max(inicial + passo * k, 0.0), 2),
            ))
            contagem["saldos"] += 1

    s.commit()

    contagem.update(semear_planejamento(dono, s, categorias))
    contagem.update(semear_contas(dono, s, categorias))
    return contagem


# ---------- Contas, investimento e natureza (mês corrente) ----------
#
# O ativo "Conta corrente" foi o quebra-galho de antes das contas: do mês
# corrente em diante ele sai (arquivado, histórico intacto) e a conta assume,
# com o mesmo valor — como a migração assistida faz numa conta de verdade.

def semear_contas(dono: User, s: Session, categorias: dict[str, Category]) -> dict:
    contagem = {"contas": 0, "transferencias": 0, "movimentos": 0}
    hoje = hoje_local()
    primeiro = hoje.replace(day=1)
    observado = dt.datetime.combine(primeiro, dt.time(9, 0), FUSO)

    def dia(n: int) -> dt.date:
        return min(hoje, primeiro + dt.timedelta(days=n - 1))

    ativos = {a.name: a for a in s.exec(select(Asset).where(Asset.user_id == dono.id)).all()}
    saldos = {(x.asset_id, x.year, x.month): x for x in s.exec(
        select(AssetSnapshot).where(AssetSnapshot.user_id == dono.id)).all()}

    antiga = ativos["Conta corrente"]
    valor_conta = saldos[(antiga.id, hoje.year, hoje.month)].value
    antiga.archived_on = primeiro
    s.add(antiga)

    corrente = FinancialAccount(user_id=dono.id, name="Conta corrente", institution="Banco Fictício",
                                type=AccountType.CHECKING)
    digital = FinancialAccount(user_id=dono.id, name="Carteira digital", type=AccountType.PAYMENT)
    s.add(corrente)
    s.add(digital)
    s.flush()
    for conta, saldo in ((corrente, valor_conta), (digital, 350.0)):
        s.add(AccountBalanceSnapshot(user_id=dono.id, account_id=conta.id, observed_at=observado,
                                     balance=round(saldo, 2), source=SnapshotSource.MANUAL))
        contagem["contas"] += 1

    # Uma aquisição de bem: entra no gasto total, fica fora do custo de vida.
    s.add(Transaction(
        user_id=dono.id, date=dia(4), description="Bicicleta elétrica", amount_paid=1850.0,
        category_id=categorias["Transporte"].id, payment_method=PaymentMethod.CASH,
        finalidade=Finalidade.PESSOAL, nature=TransactionNature.ASSET_ACQUISITION,
    ))
    s.flush()

    # Tudo o que saiu ou entrou à vista no mês corrente passou pela conta corrente.
    for t in s.exec(select(Transaction).where(
            Transaction.user_id == dono.id, Transaction.date >= primeiro,
            Transaction.amount_paid.is_not(None))).all():
        if t.payment_method != PaymentMethod.CREDIT and t.account_id is None:
            t.account_id = corrente.id
            s.add(t)
    for pg in s.exec(select(InvoicePayment).where(
            InvoicePayment.user_id == dono.id, InvoicePayment.date >= primeiro)).all():
        pg.account_id = corrente.id
        s.add(pg)

    s.add(Transfer(user_id=dono.id, from_account_id=corrente.id, to_account_id=digital.id,
                   amount=150.0, date=dia(2), description="Pra carteira digital"))
    contagem["transferencias"] += 1

    # Aporte e resgate ligados ao ativo; o saldo do ativo no mês reflete os dois
    # e um rendimento plausível (52 e 95), não a reta do histórico.
    anterior = avancar_meses(hoje.year, hoje.month, -1)
    for ativo, categoria, tipo, valor, n, rendeu, descricao in (
        ("Reserva de emergência", "Reserva", InvestmentMovementType.CONTRIBUTION, 600.0, 6, 52.0, "Aporte na reserva"),
        ("Tesouro Selic", "Tesouro Selic", InvestmentMovementType.REDEMPTION, 300.0, 8, 95.0, "Resgate parcial"),
    ):
        a = ativos[ativo]
        investimentos.registrar(s, dono, InvestmentMovementCreate(
            asset_id=a.id, type=tipo, amount=valor, date=dia(n), account_id=corrente.id,
            category_id=categorias[categoria].id, description=descricao,
        ), "script:semear_demo")
        antes = saldos[(a.id, *anterior)].value
        sinal = 1 if tipo == InvestmentMovementType.CONTRIBUTION else -1
        atual = saldos[(a.id, hoje.year, hoje.month)]
        atual.value = round(antes + sinal * valor + rendeu, 2)
        atual.observed_on = hoje
        s.add(atual)
        contagem["movimentos"] += 1

    s.commit()
    return contagem


# ---------- Planejamento ----------
#
# Ancorado no mês CORRENTE, e não em FIM: o planejamento olha de hoje pra
# frente, e um demo cujo "agora" é setembro de 2026 mostraria tudo vencido pra
# quem abrir o link em março de 2027. Os valores continuam determinísticos;
# só as datas andam com o calendário.
#
# Tudo inventado. Nenhum valor, contrato ou nome vem da conta de ninguém.

# (descrição, categoria, valor, dia, parcelas, meses atrás da 1ª, confirmado, instituição)
COMPROMISSOS = [
    ("Salário", "Salário", 4500.00, 5, None, 0, True, None),
    ("Aluguel", "Aluguel", 1450.00, 10, None, 0, True, None),
    ("Academia", "Academia", 129.00, 12, None, 0, True, None),
    ("Internet", "Assinaturas", 99.90, 15, None, 0, False, None),
    ("Financiamento do carro", "Transporte", 890.00, 20, 36, 8, True, "Banco Fictício"),
    ("IPVA", "Transporte", 412.40, 18, 3, -3, True, None),
]


def semear_planejamento(dono: User, s: Session, categorias: dict[str, Category]) -> dict:
    """Compromissos, baixas, reservas, cenários e uma conferência pequena."""
    contagem = {"compromissos": 0, "baixas": 0, "reservas": 0, "cenarios": 0, "conferencia": 0}
    hoje = hoje_local()

    criados: dict[str, Commitment] = {}
    for descricao, nome_cat, valor, dia, parcelas, atras, confirmado, instituicao in COMPROMISSOS:
        cat = categorias[nome_cat]
        ano, mes = avancar_meses(hoje.year, hoje.month, -atras)
        c = Commitment(
            user_id=dono.id,
            description=descricao,
            category_id=cat.id,
            amount=valor,
            first_due=dia_do_mes(ano, mes, dia),
            installments=parcelas,
            confirmed=confirmado,
            institution=instituicao,
            # O financiamento é compromisso financeiro: fora do custo de vida.
            nature=TransactionNature.FINANCIAL if parcelas == 36 else None,
            total_amount=26500.0 if parcelas == 36 else None,
            finalidade=(Finalidade.FAMILIA if nome_cat == "Aluguel" else Finalidade.PESSOAL)
            if cat.type == CategoryType.EXPENSE else None,
        )
        s.add(c)
        s.flush()
        criados[descricao] = c
        contagem["compromissos"] += 1

        # Baixa de tudo que já venceu — menos a internet deste mês, que fica
        # atrasada de propósito: um demo sem nada pendente não mostraria o que
        # o planejamento faz com o que passou do dia.
        n = 1
        while parcelas is None or n <= parcelas:
            a, m_ = avancar_meses(c.first_due.year, c.first_due.month, n - 1)
            venc = dia_do_mes(a, m_, dia)
            if venc >= hoje:
                break
            if not (descricao == "Internet" and (a, m_) == (hoje.year, hoje.month)):
                rotulo = f" {n}/{parcelas}" if parcelas and parcelas > 1 else ""
                s.add(Transaction(
                    user_id=dono.id, date=venc, description=descricao + rotulo,
                    amount_planned=valor, amount_paid=valor, category_id=cat.id,
                    payment_method=PaymentMethod.CASH, finalidade=c.finalidade, nature=c.nature,
                    commitment_id=c.id, commitment_no=n,
                ))
                contagem["baixas"] += 1
            n += 1

    # A academia não cobrou o mês que vem (férias do plano): dispensada.
    s.add(CommitmentSkip(user_id=dono.id, commitment_id=criados["Academia"].id, number=2,
                         note="Plano em férias"))

    # O saldo da conta neste mês, lido há três dias.
    conta = s.exec(select(Asset).where(Asset.user_id == dono.id, Asset.asset_class == AssetClass.CHECKING)).first()
    if conta is not None:
        # Se o demo for semeado no próprio mês de FIM, o saldo já existe: só
        # ganha o dia da leitura (a unicidade é por ativo e mês).
        existente = s.exec(select(AssetSnapshot).where(
            AssetSnapshot.asset_id == conta.id,
            AssetSnapshot.year == hoje.year, AssetSnapshot.month == hoje.month,
        )).first()
        if existente is not None:
            existente.observed_on = hoje - dt.timedelta(days=3)
            s.add(existente)
        else:
            s.add(AssetSnapshot(
                user_id=dono.id, asset_id=conta.id, year=hoje.year, month=hoje.month,
                value=3180.00, observed_on=hoje - dt.timedelta(days=3),
            ))

    ipva = criados["IPVA"]
    s.add(Provision(user_id=dono.id, description="IPVA 1/3", amount=412.40, created_on=hoje,
                    commitment_id=ipva.id, commitment_no=1))
    s.add(Provision(user_id=dono.id, description="Revisão do carro", amount=600.00, created_on=hoje,
                    target_date=dia_do_mes(*avancar_meses(hoje.year, hoje.month, 2), 10)))
    contagem["reservas"] += 2

    def em(meses: int, dia: int) -> dt.date:
        return dia_do_mes(*avancar_meses(hoje.year, hoje.month, meses), dia)

    ferias = Scenario(user_id=dono.id, name="Férias em família",
                      note="Viagem curta no fim do ano, sem parcelar.")
    freela = Scenario(user_id=dono.id, name="Freela extra")
    s.add_all([ferias, freela])
    s.flush()
    s.add_all([
        ScenarioItem(user_id=dono.id, scenario_id=ferias.id, kind=ScenarioItemKind.SAIDA,
                     description="Passagens e hospedagem", amount=2400.0, date=em(2, 15)),
        ScenarioItem(user_id=dono.id, scenario_id=ferias.id, kind=ScenarioItemKind.RESERVA,
                     description="Guardar pras férias", amount=500.0, date=em(0, 25), repeat_months=2),
        ScenarioItem(user_id=dono.id, scenario_id=ferias.id, kind=ScenarioItemKind.SAIDA,
                     description="Academia", amount=0.0, date=em(2, 12),
                     ref=f"compromisso:{criados['Academia'].id}:3"),
        ScenarioItem(user_id=dono.id, scenario_id=freela.id, kind=ScenarioItemKind.ENTRADA,
                     description="Projeto de site", amount=1800.0, date=em(1, 20)),
    ])
    contagem["cenarios"] += 2

    for descricao, valor, tipo, status, pergunta in (
        ("Conta de luz", 187.30, ReconciliationKind.SAIDA, ReconciliationStatus.PENDENTE, "Já foi paga?"),
        ("Presente de aniversário", 120.00, ReconciliationKind.SAIDA, ReconciliationStatus.CONFIRMAR, "Foi no Pix ou no cartão?"),
        ("Reembolso do plano de saúde", 85.00, ReconciliationKind.ENTRADA, ReconciliationStatus.PENDENTE, "Caiu na conta?"),
    ):
        s.add(ReconciliationItem(
            user_id=dono.id, year=hoje.year, month=hoje.month, description=descricao,
            amount=valor, kind=tipo, status=status, question=pergunta, source="arquivo",
        ))
        contagem["conferencia"] += 1

    s.commit()
    return contagem


def main() -> int:
    p = argumentos("Popula a conta de demonstração.")
    p.add_argument("--limpar", action="store_true",
                   help="apaga o que a conta já tem antes de semear")
    args = p.parse_args()

    with Session(engine) as s:
        dono = s.exec(select(User).where(User.email == args.usuario.strip().lower())).first()
        if dono is None:
            print(f"Não existe conta para {args.usuario}. "
                  "Crie com: uv run python -m app.criar_usuario", file=sys.stderr)
            return 1
        cabecalho("semear_demo", dono, args.apply, "| LIMPAR antes" if args.limpar else "")

        if not dono.read_only:
            # Aviso e não erro: pode ser proposital semear uma conta de teste
            # comum. Mas se for o demo público, read_only é o que impede o
            # primeiro visitante de apagar tudo.
            print(f"Atenção: {dono.email} NÃO é somente-leitura. "
                  "Como conta de demonstração pública, ela deveria ser.\n")

        if not args.apply:
            ja = s.exec(select(Transaction).where(Transaction.user_id == dono.id).limit(1)).first()
            print(f"Semearia 12 meses fictícios + o mês corrente em {dono.email}"
                  f"{' depois de apagar o que ela tem' if args.limpar else ''}.")
            if ja is not None and not args.limpar:
                print("A conta já tem lançamentos: sem --limpar, o demo ficaria duplicado.")
            print("Seco: nada foi gravado. Rode com --apply pra gravar.")
            return 0

        if args.limpar:
            # Ordem importa: o que aponta pra outro sai primeiro, senão a chave
            # estrangeira barra o delete.
            # Pagamento aponta pra fatura, parcela aponta pra compra e pra
            # fatura, compra aponta pro cartao: o que depende sai primeiro.
            # Do planejamento: o que aponta pro compromisso sai antes dele, e
            # a baixa (um lançamento) também.
            # Movimento de investimento aponta pra lançamento, ativo e conta;
            # transferência e saldo, pra conta; lançamento e pagamento, pra conta.
            for modelo in (
                InvestmentMovement, Transfer, AccountBalanceSnapshot,
                InvoicePayment, ReconciliationItem, ScenarioItem, Scenario,
                Provision, CommitmentSkip, Transaction, Commitment, FinancialAccount,
                Purchase, Invoice, Card, Budget, AssetSnapshot, Asset, Category,
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
