"""Reserva: o dinheiro existe, mas já tem destino.

O caso que guia tudo aqui: em outubro separo R$ 618,08 pra parcela de novembro.
Outubro fica com R$ 618,08 a menos de disponível; novembro continua devendo a
parcela, mas ela já está coberta. Pagar a parcela cumpre a reserva. Em nenhum
momento o mesmo dinheiro sai duas vezes do disponível.
"""

import datetime as dt

import pytest

from app.tests.apoio_planejamento import HOJE, Montagem, item

D = dt.date
PARCELA = 618.08


@pytest.fixture(name="m")
def montagem(client, monkeypatch):
    monkeypatch.setattr("app.planejamento.hoje", lambda: HOJE)
    return Montagem(client)


@pytest.fixture(name="parcelado")
def parcelado_fixture(m):
    m.conta("Banco", 3000.0, dia=HOJE)
    moto = m.categoria("Moto")
    return m.compromisso(moto, PARCELA, D(2026, 11, 9), parcelas=48, descricao="Financiamento")


def test_sem_reserva(m, parcelado):
    outubro, novembro = m.horizonte(2)
    assert outubro["reserved"] == 0.0 and outubro["available"] == 3000.0
    assert novembro["expense"] == PARCELA
    assert novembro["provisioned"] == 0.0
    assert novembro["still_needed"] == PARCELA


def test_reserva_total_entre_meses(m, parcelado):
    m.reservar(PARCELA, HOJE, cid=parcelado["id"], numero=1)
    outubro, novembro = m.horizonte(2)

    # Outubro: o dinheiro está na conta, mas não está livre.
    assert outubro["projected"] == 3000.0
    assert outubro["reserved"] == PARCELA
    assert outubro["available"] == round(3000.0 - PARCELA, 2)

    # Novembro: a obrigação continua, coberta. A reserva já não é descontada
    # de novo — quem a representa agora é a própria saída.
    linha = item(novembro, f"compromisso:{parcelado['id']}:1")
    assert linha["remaining"] == PARCELA and linha["provisioned"] == PARCELA
    assert novembro["provisioned"] == PARCELA
    assert novembro["still_needed"] == 0.0
    assert novembro["reserved"] == 0.0
    # Não contou duas vezes: o disponível do fim de novembro é o de outubro.
    assert novembro["available"] == outubro["available"]


def test_reserva_parcial(m, parcelado):
    m.reservar(300.0, HOJE, cid=parcelado["id"], numero=1)
    outubro, novembro = m.horizonte(2)
    assert outubro["reserved"] == 300.0
    assert novembro["provisioned"] == 300.0
    assert novembro["still_needed"] == round(PARCELA - 300.0, 2)


def test_obrigacao_paga_cumpre_a_reserva(m, parcelado):
    reserva = m.reservar(PARCELA, HOJE, cid=parcelado["id"], numero=1)
    assert m.pagar(parcelado["id"], 1, data=HOJE).status_code == 200

    lida = next(r for r in m.c.get("/provisions").json() if r["id"] == reserva["id"])
    assert lida["status"] == "cumprida"
    outubro, novembro = m.horizonte(2)
    # Paga em outubro: a reserva deixou de existir no mês em que o dinheiro saiu.
    assert outubro["reserved"] == 0.0
    assert novembro["expense"] == 0.0
    assert novembro["provisioned"] == 0.0


def test_reserva_ligada_aparece_com_o_alvo(m, parcelado):
    m.reservar(PARCELA, HOJE, cid=parcelado["id"], numero=1)
    outubro = m.mes()["months"][0]
    assert len(outubro["reserves"]) == 1
    r = outubro["reserves"][0]
    assert r["target_key"] == f"compromisso:{parcelado['id']}:1"
    assert r["target_label"] == "Financiamento 1/48"

    lida = m.c.get("/provisions").json()[0]
    assert lida["status"] == "ativa"
    assert lida["description"] == "Financiamento 1/48"
    assert lida["occurrence_due"] == "2026-11-09"


def test_liberar_devolve_ao_disponivel(m, parcelado):
    reserva = m.reservar(500.0, HOJE, descricao="Emergência")
    assert m.mes()["months"][0]["reserved"] == 500.0

    r = m.c.patch(f"/provisions/{reserva['id']}", json={"released_on": HOJE.isoformat()})
    assert r.status_code == 200 and r.json()["status"] == "liberada"
    assert m.mes()["months"][0]["reserved"] == 0.0

    m.c.patch(f"/provisions/{reserva['id']}", json={"released_on": None})
    assert m.mes()["months"][0]["reserved"] == 500.0


def test_reserva_de_objetivo_continua_nos_meses_seguintes(m, parcelado):
    m.reservar(200.0, HOJE, descricao="Documentação")
    meses = m.horizonte(4)
    assert [x["reserved"] for x in meses] == [200.0, 200.0, 200.0, 200.0]


def test_reserva_nao_e_gasto_nem_sai_do_patrimonio(m, parcelado):
    lancamentos = m.quantos_lancamentos()
    m.reservar(1241.08, HOJE, descricao="Provisões de outubro")
    assert m.quantos_lancamentos() == lancamentos
    caixa = m.c.get("/budgets/summary?year=2026&month=10").json()["caixa"]
    assert caixa["gasto_total"] == 0.0
    assert m.c.get("/assets/summary?year=2026&month=10").json()["net_worth"] == 3000.0


def test_reservar_ocorrencia_ja_paga_e_recusado(m, parcelado):
    m.pagar(parcelado["id"], 1)
    r = m.c.post("/provisions", json={"amount": 10.0, "commitment_id": parcelado["id"], "commitment_no": 1})
    assert r.status_code == 409


def test_reserva_precisa_de_destino_e_valor(m, parcelado):
    assert m.c.post("/provisions", json={"amount": 10.0}).status_code == 400
    assert m.c.post("/provisions", json={"amount": 0, "description": "x"}).status_code == 400
    r = m.c.post("/provisions", json={"amount": 10.0, "commitment_id": parcelado["id"], "commitment_no": 99})
    assert r.status_code == 400
