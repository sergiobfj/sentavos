"""Rotas do planejamento: compromissos, reservas, cenários e a conta do mês.

Router próprio com `Depends(require_user)`, como o do cartão e o dos
relatórios — rota nova aqui nasce fechada, e o `test_isolamento.py` percorre
cada uma com o id de outra conta.

## O que este arquivo recusa de propósito

  - **Baixa duplicada.** A ocorrência paga não aceita outra baixa, e o banco
    tem um índice único como última linha de defesa.
  - **Mudar o calendário de um compromisso que já teve baixa.** A baixa aponta
    pro NÚMERO da ocorrência; trocar o mês da primeira ou a periodicidade faria
    a "parcela 3" virar outro mês, e o pagamento de novembro passaria a dizer
    que pagou dezembro.
  - **Apagar compromisso com baixa.** O histórico de "paguei a 1/48" é dado;
    a saída é cancelar.
  - **Escrever na conta de demonstração.** Exceto simular: `POST
    /planning/simulate` só calcula, não grava, e por isso é a única porta de
    POST aberta pro demo — quem visita pode brincar de "e se eu gastar 500?".
"""

import datetime as dt
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel

from app import planejamento
from app.auth import exigir_escrita, require_user
from app.cartao import avancar_meses, limites_do_mes
from app.database import get_session
from app.escopo import buscar, consulta, exigir
from app.models import (
    Category,
    CategoryType,
    Commitment,
    CommitmentCreate,
    CommitmentSkip,
    CommitmentUpdate,
    DispensarOcorrencia,
    PausarRecorrencia,
    Finalidade,
    OccurrenceStatus,
    PagarOcorrencia,
    PaymentMethod,
    Provision,
    ProvisionCreate,
    ProvisionRead,
    ProvisionUpdate,
    Scenario,
    ScenarioCreate,
    ScenarioItem,
    ScenarioItemCreate,
    ScenarioItemUpdate,
    ScenarioRead,
    ScenarioUpdate,
    Transaction,
    User,
    VincularLancamento,
)

router_planejamento = APIRouter(dependencies=[Depends(require_user)])

DESCRICAO_MAX = 80


def _texto(bruto: str | None, oque: str, maximo: int = DESCRICAO_MAX) -> str:
    texto = " ".join((bruto or "").split())
    if not texto:
        raise HTTPException(status_code=400, detail=f"{oque} não pode ficar vazio.")
    if len(texto) > maximo:
        raise HTTPException(status_code=400, detail=f"{oque} tem no máximo {maximo} caracteres.")
    return texto


def _opcional(bruto: str | None, maximo: int = 200) -> str | None:
    texto = " ".join((bruto or "").split())
    return texto[:maximo] or None


# ---------------------------------------------------------------------------
# Compromissos
# ---------------------------------------------------------------------------


def _categoria_do_compromisso(session: Session, dono: User, category_id: int) -> Category:
    categoria = buscar(session, Category, category_id, dono)
    if categoria is None:
        raise HTTPException(status_code=400, detail="Category not found")
    if CategoryType(categoria.type) == CategoryType.INVESTMENT:
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{categoria.name}' é investimento. Guardar dinheiro não é compromisso: "
                "use uma reserva, que tira do disponível sem fingir que o dinheiro saiu."
            ),
        )
    return categoria


def _finalidade(categoria: Category, escolhida: Finalidade | None) -> Finalidade | None:
    """Mesma regra do lançamento à vista: só despesa tem, e sem escolha é pessoal."""
    if CategoryType(categoria.type) != CategoryType.EXPENSE:
        return None
    return escolhida or Finalidade.PESSOAL


def _validar_valores(amount: float | None, total: float | None, entrada: float | None) -> None:
    if amount is not None and amount <= 0:
        raise HTTPException(status_code=400, detail="O valor de cada ocorrência precisa ser maior que zero.")
    for valor, nome in ((total, "O valor total"), (entrada, "A entrada")):
        if valor is not None and valor < 0:
            raise HTTPException(status_code=400, detail=f"{nome} não pode ser negativo.")


def _validar_fim(c: Commitment) -> None:
    if c.installments is not None and c.end_date is not None:
        raise HTTPException(
            status_code=400,
            detail="Escolha um jeito de terminar: número de parcelas OU data de fim.",
        )
    if c.end_date is not None and c.end_date < c.first_due:
        raise HTTPException(status_code=400, detail="A data de fim vem antes da primeira.")


def _ler(session: Session, dono: User, c: Commitment, detalhado: bool = False):
    estado = planejamento.carregar_estado(session, dono, [c.id])
    categoria = buscar(session, Category, c.category_id, dono)
    return planejamento.ler_compromisso(c, categoria, estado, planejamento.hoje(), detalhado)


