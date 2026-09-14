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


# ---------- Caixinhas ----------
# A diferença entre caixinha e teto mensal mora aqui: no teto, o que sobra
# evapora na virada do mês; na caixinha, continua lá.

def test_sobra_do_mes_anterior_entra_na_caixinha(client, session, dono):
    from app.models import Budget, Category, Transaction

    cat = Category(name="Lazer", type="expense", color="#f00", icon="L", user_id=dono.id)
    session.add(cat)
    session.commit()
    session.refresh(cat)

    # Agosto: separou 300, gastou 230. Sobraram 70.
    session.add(Budget(category_id=cat.id, year=2026, month=8, amount=300.0, user_id=dono.id))
    session.add(Transaction(date=dt.date(2026, 8, 10), description="Cinema",
                            amount_paid=230.0, category_id=cat.id, user_id=dono.id))
    # Setembro: separou 250.
    session.add(Budget(category_id=cat.id, year=2026, month=9, amount=250.0, user_id=dono.id))
    session.commit()

    resumo = client.get("/budgets/summary?year=2026&month=9").json()
    lazer = next(i for i in resumo["items"] if i["category_name"] == "Lazer")

    assert lazer["carried_in"] == 70.0
    # 70 que vieram + 250 separados − 0 gasto = 320 disponíveis.
    assert lazer["available"] == 320.0


def test_estourar_a_caixinha_deixa_divida_pro_mes_seguinte(client, session, dono):
    """Sobra negativa é mantida de propósito.

    Zerar o negativo faria estourar a caixinha sair de graça — e a pessoa
    começaria o mês seguinte achando que tem mais do que tem.
    """
    from app.models import Budget, Category, Transaction

    cat = Category(name="Mercado", type="expense", color="#f00", icon="M", user_id=dono.id)
    session.add(cat)
    session.commit()
    session.refresh(cat)

    session.add(Budget(category_id=cat.id, year=2026, month=8, amount=500.0, user_id=dono.id))
    session.add(Transaction(date=dt.date(2026, 8, 12), description="Compras",
                            amount_paid=620.0, category_id=cat.id, user_id=dono.id))
    session.commit()

    resumo = client.get("/budgets/summary?year=2026&month=9").json()
    mercado = next(i for i in resumo["items"] if i["category_name"] == "Mercado")

    assert mercado["carried_in"] == -120.0


def test_receita_nao_acumula_sobra(client, session, dono):
    """Receita é o que entra, não um pote de onde se tira.

    Acumular "sobra de salário" misturaria as duas ideias e faria o total de
    disponível não querer dizer nada.
    """
    from app.models import Budget, Category, Transaction

    cat = Category(name="Salário", type="income", color="#0f0", icon="S", user_id=dono.id)
    session.add(cat)
    session.commit()
    session.refresh(cat)

    session.add(Budget(category_id=cat.id, year=2026, month=8, amount=4000.0, user_id=dono.id))
    session.add(Transaction(date=dt.date(2026, 8, 5), description="Salário",
                            amount_paid=4200.0, category_id=cat.id, user_id=dono.id))
    session.commit()

    resumo = client.get("/budgets/summary?year=2026&month=9").json()
    salario = next(i for i in resumo["items"] if i["category_name"] == "Salário")

    assert salario["carried_in"] == 0.0
    assert salario["available"] == 0.0


def test_nao_distribuido_e_o_que_entrou_menos_o_que_foi_separado(client, session, dono):
    """O número que abre o ritual do salário."""
    from app.models import Budget, Category, Transaction

    receita = Category(name="Salário", type="income", color="#0f0", icon="S", user_id=dono.id)
    gasto = Category(name="Aluguel", type="expense", color="#f00", icon="A", user_id=dono.id)
    session.add_all([receita, gasto])
    session.commit()
    session.refresh(receita)
    session.refresh(gasto)

    session.add(Transaction(date=dt.date(2026, 9, 5), description="Salário",
                            amount_paid=4500.0, category_id=receita.id, user_id=dono.id))
    session.add(Budget(category_id=gasto.id, year=2026, month=9, amount=1450.0, user_id=dono.id))
    session.commit()

    resumo = client.get("/budgets/summary?year=2026&month=9").json()

    assert resumo["unallocated"] == 3050.0


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


def test_categoria_sem_meta_nenhuma_nao_vira_divida(client, session, dono):
    """O bug que apareceu em produção: -R$ 5.443 na Fatura.

    A conta tinha um ano de lançamentos importados da planilha e quase nenhuma
    meta. Somando todo o histórico de gasto contra todo o histórico de alocação,
    o ano inteiro virava "dívida da caixinha" — e a tela mostrava a Fatura
    devendo cinco mil pra si mesma.

    Uma caixinha passa a existir quando alguém põe dinheiro nela. Gasto anterior
    a isso é só gasto: não tem caixa contra a qual descontar.
    """
    from app.models import Category, Transaction

    cat = Category(name="Fatura", type="expense", color="#f00", icon="F", user_id=dono.id)
    session.add(cat)
    session.commit()
    session.refresh(cat)

    # Um ano de gastos, meta nenhuma — exatamente o caso dos dados importados.
    for mes in range(1, 9):
        session.add(Transaction(
            date=dt.date(2026, mes, 10), description="Fatura",
            amount_paid=680.0, category_id=cat.id, user_id=dono.id,
        ))
    session.commit()

    resumo = client.get("/budgets/summary?year=2026&month=9").json()
    fatura = next(i for i in resumo["items"] if i["category_name"] == "Fatura")

    assert fatura["carried_in"] == 0.0, "gasto sem caixinha virou dívida"
    assert fatura["has_envelope"] is False


