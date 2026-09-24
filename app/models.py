import datetime as dt
from sqlmodel import SQLModel, Field, UniqueConstraint
from enum import Enum


# ---------- Usuário ----------
# O app nasceu de uma conta só, com e-mail e hash em variável de ambiente. Virou
# tabela quando apareceram três contas: a principal, uma de demonstração pública
# e a da namorada. O segredo que assina os tokens (SENTAVOS_JWT_SECRET) continua
# no ambiente — ele é do servidor, não de uma pessoa.

class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    # Guardado em minúsculas pra a comparação do login não depender de como a
    # pessoa digitou no teclado do celular.
    email: str = Field(unique=True, index=True)
    name: str
    # Hash Argon2id. A senha em si não existe em lugar nenhum do sistema.
    password_hash: str

    # Conta de demonstração: lê tudo, não escreve nada. A senha dela é pública
    # (vai no LinkedIn), então sem esta trava o primeiro visitante mal-
    # intencionado apagaria o demo inteiro — e só se descobriria depois.
    read_only: bool = Field(default=False)

    # A taxa CDI ao ano, em porcentagem (10.65 = 10,65% a.a.). Fica no usuário e
    # não no ativo porque é um número só pro país inteiro: repetido por
    # aplicação, atualizar a Selic viraria editar cinco lugares e esquecer o
    # sexto. Nulo = ainda não informado, e aí o app não projeta nada.
    cdi_annual: float | None = Field(default=None)

    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )


# Toda tabela de dados carrega o dono. Sem esta coluna as linhas seriam globais,
# que é exatamente o que eram quando só existia uma conta.
def dono() -> int:
    return Field(foreign_key="users.id", index=True)



class CategoryType(str, Enum):
    EXPENSE = "expense"
    INCOME = "income"
    INVESTMENT = "investment"

class Finalidade(str, Enum):
    """Quem, ou qual contexto, consumiu o gasto.

    Responde "quanto EU gastei?" — pergunta que o filtro por cartão não
    responde, porque PIX e débito não têm cartão. Não confundir com a conta de
    onde o dinheiro saiu: a compra da família no meu cartão é FAMILIA e continua
    saindo do MEU caixa quando a fatura é paga. Por isso finalidade filtra gasto
    e nunca saldo, fatura ou patrimônio.

    Só existe em DESPESA. Receita e investimento ficam nulos de propósito: ainda
    não está decidido se reembolso da empresa é receita ou abatimento de gasto
    empresarial, e codificar uma das duas agora seria inventar regra contábil.

    Como em `PaymentMethod`, o banco grava o NOME (`PESSOAL`), não o valor.
    """

    PESSOAL = "pessoal"
    FAMILIA = "familia"
    EMPRESA = "empresa"


class CategoryBase(SQLModel):
    name: str
    type: CategoryType
    color: str
    icon: str

    # Categoria arquivada some do formulário de lançamento mas continua
    # existindo: os lançamentos antigos apontam pra ela, e apagá-la levaria o
    # histórico junto. É o caminho do meio entre "conviver com 28 categorias
    # herdadas da planilha" e "perder um ano de dados".
    archived: bool = False

class Category(CategoryBase, table=True):
    __tablename__ = "categories"
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)

class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(SQLModel):
    name: str | None = None
    type: CategoryType | None = None
    color: str | None = None
    icon: str | None = None
    archived: bool | None = None


class CategoryRead(CategoryBase):
    """A categoria com o quanto ela já foi usada — só com `incluir_uso=1`.

    Serve à tela de Configurações, que precisa saber antes de oferecer a troca
    de tipo se ela vai ser recusada. A trava de verdade é no servidor; isto é só
    pra a tela não oferecer uma porta que dá em parede.
    """

    id: int
    user_id: int
    transactions: int = 0
    purchases: int = 0
    budgets: int = 0

class PaymentMethod(str, Enum):
    """Como o dinheiro sai (ou não sai) da conta neste lançamento.

    NULL é um terceiro estado, e é de propósito: os 269 lançamentos que já
    existiam quando o cartão entrou no app não têm essa informação, e inventá-la
    seria pior do que admitir que ela falta. Ver `TransactionBase.payment_method`.
    """

    # Saiu da conta na hora: PIX, débito, dinheiro, boleto.
    CASH = "cash"
    # Foi gasto agora, sai da conta quando a fatura for paga.
    CREDIT = "credit"


