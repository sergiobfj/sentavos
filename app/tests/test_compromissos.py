"""Compromissos fora do cartão e a visão dos próximos meses.

O cronograma é calculado, nunca gravado; a baixa é um lançamento vinculado; a
passagem do tempo não paga nada. E o cartão não ganha compromisso nenhum: as
parcelas futuras dele já estão nas faturas, e a visão futura as lê de lá.
"""

import datetime as dt

import pytest

from app.tests.apoio_planejamento import HOJE, Montagem, item

D = dt.date


@pytest.fixture(name="m")
def montagem(client, monkeypatch):
    monkeypatch.setattr("app.planejamento.hoje", lambda: HOJE)
    return Montagem(client)


def _financiamento(m: Montagem, **extra) -> dict:
    moto = m.categoria("Moto")
    return m.compromisso(
        moto, 618.08, D(2026, 11, 9), parcelas=48,
        descricao="Financiamento da moto", institution="Banco X",
        total_amount=13990.0, down_payment=7000.0, **extra,
    )


def test_financiamento_48x(m):
    c = _financiamento(m)
    cronograma = c["schedule"]
    assert len(cronograma) == 48
    assert cronograma[0]["due_date"] == "2026-11-09" and cronograma[0]["label"] == "1/48"
    assert cronograma[-1]["due_date"] == "2030-10-09" and cronograma[-1]["label"] == "48/48"
    assert {o["status"] for o in cronograma} == {"pendente"}

    assert c["kind"] == "parcelado" and c["direction"] == "saida"
    assert c["paid_count"] == 0 and c["remaining_count"] == 48
    # Soma NOMINAL do que falta. Não é saldo devedor, e não é 13.990.
    assert c["remaining_nominal"] == 29667.84
    assert c["next"]["number"] == 1 and c["next"]["due_date"] == "2026-11-09"
    # Nenhuma das 48 parcelas virou lançamento.
    assert m.quantos_lancamentos() == 0


def test_valor_total_e_entrada_sao_so_informacao(m):
    """Principal e entrada não somam em nada: as parcelas e o lançamento da
    entrada já dizem o que sai. Somar os três contaria o custo três vezes."""
    m.conta("Banco", 10000.0, dia=HOJE)
    _financiamento(m)
    meses = m.horizonte(3)
    assert meses[0]["expense"] == 0.0  # outubro: nada vence
    assert meses[1]["expense"] == 618.08  # novembro: só a parcela
    assert meses[2]["expense"] == 618.08


def test_primeira_parcela_e_virada_de_ano(m):
    c = _financiamento(m)
    datas = [o["due_date"] for o in c["schedule"][:4]]
    assert datas == ["2026-11-09", "2026-12-09", "2027-01-09", "2027-02-09"]

    meses = m.horizonte(6)
    janeiro = next(x for x in meses if (x["year"], x["month"]) == (2027, 1))
    assert item(janeiro, f"compromisso:{c['id']}:3")["label"] == "3/48"


def test_baixa_avanca_de_1_48_para_2_48(m):
    c = _financiamento(m)
    r = m.pagar(c["id"], 1, data=D(2026, 11, 9))
    assert r.status_code == 200, r.text
    depois = r.json()
    assert depois["paid_count"] == 1 and depois["remaining_count"] == 47
    assert depois["next"]["label"] == "2/48"
    assert depois["schedule"][0]["status"] == "paga"
    assert depois["schedule"][0]["paid_amount"] == 618.08

    # O lançamento da baixa: realizado, à vista, com previsto e pago.
    lancamento = m.c.get(f"/transactions/{depois['schedule'][0]['transaction_id']}").json()
    assert lancamento["description"] == "Financiamento da moto 1/48"
    assert lancamento["amount_planned"] == 618.08 and lancamento["amount_paid"] == 618.08
    assert lancamento["payment_method"] == "cash"
    assert lancamento["finalidade"] == "pessoal"
    assert lancamento["commitment_id"] == c["id"] and lancamento["commitment_no"] == 1
    assert lancamento["commitment_installments"] == 48


def test_vencida_nao_e_paga(m, monkeypatch):
    c = _financiamento(m)
    monkeypatch.setattr("app.planejamento.hoje", lambda: D(2026, 11, 20))
    lido = m.c.get(f"/commitments/{c['id']}").json()
    assert lido["schedule"][0]["status"] == "vencida"
    assert lido["paid_count"] == 0 and lido["overdue_count"] == 1

    novembro = m.mes(2026, 11)["months"][0]
    assert item(novembro, f"compromisso:{c['id']}:1")["status"] == "vencido"
    assert novembro["expense"] == 618.08

    # Em dezembro, a de novembro continua devida: entra no mês corrente
    # junto com a de dezembro.
    monkeypatch.setattr("app.planejamento.hoje", lambda: D(2026, 12, 5))
    dezembro = m.mes(2026, 12)["months"][0]
    assert dezembro["expense"] == round(2 * 618.08, 2)
    assert dezembro["overdue"] == 618.08


