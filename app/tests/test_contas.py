"""Contas financeiras: saldo observado + movimentos conhecidos, e as invariantes.

Cada teste é uma forma de o dinheiro "mudar" sem ter mudado: a transferência
que vira gasto, o pagamento de fatura que vira gasto de novo, o saldo de
setembro que some na virada do mês, a distribuição do saldo agregado que cria
ou destrói dinheiro.
"""

import datetime as dt

import pytest
from sqlmodel import select

from app.models import AuditEvent
from app.tests.apoio_planejamento import Montagem

HOJE = dt.date(2026, 10, 11)
UTC = dt.timezone.utc
BRT = dt.timezone(dt.timedelta(hours=-3))
D = dt.date


@pytest.fixture(name="m")
def montagem(client, monkeypatch):
    monkeypatch.setattr("app.planejamento.hoje", lambda: HOJE)
    return Montagem(client)


def conta(m, nome, tipo="checking", **extra) -> dict:
    r = m.c.post("/accounts", json={"name": nome, "type": tipo, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def saldo(m, cid, valor, quando: dt.datetime | None = None) -> dict:
    corpo = {"balance": valor}
    if quando is not None:
        corpo["observed_at"] = quando.isoformat()
    r = m.c.post(f"/accounts/{cid}/snapshots", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def lancar(m, cat, data, valor, conta_id=None, forma="cash", ocorrido=None, desc="x") -> dict:
    corpo = {"date": data.isoformat(), "description": desc, "amount_paid": valor, "category_id": cat,
             "payment_method": forma, "account_id": conta_id}
    if ocorrido is not None:
        corpo["occurred_at"] = ocorrido.isoformat()
    r = m.c.post("/transactions", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def ler(m, cid) -> dict:
    return m.c.get(f"/accounts/{cid}").json()


def resumo(m) -> dict:
    return m.c.get("/accounts/summary").json()


def as_10h(d: dt.date) -> dt.datetime:
    return dt.datetime(d.year, d.month, d.day, 10, 0, tzinfo=BRT)


# ---------- Conta e saldo ----------


def test_padroes_por_tipo_e_nome_unico(m):
    vale = conta(m, "Vale-transporte", "benefit")
    assert vale["restricted"] is True and vale["include_in_planning"] is False
    nubank = conta(m, "Nubank", "checking")
    assert nubank["restricted"] is False and nubank["include_in_planning"] is True
    assert nubank["quality"] == "sem_saldo" and nubank["balance"] is None
    assert m.c.post("/accounts", json={"name": "nubank", "type": "payment"}).status_code == 409


def test_saldo_calculado_aplica_so_os_movimentos_da_conta(m):
    nubank = conta(m, "Nubank")
    outra = conta(m, "Mercado Pago", "payment")
    casa = m.categoria("Casa")
    salario = m.categoria("Salário", "income")
    saldo(m, nubank["id"], 1000.0, as_10h(D(2026, 10, 5)))

    lancar(m, casa, D(2026, 10, 6), 100.0, nubank["id"])
    lancar(m, salario, D(2026, 10, 7), 50.0, nubank["id"])
    lancar(m, casa, D(2026, 10, 7), 999.0, outra["id"])  # outra conta
    lancar(m, casa, D(2026, 10, 4), 300.0, nubank["id"])  # antes do saldo: já está nele

    n = ler(m, nubank["id"])
    assert n["balance"] == 950.0
    assert n["quality"] == "calculado"
    assert n["observed_balance"] == 1000.0 and n["movements_after"] == 2


def test_mesmo_dia_com_hora_e_sem_hora(m):
    """Saldo lido às 10h: o Pix das 14h vem depois; o lançamento só com data, não."""
    nubank = conta(m, "Nubank")
    casa = m.categoria("Casa")
    saldo(m, nubank["id"], 684.39, as_10h(D(2026, 10, 11)))

    lancar(m, casa, D(2026, 10, 11), 25.0, nubank["id"], ocorrido=dt.datetime(2026, 10, 11, 14, 0, tzinfo=BRT))
    lancar(m, casa, D(2026, 10, 11), 7.0, nubank["id"], ocorrido=dt.datetime(2026, 10, 11, 9, 0, tzinfo=BRT))
    lancar(m, casa, D(2026, 10, 11), 3.0, nubank["id"])  # sem hora: dentro do saldo do dia

    assert ler(m, nubank["id"])["balance"] == 659.39


def test_virada_do_mes_nao_some_com_o_dinheiro(m, monkeypatch):
    monkeypatch.setattr("app.planejamento.hoje", lambda: D(2026, 11, 1))
    nubank = conta(m, "Nubank")
    # Lido na noite de 31/10; hoje é 01/11 e nada aconteceu desde então.
    saldo(m, nubank["id"], 500.0, dt.datetime(2026, 10, 31, 20, 0, tzinfo=BRT))

    n = ler(m, nubank["id"])
    assert (n["balance"], n["quality"]) == (500.0, "reconciliado")
    assert m.mes(2026, 11)["months"][0]["opening"] == 500.0


def test_saldo_antigo_fica_desatualizado_mas_continua_contando(m, monkeypatch):
    nubank = conta(m, "Nubank")
    saldo(m, nubank["id"], 500.0, as_10h(D(2026, 9, 1)))

    n = ler(m, nubank["id"])
    assert (n["balance"], n["quality"]) == (500.0, "desatualizado")
    plano = m.mes()
    assert plano["months"][0]["opening"] == 500.0
    assert plano["balance_warning"]["contas_desatualizadas"] == ["Nubank"]


def test_movimento_sem_conta_depois_do_saldo_avisa_que_pode_estar_incompleto(m):
    nubank = conta(m, "Nubank")
    casa = m.categoria("Casa")
    saldo(m, nubank["id"], 500.0, as_10h(D(2026, 10, 5)))
    lancar(m, casa, D(2026, 10, 8), 40.0)  # sem conta

    assert ler(m, nubank["id"])["maybe_incomplete"] is True
    assert resumo(m)["unassigned_movements"] == 1
    aviso = m.mes()["balance_warning"]
    assert aviso["quantidade"] == 1 and aviso["saidas"] == 40.0
    # Listado, nunca somado: o saldo de partida continua o calculado.
    assert m.mes()["months"][0]["opening"] == 500.0


# ---------- Invariantes ----------


def test_transferencia_muda_o_lugar_e_nao_o_total(m):
    nubank = conta(m, "Nubank")
    mp = conta(m, "Mercado Pago", "payment")
    saldo(m, nubank["id"], 1000.0, as_10h(D(2026, 10, 1)))
    saldo(m, mp["id"], 0.0, as_10h(D(2026, 10, 1)))
    antes_total = resumo(m)["total"]
    antes_mes = m.c.get("/budgets/summary?year=2026&month=10").json()
    antes_patrimonio = m.c.get("/assets/summary?year=2026&month=10").json()["net_worth"]

    r = m.c.post("/transfers", json={"from_account_id": nubank["id"], "to_account_id": mp["id"],
                                     "amount": 100.0, "date": "2026-10-03", "description": "Pix pra mim"})
    assert r.status_code == 200, r.text

    assert ler(m, nubank["id"])["balance"] == 900.0
    assert ler(m, mp["id"])["balance"] == 100.0
    assert resumo(m)["total"] == antes_total
    depois_mes = m.c.get("/budgets/summary?year=2026&month=10").json()
    assert depois_mes["caixa"]["gasto_total"] == antes_mes["caixa"]["gasto_total"] == 0.0
    assert depois_mes["caixa"]["entrou"] == antes_mes["caixa"]["entrou"] == 0.0
    assert m.c.get("/assets/summary?year=2026&month=10").json()["net_worth"] == antes_patrimonio
    assert m.c.app  # noqa: B018 (só pra manter o cliente vivo)


def test_transferencia_recusa_mesma_conta_e_valor_invalido(m):
    a = conta(m, "A")
    b = conta(m, "B")
    corpo = {"from_account_id": a["id"], "to_account_id": a["id"], "amount": 10.0, "date": "2026-10-03"}
    assert m.c.post("/transfers", json=corpo).status_code == 400
    corpo.update(to_account_id=b["id"], amount=0)
    assert m.c.post("/transfers", json=corpo).status_code == 400


def test_compra_no_cartao_nao_mexe_na_conta_e_o_pagamento_da_fatura_nao_e_gasto(m):
    nubank = conta(m, "Nubank")
    saldo(m, nubank["id"], 1000.0, as_10h(D(2026, 9, 20)))
    cat = m.categoria("Mercado")
    cartao = m.cartao()
    m.comprar(cartao, cat, 300.0, D(2026, 9, 21))
    assert ler(m, nubank["id"])["balance"] == 1000.0
    gasto_antes = m.c.get("/budgets/summary?year=2026&month=10").json()["caixa"]["gasto_total"]

    fatura = m.c.get("/invoices?limite=5").json()[0]
    r = m.c.post(f"/invoices/{fatura['id']}/payments",
                 json={"amount": 300.0, "date": "2026-10-02", "account_id": nubank["id"]})
    assert r.status_code == 200, r.text

    assert ler(m, nubank["id"])["balance"] == 700.0
    assert m.c.get("/budgets/summary?year=2026&month=10").json()["caixa"]["gasto_total"] == gasto_antes


def test_compra_no_cartao_nao_aceita_conta(m):
    nubank = conta(m, "Nubank")
    cat = m.categoria("Casa")
    r = m.c.post("/transactions", json={"date": "2026-10-10", "description": "x", "amount_paid": 10.0,
                                        "category_id": cat, "payment_method": "credit", "account_id": nubank["id"]})
    assert r.status_code == 400


def test_aporte_e_resgate_mexem_na_conta_e_nao_sao_gasto_nem_receita(m):
    nubank = conta(m, "Nubank")
    saldo(m, nubank["id"], 1000.0, as_10h(D(2026, 10, 1)))
    caixinha = m.categoria("Caixinha", "investment")
    lancar(m, caixinha, D(2026, 10, 2), 300.0, nubank["id"])  # aporte
    lancar(m, caixinha, D(2026, 10, 3), -100.0, nubank["id"])  # resgate

    assert ler(m, nubank["id"])["balance"] == 800.0
    caixa = m.c.get("/budgets/summary?year=2026&month=10").json()["caixa"]
    assert caixa["gasto_total"] == 0.0 and caixa["entrou"] == 0.0


def test_saldo_agregado_distribuido_nao_cria_nem_destroi_dinheiro(client, m):
    agregado = conta(m, "Saldo agregado", "reconciliation")
    nubank = conta(m, "Nubank")
    mp = conta(m, "Mercado Pago", "payment")
    carteira = conta(m, "Carteira", "cash")
    saldo(m, agregado["id"], 684.39, as_10h(D(2026, 10, 11)))
    antes = resumo(m)
    assert antes["total"] == 684.39 and antes["to_distribute"] == 684.39

    r = m.c.post(f"/accounts/{agregado['id']}/distribuir", json={"destinos": [
        {"account_id": nubank["id"], "amount": 400.0},
        {"account_id": mp["id"], "amount": 200.0},
        {"account_id": carteira["id"], "amount": 84.39},
    ]})
    assert r.status_code == 200, r.text
    depois = r.json()

    por_nome = {c["name"]: c["balance"] for c in depois["accounts"]}
    assert por_nome == {"Saldo agregado": 0.0, "Nubank": 400.0, "Mercado Pago": 200.0, "Carteira": 84.39}
    assert depois["total"] == antes["total"]
    assert depois["to_distribute"] == 0.0
    caixa = m.c.get("/budgets/summary?year=2026&month=10").json()["caixa"]
    assert caixa["entrou"] == 0.0 and caixa["gasto_total"] == 0.0


def test_distribuicao_que_nao_fecha_e_recusada(m):
    agregado = conta(m, "Saldo agregado", "reconciliation")
    nubank = conta(m, "Nubank")
    saldo(m, agregado["id"], 684.39, as_10h(D(2026, 10, 11)))
    r = m.c.post(f"/accounts/{agregado['id']}/distribuir",
                 json={"destinos": [{"account_id": nubank["id"], "amount": 600.0}]})
    assert r.status_code == 400 and "684.39" in r.json()["detail"]
    r = m.c.post(f"/accounts/{nubank['id']}/distribuir",
                 json={"destinos": [{"account_id": agregado["id"], "amount": 1.0}]})
    assert r.status_code == 400


def test_diferenca_do_saldo_e_aceite_explicito(m, session):
    nubank = conta(m, "Nubank")
    casa = m.categoria("Casa")
    saldo(m, nubank["id"], 1000.0, as_10h(D(2026, 10, 1)))
    lancar(m, casa, D(2026, 10, 3), 100.0, nubank["id"])

    r = saldo(m, nubank["id"], 850.0, as_10h(D(2026, 10, 9)))
    snap = r["snapshot"]
    # Esperado 900 (1000 − 100), observado 850: faltam 50 que ninguém lançou.
    assert snap["difference"] == -50.0 and snap["pending_difference"] == -50.0
    # Lançar o gasto que faltava resolve sozinho (a diferença é derivada).
    lancar(m, casa, D(2026, 10, 5), 30.0, nubank["id"])
    lista = m.c.get(f"/accounts/{nubank['id']}/snapshots").json()
    assert lista[0]["pending_difference"] == -20.0

    r = m.c.post(f"/accounts/{nubank['id']}/snapshots/{snap['id']}/aceitar")
    assert r.status_code == 200 and r.json()["pending_difference"] is None
    # Aceitar não cria lançamento nem mexe no gasto.
    assert m.c.get("/budgets/summary?year=2026&month=10").json()["caixa"]["gasto_total"] == 130.0
    evento = session.exec(select(AuditEvent).where(AuditEvent.action == "saldo.diferenca_aceita")).one()
    assert evento.details["diferenca"] == -20.0


def test_planejamento_usa_as_contas_livres(m):
    nubank = conta(m, "Nubank")
    vale = conta(m, "Vale-transporte", "benefit")
    conta(m, "Carteira", "cash")  # sem saldo: fica de fora
    saldo(m, nubank["id"], 684.39, as_10h(D(2026, 10, 11)))
    saldo(m, vale["id"], 300.0, as_10h(D(2026, 10, 11)))
    adiantamento = m.categoria("Adiantamento", "income")
    m.lancar(adiantamento, D(2026, 10, 15), previsto=720.0)

    plano = m.mes()
    mes = plano["months"][0]
    assert mes["opening"] == 684.39  # o vale é restrito: nunca dinheiro livre
    assert mes["available"] == 1404.39
    assert plano["balance_warning"]["contas_sem_saldo"] == ["Carteira"]
    contas = {c["name"]: c for c in plano["accounts"]}
    assert contas["Vale-transporte"]["included"] is False and contas["Vale-transporte"]["restricted"] is True


def test_patrimonio_soma_contas_e_nao_reescreve_o_passado(m):
    nubank = conta(m, "Nubank")
    saldo(m, nubank["id"], 684.39, as_10h(D(2026, 10, 11)))
    ativo = m.c.post("/assets", json={"name": "Caixinha", "asset_class": "fixed_income"}).json()
    m.c.put("/assets/snapshots", json={"asset_id": ativo["id"], "year": 2026, "month": 9, "value": 1000.0})
    m.c.put("/assets/snapshots", json={"asset_id": ativo["id"], "year": 2026, "month": 10, "value": 0.0})

    outubro = m.c.get("/assets/summary?year=2026&month=10").json()
    assert outubro["accounts_total"] == 684.39
    assert outubro["net_worth"] == 684.39
    setembro = m.c.get("/assets/summary?year=2026&month=9").json()
    assert setembro["accounts_total"] == 0.0 and setembro["net_worth"] == 1000.0


def test_ativo_arquivado_sai_a_partir_do_mes_e_fica_no_historico(m):
    ativo = m.c.post("/assets", json={"name": "Saldo agregado", "asset_class": "checking"}).json()
    m.c.put("/assets/snapshots", json={"asset_id": ativo["id"], "year": 2026, "month": 9, "value": 500.0})
    r = m.c.patch(f"/assets/{ativo['id']}", json={"archived_on": "2026-10-01"})
    assert r.status_code == 200, r.text

    assert m.c.get("/assets/summary?year=2026&month=9").json()["net_worth"] == 500.0
    outubro = m.c.get("/assets/summary?year=2026&month=10").json()
    assert outubro["net_worth"] == 0.0 and outubro["items"] == []
    assert outubro["previous_net_worth"] == 500.0


def test_baixa_de_compromisso_leva_a_conta(m):
    nubank = conta(m, "Nubank")
    saldo(m, nubank["id"], 1000.0, as_10h(D(2026, 10, 1)))
    moto = m.categoria("Moto")
    c = m.compromisso(moto, 618.08, D(2026, 10, 9), parcelas=48)
    r = m.c.post(f"/commitments/{c['id']}/ocorrencias/1/pagar",
                 json={"date": "2026-10-09", "account_id": nubank["id"]})
    assert r.status_code == 200, r.text
    assert ler(m, nubank["id"])["balance"] == 381.92
    lista = m.c.get("/transactions?year=2026&month=10").json()
    assert lista[0]["account_name"] == "Nubank"


def test_conta_arquivada_nao_recebe_lancamento(m):
    nubank = conta(m, "Nubank")
    m.c.patch(f"/accounts/{nubank['id']}", json={"archived": True})
    casa = m.categoria("Casa")
    r = m.c.post("/transactions", json={"date": "2026-10-10", "description": "x", "amount_paid": 1.0,
                                        "category_id": casa, "account_id": nubank["id"]})
    assert r.status_code == 400


def test_conta_com_movimento_nao_se_exclui(m):
    nubank = conta(m, "Nubank")
    casa = m.categoria("Casa")
    lancar(m, casa, D(2026, 10, 10), 1.0, nubank["id"])
    assert m.c.delete(f"/accounts/{nubank['id']}").status_code == 409
    vazia = conta(m, "Vazia")
    assert m.c.delete(f"/accounts/{vazia['id']}").status_code == 200


def test_lancamento_nao_aponta_pra_conta_alheia(cliente_de, criar_usuario):
    ana = criar_usuario("ana@exemplo.com", "Ana", "senha-da-ana-12345")
    bruno = criar_usuario("bruno@exemplo.com", "Bruno", "senha-do-bruno-12345")
    conta_do_bruno = cliente_de(bruno).post("/accounts", json={"name": "Do Bruno", "type": "cash"}).json()
    c = cliente_de(ana)
    cat = c.post("/categories", json={"name": "Casa", "type": "expense", "color": "#fff", "icon": "x"}).json()
    r = c.post("/transactions", json={"date": "2026-10-10", "description": "x", "amount_paid": 1.0,
                                      "category_id": cat["id"], "account_id": conta_do_bruno["id"]})
    assert r.status_code == 404
