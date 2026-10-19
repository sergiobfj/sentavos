"""Planejamento: o que ainda vai entrar e sair, do mês atual em diante.

Este arquivo responde quatro perguntas — quanto tenho, quanto já devo, quanto
posso gastar, quanto vai sobrar — sem criar nenhum dado. Tudo aqui é leitura:
ele junta o que já existe e faz a conta.

## De onde vem cada número

    saldo inicial      último saldo das contas marcadas (Patrimônio)
    + entradas         receita prevista e ocorrência de entrada ainda não recebida
    − saídas           fatura a pagar, ocorrência de compromisso a pagar,
                       despesa prevista
    = saldo projetado
    − reservas         dinheiro que existe mas já tem destino
    = disponível

O realizado NUNCA entra como entrada ou saída futura. Ele já aconteceu, então já
está (ou deveria estar) no saldo. É isso que impede o salário recebido de
contar duas vezes, e é por isso que a tela avisa quando há lançamento depois da
data do saldo, em vez de somá-lo por conta própria: o app não sabe de qual
conta cada lançamento saiu, e qualquer ajuste seria chute.

## O que é derivado e de onde

  - **Cartão**: o restante de cada fatura, no mês do vencimento. As parcelas
    futuras já estão nas faturas futuras; nada é cadastrado de novo.
  - **Compromisso**: o cronograma sai da definição (`Commitment`), a baixa é
    o lançamento vinculado, a dispensa é `CommitmentSkip`.
  - **Previsto avulso**: o lançamento com previsto e sem pago — o jeito que o
    app já tinha de dizer "isso ainda vem". Previsto de investimento é guardar
    dinheiro, então vira reserva, não saída.
  - **Reserva**: `Provision`. Reduz o disponível, nunca o saldo.
  - **Cenário**: hipóteses e ajustes que só existem dentro da conta pedida.

## O passado

O planejamento começa no mês corrente. O que venceu antes dele e não foi pago
(parcela, fatura atrasada) entra no mês corrente como vencido: a passagem do
tempo não paga nada. Previsto avulso de mês passado NÃO entra — ele era a
estimativa daquele mês, e carregá-lo faria um "MOTO 650" de maio aparecer como
dívida de outubro.
"""

import datetime as dt
from dataclasses import dataclass, field
from typing import Iterable, Protocol

from sqlmodel import Session, SQLModel

from app.cartao import avancar_meses, dia_do_mes, limites_do_mes
from app.dominio import tempo, classificacao
from app.models import ExpenseClass
from app.dominio.caixa import efeito_no_caixa
from app.escopo import consulta
from app.faturas import TOLERANCIA, totais
from app.models import (
    Asset,
    AssetClass,
    AssetSnapshot,
    Card,
    Category,
    CategoryType,
    Commitment,
    CommitmentDetail,
    CommitmentRead,
    CommitmentSkip,
    FinancialAccount,
    Invoice,
    InvoicePayment,
    OccurrenceRead,
    OccurrenceStatus,
    PaymentMethod,
    Provision,
    ScenarioItemKind,
    Transaction,
    User,
    is_liability,
)


def hoje() -> dt.date:
    """O dia de referência, no fuso do Brasil. Função, e não `date.today()`
    espalhado, pra o teste poder fixar "hoje" — vencida e pendente dependem
    dele. (No servidor, em UTC, `date.today()` virava o dia seguinte às 21h.)"""
    return tempo.hoje_local()


Mes = tuple[int, int]


def indice(m: Mes) -> int:
    return m[0] * 12 + m[1] - 1


def mes_de(d: dt.date) -> Mes:
    return (d.year, d.month)


def saldo_desatualizado(saldo: Mes, alvo: Mes, agora: dt.date) -> bool:
    """O saldo herdado de um mês anterior ao corrente NÃO é o saldo de hoje.

    Três coisas diferentes que o app tratava como uma só:
      - o saldo do período (lançado no próprio mês): vale;
      - o último saldo conhecido de um mês PASSADO, visto num mês passado: é o
        retrato histórico, e continua valendo — setembro lê o que sempre leu;
      - o último saldo conhecido de um mês passado, visto do mês corrente em
        diante: é desatualizado. Aparece, com a data, mas não entra em total
        nenhum nem no saldo de partida do planejamento.

    O caso que motivou: o Nubank de setembro (R$ 5.262) continuava somando no
    patrimônio de outubro depois que o dinheiro guardado pagou a moto.
    """
    corrente = mes_de(agora)
    return indice(alvo) >= indice(corrente) and indice(saldo) < indice(corrente)


def somar_meses(m: Mes, n: int) -> Mes:
    return avancar_meses(m[0], m[1], n)


# ---------------------------------------------------------------------------
# Cronograma
# ---------------------------------------------------------------------------

# Teto de segurança pra recorrência sem fim que começou há muito tempo. Não é
# regra de produto: só impede um laço de rodar para sempre por dado esquisito.
_TETO_DE_LACO = 5000

# Quão longe do vencimento um lançamento de entrada ainda "é" a ocorrência: o
# salário do dia 5 que caiu dia 6, o adiantamento do dia 15 que caiu dia 23
# (setembro/2026). Menos de meio mês, pra duas ocorrências mensais seguidas
# nunca disputarem o mesmo lançamento.
JANELA_DE_ENTRADA = dt.timedelta(days=12)

# Nota das dispensas criadas por "Pausar". É o que "Retomar" desfaz.
PAUSA = "Pausa"


def vencimento(c: Commitment, numero: int) -> dt.date:
    """O vencimento da ocorrência `numero` (1-based).

    Anda `interval_months` por vez a partir da primeira, mantendo o dia — e
    achatando no último dia do mês curto, como o cartão: começar dia 31 vence
    dia 28 em fevereiro, e volta a 31 em março.
    """
    ano, mes = avancar_meses(
        c.first_due.year, c.first_due.month, (numero - 1) * c.interval_months
    )
    return dia_do_mes(ano, mes, c.first_due.day)