class TransactionBase(SQLModel):
    date: dt.date
    description: str
    amount_planned: float | None = None
    amount_paid: float | None = None
    note: str | None = None
    category_id: int = Field(foreign_key="categories.id")

    # ---------- Gasto x saída de caixa ----------
    # Até aqui o app tratava os dois como o mesmo evento. É verdade pra PIX e
    # débito, e falso pro cartão: a compra é gasto hoje e só vira saída de caixa
    # quando a fatura é paga, semanas depois.
    #
    # Nulo = "ainda não sei", e só acontece em lançamento anterior a esta
    # funcionalidade. A Carteira conta esses como saída de caixa — não porque
    # sejam à vista, mas porque é assim que eles já eram contados, e mudar isso
    # sem o dono revisar reescreveria o histórico dele de um dia pro outro. A
    # tela de revisão existe pra transformar esse nulo em resposta.
    payment_method: PaymentMethod | None = None

    # ---------- Quem consumiu ----------
    # O valor EFETIVO, e é a única coluna que os relatórios consultam — à vista
    # e parcela de cartão passam pelo mesmo filtro, sem join com compra.
    #
    #   à vista sem escolha  -> PESSOAL (decidido na rota, não aqui)
    #   parcela de cartão    -> cópia de Purchase.finalidade
    #   receita/investimento -> sempre nulo
    #
    # Nulo também é o estado de todo lançamento anterior a esta funcionalidade.
    # Não se adivinha retroativamente: o filtro "Todos" os inclui, os outros
    # não, e a tela diz quanto ficou de fora.
    finalidade: Finalidade | None = None


class Transaction(TransactionBase, table=True):
    __tablename__ = "transactions"
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)

    # ---------- Só para lançamento de cartão ----------
    # Os três andam juntos: ou são todos nulos (lançamento à vista), ou todos
    # preenchidos (uma parcela de uma compra, cobrada numa fatura).
    #
    # Não vêm em TransactionCreate de propósito: parcela não se cria solta, se
    # cria pela compra — senão dava pra plantar uma parcela "3 de 2", ou uma
    # parcela numa fatura que já foi paga.
    purchase_id: int | None = Field(default=None, foreign_key="purchases.id", index=True)
    installment_no: int | None = None
    invoice_id: int | None = Field(default=None, foreign_key="invoices.id", index=True)


class TransactionCreate(TransactionBase):
    pass

class TransactionUpdate(SQLModel):
    date: dt.date | None = None
    description: str | None = None
    amount_planned: float | None = None
    amount_paid: float | None = None
    note: str | None = None
    category_id: int | None = None
    payment_method: PaymentMethod | None = None
    finalidade: Finalidade | None = None


class TransactionRead(TransactionBase):
    """O lançamento como a tela precisa dele.

    A lista mostra "Notebook · Compras · Nubank 2/10", e esses três últimos
    dados moram em duas tabelas diferentes. Resolver isso no navegador daria uma
    chamada por linha; resolver aqui custa duas consultas para a lista inteira.
    """

    id: int
    purchase_id: int | None = None
    installment_no: int | None = None
    invoice_id: int | None = None
    # Vêm da compra e do cartão — nulos em lançamento à vista.
    installments: int | None = None
    purchase_total: float | None = None
    purchase_date: dt.date | None = None
    card_id: int | None = None
    card_name: str | None = None
    card_finalidade: Finalidade | None = None


# ---------- Cartão de crédito ----------
# Três entidades e um princípio: a fatura não guarda dinheiro, ela guarda
# identidade. Total, pago, restante e status são derivados dos itens e dos
# pagamentos toda vez que a tela pede.
#
# É a mesma decisão da aba de Investimento, que não tem dados próprios: dois
# números para o mesmo dinheiro começam iguais e terminam diferentes. Um status
# gravado teria ainda um segundo defeito — precisaria de alguém passando de
# tempos em tempos só pra virar "aberta" em "atrasada" na data certa.


class CardBase(SQLModel):
    name: str
    # Dia do mês, 1 a 31. Mês curto é achatado na hora de calcular (ver
    # app/cartao.py): cartão que fecha 31 fecha 28 em fevereiro.
    closing_day: int = Field(ge=1, le=31)
    due_day: int = Field(ge=1, le=31)

    # Arquivado some do formulário de lançamento e continua no banco, igual à
    # categoria: as compras antigas apontam pra ele.
    archived: bool = False

    # O uso padrão do cartão ("o da família"). Compra nele herda isto quando a
    # pessoa não escolhe outra coisa.
    #
    # Nulo só nos cartões que existiam antes desta coluna: a migração não
    # adivinha pelo nome ("Nubank - Família" parece óbvio, e é justamente o tipo
    # de palpite que um dia erra calado). A tela pede a classificação.
    finalidade: Finalidade | None = None