def test_sobra_conta_so_a_partir_da_primeira_meta(client, session, dono):
    """A caixinha nasce na primeira alocação, não no primeiro gasto.

    Gasto de antes da caixinha existir não pode ser descontado dela: seria
    cobrar de um pote que ainda não tinha sido criado.
    """
    from app.models import Budget, Category, Transaction

    cat = Category(name="Mercado", type="expense", color="#f00", icon="M", user_id=dono.id)
    session.add(cat)
    session.commit()
    session.refresh(cat)

    # Junho e julho: gasto sem meta. Não deve entrar na conta da caixinha.
    for mes in (6, 7):
        session.add(Transaction(
            date=dt.date(2026, mes, 10), description="Compras",
            amount_paid=900.0, category_id=cat.id, user_id=dono.id,
        ))

    # Agosto: a caixinha nasce, com 800 separados e 700 gastos. Sobram 100.
    session.add(Budget(category_id=cat.id, year=2026, month=8, amount=800.0, user_id=dono.id))
    session.add(Transaction(
        date=dt.date(2026, 8, 10), description="Compras",
        amount_paid=700.0, category_id=cat.id, user_id=dono.id,
    ))
    session.commit()

    resumo = client.get("/budgets/summary?year=2026&month=9").json()
    mercado = next(i for i in resumo["items"] if i["category_name"] == "Mercado")

    assert mercado["carried_in"] == 100.0, "os 1.800 de antes da caixinha entraram na conta"
    assert mercado["has_envelope"] is True


def test_disponivel_nao_fica_negativo_sem_caixinha(client, session, dono):
    """Sem caixinha não existe "disponível" — nem zero, nem negativo."""
    from app.models import Category, Transaction

    cat = Category(name="Uber", type="expense", color="#f00", icon="U", user_id=dono.id)
    session.add(cat)
    session.commit()
    session.refresh(cat)

    session.add(Transaction(
        date=dt.date(2026, 9, 3), description="Corrida",
        amount_paid=45.0, category_id=cat.id, user_id=dono.id,
    ))
    session.commit()

    resumo = client.get("/budgets/summary?year=2026&month=9").json()
    uber = next(i for i in resumo["items"] if i["category_name"] == "Uber")

    assert uber["has_envelope"] is False
    assert uber["available"] == 0.0
    assert uber["paid"] == 45.0


def test_caixinha_nao_existe_antes_do_mes_em_que_nasceu(client, session, dono):
    """Olhar agosto de uma caixinha criada em setembro.

    O gasto de agosto aparecia como "disponível negativo" — descontado de um
    pote que naquele mês ainda não existia. Apareceu na tela com a Academia
    marcando −R$ 120 em agosto, com a meta cadastrada só em setembro.
    """
    from app.models import Budget, Category, Transaction

    cat = Category(name="Academia", type="expense", color="#f00", icon="A", user_id=dono.id)
    session.add(cat)
    session.commit()
    session.refresh(cat)

    session.add(Transaction(
        date=dt.date(2026, 8, 17), description="Mensalidade",
        amount_paid=120.0, category_id=cat.id, user_id=dono.id,
    ))
    # A caixinha só nasce em setembro.
    session.add(Budget(category_id=cat.id, year=2026, month=9, amount=130.0, user_id=dono.id))
    session.commit()

    agosto = client.get("/budgets/summary?year=2026&month=8").json()
    item = next(i for i in agosto["items"] if i["category_name"] == "Academia")

    assert item["has_envelope"] is False, "caixinha existia antes de nascer"
    assert item["available"] == 0.0
    assert item["paid"] == 120.0

    # Em setembro ela já é caixinha.
    setembro = client.get("/budgets/summary?year=2026&month=9").json()
    item = next(i for i in setembro["items"] if i["category_name"] == "Academia")
    assert item["has_envelope"] is True


def test_meta_de_zero_nao_cria_caixinha(client, session, dono):
    """Separar nada não é separar.

    Tocar no campo de meta e sair dele salva um zero. Sem esta guarda, a
    categoria virava caixinha por acidente e passava a mostrar "disponível"
    negativo — foi o que aconteceu com Academia e Internet em produção.
    """
    from app.models import Budget, Category, Transaction

    cat = Category(name="Internet", type="expense", color="#f00", icon="I", user_id=dono.id)
    session.add(cat)
    session.commit()
    session.refresh(cat)

    session.add(Budget(category_id=cat.id, year=2026, month=9, amount=0.0, user_id=dono.id))
    session.add(Transaction(
        date=dt.date(2026, 9, 5), description="Internet",
        amount_paid=60.0, category_id=cat.id, user_id=dono.id,
    ))
    session.commit()

    resumo = client.get("/budgets/summary?year=2026&month=9").json()
    item = next(i for i in resumo["items"] if i["category_name"] == "Internet")

    assert item["has_envelope"] is False
    assert item["available"] == 0.0