def existe(c: Commitment, numero: int) -> bool:
    """A ocorrência `numero` faz parte do cronograma?"""
    if numero < 1:
        return False
    if c.installments is not None:
        return numero <= c.installments
    if c.end_date is not None:
        return vencimento(c, numero) <= c.end_date
    return True


def ocorrencias_ate(c: Commitment, limite: dt.date) -> list[tuple[int, dt.date]]:
    """(número, vencimento) de cada ocorrência que vence até `limite`, inclusive."""
    saida: list[tuple[int, dt.date]] = []
    n = 1
    while n <= _TETO_DE_LACO:
        if c.installments is not None and n > c.installments:
            break
        venc = vencimento(c, n)
        if c.end_date is not None and venc > c.end_date:
            break
        if venc > limite:
            break
        saida.append((n, venc))
        n += 1
    return saida


def todas_as_ocorrencias(c: Commitment, horizonte: dt.date) -> list[tuple[int, dt.date]]:
    """Parcelado: o cronograma inteiro. Recorrente: até `horizonte`."""
    if c.installments is not None:
        return ocorrencias_ate(c, dt.date.max)
    return ocorrencias_ate(c, horizonte)


def rotulo(c: Commitment, numero: int) -> str | None:
    """"3/48" em parcelado; nada em recorrência nem em conta única."""
    if c.installments is not None and c.installments > 1:
        return f"{numero}/{c.installments}"
    return None


@dataclass
class EstadoCompromissos:
    """O que foi decidido sobre cada ocorrência, carregado de uma vez."""

    pagos: dict[tuple[int, int], Transaction] = field(default_factory=dict)
    dispensas: dict[tuple[int, int], CommitmentSkip] = field(default_factory=dict)
    reservas: list[Provision] = field(default_factory=list)
    # Entrada recorrente sem baixa, reconhecida num lançamento (ver
    # `casar_entradas`): recebida (pago) ou já prevista (só previsto).
    recebidos: dict[tuple[int, int], Transaction] = field(default_factory=dict)
    previstos: dict[tuple[int, int], Transaction] = field(default_factory=dict)

    def baixa(self, cid: int, numero: int) -> Transaction | None:
        """O lançamento que pagou/recebeu a ocorrência: vinculado ou reconhecido."""
        return self.pagos.get((cid, numero)) or self.recebidos.get((cid, numero))

    def reservado(self, cid: int, numero: int) -> float:
        """Quanto das reservas não liberadas aponta pra esta ocorrência."""
        return sum(
            p.amount
            for p in self.reservas
            if p.commitment_id == cid and p.commitment_no == numero and p.released_on is None
        )


def carregar_estado(
    session: Session, dono: User, ids: Iterable[int] | None = None
) -> EstadoCompromissos:
    """Baixas, dispensas e reservas — três consultas para a conta inteira."""
    filtro_ids = list(ids) if ids is not None else None

    q_pagos = consulta(Transaction, dono).where(Transaction.commitment_id.is_not(None))
    q_disp = consulta(CommitmentSkip, dono)
    if filtro_ids is not None:
        if not filtro_ids:
            return EstadoCompromissos(reservas=list(session.exec(consulta(Provision, dono)).all()))
        q_pagos = q_pagos.where(Transaction.commitment_id.in_(filtro_ids))
        q_disp = q_disp.where(CommitmentSkip.commitment_id.in_(filtro_ids))

    estado = EstadoCompromissos(
        pagos={(t.commitment_id, t.commitment_no): t for t in session.exec(q_pagos).all()},
        dispensas={(d.commitment_id, d.number): d for d in session.exec(q_disp).all()},
        reservas=list(session.exec(consulta(Provision, dono)).all()),
    )
    casar_entradas(session, dono, estado)
    return estado


def casar_entradas(session: Session, dono: User, estado: EstadoCompromissos) -> None:
    """Reconhece a entrada recorrente num lançamento que já existe. Só lê.

    O salário previsto (~940 no dia 5) e o salário recebido (944,34 em 06/10)
    são o MESMO dinheiro. Sem isto, quem lança o salário pelo "+" vê a
    ocorrência continuar "a receber" (e depois "vencida", contando de novo no
    mês corrente) — previsão e realizado somados.

    Regra: ocorrência em aberto de compromisso de ENTRADA × lançamento sem
    vínculo, da mesma categoria, a até `JANELA_DE_ENTRADA` do vencimento.
      1. lançamento pago → a ocorrência está recebida, pelo valor que caiu
         (diferença aceita: o recebido substitui o previsto);
      2. lançamento só previsto → a ocorrência está "prevista": conta uma vez,
         pelo lançamento.
    Cada lançamento cobre uma ocorrência só, a de vencimento mais perto.

    Só entrada: categoria de saída é larga (Casa, Saúde) e casaria a internet
    com qualquer compra da casa; saída recorrente tem baixa pelo "Paguei". A
    baixa explícita, a dispensa e o cancelamento vêm antes e não são tocados.

    Sempre sobre TODAS as entradas recorrentes da conta, com as baixas e
    dispensas delas — nunca só as do pedido. Senão o mesmo lançamento seria o
    salário do dia 5 na lista e o do dia 10 na tela de detalhe.
    """
    compromissos = session.exec(consulta(Commitment, dono)).all()
    if not compromissos:
        return
    tipos = {c.id: c.type for c in session.exec(consulta(Category, dono)).all()}
    entradas = [
        c for c in compromissos
        if CategoryType(tipos.get(c.category_id, CategoryType.EXPENSE)) == CategoryType.INCOME
    ]
    if not entradas:
        return
    ids_entrada = [c.id for c in entradas]
    baixas = {
        (t.commitment_id, t.commitment_no)
        for t in session.exec(
            consulta(Transaction, dono).where(Transaction.commitment_id.in_(ids_entrada))
        ).all()
    }
    dispensas = {
        (d.commitment_id, d.number)
        for d in session.exec(
            consulta(CommitmentSkip, dono).where(CommitmentSkip.commitment_id.in_(ids_entrada))
        ).all()
    }

    agora = hoje()
    ano, mes = avancar_meses(agora.year, agora.month, 13)
    horizonte = limites_do_mes(ano, mes)[1]
    abertas: list[tuple[Commitment, int, dt.date]] = []
    for c in entradas:
        for numero, venc in ocorrencias_ate(c, horizonte):
            if (c.id, numero) in baixas or (c.id, numero) in dispensas:
                continue
            if c.cancelled_on is not None and venc >= c.cancelled_on:
                continue
            abertas.append((c, numero, venc))
    if not abertas:
        return

    lancamentos = session.exec(
        consulta(Transaction, dono).where(
            Transaction.category_id.in_({c.category_id for c in entradas}),
            Transaction.commitment_id.is_(None),
            Transaction.purchase_id.is_(None),
            Transaction.date >= min(v for _, _, v in abertas) - JANELA_DE_ENTRADA,
            Transaction.date <= max(v for _, _, v in abertas) + JANELA_DE_ENTRADA,
        )
    ).all()
    pagos = [t for t in lancamentos if t.amount_paid is not None]
    so_previstos = [t for t in lancamentos if t.amount_paid is None and t.amount_planned is not None]

    for grupo, destino in ((pagos, estado.recebidos), (so_previstos, estado.previstos)):
        pares = sorted(
            (abs((t.date - venc).days), venc, t.id, c.id, numero, t)
            for c, numero, venc in abertas
            for t in grupo
            if t.category_id == c.category_id and abs(t.date - venc) <= JANELA_DE_ENTRADA
        )
        usados: set[int] = set()
        for _dist, _venc, tid, cid, numero, t in pares:
            if tid in usados or (cid, numero) in estado.recebidos or (cid, numero) in estado.previstos:
                continue
            destino[(cid, numero)] = t
            usados.add(tid)


