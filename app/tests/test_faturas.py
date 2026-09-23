"""Gasto, caixa e fatura pela API — os cenários que o dono confere na mão.

O que este arquivo protege é uma frase só: **compra no cartão é gasto agora e
saída de caixa depois**. Cada teste aqui é uma forma de essa frase deixar de
valer, e todos falhariam contra a versão do app que não tinha cartão.

As datas de competência são fixas (setembro/2026) porque não dependem de hoje.
As de status são relativas a `dt.date.today()`: "atrasada" é a única resposta
que muda com o calendário, e um teste com data fixa envelheceria sozinho.
"""

import datetime as dt

import pytest

HOJE = dt.date.today()


# ---------- Montagem ----------


@pytest.fixture(name="categoria")
def categoria_fixture(client):
    def criar(nome: str, tipo: str = "expense") -> int:
        r = client.post(
            "/categories",
            json={"name": nome, "type": tipo, "color": "#f5b301", "icon": "x"},
        )
        assert r.status_code == 200, r.text
        return r.json()["id"]

    return criar


@pytest.fixture(name="cartao")
def cartao_fixture(client):
    def criar(nome: str = "Nubank", fecha: int = 25, vence: int = 2) -> int:
        r = client.post(
            "/cards", json={"name": nome, "closing_day": fecha, "due_day": vence}
        )
        assert r.status_code == 200, r.text
        return r.json()["id"]

    return criar


@pytest.fixture(name="comprar")
def comprar_fixture(client):
    def criar(cartao_id, categoria_id, valor, data, parcelas=1, descricao="Compra"):
        r = client.post(
            "/purchases",
            json={
                "card_id": cartao_id,
                "category_id": categoria_id,
                "description": descricao,
                "total_amount": valor,
                "installments": parcelas,
                "purchase_date": data.isoformat(),
            },
        )
        assert r.status_code == 200, r.text
        return r.json()

    return criar


@pytest.fixture(name="lancar")
def lancar_fixture(client):
    def criar(categoria_id, valor, data, descricao="Lançamento", forma="cash"):
        corpo = {
            "date": data.isoformat(),
            "description": descricao,
            "amount_paid": valor,
            "category_id": categoria_id,
        }
        if forma is not None:
            corpo["payment_method"] = forma
        r = client.post("/transactions", json=corpo)
        assert r.status_code == 200, r.text
        return r.json()

    return criar


def caixa_de(client, ano=2026, mes=9):
    r = client.get(f"/budgets/summary?year={ano}&month={mes}")
    assert r.status_code == 200, r.text
    return r.json()


# ---------- O cenário que o dono pediu pra conferir na mão ----------


