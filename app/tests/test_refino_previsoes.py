import datetime as dt

import pytest

from app.tests.apoio_planejamento import Montagem

NOW = dt.datetime(2026, 10, 20, 15, tzinfo=dt.timezone.utc)


@pytest.fixture
def base(client, monkeypatch):
    monkeypatch.setattr("app.planejamento.hoje", lambda: NOW.date())
    monkeypatch.setattr("app.dominio.tempo.agora", lambda: NOW)
    monkeypatch.setattr("app.dominio.tempo.hoje_local", lambda: NOW.date())
    monkeypatch.setattr("app.dominio.contas.agora", lambda: NOW)
    m = Montagem(client)
    cat = m.categoria("Despesas", "expense")
    income = m.categoria("Salário", "income")
    invest = m.categoria("Investimentos", "investment")
    account = client.post("/accounts", json={"name":"Conta", "type":"checking"}).json()["id"]
    client.post(f"/accounts/{account}/snapshots", json={"balance":1000,"observed_at":"2026-10-20T10:00:00Z"})
    asset = client.post("/assets", json={"name":"Emergência","asset_class":"fixed_income"}).json()["id"]
    return client, cat, income, invest, account, asset


def summary(c):
    r = c.get("/months/summary?year=2026&month=10")
    assert r.status_code == 200, r.text
    return r.json()


def plan(base, **changes):
    c, _, _, cat, account, asset = base
    data = dict(type="contribution",amount=400,date="2026-10-27",category_id=cat,account_id=account,asset_id=asset)
    r = c.post("/investments/plans",json={**data,**changes})
    assert r.status_code == 200, r.text
    return r.json()


def test_cinco_numeros_e_pagamento_nao_aumenta_sobra(base):
    c, cat, income, _, account, _ = base
    c.post("/transactions",json=dict(date="2026-10-27",description="Salário",category_id=income,amount_planned=500))
    ids=[]
    for desc,amount,kind in [("Internet",60,"fixed"),("Academia",120,"fixed"),("Pix",40,"variable")]:
        r=c.post("/transactions",json=dict(date="2026-10-27",description=desc,category_id=cat,amount_planned=amount,expense_class=kind,payment_method="cash",account_id=account))
        assert r.status_code==200,r.text
        ids.append(r.json()["id"])
    plan(base)
    r=summary(c)
    assert [r[k] for k in ("money_now","to_receive","to_pay","contributed","to_invest","projected")] == [1000,500,220,0,400,880]
    assert not r["partial"]
    for _ in range(2):
        assert c.patch(f"/transactions/{ids[0]}",json={"date":"2026-10-20","amount_paid":60,"amount_planned":None,"occurred_at":NOW.isoformat()}).status_code==200
    r=summary(c)
    assert (r["money_now"],r["to_pay"],r["projected"]) == (940,160,880)
    assert ids[0] in r["paid_cash_ids"]


def test_plano_nao_altera_realizado_e_confirmacao_idempotente(base):
    c, _, _, _, account, _=base
    before=c.get("/assets/summary?year=2026&month=10").json()
    p=plan(base)
    assert c.get("/investments/movements").json()==[]
    assert c.get("/assets/summary?year=2026&month=10").json()==before
    assert summary(c)["money_now"]==1000
    results=[c.post(f"/investments/plans/{p['id']}/confirm",json={"date":"2026-10-20"}) for _ in range(2)]
    assert all(r.status_code==200 for r in results),[r.text for r in results]
    assert results[0].json()["movement_id"]==results[1].json()["movement_id"]
    assert len(c.get("/investments/movements").json())==1
    r=summary(c)
    assert (r["money_now"],r["contributed"],r["to_invest"],r["projected"])==(600,400,0,600)
    budget=c.get("/budgets/summary?year=2026&month=10").json()["caixa"]
    assert budget["gasto_total"]==0 and budget["entrou"]==0


def test_cancelar_editar_atrasado_e_complementar(base):
    c=base[0]
    p=plan(base,date="2026-10-10",asset_id=None,account_id=None,category_id=None)
    assert p["overdue"] and p["status"]=="planned"
    assert c.post(f"/investments/plans/{p['id']}/confirm",json={"date":"2026-10-20"}).status_code==400
    assert summary(c)["to_invest"]==400
    data={k:p[k] for k in ("type","amount","date","asset_id","account_id","category_id","description")}
    data.update(amount=300,date="2026-10-30")
    assert c.patch(f"/investments/plans/{p['id']}",json=data).status_code==200
    assert summary(c)["to_invest"]==300
    assert c.post(f"/investments/plans/{p['id']}/cancel").status_code==200
    assert summary(c)["to_invest"]==0
    assert summary(c)["money_now"]==1000
    assert c.post(f"/investments/plans/{p['id']}/confirm",json={"date":"2026-10-20"}).status_code==409


def test_resgate_previsto_nao_e_receita_e_vence_sem_realizar(base):
    c=base[0]
    p=plan(base,type="redemption",amount=200,date="2026-10-10")
    r=summary(c)
    assert (r["money_now"],r["to_receive"],r["projected"])==(1000,0,1200)
    assert r["partial"] and r["contributed"]==0
    assert c.get("/investments/movements").json()==[]
    assert p["overdue"]


