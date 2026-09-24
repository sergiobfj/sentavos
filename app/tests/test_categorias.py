"""Categorias: o que se edita livre e o que a API recusa.

Nome, ícone e cor são rótulo — mudam à vontade e o histórico continua de pé. O
tipo não: despesa virar receita inverteria o sinal de tudo que já foi lançado
nela, então a troca só passa em categoria que nunca foi usada.
"""


import pytest

from app.models import Category, CategoryType


def criar(client, nome="Mercado", tipo="expense", cor="#3987e5", icone="🛒"):
    return client.post("/categories", json={"name": nome, "type": tipo, "color": cor, "icon": icone})


def lancar(client, cat, valor=80.0):
    r = client.post(
        "/transactions",
        json={"date": "2026-09-10", "description": "x", "category_id": cat, "amount_paid": valor},
    )
    assert r.status_code == 200
    return r.json()


# ---------- Rótulo ----------


def test_editar_nome_emoji_e_cor_preserva_o_historico(client):
    cat = criar(client).json()["id"]
    t = lancar(client, cat, 80)

    r = client.patch(
        f"/categories/{cat}", json={"name": "Supermercado", "icon": "🧺", "color": "#1F94AD"}
    )

    assert r.status_code == 200
    assert r.json()["name"] == "Supermercado"
    assert r.json()["icon"] == "🧺"
    assert r.json()["color"] == "#1f94ad"
    # O lançamento continua apontando pra ela, com o mesmo valor.
    assert client.get(f"/transactions/{t['id']}").json()["category_id"] == cat
    resumo = client.get("/budgets/summary?year=2026&month=9").json()
    assert next(i for i in resumo["items"] if i["category_id"] == cat)["paid"] == 80


def test_emoji_composto_cabe(client):
    """O maxLength=4 antigo cortava a família ao meio."""
    r = criar(client, "Família", icone="👨‍👩‍👧‍👦")
    assert r.status_code == 200
    assert r.json()["icon"] == "👨‍👩‍👧‍👦"


@pytest.mark.parametrize("nome", ["", "   ", "x" * 41])
def test_nome_invalido_e_recusado(client, nome):
    assert criar(client, nome).status_code == 400


def test_nome_e_normalizado(client):
    assert criar(client, "  Mercado   do   mês ").json()["name"] == "Mercado do mês"


def test_icone_vazio_e_cor_invalida_sao_recusados(client):
    assert criar(client, icone="  ").status_code == 400
    assert criar(client, cor="vermelho").status_code == 400


# ---------- Duplicidade ----------


def test_nome_repetido_no_mesmo_tipo_e_recusado_sem_distinguir_maiuscula(client):
    assert criar(client, "Mercado").status_code == 200
    r = criar(client, "mercado")
    assert r.status_code == 409
    assert "Mercado" in r.json()["detail"]


def test_nome_repetido_em_tipo_diferente_passa(client):
    assert criar(client, "Outros", "expense").status_code == 200
    assert criar(client, "Outros", "income").status_code == 200


def test_arquivada_tambem_segura_o_nome(client):
    cat = criar(client, "Uber").json()["id"]
    client.patch(f"/categories/{cat}", json={"archived": True})

    r = criar(client, "UBER")

    assert r.status_code == 409
    assert "arquivada" in r.json()["detail"]


def test_renomear_pra_nome_de_outra_e_recusado(client):
    criar(client, "Casa")
    lazer = criar(client, "Lazer").json()["id"]
    assert client.patch(f"/categories/{lazer}", json={"name": "casa"}).status_code == 409


def test_duplicata_antiga_nao_trava_edicao_de_cor(client, session, dono):
    """Dado herdado pode já ter duas iguais; mudar a cor de uma não é criar a gêmea."""
    for _ in range(2):
        session.add(Category(name="Outros", type=CategoryType.EXPENSE, color="#fff", icon="x", user_id=dono.id))
    session.commit()
    uma = client.get("/categories").json()[0]["id"]

    assert client.patch(f"/categories/{uma}", json={"color": "#3987e5"}).status_code == 200


def test_mudar_so_maiuscula_do_proprio_nome_passa(client):
    cat = criar(client, "mercado").json()["id"]
    assert client.patch(f"/categories/{cat}", json={"name": "Mercado"}).status_code == 200


# ---------- Tipo ----------


def test_trocar_tipo_de_categoria_sem_uso_e_permitido(client):
    cat = criar(client, "Cadastro errado").json()["id"]
    r = client.patch(f"/categories/{cat}", json={"type": "income"})
    assert r.status_code == 200
    assert r.json()["type"] == "income"


def test_trocar_tipo_com_lancamento_e_bloqueado(client):
    cat = criar(client).json()["id"]
    lancar(client, cat)

    r = client.patch(f"/categories/{cat}", json={"type": "income"})

    assert r.status_code == 409
    assert "lançamento" in r.json()["detail"]
    assert client.get(f"/categories/{cat}").json()["type"] == "expense"


def test_trocar_tipo_com_compra_no_cartao_e_bloqueado(client):
    cat = criar(client).json()["id"]
    card = client.post("/cards", json={"name": "Nubank", "closing_day": 25, "due_day": 2}).json()["id"]
    client.post("/purchases", json={
        "card_id": card, "category_id": cat, "description": "x",
        "total_amount": 100, "installments": 1, "purchase_date": "2026-09-10",
    })

    r = client.patch(f"/categories/{cat}", json={"type": "investment"})

    assert r.status_code == 409
    assert "compra" in r.json()["detail"]


def test_trocar_tipo_com_meta_e_bloqueado(client):
    cat = criar(client).json()["id"]
    client.put("/budgets", json={"category_id": cat, "year": 2026, "month": 9, "amount": 500})

    r = client.patch(f"/categories/{cat}", json={"type": "income"})

    assert r.status_code == 409
    assert "meta" in r.json()["detail"]


def test_mandar_o_mesmo_tipo_nao_e_troca(client):
    """A tela manda o formulário inteiro; o tipo igual não pode travar a edição."""
    cat = criar(client).json()["id"]
    lancar(client, cat)
    assert client.patch(f"/categories/{cat}", json={"type": "expense", "name": "Mercadinho"}).status_code == 200


def test_uso_vem_com_incluir_uso(client):
    cat = criar(client).json()["id"]
    lancar(client, cat)
    lancar(client, cat)
    client.put("/budgets", json={"category_id": cat, "year": 2026, "month": 9, "amount": 1})

    linha = client.get("/categories?incluir_uso=1").json()[0]

    assert (linha["transactions"], linha["purchases"], linha["budgets"]) == (2, 0, 1)
    # Sem o parâmetro, o formato de sempre.
    assert "transactions" not in client.get("/categories").json()[0]