def status_da_ocorrencia(
    c: Commitment, numero: int, venc: dt.date, estado: EstadoCompromissos, agora: dt.date
) -> OccurrenceStatus:
    """Paga → abatida/dispensada → cancelada → vencida → pendente.

    Paga vence tudo: se o dinheiro saiu, saiu, mesmo que depois alguém tenha
    cancelado o contrato. Vencida é só "passou o dia e não houve baixa" — nunca
    "foi paga". Quem marca paga é o lançamento, não o calendário.
    """
    if (c.id, numero) in estado.pagos:
        return OccurrenceStatus.PAGA
    dispensa = estado.dispensas.get((c.id, numero))
    if dispensa is not None:
        return OccurrenceStatus.ABATIDA if dispensa.abated_on else OccurrenceStatus.DISPENSADA
    if c.cancelled_on is not None and venc >= c.cancelled_on:
        return OccurrenceStatus.CANCELADA
    if (c.id, numero) in estado.recebidos:
        return OccurrenceStatus.PAGA
    if (c.id, numero) in estado.previstos:
        return OccurrenceStatus.PREVISTA
    if venc < agora:
        return OccurrenceStatus.VENCIDA
    return OccurrenceStatus.PENDENTE


EM_ABERTO = {OccurrenceStatus.PENDENTE, OccurrenceStatus.VENCIDA}


def ler_compromisso(
    c: Commitment,
    categoria: Category | None,
    estado: EstadoCompromissos,
    agora: dt.date,
    detalhado: bool = False,
) -> CommitmentRead | CommitmentDetail:
    """O compromisso com o que se calcula dele: status, contagens, próximo.

    Recorrência sem fim mostra o cronograma até 12 meses à frente — o resto
    não existe ainda em lugar nenhum, nem precisa.
    """
    ano, mes = avancar_meses(agora.year, agora.month, 12)
    horizonte = limites_do_mes(ano, mes)[1] - dt.timedelta(days=1)

    lista: list[OccurrenceRead] = []
    for numero, venc in todas_as_ocorrencias(c, horizonte):
        st = status_da_ocorrencia(c, numero, venc, estado, agora)
        tx = estado.baixa(c.id, numero) if st == OccurrenceStatus.PAGA else None
        previsto = estado.previstos.get((c.id, numero)) if st == OccurrenceStatus.PREVISTA else None
        dispensa = estado.dispensas.get((c.id, numero))
        lista.append(
            OccurrenceRead(
                number=numero,
                due_date=venc,
                amount=round(c.amount, 2),
                status=st,
                label=rotulo(c, numero),
                transaction_id=tx.id if tx else (previsto.id if previsto else None),
                paid_amount=tx.amount_paid if tx else None,
                paid_date=tx.date if tx else (previsto.date if previsto else None),
                provisioned=round(estado.reservado(c.id, numero), 2) if st in EM_ABERTO else 0.0,
                skip_note=dispensa.note if dispensa else None,
                abated_on=dispensa.abated_on if dispensa else None,
                matched=(c.id, numero) in estado.recebidos or previsto is not None,
            )
        )

    abertas = [o for o in lista if o.status in EM_ABERTO]
    vencidas = [o for o in abertas if o.status == OccurrenceStatus.VENCIDA]
    finito = c.installments is not None

    if c.cancelled_on is not None and c.cancelled_on <= agora:
        status = "cancelado"
    elif finito and not abertas:
        status = "quitado"
    elif not finito and c.end_date is not None and c.end_date < agora and not abertas:
        status = "encerrado"
    else:
        status = "ativo"

    tipo = CategoryType(categoria.type) if categoria else CategoryType.EXPENSE
    base = dict(
        **c.model_dump(exclude={"id", "user_id", "created_at", "cancelled_on"}),
        id=c.id,
        cancelled_on=c.cancelled_on,
        kind="parcelado" if finito else "recorrente",
        direction="entrada" if tipo == CategoryType.INCOME else "saida",
        category_name=categoria.name if categoria else "?",
        color=categoria.color if categoria else "#666",
        icon=categoria.icon if categoria else "•",
        status=status,
        paid_count=sum(1 for o in lista if o.status == OccurrenceStatus.PAGA),
        skipped_count=sum(1 for o in lista if o.status == OccurrenceStatus.DISPENSADA),
        abated_count=sum(1 for o in lista if o.status == OccurrenceStatus.ABATIDA),
        overdue_count=len(vencidas),
        overdue_amount=round(sum(o.amount for o in vencidas), 2),
        total_count=c.installments,
        remaining_count=len(abertas) if finito else None,
        remaining_nominal=round(sum(o.amount for o in abertas), 2) if finito else None,
        next=abertas[0] if abertas else None,
        paused_until=max(
            (o.due_date for o in lista
             if o.status == OccurrenceStatus.DISPENSADA and o.skip_note == PAUSA and o.due_date >= agora),
            default=None,
        ),
    )
    if detalhado:
        return CommitmentDetail(**base, schedule=lista)
    return CommitmentRead(**base)


