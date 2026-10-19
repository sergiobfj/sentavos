"""A organização fixa/variável persiste sem mudar as contas financeiras."""
import datetime as dt

from sqlmodel import select

from app.models import ExpenseClass, Transaction
from app.tests.apoio_planejamento import Montagem


def test_lancamento_antigo_fica_sem_classificacao_e_pode_ser_corrigido(client):
    m = Montagem(client)
    categoria = m.categoria("Transporte")
    antigo = m.lancar(categoria, dt.date(2026, 10, 18), pago=18, descricao="Corrida")
    assert antigo["expense_class"] is None
    listado = client.get("/transactions?year=2026&month=10").json()[0]
    assert listado["effective_expense_class"] is None

    alterado = client.patch(f"/transactions/{antigo['id']}", json={"expense_class": "variable"})
    assert alterado.status_code == 200, alterado.text
    assert client.get("/transactions?year=2026&month=10").json()[0]["effective_expense_class"] == "variable"


def test_compromisso_sugere_fixa_mas_baixa_permite_excecao(client):
    m = Montagem(client)
    categoria = m.categoria("Transporte")
    compromisso = m.compromisso(categoria, 120, dt.date(2026, 11, 12), descricao="Mensalidade")
    plano = m.mes(2026, 11)["months"][0]
    item = next(i for i in plano["items"] if i["commitment_id"] == compromisso["id"])
    assert item["expense_class"] == "fixed"
    assert plano["expense_groups"]["fixed"] == 120

    pago = m.pagar(compromisso["id"], 1, data=dt.date(2026, 11, 12))
    assert pago.status_code == 200, pago.text
    linha = next(t for t in client.get("/transactions?year=2026&month=11").json() if t["commitment_id"] == compromisso["id"])
    assert linha["effective_expense_class"] == "fixed"
    r = client.patch(f"/transactions/{linha['id']}", json={"expense_class":"variable"})
    assert r.status_code == 200, r.text
    linha = next(t for t in client.get("/transactions?year=2026&month=11").json() if t["id"] == linha["id"])
    assert linha["effective_expense_class"] == "variable"


def test_parcelas_herdam_classe_e_edicao_propagada(client, session):
    m = Montagem(client)
    categoria = m.categoria("Equipamento")
    card = m.cartao()
    compra = client.post("/purchases", json={"card_id":card,"category_id":categoria,"description":"Teclado","total_amount":300,"installments":3,"purchase_date":"2026-10-18","expense_class":"variable"})
    assert compra.status_code == 200, compra.text
    pid = compra.json()["id"]
    parcelas = session.exec(select(Transaction).where(Transaction.purchase_id == pid)).all()
    assert len(parcelas) == 3
    assert all(p.expense_class == ExpenseClass.VARIABLE for p in parcelas)

    alterado = client.patch(f"/purchases/{pid}", json={"expense_class":"fixed"})
    assert alterado.status_code == 200, alterado.text
    session.expire_all()
    parcelas = session.exec(select(Transaction).where(Transaction.purchase_id == pid)).all()
    assert all(p.expense_class == ExpenseClass.FIXED for p in parcelas)


def test_classe_nao_muda_gasto_ou_fluxo(client):
    m = Montagem(client)
    categoria = m.categoria("Internet")
    criado = client.post("/transactions",json={"date":"2026-10-18","description":"Internet","category_id":categoria,"amount_paid":60,"payment_method":"cash"})
    assert criado.status_code == 200, criado.text
    antes = client.get("/budgets/summary?year=2026&month=10").json()["caixa"]
    alterado = client.patch(f"/transactions/{criado.json()['id']}",json={"expense_class":"fixed"})
    assert alterado.status_code == 200, alterado.text
    depois = client.get("/budgets/summary?year=2026&month=10").json()["caixa"]
    assert antes == depois