@router_planejamento.get("/commitments")
def listar_compromissos(
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Todos, com o próximo vencimento de cada um. Ativos primeiro."""
    compromissos = session.exec(consulta(Commitment, dono)).all()
    estado = planejamento.carregar_estado(session, dono, [c.id for c in compromissos])
    categorias = {c.id: c for c in session.exec(consulta(Category, dono)).all()}
    agora = planejamento.hoje()
    lidos = [
        planejamento.ler_compromisso(c, categorias.get(c.category_id), estado, agora)
        for c in compromissos
    ]
    ordem = {"ativo": 0, "quitado": 1, "encerrado": 2, "cancelado": 3}
    lidos.sort(
        key=lambda r: (
            ordem.get(r.status, 9),
            r.next.due_date if r.next else dt.date.max,
            r.description.casefold(),
        )
    )
    return lidos


@router_planejamento.post("/commitments")
def criar_compromisso(
    dados: CommitmentCreate,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    exigir_escrita(dono)
    c = novo_compromisso(session, dono, dados)
    session.commit()
    session.refresh(c)
    return _ler(session, dono, c, detalhado=True)


def novo_compromisso(session: Session, dono: User, dados: CommitmentCreate) -> Commitment:
    """Valida e adiciona, sem commit — a conferência cria e vincula numa vez só."""
    categoria = _categoria_do_compromisso(session, dono, dados.category_id)
    _validar_valores(dados.amount, dados.total_amount, dados.down_payment)

    c = Commitment.model_validate(
        dados,
        update={
            "user_id": dono.id,
            "description": _texto(dados.description, "A descrição"),
            "finalidade": _finalidade(categoria, dados.finalidade),
            "institution": _opcional(dados.institution, 80),
            "payment_hint": _opcional(dados.payment_hint, 40),
            "note": _opcional(dados.note, 500),
        },
    )
    _validar_fim(c)
    session.add(c)
    session.flush()
    return c


@router_planejamento.get("/commitments/{commitment_id}")
def ver_compromisso(
    commitment_id: int,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    c = exigir(session, Commitment, commitment_id, dono, "Compromisso")
    return _ler(session, dono, c, detalhado=True)


def _baixas(session: Session, dono: User, c: Commitment) -> list[Transaction]:
    return list(
        session.exec(
            consulta(Transaction, dono).where(Transaction.commitment_id == c.id)
        ).all()
    )


@router_planejamento.patch("/commitments/{commitment_id}")
def atualizar_compromisso(
    commitment_id: int,
    dados: CommitmentUpdate,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Edita. O calendário só muda enquanto nenhuma ocorrência teve baixa.

    Valor, descrição, certeza e observação mudam sempre: o valor novo vale pras
    ocorrências em aberto, e as pagas guardam o que foi pago de verdade no
    próprio lançamento.
    """
    exigir_escrita(dono)
    c = exigir(session, Commitment, commitment_id, dono, "Compromisso")
    mudancas = dados.model_dump(exclude_unset=True)
    baixas = _baixas(session, dono, c)
    numeros_pagos = sorted(t.commitment_no for t in baixas if t.commitment_no)

    if "category_id" in mudancas:
        if mudancas["category_id"] is None:
            raise HTTPException(status_code=400, detail="A categoria não pode ficar vazia.")
        nova = _categoria_do_compromisso(session, dono, mudancas["category_id"])
        antiga = buscar(session, Category, c.category_id, dono)
        if baixas and antiga and CategoryType(nova.type) != CategoryType(antiga.type):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Este compromisso já tem baixa. Trocar entre entrada e saída "
                    "inverteria o sentido do que já foi pago."
                ),
            )

    if baixas:
        primeira = mudancas.get("first_due")
        if primeira is not None and (primeira.year, primeira.month) != (
            c.first_due.year,
            c.first_due.month,
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Já há parcela paga. Mudar o mês da primeira faria a baixa de uma "
                    "parcela apontar pra outro mês. O dia pode mudar."
                ),
            )
        if "interval_months" in mudancas and mudancas["interval_months"] not in (
            None,
            c.interval_months,
        ):
            raise HTTPException(
                status_code=409,
                detail="Já há parcela paga. A periodicidade não muda depois disso.",
            )

    if "amount" in mudancas and mudancas["amount"] is None:
        raise HTTPException(status_code=400, detail="O valor não pode ficar vazio.")
    _validar_valores(mudancas.get("amount"), mudancas.get("total_amount"), mudancas.get("down_payment"))

    # As duas últimas checagens só fazem sentido com o compromisso já montado,
    # então elas rodam depois de aplicar as mudanças — e uma recusa desfaz tudo,
    # em vez de deixar o objeto alterado na sessão esperando um commit alheio.
    try:
        for chave, valor in mudancas.items():
            if chave == "description":
                valor = _texto(valor, "A descrição")
            elif chave == "institution":
                valor = _opcional(valor, 80)
            elif chave == "payment_hint":
                valor = _opcional(valor, 40)
            elif chave == "note":
                valor = _opcional(valor, 500)
            elif chave in ("first_due", "interval_months", "confirmed") and valor is None:
                continue
            setattr(c, chave, valor)

        categoria = buscar(session, Category, c.category_id, dono)
        if categoria is not None:
            c.finalidade = _finalidade(categoria, c.finalidade)
        _validar_fim(c)

        # Nenhuma baixa pode ficar fora do cronograma novo.
        fora = [n for n in numeros_pagos if not planejamento.existe(c, n)]
        if fora:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"A ocorrência {fora[0]} já foi paga e ficaria fora do cronograma. "
                    "Encerre depois dela."
                ),
            )
    except HTTPException:
        session.rollback()
        raise

    session.add(c)
    session.commit()
    session.refresh(c)
    return _ler(session, dono, c, detalhado=True)