# ---------------------------------------------------------------------------
# Saldo de partida
# ---------------------------------------------------------------------------


class ContaPlanejamento(SQLModel):
    # Uma das duas: a conta financeira (quem tem contas) ou o ativo (o jeito
    # anterior, que continua valendo pra quem ainda não cadastrou contas).
    asset_id: int | None = None
    account_id: int | None = None
    name: str
    asset_class: AssetClass | None = None
    account_type: str | None = None
    restricted: bool = False
    # Qualidade do saldo da conta (dominio/contas.py); nula no caminho de ativos.
    quality: str | None = None
    observed_at: dt.datetime | None = None
    maybe_incomplete: bool = False
    included: bool
    value: float = 0
    # "2026-09" do saldo usado; nulo se a conta nunca teve saldo.
    as_of: str | None = None
    observed_on: dt.date | None = None
    # Último saldo é de mês anterior ao corrente: aparece, mas não entra no
    # saldo de partida (ver `saldo_desatualizado`).
    stale: bool = False


class MovimentoDepois(SQLModel):
    date: dt.date
    description: str
    amount: float
    tipo: str  # entrada | saida | fatura | investimento


class AvisoSaldo(SQLModel):
    """Por que o saldo de partida talvez não seja o de hoje.

    Nada daqui é aplicado ao saldo. É a lista do que a pessoa precisa conferir
    antes de confiar na projeção.
    """

    # Alguma conta marcada só tem saldo de mês anterior — ela fica FORA do
    # saldo de partida até ser atualizada (`contas_desatualizadas`).
    desatualizado: bool = False
    contas_desatualizadas: list[str] = []
    # Há saldo deste mês, mas sem o dia — não dá pra saber o que está dentro.
    sem_dia: bool = False
    sem_contas: bool = False
    contas_sem_saldo: list[str] = []
    desde: dt.date | None = None
    entradas: float = 0
    saidas: float = 0
    investimentos: float = 0
    quantidade: int = 0
    movimentos: list[MovimentoDepois] = []


def conta_entra(asset: Asset) -> bool:
    """A escolha do dono vale; sem escolha, só a classe Conta entra."""
    if is_liability(asset.asset_class):
        return False
    if asset.include_in_planning is not None:
        return bool(asset.include_in_planning)
    return AssetClass(asset.asset_class) == AssetClass.CHECKING


def _contas_financeiras(session: Session, dono: User, contas: list[FinancialAccount]) -> list[ContaPlanejamento]:
    """O saldo de partida pelas contas: o saldo calculado de cada uma.

    Conta sem saldo observado fica de fora (`stale`, sem valor). Desatualizada
    (observação com mais de 31 dias) entra, marcada — com os movimentos
    conhecidos aplicados, o dinheiro não some porque o mês virou. Restrita
    (vale-transporte) nunca é dinheiro livre.
    """
    from app.dominio import contas as dominio_contas

    saida = []
    for s in dominio_contas.saldos(session, dono, contas=contas):
        c = s.conta
        dia = dominio_contas.dia_local(s.observado_em) if s.observado_em else None
        saida.append(ContaPlanejamento(
            account_id=c.id, name=c.name, account_type=c.type, restricted=c.restricted,
            quality=s.qualidade, observed_at=s.observado_em, maybe_incomplete=s.incompleto,
            included=c.include_in_planning and not c.restricted,
            value=s.saldo if s.saldo is not None else 0.0,
            as_of=f"{dia.year}-{dia.month:02d}" if dia else None,
            observed_on=dia,
            stale=s.saldo is None,
        ))
    return saida


def contas_de_partida(
    session: Session, dono: User, m0: Mes, agora: dt.date
) -> list[ContaPlanejamento]:
    """Cada ativo que pode ser dinheiro do mês, com o último saldo até `m0`.

    Dívida fica de fora sempre: financiamento não é dinheiro disponível, e as
    parcelas dele já entram como saída. Saldo de mês anterior vem marcado
    `stale` e não soma — o planejamento parte do que se sabe hoje.
    """
    financeiras = list(session.exec(
        consulta(FinancialAccount, dono).where(FinancialAccount.archived == False)  # noqa: E712
        .order_by(FinancialAccount.id)
    ).all())
    if financeiras:
        return _contas_financeiras(session, dono, financeiras)

    ativos = [
        a for a in session.exec(consulta(Asset, dono).order_by(Asset.asset_class, Asset.name)).all()
        if a.archived_on is None or indice((a.archived_on.year, a.archived_on.month)) > indice(m0)
    ]
    saldos = session.exec(consulta(AssetSnapshot, dono)).all()

    ultimo: dict[int, AssetSnapshot] = {}
    for s in saldos:
        if indice((s.year, s.month)) > indice(m0):
            continue
        atual = ultimo.get(s.asset_id)
        if atual is None or indice((atual.year, atual.month)) < indice((s.year, s.month)):
            ultimo[s.asset_id] = s

    contas = []
    for a in ativos:
        if is_liability(a.asset_class):
            continue
        s = ultimo.get(a.id)
        contas.append(
            ContaPlanejamento(
                asset_id=a.id,
                name=a.name,
                asset_class=a.asset_class,
                included=conta_entra(a),
                value=round(s.value, 2) if s else 0.0,
                as_of=f"{s.year}-{s.month:02d}" if s else None,
                observed_on=s.observed_on if s else None,
                stale=bool(s) and saldo_desatualizado((s.year, s.month), m0, agora),
            )
        )
    return contas


