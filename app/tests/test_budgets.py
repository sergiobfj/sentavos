def criar_categoria(client, name="Mercado", type="expense"):
    return client.post(
        "/categories",
        json={"name": name, "type": type, "color": "#ef5350", "icon": "🛒"},
    ).json()


def definir_meta(client, category_id, amount, year=2026, month=7):
    return client.put(
        "/budgets",
        json={"category_id": category_id, "year": year, "month": month, "amount": amount},
    )


def lancar(client, category_id, date, planned=None, paid=None):
    return client.post(
        "/transactions",
        json={
            "date": date,
            "description": f"lançamento {date}",
            "category_id": category_id,
            "amount_planned": planned,
            "amount_paid": paid,
        },
    )


def test_put_cria_meta(client):
    cat = criar_categoria(client)

    r = definir_meta(client, cat["id"], 800)

    assert r.status_code == 200
    assert r.json()["amount"] == 800
    assert r.json()["category_id"] == cat["id"]


def test_put_sobrescreve_em_vez_de_duplicar(client):
    cat = criar_categoria(client)
    primeira = definir_meta(client, cat["id"], 800).json()
    segunda = definir_meta(client, cat["id"], 950).json()

    # Mesmo registro atualizado — se duplicasse, a soma do summary dobraria.
    assert segunda["id"] == primeira["id"]
    assert segunda["amount"] == 950
    assert len(client.get("/budgets").json()) == 1


def test_meta_e_por_mes(client):
    cat = criar_categoria(client)
    definir_meta(client, cat["id"], 800, month=7)
    definir_meta(client, cat["id"], 400, month=8)

    assert len(client.get("/budgets").json()) == 2
    assert [b["amount"] for b in client.get("/budgets", params={"year": 2026, "month": 8}).json()] == [400]


def test_meta_com_categoria_inexistente_da_400(client):
    assert definir_meta(client, 999, 100).status_code == 400


def test_mes_invalido_da_422(client):
    cat = criar_categoria(client)
    assert definir_meta(client, cat["id"], 100, month=13).status_code == 422


def test_summary_cruza_orcado_previsto_e_pago(client):
    cat = criar_categoria(client)
    definir_meta(client, cat["id"], 800)
    lancar(client, cat["id"], "2026-07-05", planned=300, paid=280)
    lancar(client, cat["id"], "2026-07-20", planned=200, paid=150)

    r = client.get("/budgets/summary", params={"year": 2026, "month": 7})

    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["budgeted"] == 800
    assert item["planned"] == 500
    assert item["paid"] == 430


def test_summary_ignora_lancamento_de_outro_mes(client):
    cat = criar_categoria(client)
    definir_meta(client, cat["id"], 800)
    lancar(client, cat["id"], "2026-06-30", paid=999)
    lancar(client, cat["id"], "2026-07-10", paid=100)
    lancar(client, cat["id"], "2026-08-01", paid=999)

    r = client.get("/budgets/summary", params={"year": 2026, "month": 7})

    assert r.json()["items"][0]["paid"] == 100


def test_summary_traz_categoria_sem_meta_e_sem_lancamento(client):
    criar_categoria(client, name="Lazer")

    r = client.get("/budgets/summary", params={"year": 2026, "month": 7})

    item = r.json()["items"][0]
    assert item["budget_id"] is None
    assert (item["budgeted"], item["planned"], item["paid"]) == (0, 0, 0)


def test_summary_soma_valor_nulo_como_zero(client):
    # amount_planned/amount_paid são opcionais; sum() de tudo nulo não pode virar None.
    cat = criar_categoria(client)
    lancar(client, cat["id"], "2026-07-10")

    item = client.get("/budgets/summary", params={"year": 2026, "month": 7}).json()["items"][0]

    assert (item["planned"], item["paid"]) == (0, 0)


def test_summary_agrupa_totais_por_tipo(client):
    despesa = criar_categoria(client, name="Mercado", type="expense")
    receita = criar_categoria(client, name="Salário", type="income")
    definir_meta(client, despesa["id"], 800)
    definir_meta(client, receita["id"], 5000)
    lancar(client, despesa["id"], "2026-07-10", paid=430)
    lancar(client, receita["id"], "2026-07-01", paid=5000)

    totals = client.get("/budgets/summary", params={"year": 2026, "month": 7}).json()["totals"]

    assert totals["expense"]["budgeted"] == 800
    assert totals["expense"]["paid"] == 430
    assert totals["income"]["paid"] == 5000
    # Tipo sem categoria nenhuma ainda aparece zerado.
    assert totals["investment"] == {"budgeted": 0, "planned": 0, "paid": 0}


def test_summary_de_dezembro_nao_estoura(client):
    cat = criar_categoria(client)
    lancar(client, cat["id"], "2026-12-15", paid=100)
    lancar(client, cat["id"], "2027-01-02", paid=999)

    r = client.get("/budgets/summary", params={"year": 2026, "month": 12})

    assert r.json()["items"][0]["paid"] == 100


def test_summary_exige_ano_e_mes(client):
    assert client.get("/budgets/summary").status_code == 422


def test_patch_altera_valor(client):
    cat = criar_categoria(client)
    meta = definir_meta(client, cat["id"], 800).json()

    r = client.patch(f"/budgets/{meta['id']}", json={"amount": 600})

    assert r.status_code == 200
    assert r.json()["amount"] == 600


def test_delete_remove_meta(client):
    cat = criar_categoria(client)
    meta = definir_meta(client, cat["id"], 800).json()

    assert client.delete(f"/budgets/{meta['id']}").status_code == 200
    assert client.get("/budgets").json() == []


def test_patch_e_delete_inexistentes_dao_404(client):
    assert client.patch("/budgets/999", json={"amount": 1}).status_code == 404
    assert client.delete("/budgets/999").status_code == 404


def test_excluir_categoria_leva_a_meta(client):
    # Meta é planejamento, sai junto. Precisa sair ANTES da categoria, senão a
    # FK barra o delete no Postgres (o SQLite só reclama com PRAGMA ligado).
    cat = criar_categoria(client)
    definir_meta(client, cat["id"], 800)

    assert client.delete(f"/categories/{cat['id']}").status_code == 200
    assert client.get("/budgets").json() == []


def test_excluir_categoria_com_lancamento_da_409(client):
    # Lançamento é histórico; apagar junto seria destruir dado sem o usuário pedir.
    cat = criar_categoria(client)
    lancar(client, cat["id"], "2026-07-10", paid=50)

    r = client.delete(f"/categories/{cat['id']}")

    assert r.status_code == 409
    assert "lançamento" in r.json()["detail"]
    # E a categoria continua lá.
    assert len(client.get("/categories").json()) == 1
