"""Finalidade: quem consumiu o gasto — pessoal, família ou empresa.

A regra em três linhas, que é o que estes testes protegem:

  - à vista sem escolha           -> PESSOAL
  - compra no cartão sem escolha  -> a finalidade do cartão
  - escolha explícita             -> vale a escolha, em todas as parcelas

E o que ela NÃO faz: não filtra caixa, não mexe em lançamento antigo e não
existe em receita nem investimento.
"""

import datetime as dt

import pytest
import sqlalchemy as sa
from sqlmodel import select

from app.models import Card, Finalidade, Purchase, Transaction


def categoria(client, nome="Mercado", tipo="expense"):
    r = client.post(
        "/categories", json={"name": nome, "type": tipo, "color": "#3987e5", "icon": "🛒"}
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def cartao(client, nome="Nubank", finalidade="pessoal"):
    corpo = {"name": nome, "closing_day": 25, "due_day": 2}
    if finalidade is not None:
        corpo["finalidade"] = finalidade
    r = client.post("/cards", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def comprar(client, card_id, category_id, valor=300.0, parcelas=1, finalidade=None,
            data="2026-09-10", descricao="Compra"):
    corpo = {
        "card_id": card_id, "category_id": category_id, "description": descricao,
        "total_amount": valor, "installments": parcelas, "purchase_date": data,
    }
    if finalidade is not None:
        corpo["finalidade"] = finalidade
    r = client.post("/purchases", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def parcelas_da(session, compra_id):
    return session.exec(
        select(Transaction).where(Transaction.purchase_id == compra_id)
    ).all()


# ---------- Herança do cartão ----------


@pytest.mark.parametrize("fin", ["pessoal", "familia", "empresa"])
def test_compra_herda_a_finalidade_do_cartao(client, session, fin):
    cat = categoria(client)
    card = cartao(client, finalidade=fin)

    compra = comprar(client, card, cat)

    assert compra["finalidade"] == fin
    assert [p.finalidade for p in parcelas_da(session, compra["id"])] == [Finalidade(fin)]


def test_escolha_explicita_sobrescreve_o_cartao(client, session):
    """A compra da família feita no cartão pessoal."""
    cat = categoria(client)
    card = cartao(client, finalidade="pessoal")

    compra = comprar(client, card, cat, finalidade="familia")

    assert compra["finalidade"] == "familia"
    assert parcelas_da(session, compra["id"])[0].finalidade == Finalidade.FAMILIA


def test_parcelada_mantem_a_mesma_finalidade_em_todas_as_parcelas(client, session):
    cat = categoria(client)
    card = cartao(client, finalidade="pessoal")

    compra = comprar(client, card, cat, valor=1000, parcelas=10, finalidade="empresa")

    finalidades = {p.finalidade for p in parcelas_da(session, compra["id"])}
    assert finalidades == {Finalidade.EMPRESA}
    assert len(parcelas_da(session, compra["id"])) == 10


def test_editar_a_finalidade_da_compra_reescreve_todas_as_parcelas(client, session):
    cat = categoria(client)
    card = cartao(client, finalidade="pessoal")
    compra = comprar(client, card, cat, valor=900, parcelas=3)

    r = client.patch(f"/purchases/{compra['id']}", json={"finalidade": "familia"})

    assert r.status_code == 200
    assert {p.finalidade for p in parcelas_da(session, compra["id"])} == {Finalidade.FAMILIA}


def test_finalidade_muda_mesmo_com_fatura_paga(client, session):
    """É rótulo, como a categoria: não mexe em quanto a fatura cobra."""
    cat = categoria(client)
    card = cartao(client, finalidade="pessoal")
    compra = comprar(client, card, cat, valor=300)
    fatura = parcelas_da(session, compra["id"])[0].invoice_id
    assert client.post(
        f"/invoices/{fatura}/payments", json={"amount": 300, "date": "2026-10-02"}
    ).status_code == 200

    r = client.patch(f"/purchases/{compra['id']}", json={"finalidade": "empresa"})

    assert r.status_code == 200
    assert parcelas_da(session, compra["id"])[0].finalidade == Finalidade.EMPRESA


def test_refazer_parcelas_preserva_a_finalidade(client, session):
    """Mudar o número de parcelas regera as linhas — a finalidade vem junto."""
    cat = categoria(client)
    card = cartao(client, finalidade="pessoal")
    compra = comprar(client, card, cat, valor=600, parcelas=2, finalidade="familia")

    r = client.patch(f"/purchases/{compra['id']}", json={"installments": 6})

    assert r.status_code == 200
    parcelas = parcelas_da(session, compra["id"])
    assert len(parcelas) == 6
    assert {p.finalidade for p in parcelas} == {Finalidade.FAMILIA}


def test_parcela_nao_troca_de_finalidade_sozinha(client, session):
    cat = categoria(client)
    card = cartao(client)
    compra = comprar(client, card, cat, parcelas=2)
    parcela = parcelas_da(session, compra["id"])[1]

    r = client.patch(f"/transactions/{parcela.id}", json={"finalidade": "empresa"})

    assert r.status_code == 409


# ---------- À vista ----------


def lancar(client, category_id, valor=100.0, finalidade=None, data="2026-09-10"):
    corpo = {"date": data, "description": "PIX", "category_id": category_id, "amount_paid": valor}
    if finalidade is not None:
        corpo["finalidade"] = finalidade
    r = client.post("/transactions", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def test_a_vista_sem_escolha_e_pessoal(client):
    assert lancar(client, categoria(client))["finalidade"] == "pessoal"


def test_a_vista_com_escolha(client):
    assert lancar(client, categoria(client), finalidade="empresa")["finalidade"] == "empresa"


@pytest.mark.parametrize("tipo", ["income", "investment"])
def test_receita_e_investimento_nao_tem_finalidade(client, tipo):
    """Reembolso da empresa ainda não tem regra decidida; melhor não inventar."""
    cat = categoria(client, "Entrada", tipo)
    assert lancar(client, cat, finalidade="empresa")["finalidade"] is None


def test_virar_receita_limpa_a_finalidade(client):
    gasto = categoria(client, "Mercado")
    entrada = categoria(client, "Salário", "income")
    t = lancar(client, gasto, finalidade="familia")

    r = client.patch(f"/transactions/{t['id']}", json={"category_id": entrada})

    assert r.json()["finalidade"] is None


def test_editar_descricao_de_lancamento_antigo_nao_inventa_finalidade(client, session, dono):
    cat = categoria(client)
    antigo = Transaction(
        user_id=dono.id, date=dt.date(2025, 3, 1), description="antigo",
        amount_paid=50, category_id=cat,
    )
    session.add(antigo)
    session.commit()

    r = client.patch(f"/transactions/{antigo.id}", json={"description": "antigo, revisto"})

    assert r.json()["finalidade"] is None


# ---------- Cartão sem finalidade (a transição) ----------


def test_classificar_o_cartao_leva_as_compras_sem_finalidade(client, session, dono):
    cat = categoria(client)
    # Cartão como a migração deixa: sem finalidade.
    antigo = Card(user_id=dono.id, name="Nubank - Família", closing_day=25, due_day=2)
    session.add(antigo)
    session.commit()

    sem = comprar(client, antigo.id, cat, valor=200, parcelas=2)
    escolhida = comprar(client, antigo.id, cat, valor=100, finalidade="empresa")
    assert sem["finalidade"] is None

    r = client.patch(f"/cards/{antigo.id}", json={"finalidade": "familia"})

    assert r.status_code == 200
    assert {p.finalidade for p in parcelas_da(session, sem["id"])} == {Finalidade.FAMILIA}
    # A que já tinha finalidade não foi tocada.
    assert parcelas_da(session, escolhida["id"])[0].finalidade == Finalidade.EMPRESA


def test_reclassificar_o_cartao_nao_reescreve_compra_passada(client, session):
    cat = categoria(client)
    card = cartao(client, finalidade="pessoal")
    compra = comprar(client, card, cat)

    client.patch(f"/cards/{card}", json={"finalidade": "empresa"})

    assert parcelas_da(session, compra["id"])[0].finalidade == Finalidade.PESSOAL


def test_cartao_nao_volta_a_ficar_sem_finalidade(client):
    card = cartao(client)
    assert client.patch(f"/cards/{card}", json={"finalidade": None}).status_code == 400


def test_cartao_novo_sem_finalidade_informada_e_pessoal(client):
    card = cartao(client, finalidade=None)
    cartoes = client.get("/cards").json()
    assert next(c for c in cartoes if c["id"] == card)["finalidade"] == "pessoal"


def test_passar_lancamento_pro_cartao_leva_a_finalidade(client, session):
    cat = categoria(client)
    card = cartao(client, finalidade="pessoal")
    t = lancar(client, cat, finalidade="familia")

    r = client.post(
        f"/transactions/{t['id']}/forma-de-pagamento",
        json={"metodo": "credit", "card_id": card, "installments": 2},
    )

    assert r.status_code == 200
    compra = session.exec(select(Purchase)).one()
    assert compra.finalidade == Finalidade.FAMILIA
    assert {p.finalidade for p in parcelas_da(session, compra.id)} == {Finalidade.FAMILIA}


# ---------- O enum no Postgres ----------


def test_tipo_da_migracao_e_o_que_o_orm_grava():
    """A suíte monta o banco com create_all e nunca roda a migração. Sem este
    teste, um enum de valores minúsculos na 0005 passaria aqui e recusaria o
    primeiro lançamento em produção — a armadilha que quase passou na 0004."""
    import importlib.util
    import pathlib

    caminho = pathlib.Path(__file__).parents[2] / "migrations" / "versions" / "0005_finalidade.py"
    spec = importlib.util.spec_from_file_location("m0005", caminho)
    migracao = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migracao)

    for modelo in (Transaction, Card, Purchase):
        tipo = modelo.__table__.c.finalidade.type
        assert isinstance(tipo, sa.Enum)
        assert tipo.enums == migracao.finalidade.enums == ["PESSOAL", "FAMILIA", "EMPRESA"]
        assert tipo.name == migracao.finalidade.name