def aviso_do_saldo(
    session: Session, dono: User, contas: list[ContaPlanejamento], m0: Mes, agora: dt.date
) -> AvisoSaldo:
    """O que aconteceu depois da data do saldo — listado, nunca somado."""
    marcadas = [c for c in contas if c.included]
    aviso = AvisoSaldo(sem_contas=not marcadas)
    if not marcadas:
        return aviso
    if any(c.account_id is not None for c in contas):
        return _aviso_das_contas(session, dono, marcadas, aviso)

    aviso.contas_sem_saldo = [c.name for c in marcadas if c.as_of is None]
    aviso.contas_desatualizadas = [c.name for c in marcadas if c.stale]
    aviso.desatualizado = bool(aviso.contas_desatualizadas)

    # A data até onde cada saldo "sabe" das coisas. Saldo deste mês com dia
    # vale até o dia; sem dia não diz nada. Saldo desatualizado não entra no
    # saldo de partida, então também não define o que "falta" nele.
    referencias: list[dt.date] = []
    for c in marcadas:
        if c.as_of is None or c.stale:
            continue
        ano, mes = (int(x) for x in c.as_of.split("-"))
        if (ano, mes) == m0:
            if c.observed_on is not None:
                referencias.append(c.observed_on)
            else:
                aviso.sem_dia = True
        else:
            aviso.desatualizado = True
            referencias.append(limites_do_mes(ano, mes)[1] - dt.timedelta(days=1))

    if not referencias:
        return aviso

    desde = min(referencias)
    aviso.desde = desde
    if desde >= agora:
        return aviso

    movimentos: list[MovimentoDepois] = []
    tipos = {c.id: c.type for c in session.exec(consulta(Category, dono)).all()}
    for t in session.exec(
        consulta(Transaction, dono).where(
            Transaction.date > desde,
            Transaction.date <= agora,
            Transaction.amount_paid.is_not(None),
        )
    ).all():
        tipo = CategoryType(tipos.get(t.category_id, CategoryType.EXPENSE))
        valor = float(t.amount_paid or 0.0)
        if tipo == CategoryType.INCOME:
            aviso.entradas += valor
            movimentos.append(MovimentoDepois(date=t.date, description=t.description, amount=valor, tipo="entrada"))
        elif tipo == CategoryType.INVESTMENT:
            # Pode ser transferência entre duas contas suas. Fica à parte.
            aviso.investimentos += valor
            movimentos.append(MovimentoDepois(date=t.date, description=t.description, amount=valor, tipo="investimento"))
        elif efeito_no_caixa(tipo, t.payment_method, valor) != 0:
            # A regra do caixa (dominio/caixa.py): compra no cartão não sai da
            # conta agora; sai quando a fatura é paga.
            aviso.saidas += valor
            movimentos.append(MovimentoDepois(date=t.date, description=t.description, amount=valor, tipo="saida"))

    for p in session.exec(
        consulta(InvoicePayment, dono).where(
            InvoicePayment.date > desde, InvoicePayment.date <= agora
        )
    ).all():
        aviso.saidas += p.amount
        movimentos.append(MovimentoDepois(date=p.date, description="Pagamento de fatura", amount=p.amount, tipo="fatura"))

    movimentos.sort(key=lambda m: (m.date, m.description), reverse=True)
    aviso.quantidade = len(movimentos)
    aviso.movimentos = movimentos[:12]
    aviso.entradas = round(aviso.entradas, 2)
    aviso.saidas = round(aviso.saidas, 2)
    aviso.investimentos = round(aviso.investimentos, 2)
    return aviso


def _aviso_das_contas(
    session: Session, dono: User, marcadas: list[ContaPlanejamento], aviso: AvisoSaldo
) -> AvisoSaldo:
    """Com contas, os movimentos COM conta já estão no saldo calculado. O que
    falta são os movimentos SEM conta depois do saldo observado: listados,
    nunca somados — o app não sabe de qual conta saíram."""
    from app.dominio import contas as dominio_contas

    aviso.contas_sem_saldo = [c.name for c in marcadas if c.quality == dominio_contas.SEM_SALDO]
    aviso.contas_desatualizadas = [c.name for c in marcadas if c.quality == dominio_contas.DESATUALIZADO]
    aviso.desatualizado = bool(aviso.contas_desatualizadas)
    observados = [c.observed_at for c in marcadas if c.observed_at is not None]
    if not observados:
        return aviso
    desde = min(observados)
    aviso.desde = dominio_contas.dia_local(desde)
    rotulo = {"entrada": "entrada", "saida": "saida", "fatura": "fatura", "aporte": "investimento",
              "resgate": "investimento"}
    movimentos: list[MovimentoDepois] = []
    for m in dominio_contas.movimentos(session, dono, None, aviso.desde):
        if not dominio_contas.depois(m.data, m.ocorrido_em, desde):
            continue
        tipo = rotulo.get(m.tipo, "saida")
        if tipo == "entrada":
            aviso.entradas += m.valor
        elif tipo == "investimento":
            aviso.investimentos += -m.valor
        else:
            aviso.saidas += -m.valor
        movimentos.append(MovimentoDepois(date=m.data, description=m.descricao, amount=abs(m.valor), tipo=tipo))
    movimentos.sort(key=lambda m: (m.date, m.description), reverse=True)
    aviso.quantidade = len(movimentos)
    aviso.movimentos = movimentos[:12]
    aviso.entradas = round(aviso.entradas, 2)
    aviso.saidas = round(aviso.saidas, 2)
    aviso.investimentos = round(aviso.investimentos, 2)
    return aviso