class Card(CardBase, table=True):
    __tablename__ = "cards"
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )


class CardCreate(CardBase):
    # Cartão novo nasce com finalidade. A tela sempre manda a escolha; o padrão
    # só vale pra quem chama a API sem ela, e é o mesmo do lançamento à vista.
    finalidade: Finalidade | None = Finalidade.PESSOAL


class CardUpdate(SQLModel):
    name: str | None = None
    closing_day: int | None = Field(default=None, ge=1, le=31)
    due_day: int | None = Field(default=None, ge=1, le=31)
    archived: bool | None = None
    finalidade: Finalidade | None = None


# Teto de parcelas. Não é regra de cartão nenhum — é o que impede um dedo errado
# ("1200x") de plantar mil linhas no banco. A tela oferece até 24.
MAX_PARCELAS = 72


class PurchaseBase(SQLModel):
    card_id: int = Field(foreign_key="cards.id")
    category_id: int = Field(foreign_key="categories.id")
    description: str
    # O valor CHEIO da compra. As parcelas saem daqui divididas em centavos
    # inteiros, e não o contrário: guardar o valor da parcela faria o total ser
    # uma multiplicação que não fecha (33,33 × 3 = 99,99).
    total_amount: float
    installments: int = Field(default=1, ge=1, le=MAX_PARCELAS)
    # Quando a compra aconteceu de verdade. Diferente da competência do gasto
    # (que é a data de cada parcela) e da fatura que a cobra.
    purchase_date: dt.date
    note: str | None = None

    # A finalidade LÓGICA da compra, que todas as parcelas copiam. Mora aqui, e
    # não só nas parcelas, pra uma compra em 10x não ter como ficar com parcelas
    # em finalidades diferentes: parcela não se edita sozinha, e editar a compra
    # reescreve as dez de uma vez.
    #
    # Na criação, nulo quer dizer "a do cartão". Depois de gravada ela vale por
    # si: trocar a finalidade do cartão em 2027 não reescreve pra que serviu uma
    # compra de 2026. A única herança posterior é a da transição — compra sem
    # finalidade nenhuma recebe a do cartão quando ele é classificado.
    finalidade: Finalidade | None = None


class Purchase(PurchaseBase, table=True):
    """A compra no cartão, parcelada ou não.

    Existe mesmo em 1x. Poderia não existir — uma compra à vista no cartão é uma
    parcela só, e os dados caberiam na própria transação. Mas aí editar e
    apagar teriam dois caminhos diferentes conforme o número de parcelas, e o
    caminho menos usado é sempre o que quebra.
    """

    __tablename__ = "purchases"
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )


class PurchaseCreate(PurchaseBase):
    pass


class PurchaseUpdate(SQLModel):
    """O que dá pra mudar depois.

    Descrição, categoria e observação são rótulo: mudam sem mexer em dinheiro.
    Valor, parcelas e cartão mudam quanto cada fatura cobra — a rota recusa
    esses três quando alguma fatura da compra já recebeu pagamento.
    """

    description: str | None = None
    category_id: int | None = None
    note: str | None = None
    total_amount: float | None = None
    installments: int | None = Field(default=None, ge=1, le=MAX_PARCELAS)
    card_id: int | None = None
    purchase_date: dt.date | None = None
    finalidade: Finalidade | None = None


class Invoice(SQLModel, table=True):
    """Uma fatura de um cartão num período.

    `year`/`month` são a referência pela qual ela é conhecida — o mês do
    VENCIMENTO, que é como o banco a chama e como se fala dela ("a fatura de
    outubro"). O fechamento pode ser do mês anterior.

    As duas datas ficam CONGELADAS aqui, e não recalculadas a partir do cartão.
    Trocar o dia de fechamento em 2027 não pode remontar as faturas de 2026 —
    elas já foram cobradas e pagas com as datas que tinham.
    """

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("user_id", "card_id", "year", "month", name="uq_invoice_card_period"),
    )

    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)
    card_id: int = Field(foreign_key="cards.id", index=True)
    year: int = Field(ge=1900, le=2999)
    month: int = Field(ge=1, le=12)
    closing_date: dt.date
    due_date: dt.date