@router_planejamento.delete("/commitments/{commitment_id}")
def excluir_compromisso(
    commitment_id: int,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Só sem baixa. As reservas apontadas pra ele ficam, soltas.

    Soltas e não apagadas: o dinheiro foi separado por alguém, e sumir com a
    reserva junto com o compromisso devolveria esse dinheiro ao "disponível"
    sem ninguém ter decidido isso.
    """
    exigir_escrita(dono)
    c = exigir(session, Commitment, commitment_id, dono, "Compromisso")
    baixas = _baixas(session, dono, c)
    if baixas:
        raise HTTPException(
            status_code=409,
            detail=(
                f"'{c.description}' tem {len(baixas)} baixa(s). Apagar levaria junto o "
                "registro do que foi pago. Cancele em vez de apagar."
            ),
        )

    for d in session.exec(consulta(CommitmentSkip, dono).where(CommitmentSkip.commitment_id == c.id)).all():
        session.delete(d)
    soltas = 0
    for p in session.exec(consulta(Provision, dono).where(Provision.commitment_id == c.id)).all():
        p.commitment_id = None
        p.commitment_no = None
        session.add(p)
        soltas += 1
    # Sem Relationship declarado, o flush é o que garante a ordem dos DELETE.
    session.flush()
    session.delete(c)
    session.commit()
    return {"message": "Compromisso excluído.", "reservas_soltas": soltas}


# ---------- Ocorrências ----------


def _ocorrencia(c: Commitment, numero: int) -> dt.date:
    if not planejamento.existe(c, numero):
        raise HTTPException(status_code=404, detail="Ocorrência não encontrada.")
    return planejamento.vencimento(c, numero)


def _exigir_em_aberto(session: Session, dono: User, c: Commitment, numero: int) -> None:
    """A ocorrência pode receber baixa? Responde com o porquê quando não."""
    venc = _ocorrencia(c, numero)
    estado = planejamento.carregar_estado(session, dono, [c.id])
    st = planejamento.status_da_ocorrencia(c, numero, venc, estado, planejamento.hoje())
    rot = planejamento.rotulo(c, numero) or venc.strftime("%d/%m/%Y")
    if st == OccurrenceStatus.PAGA:
        tx = estado.baixa(c.id, numero)
        raise HTTPException(
            status_code=409,
            detail=f"{c.description} {rot} já foi paga em {tx.date.strftime('%d/%m/%Y')}.",
        )
    if st == OccurrenceStatus.PREVISTA:
        tx = estado.previstos[(c.id, numero)]
        raise HTTPException(
            status_code=409,
            detail=(
                f"{c.description} {rot} já está prevista no lançamento \"{tx.description}\" de "
                f"{tx.date.strftime('%d/%m/%Y')}. Quando receber, lance o valor recebido nele."
            ),
        )
    if st == OccurrenceStatus.DISPENSADA:
        raise HTTPException(
            status_code=409,
            detail=f"{c.description} {rot} está dispensada. Desfaça a dispensa antes.",
        )
    if st == OccurrenceStatus.CANCELADA:
        raise HTTPException(
            status_code=409,
            detail=f"{c.description} {rot} vence depois do cancelamento do compromisso.",
        )


@router_planejamento.post("/commitments/{commitment_id}/ocorrencias/{numero}/pagar")
def pagar_ocorrencia(
    commitment_id: int,
    numero: int,
    dados: PagarOcorrencia,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """A baixa num toque: cria o lançamento realizado já vinculado.

    É uma operação só pra não haver o caminho de três passos (lançar, marcar,
    conferir) em que o segundo passo é esquecido e a parcela aparece "a pagar"
    com o dinheiro já fora da conta.

    O lançamento guarda o previsto (o valor da parcela) e o pago (o que saiu de
    fato), como qualquer outro. Sai à vista: compromisso é o que NÃO é cartão.
    """
    exigir_escrita(dono)
    c = exigir(session, Commitment, commitment_id, dono, "Compromisso")
    _exigir_em_aberto(session, dono, c, numero)
    categoria = _categoria_do_compromisso(session, dono, c.category_id)

    valor = dados.amount if dados.amount is not None else c.amount
    if valor <= 0:
        raise HTTPException(status_code=400, detail="O valor pago precisa ser maior que zero.")

    rot = planejamento.rotulo(c, numero)
    lancamento = Transaction(
        user_id=dono.id,
        date=dados.date or planejamento.hoje(),
        description=c.description + (f" {rot}" if rot else ""),
        amount_planned=c.amount,
        amount_paid=valor,
        note=_opcional(dados.note, 500),
        category_id=c.category_id,
        payment_method=PaymentMethod.CASH,
        finalidade=_finalidade(categoria, c.finalidade),
        commitment_id=c.id,
        commitment_no=numero,
    )
    session.add(lancamento)
    try:
        session.commit()
    except IntegrityError:
        # Dois toques simultâneos: o índice único barrou o segundo.
        session.rollback()
        raise HTTPException(status_code=409, detail="Esta ocorrência acabou de receber baixa.")
    return _ler(session, dono, c, detalhado=True)


@router_planejamento.post("/commitments/{commitment_id}/ocorrencias/{numero}/vincular")
def vincular_ocorrencia(
    commitment_id: int,
    numero: int,
    pedido: VincularLancamento,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """"Já paguei": o lançamento existe, só não sabia que era esta parcela.

    Não muda valor, data nem categoria do lançamento — só diz o que ele é. É o
    caminho pra reconciliar sem criar um segundo lançamento do mesmo dinheiro.
    """
    exigir_escrita(dono)
    c = exigir(session, Commitment, commitment_id, dono, "Compromisso")
    lancamento = exigir(session, Transaction, pedido.transaction_id, dono, "Lançamento")
    # A entrada já reconhecida neste mesmo lançamento pode ganhar o vínculo
    # explícito (deixa de depender da data e da categoria). Outro lançamento
    # por cima dela, não: seria o mesmo salário duas vezes.
    reconhecido = planejamento.carregar_estado(session, dono, [c.id]).recebidos.get((c.id, numero))
    if reconhecido is None or reconhecido.id != lancamento.id:
        _exigir_em_aberto(session, dono, c, numero)

    if lancamento.commitment_id is not None:
        raise HTTPException(status_code=409, detail="Esse lançamento já é a baixa de outro compromisso.")
    if lancamento.purchase_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Parcela de cartão já é compromisso da fatura; não vira baixa de outro.",
        )
    if lancamento.amount_paid is None:
        raise HTTPException(
            status_code=400,
            detail="Esse lançamento é só previsto — nenhum dinheiro saiu ainda.",
        )
    do_compromisso = buscar(session, Category, c.category_id, dono)
    do_lancamento = buscar(session, Category, lancamento.category_id, dono)
    if (
        do_compromisso is None
        or do_lancamento is None
        or CategoryType(do_compromisso.type) != CategoryType(do_lancamento.type)
    ):
        raise HTTPException(
            status_code=400,
            detail="O lançamento e o compromisso precisam ser do mesmo tipo (entrada com entrada, saída com saída).",
        )

    lancamento.commitment_id = c.id
    lancamento.commitment_no = numero
    session.add(lancamento)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Esta ocorrência acabou de receber baixa.")
    return _ler(session, dono, c, detalhado=True)


@router_planejamento.delete("/commitments/{commitment_id}/ocorrencias/{numero}/vincular")
def desvincular_ocorrencia(
    commitment_id: int,
    numero: int,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Desfaz o vínculo e mantém o lançamento — ele continua sendo dinheiro que saiu."""
    exigir_escrita(dono)
    c = exigir(session, Commitment, commitment_id, dono, "Compromisso")
    _ocorrencia(c, numero)
    lancamento = session.exec(
        consulta(Transaction, dono).where(
            Transaction.commitment_id == c.id, Transaction.commitment_no == numero
        )
    ).first()
    if lancamento is None:
        raise HTTPException(status_code=404, detail="Esta ocorrência não tem baixa.")
    lancamento.commitment_id = None
    lancamento.commitment_no = None
    session.add(lancamento)
    session.commit()
    return _ler(session, dono, c, detalhado=True)


@router_planejamento.post("/commitments/{commitment_id}/ocorrencias/{numero}/dispensar")
def dispensar_ocorrencia(
    commitment_id: int,
    numero: int,
    dados: DispensarOcorrencia,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    exigir_escrita(dono)
    c = exigir(session, Commitment, commitment_id, dono, "Compromisso")
    _ocorrencia(c, numero)
    estado = planejamento.carregar_estado(session, dono, [c.id])
    if estado.baixa(c.id, numero) is not None:
        raise HTTPException(status_code=409, detail="Esta ocorrência já foi paga; não há o que dispensar.")
    if (c.id, numero) not in estado.dispensas:
        session.add(
            CommitmentSkip(
                user_id=dono.id, commitment_id=c.id, number=numero, note=_opcional(dados.note, 200)
            )
        )
        session.commit()
    return _ler(session, dono, c, detalhado=True)


@router_planejamento.delete("/commitments/{commitment_id}/ocorrencias/{numero}/dispensar")
def desfazer_dispensa(
    commitment_id: int,
    numero: int,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    exigir_escrita(dono)
    c = exigir(session, Commitment, commitment_id, dono, "Compromisso")
    _ocorrencia(c, numero)
    for d in session.exec(
        consulta(CommitmentSkip, dono).where(
            CommitmentSkip.commitment_id == c.id, CommitmentSkip.number == numero
        )
    ).all():
        session.delete(d)
    session.commit()
    return _ler(session, dono, c, detalhado=True)


@router_planejamento.post("/commitments/{commitment_id}/pausar")
def pausar_recorrencia(
    commitment_id: int,
    dados: PausarRecorrencia,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Pausa uma recorrência até o fim do mês de `ate`.

    Não é modelo novo: cada ocorrência em aberto de hoje até lá vira uma
    dispensa com a nota "Pausa" — o mesmo "não vai acontecer" de sempre. O que
    já foi recebido, previsto ou pago fica como está.
    """
    exigir_escrita(dono)
    c = exigir(session, Commitment, commitment_id, dono, "Compromisso")
    if c.installments is not None:
        raise HTTPException(
            status_code=400,
            detail="Só recorrência se pausa. Parcela que não vai ser paga se dispensa uma a uma.",
        )
    agora = planejamento.hoje()
    fim = limites_do_mes(dados.ate.year, dados.ate.month)[1] - dt.timedelta(days=1)
    if fim < agora:
        raise HTTPException(status_code=400, detail="A pausa termina num mês que já passou.")
    estado = planejamento.carregar_estado(session, dono, [c.id])
    for numero, venc in planejamento.ocorrencias_ate(c, fim):
        if venc < agora:
            continue
        if planejamento.status_da_ocorrencia(c, numero, venc, estado, agora) == OccurrenceStatus.PENDENTE:
            session.add(CommitmentSkip(
                user_id=dono.id, commitment_id=c.id, number=numero, note=planejamento.PAUSA,
            ))
    session.commit()
    return _ler(session, dono, c, detalhado=True)


@router_planejamento.post("/commitments/{commitment_id}/retomar")
def retomar_recorrencia(
    commitment_id: int,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Desfaz as dispensas de pausa de hoje em diante. As passadas ficam: o mês
    em que a recorrência estava pausada continua não tendo acontecido."""
    exigir_escrita(dono)
    c = exigir(session, Commitment, commitment_id, dono, "Compromisso")
    agora = planejamento.hoje()
    for d in session.exec(
        consulta(CommitmentSkip, dono).where(
            CommitmentSkip.commitment_id == c.id, CommitmentSkip.note == planejamento.PAUSA
        )
    ).all():
        if planejamento.vencimento(c, d.number) >= agora:
            session.delete(d)
    session.commit()
    return _ler(session, dono, c, detalhado=True)


# ---------------------------------------------------------------------------
# Reservas
# ---------------------------------------------------------------------------


def _ler_reservas(session: Session, dono: User, reservas: list[Provision]) -> list[ProvisionRead]:
    ids = {p.commitment_id for p in reservas if p.commitment_id}
    compromissos = {
        c.id: c
        for c in session.exec(consulta(Commitment, dono).where(Commitment.id.in_(ids))).all()
    } if ids else {}
    estado = planejamento.carregar_estado(session, dono, list(ids))
    agora = planejamento.hoje()

    saida = []
    for p in reservas:
        c = compromissos.get(p.commitment_id) if p.commitment_id else None
        venc = (
            planejamento.vencimento(c, p.commitment_no)
            if c is not None and p.commitment_no and planejamento.existe(c, p.commitment_no)
            else None
        )
        if p.released_on is not None and p.released_on <= agora:
            status = "liberada"
        elif c is not None and estado.baixa(c.id, p.commitment_no) is not None:
            status = "cumprida"
        else:
            status = "ativa"
        saida.append(
            ProvisionRead(
                **p.model_dump(exclude={"user_id", "created_at"}),
                status=status,
                commitment_description=c.description if c else None,
                occurrence_label=planejamento.rotulo(c, p.commitment_no) if c and p.commitment_no else None,
                occurrence_due=venc,
            )
        )
    ordem = {"ativa": 0, "cumprida": 1, "liberada": 2}
    saida.sort(key=lambda r: (ordem.get(r.status, 9), r.occurrence_due or r.target_date or dt.date.max, r.id))
    return saida


@router_planejamento.get("/provisions")
def listar_reservas(
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    return _ler_reservas(session, dono, list(session.exec(consulta(Provision, dono)).all()))


def _alvo_da_reserva(
    session: Session, dono: User, commitment_id: int | None, numero: int | None
) -> Commitment | None:
    if commitment_id is None and numero is None:
        return None
    if commitment_id is None or numero is None:
        raise HTTPException(status_code=400, detail="Informe o compromisso e o número da ocorrência.")
    c = buscar(session, Commitment, commitment_id, dono)
    if c is None:
        raise HTTPException(status_code=400, detail="Commitment not found")
    if not planejamento.existe(c, numero):
        raise HTTPException(status_code=400, detail="Essa ocorrência não existe no cronograma.")
    return c


@router_planejamento.post("/provisions")
def criar_reserva(
    dados: ProvisionCreate,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    exigir_escrita(dono)
    p = nova_reserva(session, dono, dados)
    session.commit()
    session.refresh(p)
    return _ler_reservas(session, dono, [p])[0]


def nova_reserva(session: Session, dono: User, dados: ProvisionCreate) -> Provision:
    """Valida e adiciona, sem commit."""
    if dados.amount <= 0:
        raise HTTPException(status_code=400, detail="A reserva precisa ser maior que zero.")
    c = _alvo_da_reserva(session, dono, dados.commitment_id, dados.commitment_no)
    if c is not None and (c.id, dados.commitment_no) in planejamento.carregar_estado(session, dono, [c.id]).pagos:
        raise HTTPException(status_code=409, detail="Essa ocorrência já foi paga; não há o que reservar.")

    if dados.description and dados.description.strip():
        descricao = _texto(dados.description, "A descrição")
    elif c is not None:
        rot = planejamento.rotulo(c, dados.commitment_no)
        descricao = c.description + (f" {rot}" if rot else "")
    else:
        raise HTTPException(status_code=400, detail="Diga pra que é a reserva.")

    p = Provision(
        user_id=dono.id,
        description=descricao,
        amount=dados.amount,
        created_on=dados.created_on or planejamento.hoje(),
        commitment_id=c.id if c else None,
        commitment_no=dados.commitment_no if c else None,
        target_date=dados.target_date,
        note=_opcional(dados.note, 500),
    )
    session.add(p)
    session.flush()
    return p


@router_planejamento.patch("/provisions/{provision_id}")
def atualizar_reserva(
    provision_id: int,
    dados: ProvisionUpdate,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Edita. `released_on` libera; mandar nulo nele devolve a reserva."""
    exigir_escrita(dono)
    p = exigir(session, Provision, provision_id, dono, "Reserva")
    mudancas = dados.model_dump(exclude_unset=True)
    if "amount" in mudancas and (mudancas["amount"] is None or mudancas["amount"] <= 0):
        raise HTTPException(status_code=400, detail="A reserva precisa ser maior que zero.")
    try:
        for chave, valor in mudancas.items():
            if chave == "description":
                valor = _texto(valor, "A descrição")
            elif chave == "note":
                valor = _opcional(valor, 500)
            elif chave == "created_on" and valor is None:
                continue
            setattr(p, chave, valor)
    except HTTPException:
        session.rollback()
        raise
    session.add(p)
    session.commit()
    session.refresh(p)
    return _ler_reservas(session, dono, [p])[0]


@router_planejamento.delete("/provisions/{provision_id}")
def excluir_reserva(
    provision_id: int,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    exigir_escrita(dono)
    p = exigir(session, Provision, provision_id, dono, "Reserva")
    session.delete(p)
    session.commit()
    return {"message": "Reserva excluída."}


# ---------------------------------------------------------------------------
# Cenários
# ---------------------------------------------------------------------------

# Referência a um item real dentro de um cenário: "compromisso:12:3".
REF = re.compile(r"^(compromisso:\d+:\d+|fatura:\d+|lancamento:\d+|reserva:\d+)$")


def _ler_cenario(session: Session, dono: User, s: Scenario) -> ScenarioRead:
    itens = session.exec(
        consulta(ScenarioItem, dono)
        .where(ScenarioItem.scenario_id == s.id)
        .order_by(ScenarioItem.date, ScenarioItem.id)
    ).all()
    return ScenarioRead(id=s.id, name=s.name, note=s.note, created_at=s.created_at, items=list(itens))


def _nome_do_cenario(bruto: str | None) -> str:
    return _texto(bruto, "O nome do cenário", 60)


@router_planejamento.get("/scenarios")
def listar_cenarios(
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    return [
        _ler_cenario(session, dono, s)
        for s in session.exec(consulta(Scenario, dono).order_by(Scenario.created_at, Scenario.id)).all()
    ]


@router_planejamento.post("/scenarios")
def criar_cenario(
    dados: ScenarioCreate,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    exigir_escrita(dono)
    s = Scenario(user_id=dono.id, name=_nome_do_cenario(dados.name), note=_opcional(dados.note, 500))
    session.add(s)
    session.commit()
    session.refresh(s)
    return _ler_cenario(session, dono, s)


@router_planejamento.get("/scenarios/{scenario_id}")
def ver_cenario(
    scenario_id: int,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    return _ler_cenario(session, dono, exigir(session, Scenario, scenario_id, dono, "Cenário"))


@router_planejamento.patch("/scenarios/{scenario_id}")
def atualizar_cenario(
    scenario_id: int,
    dados: ScenarioUpdate,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    exigir_escrita(dono)
    s = exigir(session, Scenario, scenario_id, dono, "Cenário")
    mudancas = dados.model_dump(exclude_unset=True)
    if "name" in mudancas:
        s.name = _nome_do_cenario(mudancas["name"])
    if "note" in mudancas:
        s.note = _opcional(mudancas["note"], 500)
    session.add(s)
    session.commit()
    session.refresh(s)
    return _ler_cenario(session, dono, s)


@router_planejamento.delete("/scenarios/{scenario_id}")
def excluir_cenario(
    scenario_id: int,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Apaga o cenário e os itens dele. Nada fora dele é tocado."""
    exigir_escrita(dono)
    s = exigir(session, Scenario, scenario_id, dono, "Cenário")
    for item in session.exec(consulta(ScenarioItem, dono).where(ScenarioItem.scenario_id == s.id)).all():
        session.delete(item)
    session.flush()
    session.delete(s)
    session.commit()
    return {"message": "Cenário excluído."}


class DuplicarCenario(SQLModel):
    name: str | None = None


@router_planejamento.post("/scenarios/{scenario_id}/duplicar")
def duplicar_cenario(
    scenario_id: int,
    pedido: DuplicarCenario,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    exigir_escrita(dono)
    s = exigir(session, Scenario, scenario_id, dono, "Cenário")
    nome = pedido.name if pedido.name and pedido.name.strip() else f"{s.name} (cópia)"
    copia = Scenario(user_id=dono.id, name=_nome_do_cenario(nome[:60]), note=s.note)
    session.add(copia)
    session.flush()
    for item in session.exec(consulta(ScenarioItem, dono).where(ScenarioItem.scenario_id == s.id)).all():
        session.add(
            ScenarioItem(
                user_id=dono.id,
                scenario_id=copia.id,
                **item.model_dump(exclude={"id", "user_id", "scenario_id"}),
            )
        )
    session.commit()
    session.refresh(copia)
    return _ler_cenario(session, dono, copia)


def _validar_item(kind, description, amount, ref) -> tuple[str, str | None]:
    if ref is not None:
        ref = ref.strip()
        if not REF.match(ref):
            raise HTTPException(status_code=400, detail="Referência de item inválida.")
        if amount is None or amount < 0:
            raise HTTPException(status_code=400, detail="O valor no cenário não pode ser negativo (zero remove).")
        return _texto(description or ref, "A descrição"), ref
    if amount is None or amount <= 0:
        raise HTTPException(status_code=400, detail="O valor precisa ser maior que zero.")
    return _texto(description, "A descrição"), None


@router_planejamento.post("/scenarios/{scenario_id}/items")
def criar_item_de_cenario(
    scenario_id: int,
    dados: ScenarioItemCreate,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    exigir_escrita(dono)
    s = exigir(session, Scenario, scenario_id, dono, "Cenário")
    descricao, ref = _validar_item(dados.kind, dados.description, dados.amount, dados.ref)
    if ref is not None:
        # Um ajuste por item real: o segundo substitui o primeiro.
        for antigo in session.exec(
            consulta(ScenarioItem, dono).where(
                ScenarioItem.scenario_id == s.id, ScenarioItem.ref == ref
            )
        ).all():
            session.delete(antigo)
        session.flush()
    item = ScenarioItem(
        user_id=dono.id,
        scenario_id=s.id,
        kind=dados.kind,
        description=descricao,
        amount=dados.amount,
        date=dados.date,
        repeat_months=dados.repeat_months,
        ref=ref,
    )
    session.add(item)
    session.commit()
    return _ler_cenario(session, dono, s)


def _item_do_cenario(session: Session, dono: User, s: Scenario, item_id: int) -> ScenarioItem:
    item = buscar(session, ScenarioItem, item_id, dono)
    if item is None or item.scenario_id != s.id:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    return item


@router_planejamento.patch("/scenarios/{scenario_id}/items/{item_id}")
def atualizar_item_de_cenario(
    scenario_id: int,
    item_id: int,
    dados: ScenarioItemUpdate,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    exigir_escrita(dono)
    s = exigir(session, Scenario, scenario_id, dono, "Cenário")
    item = _item_do_cenario(session, dono, s, item_id)
    mudancas = dados.model_dump(exclude_unset=True)
    try:
        for chave, valor in mudancas.items():
            if valor is not None:
                setattr(item, chave, valor)
        item.description, item.ref = _validar_item(item.kind, item.description, item.amount, item.ref)
    except HTTPException:
        session.rollback()
        raise
    session.add(item)
    session.commit()
    return _ler_cenario(session, dono, s)


@router_planejamento.delete("/scenarios/{scenario_id}/items/{item_id}")
def excluir_item_de_cenario(
    scenario_id: int,
    item_id: int,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    exigir_escrita(dono)
    s = exigir(session, Scenario, scenario_id, dono, "Cenário")
    session.delete(_item_do_cenario(session, dono, s, item_id))
    session.commit()
    return _ler_cenario(session, dono, s)


# ---------------------------------------------------------------------------
# A conta
# ---------------------------------------------------------------------------


def _hipoteses(session: Session, dono: User, scenario_id: int | None) -> tuple[Scenario | None, list]:
    if scenario_id is None:
        return None, []
    s = exigir(session, Scenario, scenario_id, dono, "Cenário")
    itens = session.exec(
        consulta(ScenarioItem, dono)
        .where(ScenarioItem.scenario_id == s.id)
        .order_by(ScenarioItem.id)
    ).all()
    return s, list(itens)


def _planejar(session, dono, ate, hipoteses, cenario=None):
    try:
        resposta = planejamento.planejar(session, dono, ate, hipoteses)
    except planejamento.PlanejamentoInvalido as e:
        raise HTTPException(status_code=400, detail=str(e))
    if cenario is not None:
        resposta.scenario_id = cenario.id
        resposta.scenario_name = cenario.name
    return resposta


def _so_o_mes(resposta, ano: int, mes: int):
    resposta.months = [m for m in resposta.months if (m.year, m.month) == (ano, mes)]
    return resposta


@router_planejamento.get("/planning/month")
def planejar_mes(
    year: int = Query(ge=1900, le=2999),
    month: int = Query(ge=1, le=12),
    scenario_id: int | None = Query(default=None),
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """O mês pedido: saldo de partida, o que entra, o que sai, o disponível.

    Mês futuro parte do projetado do anterior — por isso a conta corre desde o
    mês corrente, mesmo devolvendo só o pedido.
    """
    cenario, hipoteses = _hipoteses(session, dono, scenario_id)
    return _so_o_mes(_planejar(session, dono, (year, month), hipoteses, cenario), year, month)


class HipoteseAvulsa(ScenarioItemCreate):
    pass


class PedidoDeSimulacao(SQLModel):
    year: int
    month: int
    scenario_id: int | None = None
    extras: list[HipoteseAvulsa] = []


@router_planejamento.post("/planning/simulate")
def simular(
    pedido: PedidoDeSimulacao,
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """"E se eu gastar 500?" — calcula e esquece. Não grava nada.

    POST só porque a hipótese vai no corpo. Sem `exigir_escrita`: não escreve,
    então a conta de demonstração também pode simular.
    """
    if len(pedido.extras) > 50:
        raise HTTPException(status_code=400, detail="No máximo 50 hipóteses por vez.")
    for h in pedido.extras:
        _validar_item(h.kind, h.description, h.amount, h.ref)
    cenario, hipoteses = _hipoteses(session, dono, pedido.scenario_id)
    resposta = _planejar(
        session, dono, (pedido.year, pedido.month), hipoteses + list(pedido.extras), cenario
    )
    return _so_o_mes(resposta, pedido.year, pedido.month)


@router_planejamento.get("/planning/compare")
def comparar(
    year: int = Query(ge=1900, le=2999),
    month: int = Query(ge=1, le=12),
    scenario_id: int = Query(),
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Base × cenário no mesmo mês, e a diferença que importa."""
    cenario, hipoteses = _hipoteses(session, dono, scenario_id)
    base = _so_o_mes(_planejar(session, dono, (year, month), []), year, month).months[0]
    hipotese = _so_o_mes(
        _planejar(session, dono, (year, month), hipoteses, cenario), year, month
    ).months[0]
    campos = ("projected", "expense", "income", "reserved", "available")
    return {
        "scenario_id": cenario.id,
        "scenario_name": cenario.name,
        "base": base,
        "scenario": hipotese,
        "diff": {c: round(getattr(hipotese, c) - getattr(base, c), 2) for c in campos},
    }


@router_planejamento.get("/planning/horizon")
def horizonte(
    months: int = Query(default=6, ge=1, le=24),
    scenario_id: int | None = Query(default=None),
    session: Session = Depends(get_session),
    dono: User = Depends(require_user),
):
    """Os próximos `months` meses, a começar pelo corrente."""
    agora = planejamento.hoje()
    ate = avancar_meses(agora.year, agora.month, months - 1)
    cenario, hipoteses = _hipoteses(session, dono, scenario_id)
    return _planejar(session, dono, ate, hipoteses, cenario)