@pytest.mark.parametrize("planned",[False,True])
def test_emplacamento_cartao_competencia_fatura_e_pagamento_parcial(base,planned):
    c,cat,_,_,account,_=base
    card=c.post("/cards",json={"name":"Mercado Pago","closing_day":8,"due_day":13}).json()["id"]
    r=c.post("/purchases",json=dict(card_id=card,category_id=cat,description="Emplacamento",total_amount=904,installments=4,purchase_date="2026-10-13",expense_class="variable",planned=planned))
    assert r.status_code==200,r.text
    assert r.json()["installment_amounts"]==[226]*4
    assert summary(c)["money_now"]==1000 and summary(c)["to_pay"]==0
    rows=c.get("/transactions?year=2026&month=10").json()
    assert len(rows)==1 and rows[0]["payment_method"]=="credit"
    assert rows[0]["amount_paid"]==(None if planned else 226)
    # Novembro é o primeiro vencimento, não outubro.
    nov=c.get("/months/summary?year=2026&month=11").json()
    assert nov["to_pay"]==226
    fid=nov["due"][0]["invoice_id"]
    assert nov["due"][0]["date"]=="2026-11-13"
    if planned:
        assert c.patch(f"/purchases/{r.json()['id']}",json={"planned":False}).status_code==200
    paid=c.post(f"/invoices/{fid}/payments",json={"date":"2026-10-20","amount":100,"account_id":account,"occurred_at":NOW.isoformat()})
    assert paid.status_code==200,paid.text
    assert c.get("/months/summary?year=2026&month=11").json()["to_pay"]==126


def test_incerteza_sem_data_nao_promete_previsao_completa(base):
    c=base[0]
    c.post("/reconciliation",json={"year":2026,"month":10,"kind":"obrigacao","description":"Valor a conferir","amount":75})
    r=summary(c)
    assert r["to_pay"]==0 and r["to_check"]==75 and r["partial"]


def test_plano_isolado_e_demo(base,criar_usuario,cliente_de):
    p=plan(base)
    other=criar_usuario("outro@teste.com","Outro","senha-123456")
    c=cliente_de(other)
    assert c.get("/investments/plans?year=2026&month=10").json()==[]
    for action in ("confirm","cancel"):
        assert c.post(f"/investments/plans/{p['id']}/{action}",json={"date":"2026-10-20"}).status_code==404
    demo=criar_usuario("demo@teste.com","Demo","senha-123456",read_only=True)
    c=cliente_de(demo)
    assert c.post("/investments/plans",json={"type":"contribution","date":"2026-10-20","amount":400}).status_code==403


@pytest.mark.parametrize("amount",[0,-1,1000000000])
def test_valores_invalidos(base,amount):
    assert base[0].post("/investments/plans",json={"type":"contribution","date":"2026-10-20","amount":amount}).status_code==422


def test_saldo_observado_do_ativo_nao_vira_prejuizo_apos_confirmacao(base):
    c,_,_,_,_,asset=base
    for month in (9,10):
        assert c.put("/assets/snapshots",json={"asset_id":asset,"year":2026,"month":month,"value":1000}).status_code==200
    p=plan(base)
    assert c.post(f"/investments/plans/{p['id']}/confirm",json={"date":"2026-10-20"}).status_code==200
    r=c.get("/investments/summary?year=2026&month=10").json()
    assert r["yield_amount"] is None and r["yield_status"]=="nao_apurado"
    # A posição só muda quando o usuário informa o saldo observado.
    assert r["total"]==1000
    assert c.put("/assets/snapshots",json={"asset_id":asset,"year":2026,"month":10,"value":1405}).status_code==200
    r=c.get("/investments/summary?year=2026&month=10").json()
    assert r["yield_status"]=="apurado" and r["yield_amount"]==5


def test_referencias_de_previsao_preservadas_e_categoria_pode_ser_fundida(base):
    c,_,_,category,account,asset=base
    plan(base)
    assert c.delete(f"/assets/{asset}").status_code==409
    assert c.delete(f"/accounts/{account}").status_code==409
    assert c.delete(f"/categories/{category}").status_code==409
    assert c.patch(f"/categories/{category}",json={"type":"expense"}).status_code==409
    dest=c.post("/categories",json={"name":"Outra aplicação","type":"investment","icon":"+","color":"#ffffff"}).json()["id"]
    assert c.delete(f"/categories/{category}?mover_para={dest}").status_code==200
    assert c.get("/investments/plans?year=2026&month=10").json()[0]["category_id"]==dest


def test_previsao_atrasada_de_outro_mes_continua_acessivel(base):
    c=base[0]
    p=plan(base,date="2026-09-27")
    assert summary(c)["to_invest"]==400
    assert c.get("/investments/plans?year=2026&month=10").json()[0]["id"]==p["id"]


def test_correcao_dirigida_emplacamento_preserva_compra_sem_duplicar(base,session,dono):
    from scripts.corrigir_emplacamento import preparar,aplicar
    from app.models import ReconciliationItem
    c,cat,_,_,_,_=base
    card=c.post("/cards",json={"name":"Mercado Pago","closing_day":8,"due_day":13}).json()["id"]
    session.add(ReconciliationItem(user_id=dono.id,year=2026,month=10,description="Emplacamento",amount=908))
    session.commit()
    ids=[]
    for _ in range(2):
        args=preparar(session,dono,card,cat)
        compra=aplicar(session,dono,*args)
        session.commit()
        ids.append(compra.id)
    assert ids[0]==ids[1]
    rows=c.get("/transactions?year=2026&month=10").json()
    assert len(rows)==1 and rows[0]["amount_paid"]==226
    assert rows[0]["effective_expense_class"]=="variable"
    assert summary(c)["money_now"]==1000
    review=c.get("/reconciliation?year=2026&month=10").json()["items"][0]
    assert review["amount"]==904 and review["status"]=="resolvido" and not review["link_missing"]
