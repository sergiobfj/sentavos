"""Prova que uma conta não alcança o dado da outra.

Este é o teste que importa mais neste app. Com três pessoas no mesmo banco, um
filtro esquecido em uma rota faz alguém ler as finanças de outro — e é um bug
que não aparece testando na mão, porque cada um só olha a própria tela.

Comentário envelhece e revisão esquece. O que sobrevive é isto: cada rota que
recebe id é exercitada com o id de outra pessoa, e tem que responder 404. Rota
nova que esqueça o `consulta()`/`exigir()` quebra aqui.

404 e não 403 de propósito: 403 confirmaria que a linha existe e é de outra
pessoa. 404 não distingue "não existe" de "não é seu".
"""

import datetime as dt

import pytest
from sqlmodel import Session, select

from app.models import (
    Asset,
    AssetSnapshot,
    Budget,
    Card,
    Category,
    Invoice,
    InvoicePayment,
    PaymentMethod,
    Purchase,
    Transaction,
    User,
)


def _semear(session: Session, dono: User) -> dict:
    """Um conjunto completo de dados para um dono."""
    cat = Category(
        name=f"Cat de {dono.name}", type="expense", color="#fff", icon="x",
        user_id=dono.id,
    )
    session.add(cat)
    session.commit()
    session.refresh(cat)

    tx = Transaction(
        date=dt.date(2026, 9, 10), description=f"Lançamento de {dono.name}",
        amount_paid=100.0, category_id=cat.id, user_id=dono.id,
    )
    meta = Budget(category_id=cat.id, year=2026, month=9, amount=500.0, user_id=dono.id)
    ativo = Asset(name=f"Ativo de {dono.name}", asset_class="checking", user_id=dono.id)
    session.add_all([tx, meta, ativo])
    session.commit()
    session.refresh(tx)
    session.refresh(meta)
    session.refresh(ativo)

    snap = AssetSnapshot(
        asset_id=ativo.id, year=2026, month=9, value=1000.0, user_id=dono.id
    )
    cartao = Card(
        name=f"Cartão de {dono.name}", closing_day=25, due_day=2, user_id=dono.id
    )
    session.add_all([snap, cartao])
    session.commit()
    session.refresh(snap)
    session.refresh(cartao)

    # A compra no cartão, com a fatura que a cobra e uma parcela dentro dela —
    # o conjunto inteiro, pra o teste poder bater em cada um dos ids.
    compra = Purchase(
        user_id=dono.id, card_id=cartao.id, category_id=cat.id,
        description=f"Compra de {dono.name}", total_amount=300.0,
        installments=1, purchase_date=dt.date(2026, 9, 12),
    )
    fatura = Invoice(
        user_id=dono.id, card_id=cartao.id, year=2026, month=10,
        closing_date=dt.date(2026, 9, 25), due_date=dt.date(2026, 10, 2),
    )
    session.add_all([compra, fatura])
    session.commit()
    session.refresh(compra)
    session.refresh(fatura)

    parcela = Transaction(
        date=dt.date(2026, 9, 12), description=f"Parcela de {dono.name}",
        amount_paid=300.0, category_id=cat.id, user_id=dono.id,
        payment_method=PaymentMethod.CREDIT, purchase_id=compra.id,
        installment_no=1, invoice_id=fatura.id,
    )
    pagamento = InvoicePayment(
        user_id=dono.id, invoice_id=fatura.id,
        date=dt.date(2026, 10, 2), amount=100.0,
    )
    session.add_all([parcela, pagamento])
    session.commit()
    session.refresh(pagamento)

    return {
        "categoria": cat.id, "transacao": tx.id, "meta": meta.id,
        "ativo": ativo.id, "saldo": snap.id,
        "cartao": cartao.id, "compra": compra.id,
        "fatura": fatura.id, "pagamento": pagamento.id,
    }