# ---------------------------------------------------------------------------
# O mês planejado
# ---------------------------------------------------------------------------


class PlanoItem(SQLModel):
    category_type: CategoryType | None = None
    expense_class: ExpenseClass | None = None
    """Uma linha do mês: algo que ainda vai entrar ou sair (ou que já foi)."""

    key: str
    # cartao | parcelado | recorrente | previsto | cenario
    source: str
    direction: str  # entrada | saida
    description: str
    detail: str | None = None
    date: dt.date
    year: int
    month: int
    # O valor esperado; `remaining` é o que ainda conta na conta do mês.
    amount: float
    remaining: float
    certainty: str  # confirmado | estimado | hipotetico
    status: str  # pendente | vencido | pago
    label: str | None = None
    provisioned: float = 0
    # Mudado por um cenário: o valor antes do ajuste.
    original_amount: float | None = None
    icon: str | None = None
    color: str | None = None
    commitment_id: int | None = None
    commitment_no: int | None = None
    invoice_id: int | None = None
    transaction_id: int | None = None
    scenario_item_id: int | None = None


class PlanoReserva(SQLModel):
    key: str
    source: str  # reserva | aporte | cenario
    description: str
    amount: float
    certainty: str
    since: Mes
    # O item que ela cobre, quando é reserva pra um compromisso.
    target_key: str | None = None
    target_label: str | None = None
    original_amount: float | None = None
    provision_id: int | None = None


class PlanoMes(SQLModel):
    expense_groups: dict[str, float] = {}
    year: int
    month: int
    is_current: bool
    # "saldos" no mês corrente; "projecao" nos seguintes.
    opening_source: str
    opening: float
    income: float = 0
    expense: float = 0
    projected: float = 0
    reserved: float = 0
    available: float = 0
    # Das saídas: quanto é de cada grau de certeza e de cada origem.
    by_certainty: dict[str, float] = {}
    by_source: dict[str, float] = {}
    overdue: float = 0
    provisioned: float = 0
    still_needed: float = 0
    items: list[PlanoItem] = []
    reserves: list[PlanoReserva] = []


class PlanoResposta(SQLModel):
    today: dt.date
    scenario_id: int | None = None
    scenario_name: str | None = None
    accounts: list[ContaPlanejamento] = []
    balance_warning: AvisoSaldo = AvisoSaldo()
    months: list[PlanoMes] = []


class ItemHipotetico(Protocol):
    kind: ScenarioItemKind
    description: str
    amount: float
    date: dt.date
    repeat_months: int
    ref: str | None


@dataclass
class _Reserva:
    chave: str
    origem: str
    descricao: str
    valor: float
    certeza: str
    inicio: Mes
    fim: Mes | None = None  # exclusivo: no mês `fim` ela já não conta
    alvo: str | None = None
    alvo_rotulo: str | None = None
    provision_id: int | None = None
    original: float | None = None

    def ativa_em(self, m: Mes) -> bool:
        if indice(m) < indice(self.inicio):
            return False
        return self.fim is None or indice(m) < indice(self.fim)


class PlanejamentoInvalido(ValueError):
    pass