def test_recorrencia_sem_fim_e_com_fim(m):
    saude = m.categoria("Saúde")
    academia = m.compromisso(saude, 120.0, D(2026, 10, 22), descricao="Academia")
    assert academia["kind"] == "recorrente" and academia["total_count"] is None
    assert academia["remaining_nominal"] is None

    meses = m.horizonte(6)
    for mes in meses:
        assert item(mes, f"compromisso:{academia['id']}:")["amount"] == 120.0
    # Recorrência não enche a tabela de lançamentos com meses futuros.
    assert m.quantos_lancamentos() == 0

    r = m.c.patch(f"/commitments/{academia['id']}", json={"end_date": "2026-12-31"})
    assert r.status_code == 200, r.text
    meses = m.horizonte(6)
    com = [x for x in meses if any(i["key"].startswith(f"compromisso:{academia['id']}:") for i in x["items"])]
    assert [(x["year"], x["month"]) for x in com] == [(2026, 10), (2026, 11), (2026, 12)]


def test_cancelamento(m, monkeypatch):
    saude = m.categoria("Saúde")
    c = m.compromisso(saude, 120.0, D(2026, 10, 22), descricao="Academia")
    r = m.c.patch(f"/commitments/{c['id']}", json={"cancelled_on": "2026-12-01"})
    assert r.status_code == 200
    cronograma = {o["due_date"]: o["status"] for o in r.json()["schedule"]}
    assert cronograma["2026-10-22"] == "pendente"
    assert cronograma["2026-11-22"] == "pendente"
    assert cronograma["2026-12-22"] == "cancelada"

    meses = m.horizonte(4)
    assert meses[2]["expense"] == 0.0 and meses[3]["expense"] == 0.0

    # Cancelado em dezembro, novembro em aberto continua devido.
    monkeypatch.setattr("app.planejamento.hoje", lambda: D(2026, 12, 10))
    lido = m.c.get(f"/commitments/{c['id']}").json()
    assert lido["status"] == "cancelado"
    assert lido["overdue_count"] == 2  # outubro e novembro, sem baixa


def test_parcelamento_fora_do_cartao(m):
    """Emplacamento em 4x direto com o fornecedor: compromisso, não cartão."""
    documentacao = m.categoria("Documentação")
    c = m.compromisso(documentacao, 227.0, D(2026, 11, 20), parcelas=4, descricao="Emplacamento")
    assert c["remaining_nominal"] == 908.0
    meses = m.horizonte(6)
    valores = [x["by_source"]["parcelado"] for x in meses]
    assert valores == [0.0, 227.0, 227.0, 227.0, 227.0, 0.0]


def test_cartao_existente_entra_sem_duplicar(m):
    """Compra em 4x: as faturas de novembro a fevereiro já têm as parcelas.
    A visão futura as soma uma vez, pela fatura, sem cadastro nenhum."""
    compras = m.categoria("Compras")
    nubank = m.cartao("Nubank")
    m.comprar(nubank, compras, 400.0, D(2026, 10, 5), parcelas=4)

    meses = m.horizonte(6)
    cartao = [x["by_source"]["cartao"] for x in meses]
    assert cartao == [0.0, 100.0, 100.0, 100.0, 100.0, 0.0]
    for mes in meses[1:5]:
        assert [i["source"] for i in mes["items"]] == ["cartao"]
    assert m.c.get("/commitments").json() == []


def test_fatura_entra_pelo_restante_e_paga_nao_conta(m):
    compras = m.categoria("Compras")
    nubank = m.cartao("Nubank")
    m.comprar(nubank, compras, 300.0, D(2026, 9, 20))  # fatura que vence 02/10
    m.comprar(nubank, compras, 500.0, D(2026, 10, 3))  # fatura que vence 02/11
    faturas = {f["month"]: f for f in m.c.get("/invoices").json()}

    m.c.post(f"/invoices/{faturas[10]['id']}/payments", json={"amount": 300.0, "date": "2026-10-02"})
    m.c.post(f"/invoices/{faturas[11]['id']}/payments", json={"amount": 200.0, "date": "2026-10-09"})

    meses = m.horizonte(2)
    outubro = item(meses[0], f"fatura:{faturas[10]['id']}")
    assert outubro["status"] == "pago" and outubro["remaining"] == 0.0
    assert meses[0]["expense"] == 0.0
    novembro = item(meses[1], f"fatura:{faturas[11]['id']}")
    assert novembro["amount"] == 500.0 and novembro["remaining"] == 300.0
    assert meses[1]["expense"] == 300.0