@pytest.fixture(name="duas_contas")
def duas_contas_fixture(session, criar_usuario):
    """Duas contas, cada uma com o conjunto completo de dados."""
    ana = criar_usuario("ana@exemplo.com", "Ana", "senha-da-ana-12345")
    bruno = criar_usuario("bruno@exemplo.com", "Bruno", "senha-do-bruno-12345")
    return {
        "ana": (ana, _semear(session, ana)),
        "bruno": (bruno, _semear(session, bruno)),
    }


# Cada rota que recebe id, com o nome do recurso que o teste vai plantar.
ROTAS_POR_ID = [
    ("get", "/transactions/{transacao}", None),
    ("patch", "/transactions/{transacao}", {"description": "invadido"}),
    ("delete", "/transactions/{transacao}", None),
    ("get", "/categories/{categoria}", None),
    ("patch", "/categories/{categoria}", {"name": "invadida"}),
    ("delete", "/categories/{categoria}", None),
    ("patch", "/budgets/{meta}", {"amount": 1.0}),
    ("delete", "/budgets/{meta}", None),
    ("patch", "/assets/{ativo}", {"name": "invadido"}),
    ("delete", "/assets/{ativo}", None),
    ("patch", "/assets/snapshots/{saldo}", {"value": 1.0}),
    ("delete", "/assets/snapshots/{saldo}", None),
    # ---------- Cartão ----------
    # Toda rota nova de app/rotas_cartao.py entra aqui. É este teste, e não o
    # comentário no topo daquele arquivo, que garante que o router de lá também
    # filtra por dono.
    ("patch", "/cards/{cartao}", {"name": "invadido"}),
    ("delete", "/cards/{cartao}", None),
    ("get", "/purchases/{compra}", None),
    ("patch", "/purchases/{compra}", {"description": "invadida"}),
    ("delete", "/purchases/{compra}", None),
    ("get", "/invoices/{fatura}", None),
    ("get", "/invoices/{fatura}/candidatos-a-pagamento", None),
    ("post", "/invoices/{fatura}/payments", {"amount": 1.0, "date": "2026-10-02"}),
    ("delete", "/invoice_payments/{pagamento}", None),
    ("post", "/transactions/{transacao}/forma-de-pagamento", {"metodo": "cash"}),
]


@pytest.mark.parametrize("metodo,rota,corpo", ROTAS_POR_ID)
def test_nao_alcanca_dado_de_outra_conta(cliente_de, duas_contas, metodo, rota, corpo):
    ana, _ = duas_contas["ana"]
    _, ids_do_bruno = duas_contas["bruno"]

    caminho = rota.format(**ids_do_bruno)
    cliente = cliente_de(ana)
    r = getattr(cliente, metodo)(caminho, **({"json": corpo} if corpo else {}))

    assert r.status_code == 404, (
        f"{metodo.upper()} {caminho} respondeu {r.status_code} — a conta da Ana "
        f"alcançou dado do Bruno."
    )


def test_listagens_so_trazem_o_proprio(cliente_de, duas_contas):
    ana, _ = duas_contas["ana"]
    cliente = cliente_de(ana)

    for rota, campo in (
        ("/transactions", "description"),
        ("/categories", "name"),
        ("/assets", "name"),
        ("/cards", "name"),
    ):
        itens = cliente.get(rota).json()
        assert itens, f"{rota} veio vazio — o teste não provaria nada"
        for item in itens:
            assert "Bruno" not in str(item.get(campo, "")), (
                f"{rota} devolveu dado do Bruno para a Ana: {item}"
            )