def test_cenario_completo_de_ponta_a_ponta(client, categoria, cartao, comprar, lancar):
    """Entrou 2.000, à vista 200, cartão 600, e os dois pagamentos da fatura.

    É o cenário do enunciado, conferido passo a passo. Cada asserção aqui é um
    número que o dono consegue refazer de cabeça olhando a tela.
    """
    salario = categoria("Salário", "income")
    alimentacao = categoria("Alimentação")
    nubank = cartao()

    lancar(salario, 2000.0, dt.date(2026, 9, 5), "Salário")
    lancar(alimentacao, 200.0, dt.date(2026, 9, 10), "Mercado")
    compra = comprar(nubank, alimentacao, 600.0, dt.date(2026, 9, 12), descricao="Restaurante")

    # --- Antes de pagar a fatura ---
    c = caixa_de(client)["caixa"]
    assert c["entrou"] == 2000.0
    assert c["saiu_a_vista"] == 200.0
    # A Carteira reflete SÓ a saída à vista: os 600 do cartão não saíram.
    assert c["carteira"] == 1800.0
    # O gasto do mês são os dois: 200 à vista + 600 no cartão.
    assert c["gasto_total"] == 800.0
    assert c["no_cartao"] == 600.0
    assert c["faturas_em_aberto"] == 600.0
    assert c["apos_faturas"] == 1200.0

    faturas = client.get("/invoices/summary?year=2026&month=9").json()
    fatura_id = faturas["cards"][0]["next"]["id"]  # fecha 25/09, vence 02/10
    assert faturas["cards"][0]["next"]["total"] == 600.0

    # --- Pagamento parcial de 400 ---
    r = client.post(
        f"/invoices/{fatura_id}/payments",
        json={"amount": 400.0, "date": "2026-09-20"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "parcial"
    assert r.json()["remaining"] == 200.0

    c = caixa_de(client)["caixa"]
    assert c["carteira"] == 1400.0  # reduziu mais 400
    assert c["gasto_total"] == 800.0  # o gasto NÃO mudou
    assert c["faturas_pagas"] == 400.0

    # --- Pagamento dos 200 restantes ---
    r = client.post(
        f"/invoices/{fatura_id}/payments",
        json={"amount": 200.0, "date": "2026-09-22"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "paga"
    assert r.json()["remaining"] == 0.0

    c = caixa_de(client)["caixa"]
    assert c["carteira"] == 1200.0
    assert c["gasto_total"] == 800.0  # continua 800, pela terceira vez
    assert c["faturas_em_aberto"] == 0.0

    # E a categoria recebeu os 800 uma vez só, não 1.400.
    resumo = caixa_de(client)
    linha = next(i for i in resumo["items"] if i["category_id"] == alimentacao)
    assert linha["paid"] == 800.0


def test_pagar_a_fatura_no_mes_seguinte_tira_o_dinheiro_daquele_mes(
    client, categoria, cartao, comprar
):
    """A saída de caixa acontece no mês do pagamento, não no da compra."""
    alimentacao = categoria("Alimentação")
    nubank = cartao()
    comprar(nubank, alimentacao, 300.0, dt.date(2026, 9, 12))

    fatura = client.get("/invoices/summary?year=2026&month=10").json()["cards"][0]["current"]
    assert fatura["due_date"] == "2026-10-02"

    client.post(
        f"/invoices/{fatura['id']}/payments", json={"amount": 300.0, "date": "2026-10-02"}
    )

    setembro = caixa_de(client, 2026, 9)["caixa"]
    outubro = caixa_de(client, 2026, 10)["caixa"]

    # Setembro: o gasto aconteceu, o dinheiro não saiu.
    assert setembro["gasto_total"] == 300.0
    assert setembro["carteira"] == 0.0
    # Outubro: o dinheiro saiu, e nenhum gasto novo foi criado.
    assert outubro["gasto_total"] == 0.0
    assert outubro["carteira"] == -300.0
    assert outubro["faturas_pagas"] == 300.0


# ---------- À vista continua como era ----------


def test_a_vista_reduz_a_carteira_e_o_gasto_juntos(client, categoria, lancar):
    alimentacao = categoria("Alimentação")
    lancar(alimentacao, 40.0, dt.date(2026, 9, 3), "Padaria")

    c = caixa_de(client)["caixa"]
    assert c["saiu_a_vista"] == 40.0
    assert c["gasto_total"] == 40.0
    assert c["carteira"] == -40.0
    assert c["no_cartao"] == 0.0
    assert c["faturas_em_aberto"] == 0.0


# ---------- Parcelamento ----------


def test_compra_em_1x_conta_inteira_no_mes_da_compra(client, categoria, cartao, comprar):
    compras = categoria("Compras")
    nubank = cartao()
    comprar(nubank, compras, 1200.0, dt.date(2026, 9, 23), descricao="Notebook")

    assert caixa_de(client, 2026, 9)["caixa"]["gasto_total"] == 1200.0
    assert caixa_de(client, 2026, 10)["caixa"]["gasto_total"] == 0.0


def test_compra_em_3x_espalha_o_gasto_por_tres_meses(client, categoria, cartao, comprar):
    """R$ 900 em 3x em setembro: 300 em set, 300 em out, 300 em nov."""
    compras = categoria("Compras")
    nubank = cartao()
    comprar(nubank, compras, 900.0, dt.date(2026, 9, 12), parcelas=3, descricao="Sofá")

    assert caixa_de(client, 2026, 9)["caixa"]["gasto_total"] == 300.0
    assert caixa_de(client, 2026, 10)["caixa"]["gasto_total"] == 300.0
    assert caixa_de(client, 2026, 11)["caixa"]["gasto_total"] == 300.0
    assert caixa_de(client, 2026, 12)["caixa"]["gasto_total"] == 0.0

    # Nenhum desses meses teve saída de caixa: nada foi pago ainda.
    for mes in (9, 10, 11):
        assert caixa_de(client, 2026, mes)["caixa"]["carteira"] == 0.0


def test_parcelas_caem_em_faturas_seguidas(client, categoria, cartao, comprar):
    compras = categoria("Compras")
    nubank = cartao()
    comprar(nubank, compras, 900.0, dt.date(2026, 9, 12), parcelas=3)

    refs = []
    for mes in (10, 11, 12):
        resumo = client.get(f"/invoices/summary?year=2026&month={mes}").json()
        atual = resumo["cards"][0]["current"]
        refs.append((atual["year"], atual["month"], atual["total"]))

    assert refs == [(2026, 10, 300.0), (2026, 11, 300.0), (2026, 12, 300.0)]


def test_parcelamento_atravessando_o_ano(client, categoria, cartao, comprar):
    compras = categoria("Compras")
    nubank = cartao()
    comprar(nubank, compras, 900.0, dt.date(2026, 11, 15), parcelas=3)

    assert caixa_de(client, 2026, 11)["caixa"]["gasto_total"] == 300.0
    assert caixa_de(client, 2026, 12)["caixa"]["gasto_total"] == 300.0
    assert caixa_de(client, 2027, 1)["caixa"]["gasto_total"] == 300.0

    fatura_de_fevereiro = client.get("/invoices/summary?year=2027&month=2").json()
    assert fatura_de_fevereiro["cards"][0]["current"]["total"] == 300.0


def test_centavos_da_compra_parcelada_somam_o_total(client, categoria, cartao, comprar):
    """R$ 100 em 3x: 33,34 + 33,33 + 33,33, e a fatura de cada mês confere."""
    compras = categoria("Compras")
    nubank = cartao()
    compra = comprar(nubank, compras, 100.0, dt.date(2026, 9, 12), parcelas=3)

    assert compra["installment_amounts"] == [33.34, 33.33, 33.33]

    mensais = [caixa_de(client, 2026, m)["caixa"]["gasto_total"] for m in (9, 10, 11)]
    assert mensais == [33.34, 33.33, 33.33]
    assert round(sum(mensais), 2) == 100.00


# ---------- O ciclo do cartão pela API ----------


@pytest.mark.parametrize(
    "dia_da_compra,mes_da_fatura",
    [
        (24, 10),  # antes do fechamento
        (25, 10),  # NO dia do fechamento — ainda entra nesta
        (26, 11),  # depois — vai pra próxima
    ],
)
def test_fechamento_decide_a_fatura_mas_nao_a_competencia(
    client, categoria, cartao, comprar, dia_da_compra, mes_da_fatura
):
    """Os três casos de corte, e o que NÃO muda entre eles.

    A fatura muda conforme o dia da compra. O mês do gasto, não: as três
    compras são de setembro, porque foi em setembro que aconteceram.
    """
    compras = categoria("Compras")
    nubank = cartao()
    comprar(nubank, compras, 100.0, dt.date(2026, 9, dia_da_compra))

    assert caixa_de(client, 2026, 9)["caixa"]["gasto_total"] == 100.0

    resumo = client.get(f"/invoices/summary?year=2026&month={mes_da_fatura}").json()
    assert resumo["cards"][0]["current"]["total"] == 100.0


def test_uma_fatura_junta_varias_compras(client, categoria, cartao, comprar):
    alimentacao = categoria("Alimentação")
    compras = categoria("Compras")
    nubank = cartao()

    comprar(nubank, alimentacao, 89.90, dt.date(2026, 9, 10), descricao="Pizza")
    comprar(nubank, compras, 200.0, dt.date(2026, 9, 15), descricao="Amazon")
    comprar(nubank, alimentacao, 53.90, dt.date(2026, 9, 20), descricao="Jantar")

    fatura = client.get("/invoices/summary?year=2026&month=10").json()["cards"][0]["current"]
    assert fatura["total"] == 343.80
    assert fatura["item_count"] == 3

    detalhe = client.get(f"/invoices/{fatura['id']}").json()
    assert {i["description"] for i in detalhe["items"]} == {"Pizza", "Amazon", "Jantar"}


def test_cartoes_diferentes_nao_se_misturam(client, categoria, cartao, comprar):
    compras = categoria("Compras")
    nubank = cartao("Nubank", 25, 2)
    itau = cartao("Itaú", 5, 15)

    comprar(nubank, compras, 100.0, dt.date(2026, 9, 10), descricao="No Nubank")
    comprar(itau, compras, 250.0, dt.date(2026, 9, 3), descricao="No Itaú")

    # O Itaú fecha 05/09 e vence 15/09: a fatura dele é de SETEMBRO.
    setembro = client.get("/invoices/summary?year=2026&month=9").json()
    por_nome = {c["name"]: c for c in setembro["cards"]}
    assert por_nome["Itaú"]["current"]["total"] == 250.0
    assert por_nome["Nubank"]["current"] is None
    assert por_nome["Nubank"]["next"]["total"] == 100.0


# ---------- Status ----------


def test_fatura_vencida_com_saldo_fica_atrasada(client, categoria, cartao, comprar):
    compras = categoria("Compras")
    nubank = cartao()
    # Quatro meses atrás: a fatura já venceu e não foi paga.
    antiga = HOJE - dt.timedelta(days=120)
    comprar(nubank, compras, 500.0, antiga)

    faturas = client.get("/invoices").json()
    assert faturas[0]["status"] == "atrasada"


def test_fatura_do_mes_que_vem_fica_aberta(client, categoria, cartao, comprar):
    compras = categoria("Compras")
    nubank = cartao()
    comprar(nubank, compras, 500.0, HOJE)

    faturas = client.get("/invoices").json()
    assert faturas[0]["status"] in {"aberta", "atrasada"}
    # Compra de hoje: a fatura dela ainda não venceu.
    assert faturas[0]["status"] == "aberta"


def test_fatura_vencida_e_paga_fica_paga(client, categoria, cartao, comprar):
    """Paga vence atrasada na precedência: não há o que cobrar."""
    compras = categoria("Compras")
    nubank = cartao()
    antiga = HOJE - dt.timedelta(days=120)
    comprar(nubank, compras, 500.0, antiga)

    fatura = client.get("/invoices").json()[0]
    client.post(
        f"/invoices/{fatura['id']}/payments",
        json={"amount": 500.0, "date": fatura["due_date"]},
    )

    assert client.get(f"/invoices/{fatura['id']}").json()["status"] == "paga"


def test_pagamento_maior_que_o_restante_e_recusado(client, categoria, cartao, comprar):
    compras = categoria("Compras")
    nubank = cartao()
    comprar(nubank, compras, 100.0, dt.date(2026, 9, 10))
    fatura = client.get("/invoices").json()[0]

    r = client.post(
        f"/invoices/{fatura['id']}/payments", json={"amount": 1000.0, "date": "2026-10-02"}
    )
    assert r.status_code == 400
    assert "a pagar" in r.json()["detail"]


def test_desfazer_pagamento_devolve_o_dinheiro_pra_carteira(
    client, categoria, cartao, comprar
):
    compras = categoria("Compras")
    nubank = cartao()
    comprar(nubank, compras, 100.0, dt.date(2026, 9, 10))
    fatura = client.get("/invoices").json()[0]

    client.post(f"/invoices/{fatura['id']}/payments", json={"amount": 100.0, "date": "2026-09-30"})
    assert caixa_de(client)["caixa"]["carteira"] == -100.0

    pagamento = client.get(f"/invoices/{fatura['id']}").json()["payments"][0]
    assert client.delete(f"/invoice_payments/{pagamento['id']}").status_code == 200

    assert caixa_de(client)["caixa"]["carteira"] == 0.0
    assert client.get(f"/invoices/{fatura['id']}").json()["status"] == "aberta"


# ---------- Metas ----------


def test_meta_mede_gasto_e_enxerga_o_cartao(client, categoria, cartao, comprar, lancar):
    """O exemplo do enunciado: meta 600, PIX 200, cartão 250 → 450 de 600.

    Não importa que os 250 ainda não tenham sido pagos: meta mede o que foi
    consumido, e a comida do cartão foi comida.
    """
    alimentacao = categoria("Alimentação")
    nubank = cartao()

    client.put(
        "/budgets",
        json={"category_id": alimentacao, "year": 2026, "month": 9, "amount": 600.0},
    )
    lancar(alimentacao, 200.0, dt.date(2026, 9, 5), "Mercado")
    comprar(nubank, alimentacao, 250.0, dt.date(2026, 9, 12), descricao="Restaurante")

    linha = next(
        i for i in caixa_de(client)["items"] if i["category_id"] == alimentacao
    )
    assert linha["budgeted"] == 600.0
    assert linha["paid"] == 450.0


# ---------- Lançamentos antigos, sem forma de pagamento ----------


def test_lancamento_sem_forma_conta_como_saida_de_caixa(client, categoria, lancar):
    """O histórico anterior ao cartão continua valendo exatamente o que valia.

    É a regra de transição: nulo não é "à vista", é "ainda não sei" — mas a
    Carteira o conta como saída, porque é assim que ele já era contado. Mudar
    isso faria o número de todo mês passado trocar de valor da noite pro dia.
    """
    alimentacao = categoria("Alimentação")
    lancar(alimentacao, 150.0, dt.date(2026, 9, 8), "Antigo", forma=None)

    c = caixa_de(client)["caixa"]
    assert c["carteira"] == -150.0
    assert c["gasto_total"] == 150.0
    assert c["saiu_a_vista"] == 150.0
    # E a tela sabe que existe pergunta sem resposta aqui.
    assert c["sem_forma_definida"] == 150.0
    assert c["sem_forma_definida_qtd"] == 1


def test_classificar_como_a_vista_nao_muda_numero_nenhum(client, categoria, lancar):
    """Responder "foi à vista" confirma o que já estava sendo contado."""
    alimentacao = categoria("Alimentação")
    t = lancar(alimentacao, 150.0, dt.date(2026, 9, 8), "Antigo", forma=None)

    antes = caixa_de(client)["caixa"]
    r = client.post(f"/transactions/{t['id']}/forma-de-pagamento", json={"metodo": "cash"})
    assert r.status_code == 200
    depois = caixa_de(client)["caixa"]

    assert depois["carteira"] == antes["carteira"]
    assert depois["gasto_total"] == antes["gasto_total"]
    # O que muda é só a pergunta em aberto.
    assert antes["sem_forma_definida_qtd"] == 1
    assert depois["sem_forma_definida_qtd"] == 0


def test_classificar_como_cartao_tira_o_dinheiro_da_carteira(
    client, categoria, cartao, lancar
):
    """E aqui o número MUDA, que é o ponto: era à vista e não era."""
    alimentacao = categoria("Alimentação")
    nubank = cartao()
    t = lancar(alimentacao, 150.0, dt.date(2026, 9, 8), "Era cartão", forma=None)

    r = client.post(
        f"/transactions/{t['id']}/forma-de-pagamento",
        json={"metodo": "credit", "card_id": nubank},
    )
    assert r.status_code == 200, r.text

    c = caixa_de(client)["caixa"]
    assert c["carteira"] == 0.0  # o dinheiro não saiu
    assert c["gasto_total"] == 150.0  # mas o gasto continua
    assert c["no_cartao"] == 150.0
    assert c["faturas_em_aberto"] == 150.0


def test_classificar_em_cartao_parcelado(client, categoria, cartao, lancar):
    alimentacao = categoria("Compras")
    nubank = cartao()
    t = lancar(alimentacao, 300.0, dt.date(2026, 9, 8), "Parcelei", forma=None)

    r = client.post(
        f"/transactions/{t['id']}/forma-de-pagamento",
        json={"metodo": "credit", "card_id": nubank, "installments": 3},
    )
    assert r.status_code == 200, r.text

    assert caixa_de(client, 2026, 9)["caixa"]["gasto_total"] == 100.0
    assert caixa_de(client, 2026, 10)["caixa"]["gasto_total"] == 100.0
    assert caixa_de(client, 2026, 11)["caixa"]["gasto_total"] == 100.0


def test_classificar_em_lote(client, categoria, lancar):
    alimentacao = categoria("Alimentação")
    ids = [
        lancar(alimentacao, v, dt.date(2026, 9, d), n, forma=None)["id"]
        for v, d, n in [(89.9, 3, "Pizza"), (100.0, 5, "Academia"), (23.5, 7, "Uber")]
    ]

    r = client.post(
        "/transactions/forma-de-pagamento", json={"ids": ids, "metodo": "cash"}
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"atualizados": 3, "ignorados": []}
    assert caixa_de(client)["caixa"]["sem_forma_definida_qtd"] == 0


def test_lote_explica_o_que_nao_deu(client, categoria, cartao, comprar, lancar):
    """Parcela não se reclassifica: ela já é de uma compra."""
    compras = categoria("Compras")
    nubank = cartao()
    comprar(nubank, compras, 300.0, dt.date(2026, 9, 12), parcelas=3)
    parcela = client.get("/transactions?year=2026&month=9").json()[0]

    r = client.post(
        "/transactions/forma-de-pagamento",
        json={"ids": [parcela["id"]], "metodo": "cash"},
    )
    assert r.json()["atualizados"] == 0
    assert "parcela" in r.json()["ignorados"][0]["motivo"]


# ---------- Reconciliar o jeito antigo de lançar fatura ----------


def test_reconciliar_transforma_a_despesa_antiga_em_pagamento(
    client, categoria, cartao, comprar, lancar
):
    """O mês reconstruído não pode contar o mesmo dinheiro duas vezes.

    Antes do cartão, a fatura era UMA despesa numa categoria "Fatura do cartão".
    Reconstruído o mês com as compras individuais, esse lançamento passaria a
    somar de novo — no gasto E na saída de caixa. A reconciliação o transforma
    no que ele sempre foi: o pagamento da fatura.
    """
    alimentacao = categoria("Alimentação")
    fatura_antiga = categoria("Fatura do cartão")
    nubank = cartao()

    # O jeito antigo: uma linha só, com o total da fatura.
    antigo = lancar(fatura_antiga, 300.0, dt.date(2026, 10, 2), "FATURA", forma=None)

    # O jeito novo: as compras que formaram essa fatura.
    comprar(nubank, alimentacao, 200.0, dt.date(2026, 9, 10), descricao="Pizza")
    comprar(nubank, alimentacao, 100.0, dt.date(2026, 9, 15), descricao="Jantar")

    fatura = client.get("/invoices/summary?year=2026&month=10").json()["cards"][0]["current"]

    # Antes de reconciliar, outubro tem a contagem dupla: a despesa antiga.
    assert caixa_de(client, 2026, 10)["caixa"]["gasto_total"] == 300.0

    r = client.post(
        f"/invoices/{fatura['id']}/reconciliar", json={"transaction_id": antigo["id"]}
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "paga"

    setembro = caixa_de(client, 2026, 9)["caixa"]
    outubro = caixa_de(client, 2026, 10)["caixa"]

    # 1. As compras contam uma vez só, em setembro.
    assert setembro["gasto_total"] == 300.0
    linha = next(
        i for i in caixa_de(client, 2026, 9)["items"] if i["category_id"] == alimentacao
    )
    assert linha["paid"] == 300.0

    # 2. O lançamento antigo não soma mais como gasto em outubro.
    assert outubro["gasto_total"] == 0.0

    # 3 e 4. O dinheiro sai uma vez só, em outubro, como pagamento de fatura.
    assert outubro["faturas_pagas"] == 300.0
    assert outubro["carteira"] == -300.0
    assert setembro["carteira"] == 0.0

    # E o rastro de onde veio fica guardado.
    detalhe = client.get(f"/invoices/{fatura['id']}").json()
    assert "FATURA" in detalhe["payments"][0]["note"]


def test_reconciliar_recusa_lancamento_so_previsto(client, categoria, cartao, comprar, lancar):
    """Previsão não tirou dinheiro da conta — virar pagamento seria inventar um."""
    compras = categoria("Compras")
    fatura_antiga = categoria("Fatura do cartão")
    nubank = cartao()
    comprar(nubank, compras, 120.0, dt.date(2026, 9, 10))
    fatura = client.get("/invoices").json()[0]

    r = client.post("/transactions", json={
        "date": "2026-09-16", "description": "Fatura",
        "amount_planned": 120.0, "category_id": fatura_antiga,
    })
    previsto = r.json()

    r = client.post(
        f"/invoices/{fatura['id']}/reconciliar", json={"transaction_id": previsto["id"]}
    )
    assert r.status_code == 400
    assert "previsão" in r.json()["detail"]


def test_reconciliar_recusa_parcela(client, categoria, cartao, comprar):
    """Parcela é item da fatura, não o pagamento dela."""
    compras = categoria("Compras")
    nubank = cartao()
    comprar(nubank, compras, 100.0, dt.date(2026, 9, 10))
    fatura = client.get("/invoices").json()[0]
    parcela = client.get("/transactions?year=2026&month=9").json()[0]

    r = client.post(
        f"/invoices/{fatura['id']}/reconciliar", json={"transaction_id": parcela["id"]}
    )
    assert r.status_code == 400
    assert "item" in r.json()["detail"]


def test_candidatos_a_pagamento_nao_chutam_por_nome(client, categoria, cartao, comprar, lancar):
    """A lista é por forma (despesa, paga, perto do vencimento), não por palpite.

    Quem decide qual lançamento era o pagamento é o dono — o app só encurta a
    procura, colocando primeiro o de valor mais parecido com o restante.
    """
    compras = categoria("Compras")
    fatura_antiga = categoria("Fatura do cartão")
    nubank = cartao()
    comprar(nubank, compras, 300.0, dt.date(2026, 9, 10))
    fatura = client.get("/invoices").json()[0]

    lancar(fatura_antiga, 300.0, dt.date(2026, 10, 2), "FATURA", forma=None)
    lancar(compras, 19.9, dt.date(2026, 10, 3), "Café", forma=None)

    candidatos = client.get(f"/invoices/{fatura['id']}/candidatos-a-pagamento").json()
    nomes = [c["description"] for c in candidatos]

    # Os dois são candidatos: nenhum é descartado por nome.
    assert set(nomes) == {"FATURA", "Café"}
    # Mas o de valor igual ao restante vem primeiro.
    assert nomes[0] == "FATURA"


def test_mes_nao_revisado_continua_igual(client, categoria, cartao, comprar, lancar):
    """Reconstruir setembro não pode mexer em agosto.

    É a garantia de que a funcionalidade não reescreve o passado: só o mês em
    que o dono encostou muda.
    """
    alimentacao = categoria("Alimentação")
    fatura_antiga = categoria("Fatura do cartão")
    nubank = cartao()

    # Agosto, do jeito antigo, e ninguém vai mexer nele.
    lancar(fatura_antiga, 770.0, dt.date(2026, 8, 1), "FATURA", forma=None)
    lancar(alimentacao, 120.0, dt.date(2026, 8, 12), "Mercado", forma=None)
    agosto_antes = caixa_de(client, 2026, 8)["caixa"]

    # Setembro é reconstruído por inteiro.
    comprar(nubank, alimentacao, 200.0, dt.date(2026, 9, 10))
    antigo = lancar(fatura_antiga, 200.0, dt.date(2026, 10, 2), "FATURA", forma=None)
    fatura = client.get("/invoices/summary?year=2026&month=10").json()["cards"][0]["current"]
    client.post(f"/invoices/{fatura['id']}/reconciliar", json={"transaction_id": antigo["id"]})

    assert caixa_de(client, 2026, 8)["caixa"] == agosto_antes


# ---------- Edição e exclusão ----------


def test_parcela_nao_se_edita_nem_se_apaga_sozinha(client, categoria, cartao, comprar):
    compras = categoria("Compras")
    nubank = cartao()
    comprar(nubank, compras, 900.0, dt.date(2026, 9, 12), parcelas=3)
    parcela = client.get("/transactions?year=2026&month=9").json()[0]

    r = client.patch(f"/transactions/{parcela['id']}", json={"amount_paid": 1.0})
    assert r.status_code == 409
    assert "compra" in r.json()["detail"]

    r = client.delete(f"/transactions/{parcela['id']}")
    assert r.status_code == 409

    # E o valor não mudou.
    assert caixa_de(client, 2026, 9)["caixa"]["gasto_total"] == 300.0


def test_apagar_a_compra_leva_as_parcelas_e_a_fatura(client, categoria, cartao, comprar):
    compras = categoria("Compras")
    nubank = cartao()
    compra = comprar(nubank, compras, 900.0, dt.date(2026, 9, 12), parcelas=3)

    assert client.delete(f"/purchases/{compra['id']}").status_code == 200

    for mes in (9, 10, 11):
        assert caixa_de(client, 2026, mes)["caixa"]["gasto_total"] == 0.0
    # A fatura vazia some junto: "fatura de outubro: R$ 0,00" não é informação.
    assert client.get("/invoices").json() == []


def test_compra_com_fatura_paga_nao_muda_de_valor(client, categoria, cartao, comprar):
    """Restrição segura em vez de mágica: o extrato do banco não se reescreve."""
    compras = categoria("Compras")
    nubank = cartao()
    compra = comprar(nubank, compras, 300.0, dt.date(2026, 9, 12))
    fatura = client.get("/invoices").json()[0]
    client.post(f"/invoices/{fatura['id']}/payments", json={"amount": 300.0, "date": "2026-10-02"})

    r = client.patch(f"/purchases/{compra['id']}", json={"total_amount": 500.0})
    assert r.status_code == 409
    assert "paga" in r.json()["detail"]

    r = client.delete(f"/purchases/{compra['id']}")
    assert r.status_code == 409

    # Mas o rótulo continua editável — mudar o nome não mexe em dinheiro.
    r = client.patch(f"/purchases/{compra['id']}", json={"description": "Nome novo"})
    assert r.status_code == 200
    assert client.get("/transactions?year=2026&month=9").json()[0]["description"] == "Nome novo"


def test_mudar_as_parcelas_refaz_tudo_enquanto_nada_foi_pago(
    client, categoria, cartao, comprar
):
    compras = categoria("Compras")
    nubank = cartao()
    compra = comprar(nubank, compras, 900.0, dt.date(2026, 9, 12), parcelas=3)

    r = client.patch(f"/purchases/{compra['id']}", json={"installments": 1})
    assert r.status_code == 200, r.text

    assert caixa_de(client, 2026, 9)["caixa"]["gasto_total"] == 900.0
    assert caixa_de(client, 2026, 10)["caixa"]["gasto_total"] == 0.0
    # As faturas que sobraram vazias saíram junto.
    assert len(client.get("/invoices").json()) == 1


def test_cartao_com_compra_nao_se_apaga(client, categoria, cartao, comprar):
    compras = categoria("Compras")
    nubank = cartao()
    comprar(nubank, compras, 100.0, dt.date(2026, 9, 10))

    r = client.delete(f"/cards/{nubank}")
    assert r.status_code == 409
    assert "Arquive" in r.json()["detail"]


def test_cartao_sem_compra_se_apaga(client, cartao):
    nubank = cartao()
    assert client.delete(f"/cards/{nubank}").status_code == 200
    assert client.get("/cards").json() == []


# ---------- Portas fechadas ----------


def test_nao_da_pra_criar_lancamento_marcado_como_cartao(client, categoria):
    """Ele ficaria fora de qualquer fatura: gasto que nunca vira saída de caixa."""
    alimentacao = categoria("Alimentação")
    r = client.post("/transactions", json={
        "date": "2026-09-10", "description": "x", "amount_paid": 10.0,
        "category_id": alimentacao, "payment_method": "credit",
    })
    assert r.status_code == 400
    assert "/purchases" in r.json()["detail"]


def test_compra_no_cartao_tem_que_ser_despesa(client, categoria, cartao):
    salario = categoria("Salário", "income")
    nubank = cartao()

    r = client.post("/purchases", json={
        "card_id": nubank, "category_id": salario, "description": "x",
        "total_amount": 100.0, "installments": 1, "purchase_date": "2026-09-10",
    })
    assert r.status_code == 400
    assert "despesa" in r.json()["detail"]


def test_compra_precisa_de_valor_positivo(client, categoria, cartao):
    compras = categoria("Compras")
    nubank = cartao()
    r = client.post("/purchases", json={
        "card_id": nubank, "category_id": compras, "description": "x",
        "total_amount": 0, "installments": 1, "purchase_date": "2026-09-10",
    })
    assert r.status_code == 400


def test_a_lista_de_lancamentos_diz_de_que_cartao_e_qual_parcela(
    client, categoria, cartao, comprar
):
    """É o que a tela mostra: "Notebook · Compras · Nubank 2/3"."""
    compras = categoria("Compras")
    nubank = cartao()
    comprar(nubank, compras, 900.0, dt.date(2026, 9, 12), parcelas=3, descricao="Sofá")

    linha = client.get("/transactions?year=2026&month=10").json()[0]
    assert linha["card_name"] == "Nubank"
    assert linha["installment_no"] == 2
    assert linha["installments"] == 3
    assert linha["purchase_total"] == 900.0
    assert linha["purchase_date"] == "2026-09-12"
    assert linha["payment_method"] == "credit"


def test_fundir_categoria_leva_a_compra_junto(client, categoria, cartao, comprar):
    """Mover os lançamentos sem mover a compra deixaria a FK barrar o DELETE.

    A compra no cartão aponta pra categoria igual ao lançamento aponta. Como as
    parcelas SÃO lançamentos, elas se mudam com o resto e a contagem não acusa
    nada — a compra é que fica apontando pra uma categoria que vai deixar de
    existir. No Postgres isso é 500; no SQLite só aparece com o PRAGMA de chave
    estrangeira ligado, que o conftest liga.
    """
    antiga = categoria("Eletrônicos")
    nova = categoria("Compras")
    nubank = cartao()
    comprar(nubank, antiga, 900.0, dt.date(2026, 9, 12), parcelas=3, descricao="Notebook")

    r = client.delete(f"/categories/{antiga}?mover_para={nova}")
    assert r.status_code == 200, r.text
    assert r.json()["moved"] == 3

    # A compra foi junto, e as parcelas continuam de pé nos três meses.
    parcela = client.get("/transactions?year=2026&month=10").json()[0]
    assert parcela["category_id"] == nova
    compra = client.get(f"/purchases/{parcela['purchase_id']}").json()
    assert compra["category_id"] == nova
    assert compra["category_name"] == "Compras"

    # E a fatura continua inteira.
    assert client.get("/invoices").json()[0]["total"] == 300.0