def planejar(
    session: Session,
    dono: User,
    ate: Mes,
    hipoteses: list[ItemHipotetico] | None = None,
    agora: dt.date | None = None,
) -> PlanoResposta:
    """Do mês corrente até `ate`, inclusive, com as hipóteses aplicadas."""
    agora = agora or hoje()
    m0 = mes_de(agora)
    if indice(ate) < indice(m0):
        raise PlanejamentoInvalido("O planejamento começa no mês atual.")

    inicio_m0 = limites_do_mes(*m0)[0]
    fim_ate = limites_do_mes(*ate)[1]
    ultimo_dia = fim_ate - dt.timedelta(days=1)

    categorias = {c.id: c for c in session.exec(consulta(Category, dono)).all()}
    itens: list[PlanoItem] = []
    reservas: list[_Reserva] = []

    def mes_do_plano(data: dt.date) -> Mes:
        """Vencido antes do mês corrente conta no mês corrente."""
        return m0 if indice(mes_de(data)) < indice(m0) else mes_de(data)

    # ---------- Cartão: o restante de cada fatura, no mês do vencimento ----------
    agregados = totais(session, dono)
    nomes = {c.id: c.name for c in session.exec(consulta(Card, dono)).all()}
    for f in session.exec(consulta(Invoice, dono)).all():
        total, pago, _ = agregados.get(f.id, (0.0, 0.0, 0))
        restante = max(total - pago, 0.0)
        ref = (f.year, f.month)
        if indice(ref) > indice(ate):
            continue
        if restante <= TOLERANCIA:
            # Paga: só aparece se for do período, como contexto ("a de outubro
            # já foi"). Não conta em nada.
            if indice(ref) < indice(m0) or total <= TOLERANCIA:
                continue
            situacao = "pago"
            restante = 0.0
        else:
            situacao = "vencido" if f.due_date < agora else "pendente"
        m = m0 if indice(ref) < indice(m0) else ref
        itens.append(
            PlanoItem(
                key=f"fatura:{f.id}",
                source="cartao",
                direction="saida",
                description=f"Fatura {nomes.get(f.card_id, '?')}",
                detail=None,
                date=f.due_date,
                year=m[0],
                month=m[1],
                amount=round(total, 2),
                remaining=round(restante, 2),
                certainty="confirmado",
                status=situacao,
                icon="💳",
                invoice_id=f.id,
            )
        )

    # ---------- Compromissos: o cronograma, menos o que já foi decidido ----------
    compromissos = session.exec(consulta(Commitment, dono)).all()
    estado = carregar_estado(session, dono, [c.id for c in compromissos])
    for c in compromissos:
        cat = categorias.get(c.category_id)
        if cat is None or CategoryType(cat.type) == CategoryType.INVESTMENT:
            continue
        direcao = "entrada" if CategoryType(cat.type) == CategoryType.INCOME else "saida"
        for numero, venc in ocorrencias_ate(c, ultimo_dia):
            st = status_da_ocorrencia(c, numero, venc, estado, agora)
            # "Prevista": o lançamento previsto já entra abaixo, como avulso.
            if st in (OccurrenceStatus.DISPENSADA, OccurrenceStatus.ABATIDA, OccurrenceStatus.CANCELADA, OccurrenceStatus.PREVISTA):
                continue
            if st == OccurrenceStatus.PAGA:
                if indice(mes_de(venc)) < indice(m0):
                    continue
                tx = estado.baixa(c.id, numero)
                situacao, restante = "pago", 0.0
                transacao = tx.id
            else:
                situacao = "vencido" if st == OccurrenceStatus.VENCIDA else "pendente"
                restante = c.amount
                transacao = None
            m = mes_do_plano(venc)
            itens.append(
                PlanoItem(
                    key=f"compromisso:{c.id}:{numero}",
                    source="parcelado" if c.installments is not None else "recorrente",
                    category_type=cat.type,
                    expense_class=classificacao.do_compromisso(c, cat.type),
                    direction=direcao,
                    description=c.description,
                    detail=c.institution,
                    date=venc,
                    year=m[0],
                    month=m[1],
                    amount=round(c.amount, 2),
                    remaining=round(restante, 2),
                    certainty="confirmado" if c.confirmed else "estimado",
                    status=situacao,
                    label=rotulo(c, numero),
                    icon=cat.icon,
                    color=cat.color,
                    commitment_id=c.id,
                    commitment_no=numero,
                    transaction_id=transacao,
                )
            )

    # ---------- Previsto avulso: o lançamento com previsto e sem pago ----------
    for t in session.exec(
        consulta(Transaction, dono).where(
            Transaction.date >= inicio_m0,
            Transaction.date < fim_ate,
            Transaction.amount_paid.is_(None),
            Transaction.amount_planned.is_not(None),
            Transaction.purchase_id.is_(None),
            Transaction.commitment_id.is_(None),
        )
    ).all():
        valor = float(t.amount_planned or 0.0)
        if abs(valor) <= TOLERANCIA:
            continue
        cat = categorias.get(t.category_id)
        tipo = CategoryType(cat.type) if cat else CategoryType.EXPENSE
        if tipo == CategoryType.INVESTMENT and valor > 0:
            # Guardar dinheiro: sai do disponível, não do saldo nem do
            # patrimônio — pode ser só uma transferência pra caixinha.
            reservas.append(
                _Reserva(
                    chave=f"lancamento:{t.id}",
                    origem="aporte",
                    descricao=t.description,
                    valor=valor,
                    certeza="estimado",
                    inicio=mes_de(t.date),
                )
            )
            continue
        if tipo == CategoryType.INVESTMENT:
            # Resgate previsto (valor negativo): dinheiro que volta pra conta.
            direcao, valor = "entrada", -valor
        else:
            direcao = "entrada" if tipo == CategoryType.INCOME else "saida"
        itens.append(
            PlanoItem(
                key=f"lancamento:{t.id}",
                source="previsto",
                category_type=tipo,
                expense_class=classificacao.efetiva(t) if tipo == CategoryType.EXPENSE else None,
                direction=direcao,
                description=t.description,
                date=t.date,
                year=t.date.year,
                month=t.date.month,
                amount=round(valor, 2),
                remaining=round(valor, 2),
                certainty="estimado",
                status="vencido" if t.date < agora else "pendente",
                icon=cat.icon if cat else None,
                color=cat.color if cat else None,
                transaction_id=t.id,
            )
        )

    # ---------- Reservas ----------
    # Uma reserva pra uma ocorrência deixa de ser "dinheiro separado" no mês em
    # que a ocorrência conta como saída — dali em diante quem a representa é a
    # própria saída. Antes disso, ela tira o valor do disponível.
    por_chave = {i.key: i for i in itens}
    compromissos_por_id = {c.id: c for c in compromissos}
    for p in estado.reservas:
        inicio = mes_de(p.created_on)
        fim = mes_de(p.released_on) if p.released_on else None
        alvo = None
        alvo_rotulo = None
        c = compromissos_por_id.get(p.commitment_id) if p.commitment_id is not None else None
        if c is not None and p.commitment_no is not None and existe(c, p.commitment_no):
            numero = p.commitment_no
            chave_alvo = f"compromisso:{c.id}:{numero}"
            venc = vencimento(c, numero)
            st = status_da_ocorrencia(c, numero, venc, estado, agora)
            alvo_rotulo = c.description + (f" {rotulo(c, numero)}" if rotulo(c, numero) else "")
            if st == OccurrenceStatus.PAGA:
                # Cumprida: o dinheiro separado saiu na baixa, no mês dela.
                fim_pago = mes_de(estado.baixa(c.id, numero).date)
                fim = fim_pago if fim is None or indice(fim_pago) < indice(fim) else fim
            elif st in EM_ABERTO:
                alvo = chave_alvo
                m_alvo = mes_do_plano(venc)
                fim = m_alvo if fim is None or indice(m_alvo) < indice(fim) else fim
                item = por_chave.get(chave_alvo)
                liberada_antes = p.released_on is not None and indice(
                    mes_de(p.released_on)
                ) <= indice(m_alvo)
                # Cobre o item se ainda estava separada no mês dele.
                if item is not None and indice(inicio) <= indice(m_alvo) and not liberada_antes:
                    item.provisioned = round(item.provisioned + p.amount, 2)
            # Dispensada ou cancelada: a reserva não tem mais pra onde ir, e
            # continua separada até o dono liberá-la — o app não decide por ele
            # que aquele dinheiro voltou a ser livre.
        reservas.append(
            _Reserva(
                chave=f"reserva:{p.id}",
                origem="reserva",
                descricao=p.description,
                valor=p.amount,
                certeza="confirmado",
                inicio=inicio,
                fim=fim,
                alvo=alvo,
                alvo_rotulo=alvo_rotulo,
                provision_id=p.id,
            )
        )

    # ---------- Cenário ----------
    _aplicar_hipoteses(hipoteses or [], itens, reservas, m0, ate)

    # ---------- A conta, mês a mês ----------
    contas = contas_de_partida(session, dono, m0, agora)
    resposta = PlanoResposta(
        today=agora,
        accounts=contas,
        balance_warning=aviso_do_saldo(session, dono, contas, m0, agora),
    )

    saldo = round(sum(c.value for c in contas if c.included and not c.stale), 2)
    meses = []
    m = m0
    while indice(m) <= indice(ate):
        do_mes = sorted(
            (i for i in itens if (i.year, i.month) == m),
            key=lambda i: (i.status == "pago", i.date, i.direction != "entrada", i.description),
        )
        entradas = sum(i.remaining for i in do_mes if i.direction == "entrada")
        saidas_itens = [i for i in do_mes if i.direction == "saida"]
        saidas = sum(i.remaining for i in saidas_itens)
        grupos = {"fixed": 0.0, "variable": 0.0, "unclassified": 0.0, "invoices": 0.0}
        for item in saidas_itens:
            chave = "invoices" if item.source == "cartao" else (item.expense_class.value if item.expense_class else "unclassified")
            grupos[chave] += item.remaining

        por_certeza = {"confirmado": 0.0, "estimado": 0.0, "hipotetico": 0.0}
        por_origem = {"cartao": 0.0, "parcelado": 0.0, "recorrente": 0.0, "previsto": 0.0, "cenario": 0.0}
        vencido = provisionado = ainda = 0.0
        for i in saidas_itens:
            por_certeza[i.certainty] = por_certeza.get(i.certainty, 0.0) + i.remaining
            por_origem[i.source] = por_origem.get(i.source, 0.0) + i.remaining
            if i.status == "vencido":
                vencido += i.remaining
            coberto = min(i.provisioned, i.remaining)
            provisionado += coberto
            ainda += i.remaining - coberto

        ativas = [r for r in reservas if r.ativa_em(m) and abs(r.valor) > TOLERANCIA]
        reservado = sum(r.valor for r in ativas)
        projetado = saldo + entradas - saidas

        meses.append(
            PlanoMes(
                year=m[0],
                month=m[1],
                is_current=m == m0,
                opening_source="saldos" if m == m0 else "projecao",
                opening=round(saldo, 2),
                income=round(entradas, 2),
                expense=round(saidas, 2),
                expense_groups={k: round(v, 2) for k, v in grupos.items()},
                projected=round(projetado, 2),
                reserved=round(reservado, 2),
                available=round(projetado - reservado, 2),
                by_certainty={k: round(v, 2) for k, v in por_certeza.items()},
                by_source={k: round(v, 2) for k, v in por_origem.items()},
                overdue=round(vencido, 2),
                provisioned=round(provisionado, 2),
                still_needed=round(ainda, 2),
                items=do_mes,
                reserves=[
                    PlanoReserva(
                        key=r.chave,
                        source=r.origem,
                        description=r.descricao,
                        amount=round(r.valor, 2),
                        certainty=r.certeza,
                        since=r.inicio,
                        target_key=r.alvo,
                        target_label=r.alvo_rotulo,
                        original_amount=r.original,
                        provision_id=r.provision_id,
                    )
                    for r in ativas
                ],
            )
        )
        saldo = projetado
        m = somar_meses(m, 1)

    resposta.months = meses
    return resposta


