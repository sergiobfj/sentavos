def criar_categoria(client):
    return client.post(
        "/categories",
        json={"name": "Mercado", "type": "expense", "color": "#ef5350", "icon": "🛒"},
    ).json()


def criar_transacao(client, category_id, date):
    return client.post(
        "/transactions",
        json={
            "date": date,
            "description": f"compra {date}",
            "category_id": category_id,
            "amount_paid": 10,
        },
    )


def test_filtra_transacoes_por_mes(client):
    cat = criar_categoria(client)
    # 30/06 e 01/08 são as datas que importam: provam que as bordas do
    # intervalo estão certas, o que um teste só com datas do meio do mês não pega.
    for date in ["2026-06-30", "2026-07-01", "2026-07-31", "2026-08-01"]:
        criar_transacao(client, cat["id"], date)

    r = client.get("/transactions", params={"year": 2026, "month": 7})

    assert r.status_code == 200
    assert [t["date"] for t in r.json()] == ["2026-07-31", "2026-07-01"]


def test_dezembro_nao_estoura(client):
    cat = criar_categoria(client)
    criar_transacao(client, cat["id"], "2026-12-15")
    criar_transacao(client, cat["id"], "2027-01-02")

    r = client.get("/transactions", params={"year": 2026, "month": 12})

    assert r.status_code == 200
    assert [t["date"] for t in r.json()] == ["2026-12-15"]


def test_filtra_por_ano_inteiro(client):
    cat = criar_categoria(client)
    for date in ["2025-12-31", "2026-03-10", "2026-11-20", "2027-01-01"]:
        criar_transacao(client, cat["id"], date)

    r = client.get("/transactions", params={"year": 2026})

    assert [t["date"] for t in r.json()] == ["2026-11-20", "2026-03-10"]


def test_sem_periodo_devolve_tudo(client):
    cat = criar_categoria(client)
    criar_transacao(client, cat["id"], "2025-01-01")
    criar_transacao(client, cat["id"], "2026-07-10")

    r = client.get("/transactions")

    assert len(r.json()) == 2


def test_mes_sem_ano_da_400(client):
    assert client.get("/transactions", params={"month": 7}).status_code == 400


def test_mes_invalido_da_422(client):
    assert client.get("/transactions", params={"year": 2026, "month": 13}).status_code == 422


def test_ordena_por_data_desc(client):
    cat = criar_categoria(client)
    for date in ["2026-07-05", "2026-07-20", "2026-07-01"]:
        criar_transacao(client, cat["id"], date)

    r = client.get("/transactions", params={"year": 2026, "month": 7})

    assert [t["date"] for t in r.json()] == ["2026-07-20", "2026-07-05", "2026-07-01"]
