import datetime as dt

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


# ---------- Arquivamento ----------

def test_categoria_arquivada_sai_da_listagem_mas_nao_do_banco(client, session, dono):
    from app.models import Category

    ativa = Category(name="Mercado", type="expense", color="#f00", icon="M", user_id=dono.id)
    velha = Category(name="SECCO", type="expense", color="#f00", icon="S",
                     user_id=dono.id, archived=True)
    session.add_all([ativa, velha])
    session.commit()

    nomes = [c["name"] for c in client.get("/categories").json()]
    assert nomes == ["Mercado"]

    todas = [c["name"] for c in client.get("/categories?incluir_arquivadas=1").json()]
    assert sorted(todas) == ["Mercado", "SECCO"]


# ---------- Teto mensal, sem acúmulo ----------
# Existiu aqui uma bateria de testes de caixinha: sobra do mês anterior,
# dívida herdada, mês de nascimento da caixinha. Ela protegia um cálculo que
# somava todo o histórico de metas e gastos — e cujo resultado ninguém
# conseguia conferir de cabeça. Os testes abaixo travam o contrário: cada mês
# se explica sozinho.

def test_mes_nao_herda_sobra_do_anterior(client):
    """Sobrar em julho não aumenta o teto de agosto."""
    cat = criar_categoria(client, "Lazer")
    definir_meta(client, cat["id"], 250, year=2026, month=7)
    lancar(client, cat["id"], "2026-07-10", paid=180)  # sobraram 70

    definir_meta(client, cat["id"], 250, year=2026, month=8)
    lancar(client, cat["id"], "2026-08-05", paid=200)

    agosto = client.get("/budgets/summary?year=2026&month=8").json()
    lazer = next(i for i in agosto["items"] if i["category_name"] == "Lazer")

    assert lazer["budgeted"] == 250.0, "o teto de agosto é o de agosto"
    assert lazer["paid"] == 200.0
    # E os 70 que sobraram em julho não aparecem em campo nenhum.
    assert "carried_in" not in lazer
    assert "available" not in lazer
    assert "has_envelope" not in lazer


def test_estourar_um_mes_nao_deixa_divida_no_seguinte(client):
    """O bug da Fatura com −R$ 5.443, agora impossível por construção."""
    cat = criar_categoria(client, "Fatura")
    definir_meta(client, cat["id"], 100, year=2026, month=7)
    lancar(client, cat["id"], "2026-07-10", paid=5000)

    agosto = client.get("/budgets/summary?year=2026&month=8").json()
    fatura = next(i for i in agosto["items"] if i["category_name"] == "Fatura")

    assert fatura["paid"] == 0.0, "o estouro de julho não persegue agosto"
    assert fatura["budgeted"] == 0.0


def test_gasto_sem_meta_aparece_sem_teto(client):
    """Categoria sem meta não é categoria proibida — só não tem régua."""
    cat = criar_categoria(client, "Uber")
    lancar(client, cat["id"], "2026-07-10", paid=42)

    resumo = client.get("/budgets/summary?year=2026&month=7").json()
    uber = next(i for i in resumo["items"] if i["category_name"] == "Uber")

    assert uber["paid"] == 42.0
    assert uber["budgeted"] == 0.0
    assert uber["budget_id"] is None


def test_summary_nao_devolve_mais_unallocated(client):
    criar_categoria(client)
    resumo = client.get("/budgets/summary?year=2026&month=7").json()
    assert "unallocated" not in resumo


# ---------- Fundir categoria ----------
# "Apagar Uber" não é o que se quer; o que se quer é "Uber virou Transporte".

def test_mover_para_transfere_os_lancamentos_e_apaga_a_categoria(client):
    uber = criar_categoria(client, "UBER")
    transporte = criar_categoria(client, "Transporte")
    lancar(client, uber["id"], "2026-07-10", paid=30)
    lancar(client, uber["id"], "2026-07-12", paid=12)

    r = client.delete(f"/categories/{uber['id']}?mover_para={transporte['id']}")

    assert r.status_code == 200
    assert r.json()["moved"] == 2
    assert [c["name"] for c in client.get("/categories").json()] == ["Transporte"]

    # E o dinheiro chegou inteiro do outro lado.
    resumo = client.get("/budgets/summary?year=2026&month=7").json()
    linha = next(i for i in resumo["items"] if i["category_name"] == "Transporte")
    assert linha["paid"] == 42.0


def test_mover_para_tipo_diferente_da_400(client):
    """Mover despesa pra receita trocaria o sinal e faria o mês mentir."""
    gasto = criar_categoria(client, "Mercado", type="expense")
    entrada = criar_categoria(client, "Salário", type="income")
    lancar(client, gasto["id"], "2026-07-10", paid=300)

    r = client.delete(f"/categories/{gasto['id']}?mover_para={entrada['id']}")

    assert r.status_code == 400
    assert "sinal" in r.json()["detail"]
    # Nada se move quando a resposta é recusa.
    assert len(client.get("/categories").json()) == 2
    resumo = client.get("/budgets/summary?year=2026&month=7").json()
    assert next(i for i in resumo["items"] if i["category_name"] == "Mercado")["paid"] == 300.0


def test_mover_para_ela_mesma_da_400(client):
    cat = criar_categoria(client)
    lancar(client, cat["id"], "2026-07-10", paid=10)

    r = client.delete(f"/categories/{cat['id']}?mover_para={cat['id']}")

    assert r.status_code == 400
    assert len(client.get("/categories").json()) == 1


def test_mover_para_categoria_inexistente_da_404(client):
    cat = criar_categoria(client)
    lancar(client, cat["id"], "2026-07-10", paid=10)

    assert client.delete(f"/categories/{cat['id']}?mover_para=9999").status_code == 404
    assert len(client.get("/categories").json()) == 1