def test_pagar_duas_vezes_e_recusado(m):
    c = _financiamento(m)
    assert m.pagar(c["id"], 1).status_code == 200
    r = m.pagar(c["id"], 1)
    assert r.status_code == 409
    assert "já foi paga" in r.json()["detail"]
    assert m.quantos_lancamentos() == 1


def test_ocorrencia_fora_do_cronograma(m):
    c = _financiamento(m)
    assert m.pagar(c["id"], 49).status_code == 404
    assert m.pagar(c["id"], 0).status_code == 404


def test_ja_paguei_vincula_sem_criar_outro_lancamento(m):
    c = _financiamento(m)
    moto = c["category_id"]
    existente = m.lancar(moto, D(2026, 11, 8), pago=618.08, descricao="Parcela moto")
    antes = m.quantos_lancamentos()

    r = m.c.post(f"/commitments/{c['id']}/ocorrencias/1/vincular", json={"transaction_id": existente["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["schedule"][0]["status"] == "paga"
    assert m.quantos_lancamentos() == antes

    # O mesmo lançamento não paga duas parcelas.
    r = m.c.post(f"/commitments/{c['id']}/ocorrencias/2/vincular", json={"transaction_id": existente["id"]})
    assert r.status_code == 409


def test_vincular_recusa_parcela_de_cartao_previsto_e_tipo_trocado(m):
    c = _financiamento(m)
    nubank = m.cartao()
    compra = m.comprar(nubank, c["category_id"], 618.08, D(2026, 11, 8))
    parcela = next(t for t in m.c.get("/transactions").json() if t["purchase_id"] == compra["id"])
    so_previsto = m.lancar(c["category_id"], D(2026, 11, 8), previsto=618.08)
    receita = m.lancar(m.categoria("Outras", "income"), D(2026, 11, 8), pago=618.08)

    for t in (parcela, so_previsto, receita):
        r = m.c.post(f"/commitments/{c['id']}/ocorrencias/1/vincular", json={"transaction_id": t["id"]})
        assert r.status_code == 400, (t["description"], r.text)


def test_desvincular_mantem_o_lancamento(m):
    c = _financiamento(m)
    m.pagar(c["id"], 1)
    antes = m.quantos_lancamentos()
    r = m.c.delete(f"/commitments/{c['id']}/ocorrencias/1/vincular")
    assert r.status_code == 200
    assert r.json()["schedule"][0]["status"] == "pendente"
    assert m.quantos_lancamentos() == antes


def test_apagar_o_lancamento_desfaz_a_baixa(m):
    c = _financiamento(m)
    pago = m.pagar(c["id"], 1).json()
    tid = pago["schedule"][0]["transaction_id"]
    assert m.c.delete(f"/transactions/{tid}").status_code == 200
    lido = m.c.get(f"/commitments/{c['id']}").json()
    assert lido["schedule"][0]["status"] == "pendente" and lido["paid_count"] == 0


def test_dispensar_tira_da_conta_e_impede_a_baixa(m):
    saude = m.categoria("Saúde")
    c = m.compromisso(saude, 120.0, D(2026, 10, 5), descricao="Academia")
    assert m.mes()["months"][0]["overdue"] == 120.0

    r = m.c.post(f"/commitments/{c['id']}/ocorrencias/1/dispensar", json={"note": "não cobrou"})
    assert r.status_code == 200
    assert r.json()["schedule"][0]["status"] == "dispensada"
    assert m.mes()["months"][0]["expense"] == 0.0
    assert m.pagar(c["id"], 1).status_code == 409

    m.c.delete(f"/commitments/{c['id']}/ocorrencias/1/dispensar")
    assert m.mes()["months"][0]["expense"] == 120.0


def test_calendario_trava_depois_da_baixa(m):
    c = _financiamento(m)
    m.pagar(c["id"], 3)
    url = f"/commitments/{c['id']}"
    assert m.c.patch(url, json={"first_due": "2026-12-09"}).status_code == 409
    assert m.c.patch(url, json={"interval_months": 2}).status_code == 409
    assert m.c.patch(url, json={"installments": 2}).status_code == 409
    # O dia pode mudar (o banco moveu o vencimento), e o valor também.
    r = m.c.patch(url, json={"first_due": "2026-11-15", "amount": 620.0})
    assert r.status_code == 200, r.text
    assert r.json()["schedule"][0]["due_date"] == "2026-11-15"
    # A parcela paga guarda o que foi pago de verdade.
    assert r.json()["schedule"][2]["paid_amount"] == 618.08


def test_apagar_compromisso(m):
    c = _financiamento(m)
    m.reservar(618.08, HOJE, cid=c["id"], numero=1)
    m.pagar(c["id"], 2)
    assert m.c.delete(f"/commitments/{c['id']}").status_code == 409

    m.c.delete(f"/commitments/{c['id']}/ocorrencias/2/vincular")
    r = m.c.delete(f"/commitments/{c['id']}")
    assert r.status_code == 200 and r.json()["reservas_soltas"] == 1
    # A reserva fica, solta: o dinheiro continua separado.
    reservas = m.c.get("/provisions").json()
    assert len(reservas) == 1 and reservas[0]["commitment_id"] is None


def test_categoria_usada_por_compromisso(m):
    c = _financiamento(m)
    cat = c["category_id"]
    assert m.c.delete(f"/categories/{cat}").status_code == 409
    assert m.c.patch(f"/categories/{cat}", json={"type": "income"}).status_code == 409
    uso = next(x for x in m.c.get("/categories?incluir_uso=1").json() if x["id"] == cat)
    assert uso["commitments"] == 1

    destino = m.categoria("Veículo")
    r = m.c.delete(f"/categories/{cat}?mover_para={destino}")
    assert r.status_code == 200, r.text
    assert m.c.get(f"/commitments/{c['id']}").json()["category_id"] == destino


def test_investimento_nao_e_compromisso(m):
    reserva = m.categoria("Reserva", "investment")
    r = m.c.post(
        "/commitments",
        json={"description": "Guardar", "category_id": reserva, "amount": 400.0, "first_due": "2026-10-20"},
    )
    assert r.status_code == 400


def test_dia_31_achata_no_mes_curto(m):
    contas = m.categoria("Contas")
    c = m.compromisso(contas, 50.0, D(2027, 1, 31), parcelas=3)
    assert [o["due_date"] for o in c["schedule"]] == ["2027-01-31", "2027-02-28", "2027-03-31"]


def test_parcelas_e_data_de_fim_juntas_sao_recusadas(m):
    contas = m.categoria("Contas")
    r = m.c.post(
        "/commitments",
        json={"description": "x", "category_id": contas, "amount": 10.0, "first_due": "2026-10-20",
              "installments": 3, "end_date": "2027-01-01"},
    )
    assert r.status_code == 400


def test_baixa_nao_vai_pro_cartao_nem_vira_pagamento_de_fatura(m):
    """Os dois caminhos que APAGAM um lançamento recusam a baixa de compromisso:
    a parcela voltaria a "a pagar" com o dinheiro já fora da conta."""
    c = _financiamento(m)
    tid = m.pagar(c["id"], 1).json()["schedule"][0]["transaction_id"]
    nubank = m.cartao()

    r = m.c.post(f"/transactions/{tid}/forma-de-pagamento", json={"metodo": "credit", "card_id": nubank})
    assert r.status_code == 409

    compra = m.comprar(nubank, c["category_id"], 100.0, D(2026, 10, 5))
    fatura = m.c.get("/invoices").json()[0]
    r = m.c.post(f"/invoices/{fatura['id']}/reconciliar", json={"transaction_id": tid})
    assert r.status_code == 409
    assert m.c.get(f"/transactions/{tid}").status_code == 200
    assert compra["id"]


def test_baixa_nao_troca_de_tipo_pela_edicao(m):
    c = _financiamento(m)
    tid = m.pagar(c["id"], 1).json()["schedule"][0]["transaction_id"]
    receita = m.categoria("Outras", "income")
    assert m.c.patch(f"/transactions/{tid}", json={"category_id": receita}).status_code == 409
    outra = m.categoria("Veículo")
    assert m.c.patch(f"/transactions/{tid}", json={"category_id": outra}).status_code == 200


def test_entrada_recorrente_recebida_pela_baixa(m):
    salario = m.categoria("Salário", "income")
    c = m.compromisso(salario, 720.0, D(2026, 10, 15), descricao="Adiantamento", confirmed=False)
    assert c["direction"] == "entrada" and c["finalidade"] is None
    m.conta("Banco", 100.0, dia=HOJE)
    assert m.mes()["months"][0]["income"] == 720.0

    r = m.pagar(c["id"], 1, data=D(2026, 10, 15), valor=715.0)
    assert r.status_code == 200
    lancamento = m.c.get(f"/transactions/{r.json()['schedule'][0]['transaction_id']}").json()
    assert lancamento["amount_paid"] == 715.0 and lancamento["finalidade"] is None
    assert m.mes()["months"][0]["income"] == 0.0
