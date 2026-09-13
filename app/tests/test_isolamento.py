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
    Category,
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
    session.add(snap)
    session.commit()
    session.refresh(snap)

    return {
        "categoria": cat.id, "transacao": tx.id, "meta": meta.id,
        "ativo": ativo.id, "saldo": snap.id,
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
    # Cada uma tem exatamente um lançamento de 100.
    assert resumo["totals"]["expense"]["paid"] == 100.0

    patrimonio = cliente.get("/assets/summary?year=2026&month=9").json()
    # Cada uma tem exatamente um ativo de 1000.
    assert patrimonio["assets"] == 1000.0
    assert len(patrimonio["items"]) == 1


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
]


@pytest.mark.parametrize("metodo,rota,corpo", ROTAS_DE_ESCRITA)
def test_conta_de_demonstracao_nao_escreve(cliente_de, criar_usuario, metodo, rota, corpo):
    """A senha do demo é pública; a trava tem que estar no servidor.

    Esconder o botão no front não protege nada — qualquer um manda o POST na
    mão. Por isso o teste bate direto na API.
    """
    demo = criar_usuario("demo@exemplo.com", "Demo", "senha-do-demo-12345", read_only=True)

    r = getattr(cliente_de(demo), metodo)(rota, json=corpo)

    assert r.status_code == 403


def test_conta_de_demonstracao_le_normalmente(cliente_de, criar_usuario, session):
    demo = criar_usuario("demo2@exemplo.com", "Demo", "senha-do-demo-12345", read_only=True)
    _semear(session, demo)

    cliente = cliente_de(demo)

    assert cliente.get("/transactions").status_code == 200
    assert cliente.get("/budgets/summary?year=2026&month=9").status_code == 200
    assert len(cliente.get("/categories").json()) == 1