def test_resumos_nao_somam_dinheiro_alheio(cliente_de, duas_contas):
    """O caso mais traiçoeiro: o total vaza sem nenhuma linha aparecer."""
    ana, _ = duas_contas["ana"]
    cliente = cliente_de(ana)

    resumo = cliente.get("/budgets/summary?year=2026&month=9").json()
    # Cada uma tem um lançamento à vista de 100 e uma parcela de cartão de 300.
    # Os dois contam como gasto — é o que a meta mede —, e nenhum dos 400 pode
    # vir da outra conta.
    assert resumo["totals"]["expense"]["paid"] == 400.0

    patrimonio = cliente.get("/assets/summary?year=2026&month=9").json()
    # Cada uma tem exatamente um ativo de 1000.
    assert patrimonio["assets"] == 1000.0
    assert len(patrimonio["items"]) == 1

    # O resumo de caixa é o mais fácil de vazar sem ninguém ver: ele soma
    # lançamentos e pagamentos de fatura sem mostrar linha nenhuma.
    caixa = resumo["caixa"]
    assert caixa["gasto_total"] == 400.0  # 100 à vista + 300 da parcela, só da Ana
    assert caixa["no_cartao"] == 300.0
    assert caixa["faturas_em_aberto"] == 200.0  # 300 de fatura − 100 pago

    faturas = cliente.get("/invoices/summary?year=2026&month=10").json()
    assert len(faturas["cards"]) == 1
    assert faturas["cards"][0]["current"]["total"] == 300.0
    assert faturas["open_total"] == 200.0
    # O pagamento de outubro é um só, e é o dela.
    assert len(faturas["payments"]) == 1

    assert len(cliente.get("/invoices").json()) == 1


def test_nao_da_pra_lancar_na_categoria_de_outra_conta(cliente_de, duas_contas):
    """Informar o id da categoria alheia não pode plantar dado na conta dela."""
    ana, _ = duas_contas["ana"]
    _, ids_do_bruno = duas_contas["bruno"]

    r = cliente_de(ana).post(
        "/transactions",
        json={
            "date": "2026-09-11",
            "description": "enxerido",
            "amount_paid": 10,
            "category_id": ids_do_bruno["categoria"],
        },
    )

    assert r.status_code == 400


def test_nao_da_pra_comprar_no_cartao_de_outra_conta(cliente_de, duas_contas):
    """Informar o id do cartão alheio não pode plantar compra na fatura dele."""
    ana, ids_da_ana = duas_contas["ana"]
    _, ids_do_bruno = duas_contas["bruno"]

    r = cliente_de(ana).post(
        "/purchases",
        json={
            "card_id": ids_do_bruno["cartao"],
            "category_id": ids_da_ana["categoria"],
            "description": "enxerida",
            "total_amount": 100.0,
            "installments": 1,
            "purchase_date": "2026-09-11",
        },
    )

    assert r.status_code == 400


def test_reconciliar_nao_cruza_contas(cliente_de, duas_contas):
    """A rota recebe DOIS ids, e os dois precisam ser do dono.

    É o caso mais fácil de deixar passar: quem revisa olha o primeiro `exigir` e
    dá o segundo como coberto. Aqui as duas combinações são exercitadas.
    """
    ana, ids_da_ana = duas_contas["ana"]
    bruno, ids_do_bruno = duas_contas["bruno"]

    # Fatura dela, lançamento dele.
    r = cliente_de(ana).post(
        f"/invoices/{ids_da_ana['fatura']}/reconciliar",
        json={"transaction_id": ids_do_bruno["transacao"]},
    )
    assert r.status_code == 404

    # Fatura dele, lançamento dela.
    r = cliente_de(ana).post(
        f"/invoices/{ids_do_bruno['fatura']}/reconciliar",
        json={"transaction_id": ids_da_ana["transacao"]},
    )
    assert r.status_code == 404

    # E o lançamento do Bruno continua lá, inteiro.
    assert cliente_de(bruno).get(f"/transactions/{ids_do_bruno['transacao']}").status_code == 200


def test_classificar_em_lote_nao_alcanca_lancamento_alheio(cliente_de, duas_contas):
    """O lote não pode ser a porta dos fundos das rotas por id.

    Ele recebe uma lista, então um id alheio no meio não daria 404 na resposta
    inteira — precisa ser ignorado item a item.
    """
    ana, _ = duas_contas["ana"]
    bruno, ids_do_bruno = duas_contas["bruno"]

    r = cliente_de(ana).post(
        "/transactions/forma-de-pagamento",
        json={"ids": [ids_do_bruno["transacao"]], "metodo": "cash"},
    )

    assert r.status_code == 200
    assert r.json()["atualizados"] == 0
    assert r.json()["ignorados"][0]["motivo"] == "não encontrado"

    # E o lançamento do Bruno não foi tocado.
    dele = cliente_de(bruno).get(f"/transactions/{ids_do_bruno['transacao']}").json()
    assert dele["payment_method"] is None


