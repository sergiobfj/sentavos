import datetime as dt

import pytest
from sqlmodel import select

from app.models import Category, Commitment, CommitmentSkip, Transaction, User
from app.planejamento import carregar_estado, status_da_ocorrencia, vencimento
from scripts.reiniciar_novembro_2026 import apply_occurrences, prepare


def setup_month(session):
    user = User(email="reinicio@example.test", name="Teste", password_hash="unused")
    session.add(user)
    session.flush()
    category = Category(user_id=user.id, name="Financiamento", type="expense", color="#000000", icon="x")
    session.add(category)
    session.flush()
    c = Commitment(user_id=user.id, category_id=category.id, description="Contrato real",
                   amount=618.08, first_due=dt.date(2026, 10, 9), installments=48)
    session.add(c)
    session.commit()
    return user, category, c


def test_suspende_so_novembro_sem_mudar_contrato_ou_criar_pagamento(session):
    user, _, c = setup_month(session)
    before = c.model_dump()
    plan = prepare(session, user.id)
    assert [(t["commitment_id"], t["number"]) for t in plan["targets"]] == [(c.id, 2)]
    assert apply_occurrences(session, plan) == 1
    session.commit()
    assert c.model_dump() == before
    assert session.exec(select(Transaction)).all() == []
    state = carregar_estado(session, user, [c.id])
    assert status_da_ocorrencia(c, 2, vencimento(c, 2), state, dt.date(2026, 11, 3)) == "dispensada"
    for number in (1, 3, 15, 48):
        assert (c.id, number) not in state.dispensas


def test_repetir_nao_afeta_novos_registros_e_novas_recorrencias(session):
    user, category, _ = setup_month(session)
    plan = prepare(session, user.id)
    apply_occurrences(session, plan)
    session.commit()
    tx = Transaction(user_id=user.id, category_id=category.id, date=dt.date(2026, 11, 3),
                     description="Novo lançamento manual", amount_paid=10)
    new = Commitment(user_id=user.id, category_id=category.id, first_due=dt.date(2026, 11, 15),
                     description="Nova recorrência", amount=20)
    session.add(tx)
    session.add(new)
    session.commit()
    assert apply_occurrences(session, plan) == 0
    session.commit()
    assert session.get(Transaction, tx.id).amount_paid == 10
    assert len(session.exec(select(CommitmentSkip)).all()) == 1


def test_recusa_compromisso_alterado_desde_a_simulacao(session):
    user, _, c = setup_month(session)
    plan = prepare(session, user.id)
    c.amount = 777
    session.add(c)
    session.commit()
    with pytest.raises(ValueError, match="mudou após simulação"):
        apply_occurrences(session, plan)
    assert session.exec(select(CommitmentSkip)).all() == []


def test_recusa_baixa_recente_sem_apagar_pagamento(session):
    user, category, c = setup_month(session)
    plan = prepare(session, user.id)
    tx = Transaction(user_id=user.id, category_id=category.id, date=dt.date(2026, 11, 9),
                     description="Pagamento recente", amount_paid=618.08, commitment_id=c.id, commitment_no=2)
    session.add(tx)
    session.commit()
    with pytest.raises(ValueError, match="lançamento vinculado"):
        apply_occurrences(session, plan)
    assert session.get(Transaction, tx.id).amount_paid == 618.08
    assert session.exec(select(CommitmentSkip)).all() == []


def test_recusa_plano_que_tente_suspender_outubro(session):
    user, _, _ = setup_month(session)
    plan = prepare(session, user.id)
    plan["targets"][0].update(number=1, due="2026-10-09")
    with pytest.raises(ValueError, match="Fora de novembro"):
        apply_occurrences(session, plan)
    assert session.exec(select(CommitmentSkip)).all() == []