class InvoicePaymentBase(SQLModel):
    date: dt.date
    amount: float
    # Livre, e é o que guarda o rastro de uma reconciliação: quando um
    # lançamento antigo de "Fatura do cartão" vira pagamento, o que ele era
    # fica escrito aqui. Sem isso a operação apagaria a origem sem deixar marca.
    note: str | None = None


class InvoicePayment(InvoicePaymentBase, table=True):
    """O pagamento da fatura: saída de caixa que NÃO é gasto de categoria.

    É por isso que ele não é uma `Transaction`. O gasto já foi contado quando a
    compra foi lançada; contar de novo aqui somaria o mesmo dinheiro duas vezes,
    e o erro apareceria como "gastei 2.400 num mês em que gastei 1.200".

    Não ter `category_id` não é esquecimento: é a garantia estrutural de que
    isso nunca vai cair numa meta nem no "para onde foi".
    """

    __tablename__ = "invoice_payments"
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)
    invoice_id: int = Field(foreign_key="invoices.id", index=True)


class InvoicePaymentCreate(InvoicePaymentBase):
    pass


class InvoiceStatus(str, Enum):
    """Calculado na hora, nunca gravado.

    A precedência é `paga` → `atrasada` → `parcial` → `aberta`: uma fatura
    vencida com saldo aparece como atrasada mesmo se já recebeu parte, porque é
    a informação que pede ação. Quanto já foi pago continua visível ao lado.
    """

    ABERTA = "aberta"
    PARCIAL = "parcial"
    PAGA = "paga"
    ATRASADA = "atrasada"


# Sem juros, multa, rotativo ou IOF — de propósito. Cobrança dessas entra como
# lançamento normal, feito pelo dono, com o valor que o banco cobrou de fato.


class InvoiceItem(SQLModel):
    """Uma linha da fatura: a parcela, com o rastro até a compra que a gerou."""

    transaction_id: int
    # A competência do gasto — o mês em que esta parcela conta no orçamento.
    date: dt.date
    description: str
    amount: float
    category_id: int
    category_name: str
    color: str
    icon: str
    # "1/3". Nulo em compra de uma parcela só, pra a tela não escrever "1/1".
    installment_no: int | None = None
    installments: int | None = None
    purchase_id: int
    purchase_total: float
    purchase_date: dt.date
    finalidade: Finalidade | None = None


class InvoiceRead(SQLModel):
    id: int
    card_id: int
    card_name: str
    year: int
    month: int
    closing_date: dt.date
    due_date: dt.date
    total: float = 0
    paid: float = 0
    remaining: float = 0
    status: InvoiceStatus = InvoiceStatus.ABERTA
    item_count: int = 0


class InvoicePaymentRead(InvoicePaymentBase):
    id: int
    invoice_id: int
    card_id: int
    card_name: str
    # Pra a lista de lançamentos poder linkar de volta sem uma segunda consulta.
    invoice_year: int
    invoice_month: int


class InvoiceDetail(InvoiceRead):
    items: list[InvoiceItem] = []
    payments: list[InvoicePaymentRead] = []


class CardInvoices(SQLModel):
    """O que a aba de Faturas mostra por cartão."""

    card_id: int
    name: str
    closing_day: int
    due_day: int
    archived: bool
    # A fatura que vence no mês selecionado — a que se paga agora.
    current: InvoiceRead | None = None
    # A que está acumulando para o mês seguinte.
    next: InvoiceRead | None = None
    # Tudo que ainda não foi pago, deste cartão, somando todas as faturas.
    open_total: float = 0


class InvoicesSummary(SQLModel):
    year: int
    month: int
    cards: list[CardInvoices] = []
    # Os pagamentos feitos no mês — é o que a lista de lançamentos mescla, e o
    # que a Carteira desconta.
    payments: list[InvoicePaymentRead] = []
    # Faturas que vencem no mês selecionado.
    due_this_month: float = 0
    paid_this_month: float = 0
    # Restante de TODAS as faturas em aberto, de todos os cartões. É o número
    # que vira "após faturas" no Início.
    open_total: float = 0


class PurchaseRead(PurchaseBase):
    """A compra com o contexto que a tela mostra ao abrir uma parcela."""

    id: int
    card_name: str
    category_name: str
    color: str
    icon: str
    # Valor de cada parcela, na ordem — a primeira leva os centavos que sobram.
    installment_amounts: list[float] = []
    # Quantas parcelas estão em fatura já paga: é o que decide se dá pra editar
    # valor, parcelas e cartão.
    paid_installments: int = 0
    locked: bool = False


