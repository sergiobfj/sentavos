"""Salário futuro como recorrência de entrada — nunca lançamento antecipado.

O caso real (outubro/2026): ~940 no dia 5, 720 no dia 15, 700 no dia 20. O de
outubro caiu em 06/10 por 944,34 e já estava lançado; o 720 e o 700 de outubro
já eram lançamentos previstos. Nada disso pode ser somado duas vezes, e nenhum
lançamento futuro pode nascer da recorrência.
"""

import datetime as dt

import pytest

from app.tests.apoio_planejamento import HOJE, Montagem, item

D = dt.date


@pytest.fixture(name="m")
def montagem(client, monkeypatch):
    monkeypatch.setattr("app.planejamento.hoje", lambda: HOJE)
    return Montagem(client)


def _salarios(m: Montagem) -> dict:
    """As três recorrências do mês, a partir de outubro, como as de produção."""
    salario = m.categoria("Salário", "income")
    adiantamento = m.categoria("Adiantamento", "income")
    meta = m.categoria("Meta", "income")
    return {
        "cats": (salario, adiantamento, meta),
        "dia5": m.compromisso(salario, 940.0, D(2026, 10, 5), descricao="Salário (dia 5)", confirmed=False),
        "dia15": m.compromisso(adiantamento, 720.0, D(2026, 10, 15), descricao="Adiantamento (dia 15)"),
        "dia20": m.compromisso(meta, 700.0, D(2026, 10, 20), descricao="Meta (dia 20)"),
    }


def _ids(m: Montagem) -> dict:
    return {c["description"]: c for c in m.c.get("/commitments").json()}


def _ocorrencia(m: Montagem, cid: int, numero: int) -> dict:
    corpo = m.c.get(f"/commitments/{cid}").json()
    return next(o for o in corpo["schedule"] if o["number"] == numero)


def test_meses_futuros_recebem_as_tres_entradas_sem_criar_lancamento(m):
    m.conta("Banco", 684.39, dia=HOJE)
    antes = m.quantos_lancamentos()
    _salarios(m)

    outubro, novembro, dezembro = m.horizonte(3)

    assert m.quantos_lancamentos() == antes
    assert novembro["income"] == 2360.0
    assert dezembro["income"] == 2360.0
    datas = sorted(i["date"] for i in novembro["items"] if i["direction"] == "entrada")
    assert datas == ["2026-11-05", "2026-11-15", "2026-11-20"]
    # O "aproximadamente" do dia 5 aparece como estimado, os outros como certos.
    s = {k: v["id"] for k, v in _ids(m).items()}
    assert item(novembro, f"compromisso:{s['Salário (dia 5)']}:")["certainty"] == "estimado"
    assert item(novembro, f"compromisso:{s['Adiantamento (dia 15)']}:")["certainty"] == "confirmado"


def test_horizonte_de_12_meses_usa_as_entradas(m):
    m.conta("Banco", 0.0, dia=HOJE)
    _salarios(m)

    meses = m.horizonte(12)

    assert len(meses) == 12
    assert all(mes["income"] == 2360.0 for mes in meses[1:])


def test_salario_recebido_substitui_a_previsao_mesmo_com_valor_diferente(m):
    """944,34 em 06/10 é o "~940 no dia 5": recebido, sem baixa à mão."""
    m.conta("Banco", 684.39, dia=HOJE)
    s = _salarios(m)
    salario = s["cats"][0]
    real = m.lancar(salario, D(2026, 10, 6), pago=944.34, descricao="Salário")

    o = _ocorrencia(m, s["dia5"]["id"], 1)
    assert o["status"] == "paga"
    assert o["matched"] is True
    assert (o["transaction_id"], o["paid_amount"], o["paid_date"]) == (real["id"], 944.34, "2026-10-06")

    outubro = m.mes()["months"][0]
    # Não volta como "a receber" nem como vencida: o dinheiro já está no saldo.
    # Sobra só o que ainda vem (15 e 20 de outubro).
    assert outubro["income"] == 1420.0
    assert item(outubro, f"compromisso:{s['dia5']['id']}:1")["status"] == "pago"
    # O lançamento continua sendo só dele: nada foi gravado na recorrência.
    assert m.c.get(f"/transactions/{real['id']}").json()["commitment_id"] is None


def test_previsto_lancado_a_mao_nao_soma_com_a_recorrencia(m):
    """O 720 e o 700 de outubro já eram lançamentos previstos: contam uma vez."""
    m.conta("Banco", 684.39, dia=HOJE)
    s = _salarios(m)
    salario, adiantamento, meta = s["cats"]
    m.lancar(salario, D(2026, 10, 6), pago=944.34, descricao="Salário")
    m.lancar(adiantamento, D(2026, 10, 15), previsto=720.0, descricao="Adiantamento")
    m.lancar(meta, D(2026, 10, 20), previsto=700.0, descricao="Meta")

    outubro = m.mes()["months"][0]

    assert outubro["income"] == 1420.0
    assert outubro["available"] == 2104.39
    o = _ocorrencia(m, s["dia15"]["id"], 1)
    assert o["status"] == "prevista" and o["matched"] is True
    # E a recorrência não deixa dar baixa por cima do previsto.
    r = m.pagar(s["dia15"]["id"], 1, valor=720.0)
    assert r.status_code == 409


