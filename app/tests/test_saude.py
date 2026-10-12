"""Conferir mês: o estado do mês sai dos dados, e cada pendência é real.

Nenhuma pendência é gravada — o teste cria a situação e lê o estado. E as
pendências vêm agrupadas: seis lançamentos sem conta são UMA pendência.
"""

import datetime as dt

import pytest

from app.tests.apoio_planejamento import Montagem

HOJE = dt.date(2026, 10, 11)
BRT = dt.timezone(dt.timedelta(hours=-3))
D = dt.date


@pytest.fixture(name="m")
def montagem(client, monkeypatch):
    monkeypatch.setattr("app.planejamento.hoje", lambda: HOJE)
    return Montagem(client)


def saude(m, ym="2026-10") -> dict:
    r = m.c.get(f"/months/{ym}/health")
    assert r.status_code == 200, r.text
    return r.json()


def codigos(r) -> set[str]:
    return {i["code"] for i in r["issues"]}


def conta(m, nome, saldo=None, quando=dt.datetime(2026, 10, 5, 10, 0, tzinfo=BRT), tipo="checking") -> int:
    c = m.c.post("/accounts", json={"name": nome, "type": tipo}).json()
    if saldo is not None:
        m.c.post(f"/accounts/{c['id']}/snapshots", json={"balance": saldo, "observed_at": quando.isoformat()})
    return c["id"]


def test_mes_vazio_esta_conciliado(m):
    r = saude(m)
    assert (r["state"], r["issues"], r["trustworthy_balance"]) == ("conciliado", [], True)


def test_lancamentos_sem_conta_depois_do_saldo_viram_uma_pendencia(m):
    conta(m, "Nubank", 1000.0)
    casa = m.categoria("Casa")
    m.lancar(casa, D(2026, 10, 3), pago=5.0)  # antes do saldo: já está nele
    for dia in (6, 7, 8):
        m.lancar(casa, D(2026, 10, dia), pago=10.0)

    r = saude(m)
    falta = next(i for i in r["issues"] if i["code"] == "MISSING_ACCOUNT")
    assert (falta["count"], falta["amount"], falta["severity"]) == (3, 30.0, "revisar")
    assert r["state"] == "precisa_revisar"


def test_conta_sem_saldo_e_agregado_sao_avisos(m):
    conta(m, "Nubank")
    conta(m, "Saldo agregado", 684.39, tipo="reconciliation")
    r = saude(m)
    assert codigos(r) == {"STALE_BALANCE", "TEMPORARY_AGGREGATE_BALANCE"}
    assert r["state"] == "parcial"
    # Mês passado não cobra saldo de hoje.
    assert "STALE_BALANCE" not in codigos(saude(m, "2026-09"))


def test_diferenca_de_saldo_ate_ser_aceita(m):
    nubank = conta(m, "Nubank", 1000.0, dt.datetime(2026, 10, 1, 10, 0, tzinfo=BRT))
    snap = m.c.post(f"/accounts/{nubank}/snapshots", json={
        "balance": 950.0, "observed_at": dt.datetime(2026, 10, 9, 10, 0, tzinfo=BRT).isoformat()}).json()["snapshot"]
    assert "BALANCE_DIFFERENCE" in codigos(saude(m))
    m.c.post(f"/accounts/{nubank}/snapshots/{snap['id']}/aceitar")
    assert "BALANCE_DIFFERENCE" not in codigos(saude(m))


def test_resgate_sem_valor_deixa_o_saldo_do_mes_sem_confianca(m):
    a = m.c.post("/assets", json={"name": "Caixinha", "asset_class": "fixed_income"}).json()["id"]
    m.c.put("/assets/snapshots", json={"asset_id": a, "year": 2026, "month": 9, "value": 1000.0})
    m.c.put("/assets/snapshots", json={"asset_id": a, "year": 2026, "month": 10, "value": 0.0,
                                       "reconciliation_note": "Resgate sem extrato."})
    r = saude(m)
    assert "UNMATCHED_REDEMPTION" in codigos(r)
    assert r["trustworthy_balance"] is False


def test_compromisso_vencido_e_fatura_atrasada(m):
    moto = m.categoria("Moto")
    m.compromisso(moto, 618.08, D(2026, 10, 5), parcelas=3)
    cat = m.categoria("Mercado")
    cartao = m.cartao(fecha=25, vence=2)
    m.comprar(cartao, cat, 100.0, D(2026, 9, 10))  # fatura que venceu em 02/10 e não foi paga
    r = saude(m)
    assert {"OVERDUE_COMMITMENT", "OVERDUE_INVOICE"} <= codigos(r)
    vencido = next(i for i in r["issues"] if i["code"] == "OVERDUE_COMMITMENT")
    assert (vencido["count"], vencido["amount"]) == (1, 618.08)


def test_itens_da_conferencia_e_duplicidade(m):
    m.c.post("/reconciliation", json={"year": 2026, "month": 10, "description": "Emplacamento", "amount": 908.0})
    casa = m.categoria("Casa")
    m.lancar(casa, D(2026, 10, 6), pago=25.0, descricao="Pix")
    m.lancar(casa, D(2026, 10, 6), pago=25.0, descricao="pix")
    r = saude(m)
    assert {"REVIEW_ITEMS", "DUPLICATE_SUSPECT"} <= codigos(r)
    assert next(i for i in r["issues"] if i["code"] == "DUPLICATE_SUSPECT")["severity"] == "aviso"


def test_mes_invalido(m):
    assert m.c.get("/months/2026-13/health").status_code == 422
    assert m.c.get("/months/outubro/health").status_code == 422