# ---------- Orçamento ----------
# A meta de gasto de uma categoria num mês. Não confundir com o
# amount_planned da transação: "orçado" é o teto que você definiu pra
# categoria, "previsto" é a soma dos lançamentos que você já sabe que vêm.

class BudgetBase(SQLModel):
    category_id: int = Field(foreign_key="categories.id")
    year: int = Field(ge=1900, le=2999)
    month: int = Field(ge=1, le=12)
    amount: float

class Budget(BudgetBase, table=True):
    __tablename__ = "budgets"
    # Uma meta por categoria por mês — o PUT depende disso pra decidir
    # entre criar e atualizar.
    __table_args__ = (
        UniqueConstraint("user_id", "category_id", "year", "month", name="uq_budget_category_period"),
    )
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)

class BudgetCreate(BudgetBase):
    pass

class BudgetUpdate(SQLModel):
    amount: float | None = None


# Resposta do /budgets/summary: uma linha por categoria com orçado,
# previsto e pago já cruzados, pra aba de Orçamento não precisar
# somar transação no navegador.

class BudgetSummaryItem(SQLModel):
    category_id: int
    category_name: str
    category_type: CategoryType
    color: str
    icon: str
    archived: bool = False
    budget_id: int | None = None
    # O teto do mês. Zero (ou sem meta) significa categoria sem teto, não
    # categoria proibida: gastar nela continua valendo, só não há régua.
    budgeted: float = 0
    planned: float = 0
    paid: float = 0

    # ---------- Por que não há acúmulo aqui ----------
    # Existiu uma versão com caixinha: o que sobrava num mês virava saldo do
    # mês seguinte (carried_in, available, has_envelope). A ideia é boa no
    # papel e ruim na prática — o número que a tela mostrava dependia de todo
    # o passado, então uma meta esquecida em janeiro reaparecia como dívida em
    # setembro, e a Fatura chegou a mostrar −R$ 5.443 de "disponível".
    #
    # O teto mensal não tem passado: gastei 480 de 750, faltam 270, e na virada
    # recomeça. É menos poderoso e é conferível de cabeça, que é o que importa
    # numa tela que se abre no meio do mercado.

class BudgetSummaryTotals(SQLModel):
    budgeted: float = 0
    planned: float = 0
    paid: float = 0

class Caixa(SQLModel):
    """Os dois eixos do mês, lado a lado: o que gastei e o que saiu da conta.

    Eles eram o mesmo número até o cartão entrar no app. Agora:

        gastei 1.200 no mês  (500 à vista + 700 no cartão)
        saiu da conta 500    (o cartão sai quando a fatura for paga)

    Mora no resumo do orçamento, e não numa rota própria, porque a tela de
    Início já pede este resumo — uma chamada a mais na tela que mais se abre
    seria meio segundo de espera por nada.
    """

    # ---------- Eixo caixa: dinheiro de verdade ----------
    entrou: float = 0
    saiu_a_vista: float = 0
    investido: float = 0
    faturas_pagas: float = 0
    # entrou − saiu à vista − investido − faturas pagas. Na tela é o "Saldo do
    # mês" — o nome do campo ficou pra não quebrar o front já publicado.
    carteira: float = 0

    # ---------- Eixo gasto: o que consumi ----------
    # gasto_total inclui o que foi no cartão; é o número das metas.
    gasto_total: float = 0
    no_cartao: float = 0

    # ---------- Transição ----------
    # Despesa anterior ao cartão, ainda sem forma de pagamento definida. Conta
    # como saída de caixa (é como já era contada), mas a tela avisa que esses
    # lançamentos existem em vez de fingir que a resposta está completa.
    sem_forma_definida: float = 0
    sem_forma_definida_qtd: int = 0

    # ---------- Compromisso ----------
    # Faturas que vencem neste mês, e o que ainda falta pagar de todas elas.
    faturas_do_mes: float = 0
    faturas_em_aberto: float = 0
    # Carteira − faturas em aberto. Saiu da tela na V2: subtraía faturas de
    # meses futuros do fluxo de UM mês, misturando dois horizontes. Continua
    # aqui só pra o front antigo não quebrar durante o deploy.
    apos_faturas: float = 0