def test_salario_lancado_fora_da_janela_nao_e_reconhecido(m):
    """Longe do vencimento não é "o mesmo salário": fica em aberto (e a baixa à mão resolve)."""
    s = _salarios(m)
    m.lancar(s["cats"][0], D(2026, 10, 25), pago=944.34, descricao="Salário")

    assert _ocorrencia(m, s["dia5"]["id"], 1)["status"] == "vencida"


def test_um_lancamento_cobre_uma_ocorrencia_so(m):
    """Duas recorrências na mesma categoria: o salário de 06/10 é o do dia 5, não o do dia 10."""
    salario = m.categoria("Salário", "income")
    dia5 = m.compromisso(salario, 940.0, D(2026, 10, 5), descricao="Dia 5")
    dia10 = m.compromisso(salario, 500.0, D(2026, 10, 10), descricao="Dia 10")
    m.lancar(salario, D(2026, 10, 6), pago=944.34)

    assert _ocorrencia(m, dia5["id"], 1)["status"] == "paga"
    assert _ocorrencia(m, dia10["id"], 1)["status"] == "pendente"


def test_saida_recorrente_nao_e_reconhecida_por_categoria(m):
    """A internet não vira "paga" por qualquer compra da casa no mesmo dia."""
    casa = m.categoria("Casa")
    internet = m.compromisso(casa, 60.0, D(2026, 10, 10), descricao="Internet")
    m.lancar(casa, D(2026, 10, 9), pago=60.0, descricao="Lâmpadas")

    assert _ocorrencia(m, internet["id"], 1)["status"] == "pendente"


def test_baixa_a_mao_vem_antes_do_reconhecimento(m):
    s = _salarios(m)
    salario = s["cats"][0]
    r = m.pagar(s["dia5"]["id"], 1, data=D(2026, 10, 7), valor=950.0)
    assert r.status_code == 200, r.text
    # Um lançamento solto da mesma categoria depois não "rouba" a ocorrência.
    reconhecivel = m.lancar(salario, D(2026, 10, 6), pago=944.34)

    o = _ocorrencia(m, s["dia5"]["id"], 1)
    assert o["matched"] is False and o["paid_amount"] == 950.0
    assert o["transaction_id"] != reconhecivel["id"]


def test_pausar_e_retomar(m):
    m.conta("Banco", 0.0, dia=HOJE)
    s = _salarios(m)
    cid = s["dia20"]["id"]

    r = m.c.post(f"/commitments/{cid}/pausar", json={"ate": "2026-12-01"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["paused_until"] == "2026-12-20"
    pausadas = [o for o in corpo["schedule"] if o["status"] == "dispensada"]
    # Outubro (20/10, ainda por vir), novembro e dezembro.
    assert [o["due_date"] for o in pausadas] == ["2026-10-20", "2026-11-20", "2026-12-20"]
    _, novembro, _, janeiro = m.horizonte(4)
    assert novembro["income"] == 2360.0 - 700.0
    assert janeiro["income"] == 2360.0

    r = m.c.post(f"/commitments/{cid}/retomar")
    assert r.status_code == 200, r.text
    assert r.json()["paused_until"] is None
    assert m.horizonte(2)[1]["income"] == 2360.0


def test_pausa_nao_toca_no_que_ja_foi_recebido_nem_em_parcelado(m):
    s = _salarios(m)
    m.lancar(s["cats"][0], D(2026, 10, 6), pago=944.34)
    cid = s["dia5"]["id"]

    corpo = m.c.post(f"/commitments/{cid}/pausar", json={"ate": "2026-11-30"}).json()

    assert next(o for o in corpo["schedule"] if o["number"] == 1)["status"] == "paga"
    moto = m.categoria("Moto")
    financiamento = m.compromisso(moto, 618.08, D(2026, 11, 9), parcelas=48)
    r = m.c.post(f"/commitments/{financiamento['id']}/pausar", json={"ate": "2026-12-01"})
    assert r.status_code == 400


def test_encerrar_e_editar_a_recorrencia(m):
    m.conta("Banco", 0.0, dia=HOJE)
    s = _salarios(m)
    cid = s["dia5"]["id"]

    # Editar: o valor aproximado vira 960 a partir de agora (nenhuma baixa ainda).
    r = m.c.patch(f"/commitments/{cid}", json={"amount": 960.0})
    assert r.status_code == 200, r.text
    assert m.horizonte(2)[1]["income"] == 2380.0
    # Encerrar: termina em novembro; dezembro já não tem o dia 5.
    r = m.c.patch(f"/commitments/{cid}", json={"end_date": "2026-11-30"})
    assert r.status_code == 200, r.text
    _, novembro, dezembro = m.horizonte(3)
    assert novembro["income"] == 2380.0
    assert dezembro["income"] == 1420.0