def test_meta_do_mesmo_mes_nao_colide_entre_contas(cliente_de, duas_contas, session):
    """A unicidade de meta vale por dono, não global.

    Sem `user_id` na restrição, a segunda pessoa a orçar a mesma categoria no
    mesmo mês receberia erro de chave duplicada — e o app dela quebraria por
    causa de um dado que nem é dela.
    """
    ana, ids_da_ana = duas_contas["ana"]
    bruno, ids_do_bruno = duas_contas["bruno"]

    # As duas já têm meta para setembro/2026 (criadas no _semear). Se a
    # restrição fosse global, o _semear do segundo teria falhado.
    metas = session.exec(select(Budget).where(Budget.year == 2026, Budget.month == 9)).all()
    assert len(metas) == 2
    assert {m.user_id for m in metas} == {ana.id, bruno.id}


# ---------- Conta de demonstração ----------

ROTAS_DE_ESCRITA = [
    ("post", "/transactions", {"date": "2026-09-01", "description": "x", "category_id": 1}),
    ("post", "/categories", {"name": "x", "type": "expense", "color": "#fff", "icon": "x"}),
    ("put", "/budgets", {"category_id": 1, "year": 2026, "month": 9, "amount": 1}),
    ("post", "/assets", {"name": "x", "asset_class": "checking"}),
    ("put", "/assets/snapshots", {"asset_id": 1, "year": 2026, "month": 9, "value": 1}),
    # ---------- Cartão ----------
    # A senha do demo é pública: se qualquer uma destas passar, o primeiro
    # visitante cria cartão, compra e pagamento na conta de demonstração.
    ("post", "/cards", {"name": "x", "closing_day": 25, "due_day": 2}),
    ("patch", "/cards/1", {"name": "x"}),
    ("delete", "/cards/1", None),
    ("post", "/purchases", {
        "card_id": 1, "category_id": 1, "description": "x",
        "total_amount": 10, "installments": 1, "purchase_date": "2026-09-10",
    }),
    ("patch", "/purchases/1", {"description": "x"}),
    ("delete", "/purchases/1", None),
    ("post", "/invoices/1/payments", {"amount": 1, "date": "2026-10-02"}),
    ("post", "/invoices/1/reconciliar", {"transaction_id": 1}),
    ("delete", "/invoice_payments/1", None),
    ("post", "/transactions/forma-de-pagamento", {"ids": [1], "metodo": "cash"}),
    ("post", "/transactions/1/forma-de-pagamento", {"metodo": "cash"}),
]


@pytest.mark.parametrize("metodo,rota,corpo", ROTAS_DE_ESCRITA)
def test_conta_de_demonstracao_nao_escreve(cliente_de, criar_usuario, metodo, rota, corpo):
    """A senha do demo é pública; a trava tem que estar no servidor.

    Esconder o botão no front não protege nada — qualquer um manda o POST na
    mão. Por isso o teste bate direto na API.
    """
    demo = criar_usuario("demo@exemplo.com", "Demo", "senha-do-demo-12345", read_only=True)

    # DELETE do TestClient não aceita corpo, então a chamada só leva `json`
    # quando há um.
    cliente = cliente_de(demo)
    r = getattr(cliente, metodo)(rota, **({"json": corpo} if corpo else {}))

    assert r.status_code == 403


def test_conta_de_demonstracao_le_normalmente(cliente_de, criar_usuario, session):
    demo = criar_usuario("demo2@exemplo.com", "Demo", "senha-do-demo-12345", read_only=True)
    _semear(session, demo)

    cliente = cliente_de(demo)

    assert cliente.get("/transactions").status_code == 200
    assert cliente.get("/budgets/summary?year=2026&month=9").status_code == 200
    assert len(cliente.get("/categories").json()) == 1