class BudgetSummary(SQLModel):
    year: int
    month: int
    items: list[BudgetSummaryItem]
    # Chaveado pelo tipo de categoria: expense, income, investment.
    #
    # Continua somando TODA despesa, à vista ou no cartão: meta mede gasto, e
    # uma compra parcelada no cartão consome o teto de Alimentação no mês da
    # parcela mesmo sem ter saído da conta ainda.
    totals: dict[str, BudgetSummaryTotals]
    caixa: Caixa = Caixa()


# ---------- Patrimônio ----------
# Enquanto Transaction é fluxo (o que entrou e saiu no mês), aqui é estoque:
# quanto cada coisa vale num ponto do tempo. Por isso não dá pra derivar
# patrimônio das transações — precisa de saldo lançado, não de movimento.

class AssetClass(str, Enum):
    CHECKING = "checking"
    FIXED_INCOME = "fixed_income"
    EQUITY = "equity"
    CRYPTO = "crypto"
    REAL_ESTATE = "real_estate"
    VEHICLE = "vehicle"
    DEBT = "debt"


# Dívida entra no mesmo lugar dos ativos e sai subtraindo — financiamento é
# patrimônio negativo, não uma entidade à parte.
LIABILITY_CLASSES = {AssetClass.DEBT}

# As classes que a aba de Investimento vai filtrar. Mora aqui pra as duas
# telas não discordarem sobre o que conta como investimento.
INVESTMENT_CLASSES = {AssetClass.FIXED_INCOME, AssetClass.EQUITY, AssetClass.CRYPTO}


def is_liability(asset_class: AssetClass) -> bool:
    return AssetClass(asset_class) in LIABILITY_CLASSES


class AssetBase(SQLModel):
    name: str
    asset_class: AssetClass
    note: str | None = None

    # Quanto do CDI a aplicação paga, em porcentagem (115.0 = 115% do CDI). É
    # como o banco apresenta renda fixa, então o número é copiado direto de lá.
    #
    # Nulo significa "não rende", que é o caso de conta corrente, imóvel e
    # carro — a maioria dos ativos. Zero diria a mesma coisa, mas tornaria
    # impossível distinguir "não sei a taxa" de "a taxa é zero".
    cdi_percent: float | None = None

class Asset(AssetBase, table=True):
    __tablename__ = "assets"
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)

class AssetCreate(AssetBase):
    pass

class AssetUpdate(SQLModel):
    name: str | None = None
    asset_class: AssetClass | None = None
    note: str | None = None
    cdi_percent: float | None = None


# O saldo de um ativo num mês. Preenchido à mão — sem cotação automática no v1.
class AssetSnapshotBase(SQLModel):
    asset_id: int = Field(foreign_key="assets.id")
    year: int = Field(ge=1900, le=2999)
    month: int = Field(ge=1, le=12)
    value: float

class AssetSnapshot(AssetSnapshotBase, table=True):
    __tablename__ = "asset_snapshots"
    __table_args__ = (
        UniqueConstraint("user_id", "asset_id", "year", "month", name="uq_snapshot_asset_period"),
    )
    user_id: int = dono()
    id: int | None = Field(default=None, primary_key=True)

class AssetSnapshotCreate(AssetSnapshotBase):
    pass

class AssetSnapshotUpdate(SQLModel):
    value: float | None = None


class AssetSummaryItem(SQLModel):
    asset_id: int
    name: str
    asset_class: AssetClass
    liability: bool
    note: str | None = None
    cdi_percent: float | None = None
    # Quanto a aplicação DEVERIA render no mês, pela taxa declarada. É bruto:
    # não desconta imposto de renda nem IOF. Nulo quando não há taxa ou o
    # usuário ainda não informou o CDI.
    expected_yield: float | None = None
    # id do snapshot deste mês exato; None quando o valor veio de mês anterior.
    snapshot_id: int | None = None
    value: float = 0
    previous: float = 0
    change: float = 0
    # "YYYY-MM" de onde o valor saiu, ou None se o ativo nunca teve saldo.
    # Deixa a tela avisar que o número é herdado em vez de fingir que é atual.
    as_of: str | None = None

class AssetClassTotal(SQLModel):
    value: float = 0
    previous: float = 0

class AssetSummary(SQLModel):
    year: int
    month: int
    items: list[AssetSummaryItem]
    # Chaveado pela classe: checking, fixed_income, equity, cripto...
    by_class: dict[str, AssetClassTotal]
    assets: float = 0
    liabilities: float = 0
    net_worth: float = 0
    previous_net_worth: float = 0