def _aplicar_hipoteses(
    hipoteses: list[ItemHipotetico],
    itens: list[PlanoItem],
    reservas: list[_Reserva],
    m0: Mes,
    ate: Mes,
) -> None:
    """Ajustes em itens reais e itens novos — só dentro desta conta.

    Nada daqui é gravado em lugar nenhum: a lista `itens` é montada a cada
    pedido e morre com ele.
    """
    por_chave = {i.key: i for i in itens}
    reservas_por_chave = {r.chave: r for r in reservas}

    for n, h in enumerate(hipoteses):
        hid = getattr(h, "id", None)
        chave_h = f"cenario:{hid}" if hid is not None else f"simulado:{n}"

        if h.ref:
            alvo = por_chave.get(h.ref)
            if alvo is not None and alvo.status != "pago":
                alvo.original_amount = alvo.amount
                alvo.amount = round(h.amount, 2)
                alvo.remaining = round(max(h.amount, 0.0), 2)
                alvo.scenario_item_id = hid
                continue
            r = reservas_por_chave.get(h.ref)
            if r is not None:
                r.original = r.valor
                r.valor = h.amount
            continue

        kind = ScenarioItemKind(h.kind)
        repeticoes = max(1, int(h.repeat_months or 1))
        for k in range(repeticoes):
            ano, mes = avancar_meses(h.date.year, h.date.month, k)
            data = dia_do_mes(ano, mes, h.date.day)
            m = (ano, mes)
            if kind == ScenarioItemKind.RESERVA:
                reservas.append(
                    _Reserva(
                        chave=f"{chave_h}:{k + 1}",
                        origem="cenario",
                        descricao=h.description,
                        valor=h.amount,
                        certeza="hipotetico",
                        inicio=m,
                    )
                )
                continue
            if indice(m) < indice(m0) or indice(m) > indice(ate):
                continue
            itens.append(
                PlanoItem(
                    key=f"{chave_h}:{k + 1}",
                    source="cenario",
                    direction="entrada" if kind == ScenarioItemKind.ENTRADA else "saida",
                    description=h.description,
                    date=data,
                    year=ano,
                    month=mes,
                    amount=round(h.amount, 2),
                    remaining=round(h.amount, 2),
                    certainty="hipotetico",
                    status="pendente",
                    label=f"{k + 1}/{repeticoes}" if repeticoes > 1 else None,
                    scenario_item_id=hid,
                )
            )
