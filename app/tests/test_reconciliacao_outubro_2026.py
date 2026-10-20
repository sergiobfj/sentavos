"""Casos sintéticos: fatos confirmados corrigem só registros identificados.

O inventário real e os planos com dados pessoais ficam fora do Git.
"""
import datetime as dt

import pytest
from sqlmodel import select

from app.models import (AccountBalanceSnapshot, AuditEvent, Category, Commitment, CommitmentSkip,
                        InvoicePayment, Purchase, ReconciliationItem, Transaction)
from scripts.reconciliar_outubro_2026 import fingerprint, local_only, reconcile, state


@pytest.fixture
def case(client, session, dono, monkeypatch):
    now = dt.datetime(2026, 10, 20, 15, tzinfo=dt.timezone.utc)
    monkeypatch.setattr("app.planejamento.hoje", lambda: now.date())
    monkeypatch.setattr("app.dominio.tempo.hoje_local", lambda: now.date())
    monkeypatch.setattr("app.dominio.tempo.agora", lambda: now)
    monkeypatch.setattr("app.dominio.contas.agora", lambda: now)

    def post(url, data):
        r = client.post(url, json=data)
        assert r.status_code == 200, r.text
        return r.json()

    def get(url):
        r = client.get(url)
        assert r.status_code == 200, r.text
        return r.json()

    expense = post('/categories', dict(name='Despesas', type='expense', color='#67C7A2', icon='•'))['id']
    income = post('/categories', dict(name='Outras entradas', type='income', color='#67C7A2', icon='+'))['id']
    investment = post('/categories', dict(name='Investimentos', type='investment', color='#A79AF5', icon='↗'))['id']
    aggregate = post('/accounts', dict(name='Saldo agregado', type='reconciliation'))['id']
    post(f'/accounts/{aggregate}/snapshots', dict(balance=684.39, observed_at='2026-10-11T21:45:00Z'))
    for name in ['Nubank', 'Mercado Pago']:
        post('/accounts', dict(name=name, type='checking'))
    restricted = post('/accounts', dict(name='Auxílio restrito', type='benefit', restricted=True))['id']
    post(f'/accounts/{restricted}/snapshots', dict(balance=300, observed_at='2026-10-11T21:45:00Z'))
    asset = post('/assets', dict(name='Caixinha Mercado Pago', asset_class='fixed_income'))['id']
    r = client.put('/assets/snapshots', json=dict(asset_id=asset, year=2026, month=10, value=0,
        reconciliation_note='Resgate usado na Hunter: valor/data/destino desconhecidos.'))
    assert r.status_code == 200, r.text
    post('/investments/movements', dict(asset_id=asset, category_id=investment,
        type='contribution', amount=800, date='2026-10-06'))

    def tx(description, amount, planned=False, category=expense, **extra):
        return post('/transactions', {**dict(description=description, date='2026-10-20', category_id=category,
            payment_method='cash', **{'amount_planned' if planned else 'amount_paid': amount}), **extra})['id']

    salary = tx('Salário recebido', 944.34, category=income, date='2026-10-06')
    advance = tx('Adiantamento', 720, True, income, date='2026-10-15')
    tx('Meta', 700, True, income)
    academy = tx('Assinaturas', 122.30, True, expense_class='fixed')
    other_subscription = tx('Assinaturas', 35, date='2026-09-01')
    internet = tx('Internet', 60, True, expense_class='fixed')
    quote = tx('Seguro da Hunter', 94, True, expense_class='fixed')
    quote_review = post('/reconciliation', dict(year=2026, month=10, kind='obrigacao',
        description='Proteção veicular', amount=94))['id']
    old = post('/reconciliation', dict(year=2026, month=10, kind='obrigacao',
        description='Emplacamento antigo', amount=908))['id']
    hunter = post('/commitments', dict(description='Hunter sintética', category_id=expense,
        amount=618.08, first_due='2026-11-09', installments=48, total_amount=13990))['id']
    mp = post('/cards', dict(name='Mercado Pago', closing_day=8, due_day=13, finalidade='pessoal'))['id']
    purchase = post('/purchases', dict(description='Documentação', card_id=mp, category_id=expense,
        total_amount=904, installments=4, purchase_date='2026-10-20', finalidade='pessoal'))['id']
    for name, purpose, values in [('Sergio','pessoal',[(15.17,1)]),
        ('Família','familia',[(561,5),(1820,10)]), ('SECCO','empresa',[(328.72,2),(121.40,1)])]:
        card = post('/cards', dict(name=name, closing_day=25, due_day=2, finalidade=purpose))['id']
        for value, installments in values:
            post('/purchases', dict(description=name, card_id=card, category_id=expense,
                total_amount=value, installments=installments, purchase_date='2026-09-23'))
        invoice = next(i for i in get('/invoices') if i['card_id']==card and i['month']==10)
        post(f"/invoices/{invoice['id']}/payments", dict(amount=invoice['remaining'], date='2026-10-06'))
        if purpose == 'pessoal':
            for value in [65.90,5.80]:
                post('/purchases', dict(description='Uber preservado', card_id=card, category_id=expense,
                    total_amount=value, installments=1, purchase_date='2026-10-13'))

    def build(with_old=True):
        ops=[]
        def update(model, identity, after):
            ops.append(dict(kind='update',table=model.__tablename__,id=identity,
                            expected=state(session.get(model,identity)),after=after))
        def insert(model, values, match):
            row=model.model_validate(dict(user_id=dono.id,**values))
            data=state(row)
            ops.append(dict(kind='insert',table=model.__tablename__,values=data,match={k:data[k] for k in match}))
        update(Transaction, advance, {'date':'2026-10-20'})
        update(Transaction, academy, {'description':'Academia'})
        update(Commitment, hunter, {'first_due':'2026-11-12','total_amount':16469.24})
        insert(AccountBalanceSnapshot, dict(account_id=aggregate, balance=668.96,
            observed_at='2026-10-19T11:44:15Z',source='manual'), ['account_id','observed_at'])
        for number in (1,2):
            insert(CommitmentSkip, dict(commitment_id=hunter,number=number,abated_on='2026-10-15'),['commitment_id','number'])
        insert(Transaction, dict(description='Reembolso pontual',date='2026-10-28',category_id=income,
            amount_planned=550,payment_method='cash'),['description'])
        update(Purchase,purchase,{'purchase_date':'2026-10-13'})
        txs=session.exec(select(Transaction).where(Transaction.purchase_id==purchase)).all()
        for t in txs:
            update(Transaction,t.id,{'date':dt.date(2026+(9+t.installment_no-1)//12,(9+t.installment_no-1)%12+1,13).isoformat()})
        if with_old: update(ReconciliationItem,old,{'status':'ignorado'})
        update(ReconciliationItem,quote_review,{'prefill':{'confirmed':False,'bill_visibility':'quote'}})
        ops.append(dict(kind='remove_prediction',table='transactions',id=quote,expected=state(session.get(Transaction,quote))))
        insert(ReconciliationItem,dict(year=2026,month=10,kind='outro',description='Resgate a conferir',
            source='reconciliacao_outubro_2026_resgate'),['year','month','source'])
        for op in ops:
            op.update(reason='Fato confirmado pelo titular',evidence='Fixture sintética do pedido',
                      confidence='alta',cash_effect='Não cria saída de caixa')
        return dict(user_id=dono.id,period='2026-10',baseline_sha256=fingerprint(session,dono),operations=ops)

    def apply(plan):
        report=reconcile(session,dono,plan,True)
        session.commit()
        return report
    return locals()


@pytest.mark.parametrize('removed',[False,True])
def test_reconciliacao_direcionada_preserva_caixa_parcelas_e_idempotencia(case, removed):
    w=case; s=w['session']; c=w['client']; get=w['get']
    if removed:
        assert c.delete(f"/reconciliation/{w['old']}").status_code==200
    plan=w['build'](not removed)
    before=get('/budgets/summary?year=2026&month=10')['caixa']
    ids={t.id for t in s.exec(select(Transaction).where(Transaction.purchase_id==w['purchase'])).all()}
    original=fingerprint(s,w['dono'])
    assert reconcile(s,w['dono'],plan)['changes']
    assert fingerprint(s,w['dono'])==original  # seco nem avança dados/auditoria
    report=w['apply'](plan)
    assert report['backup'] and report['backup_sha256']
    assert fingerprint(s,w['dono'])!=original
    after=get('/budgets/summary?year=2026&month=10')['caixa']
    assert before==after
    assert after['entrou']==944.34 and after['investido']==800
    assert after['faturas_pagas']==pytest.approx(595.13)
    txs=s.exec(select(Transaction).where(Transaction.purchase_id==w['purchase'])).all()
    assert {t.id for t in txs}==ids and sorted(t.amount_paid for t in txs)==[226]*4
    invoice_ids={t.invoice_id for t in txs}
    invoices=[i for i in get('/invoices') if i['id'] in invoice_ids]
    assert sorted(i['due_date'] for i in invoices)==['2026-11-13','2026-12-13','2027-01-13','2027-02-13']
    assert all(i['paid']==0 for i in invoices)
    summary=get('/months/summary?year=2026&month=10')
    assert (summary['money_now'],summary['to_receive'],summary['to_pay'])==(668.96,1970,182.3)
    assert summary['partial'] and summary['projected'] is None
    assert len(get('/accounts'))==4 and get('/accounts/summary')['restricted']==300
    assert s.get(Transaction,w['salary']).amount_paid==944.34
    assert s.get(Transaction,w['academy']).description=='Academia'
    assert s.get(Transaction,w['academy']).amount_planned==122.3
    assert s.get(Transaction,w['other_subscription']).description=='Assinaturas'
    assert not any(t.description=='Academia' and t.amount_planned==120 for t in s.exec(select(Transaction)).all())
    assert s.get(Transaction,w['quote']) is None
    review=get('/reconciliation?year=2026&month=10')['items']
    assert len([r for r in summary['review'] if r['amount']==94])==1
    assert not any(i['remaining']==94 for i in summary['due'])
    if removed: assert not any(r['description']=='Emplacamento antigo' for r in review)
    else: assert s.get(ReconciliationItem,w['old']).status.value=='ignorado'
    hunter=get(f"/commitments/{w['hunter']}")['schedule']
    assert [i['status'] for i in hunter[:3]]==['abatida','abatida','pendente']
    assert hunter[2]['due_date']=='2027-01-12'
    assert not any(t.commitment_id==w['hunter'] for t in s.exec(select(Transaction)).all())
    for month in (11,12):
        month_summary=get(f'/months/summary?year=2026&month={month}')
        assert not any(i['commitment_id']==w['hunter'] for i in month_summary['due'])
    assert not any(t.amount_paid==251.84 or t.amount_planned==251.84 for t in s.exec(select(Transaction)).all())
    inv=get('/investments/summary?year=2026&month=10')
    assert inv['contributed']==800 and inv['redeemed']==0 and inv['yield_status']=='nao_apurado'
    assert inv['yield_amount'] is None
    counts=fingerprint(s,w['dono'])
    repeat=w['apply'](plan)
    assert repeat['changes']==[] and repeat['backup'] is None
    assert fingerprint(s,w['dono'])==counts
    assert len(s.exec(select(AuditEvent).where(AuditEvent.action=='reconciliacao.outubro_2026')).all())==1
    # Auditoria guarda a previsão retirada; nenhuma linha realizada desaparece.
    event=s.exec(select(AuditEvent).where(AuditEvent.action=='reconciliacao.outubro_2026')).one()
    deletion=next(d for d in event.details['changes'] if d['kind']=='remove_prediction')
    assert deletion['before']['amount_planned']==94 and deletion['before']['amount_paid'] is None


def test_precondicoes_recusam_novidades_e_futuro_saldo_sem_escrita(case):
    w=case; plan=w['build'](); s=w['session']
    w['post'](f"/accounts/{w['aggregate']}/snapshots",dict(balance=900,observed_at='2026-10-20T11:00:00Z'))
    before=fingerprint(s,w['dono'])
    with pytest.raises(ValueError,match='saldo posterior'):
        w['apply'](plan)
    assert fingerprint(s,w['dono'])==before


def test_recebimento_posterior_nao_e_sobrescrito(case):
    w=case; s=w['session']; c=w['client']; plan=w['build']()
    r=c.patch(f"/transactions/{w['advance']}",json={'amount_paid':720,'amount_planned':None})
    assert r.status_code==200,r.text
    before=fingerprint(s,w['dono'])
    with pytest.raises(ValueError,match='realizado'):
        w['apply'](plan)
    assert fingerprint(s,w['dono'])==before


def test_cotacao_realizada_nao_pode_ser_retirada(case):
    w=case; s=w['session']; plan=w['build']()
    assert w['client'].patch(f"/transactions/{w['quote']}",json={'amount_paid':94}).status_code==200
    before=fingerprint(s,w['dono'])
    with pytest.raises(ValueError,match='Nunca retirar'):
        w['apply'](plan)
    assert fingerprint(s,w['dono'])==before


def test_compra_com_fatura_paga_aborta_antes_de_gravar(case):
    w=case; s=w['session']; plan=w['build']()
    tx=s.exec(select(Transaction).where(Transaction.purchase_id==w['purchase'])).first()
    w['post'](f'/invoices/{tx.invoice_id}/payments',dict(date='2026-10-20',amount=226))
    before=fingerprint(s,w['dono'])
    with pytest.raises(ValueError,match='fatura paga'):
        w['apply'](plan)
    assert fingerprint(s,w['dono'])==before


def test_mudanca_de_ciclo_exige_conferencia_sem_mover_faturas(case):
    w=case; s=w['session']; plan=w['build']()
    for op in plan['operations']:
        if op['kind']=='update' and op['table']=='purchases': op['after']['purchase_date']='2026-10-01'
        if op['kind']=='update' and op['table']=='transactions' and op['expected']['purchase_id']==w['purchase']:
            op['after']['date']=op['after']['date'][:-2]+'01'
    before=fingerprint(s,w['dono'])
    with pytest.raises(ValueError,match='mudaria ciclo'):
        w['apply'](plan)
    assert fingerprint(s,w['dono'])==before


def test_estado_alterado_fora_dos_alvos_tambem_aborta(case):
    w=case; plan=w['build'](); s=w['session']
    assert w['client'].patch(f"/transactions/{w['internet']}",json={'amount_paid':60}).status_code==200
    before=fingerprint(s,w['dono'])
    with pytest.raises(ValueError,match='alterações desde o plano'):
        w['apply'](plan)
    assert fingerprint(s,w['dono'])==before


def test_isolamento_do_titular_recusa_id_de_outra_conta(case,criar_usuario):
    w=case; s=w['session']
    other=criar_usuario('outra@exemplo.com','Outra','senha-ficticia-1234')
    category=Category(user_id=other.id,name='Assinaturas',type='expense',color='#67C7A2',icon='•')
    s.add(category); s.commit(); s.refresh(category)
    tx=Transaction(user_id=other.id,description='Assinaturas',date=dt.date(2026,10,20),
                   amount_planned=122.30,category_id=category.id)
    s.add(tx); s.commit(); s.refresh(tx)
    original=state(tx)
    plan=w['build']()
    op=next(o for o in plan['operations'] if o.get('id')==w['academy'] and o['table']=='transactions')
    op['id']=tx.id
    op['expected']={**original,'user_id':w['dono'].id}
    before=fingerprint(s,w['dono'])
    with pytest.raises(ValueError,match='precondição'):
        w['apply'](plan)
    assert fingerprint(s,w['dono'])==before and state(s.get(Transaction,tx.id))==original


def test_fontes_das_cinco_abas_e_finalidades_permanecem_coerentes(case):
    w=case; w['apply'](w['build']()); get=w['get']
    summary=get('/months/summary?year=2026&month=10')
    budget=get('/budgets/summary?year=2026&month=10')['caixa']
    investment=get('/investments/summary?year=2026&month=10')
    series=get('/reports/monthly?from=2026-10&to=2026-10')['months'][0]
    assert series['income']==budget['entrou']
    assert series['expense']==budget['gasto_total']
    assert series['cash_flow']==budget['carteira']
    assert summary['contributed']==investment['contributed']==budget['investido']
    assert summary['to_pay']==sum(i['remaining'] for i in summary['due'])
    txs=get('/transactions?year=2026&month=10')
    for purpose in ('pessoal','familia','empresa'):
        report=get('/reports/categories?year=2026&month=10&finalidade='+purpose)
        expected=sum(t['amount_paid'] or 0 for t in txs if t['category_id']==w['expense'] and t['finalidade']==purpose)
        assert report['total']==pytest.approx(expected)
        filtered=get('/reports/monthly?from=2026-10&to=2026-10&finalidade='+purpose)['months'][0]
        assert filtered['cash_flow']==series['cash_flow']  # finalidade filtra gasto, nunca saldo de terceiros
    assert w['academy'] not in summary['paid_cash_ids'] and w['internet'] not in summary['paid_cash_ids']
    assert {w['academy'],w['internet']} <= {i['transaction_id'] for i in summary['due']}


def test_variavel_prevista_integra_a_pagar_sem_virar_gasto_ou_pagamento(case):
    w=case; w['apply'](w['build']()); get=w['get']
    before=get('/months/summary?year=2026&month=10')
    cash=get('/budgets/summary?year=2026&month=10')['caixa']
    variable=w['tx']('Despesa variável prevista',37,True,expense_class='variable')
    after=get('/months/summary?year=2026&month=10')
    assert after['money_now']==before['money_now']
    assert after['to_pay']==before['to_pay']+37
    assert variable in {i['transaction_id'] for i in after['due']}
    assert variable not in after['paid_cash_ids']
    assert get('/budgets/summary?year=2026&month=10')['caixa']==cash


def test_resumo_historico_nao_herda_saldos_ou_movimentos_de_meses_posteriores(case,monkeypatch):
    w=case; get=w['get']; w['apply'](w['build']())
    september=get('/months/summary?year=2026&month=9')
    assert september['money_now'] is None and september['balance_date'] is None
    assert september['month']['opening']==0
    now=dt.datetime(2026,11,20,15,tzinfo=dt.timezone.utc)
    monkeypatch.setattr('app.planejamento.hoje',lambda:now.date())
    monkeypatch.setattr('app.dominio.tempo.hoje_local',lambda:now.date())
    monkeypatch.setattr('app.dominio.tempo.agora',lambda:now)
    monkeypatch.setattr('app.dominio.contas.agora',lambda:now)
    w['post'](f"/accounts/{w['aggregate']}/snapshots",dict(balance=900,observed_at='2026-11-02T11:00:00Z'))
    w['tx']('Recebido em novembro',100,category=w['income'],date='2026-11-03',account_id=w['aggregate'])
    w['tx']('Saída sem conta em novembro',17,date='2026-11-04')
    october=get('/months/summary?year=2026&month=10')
    assert october['money_now']==668.96 and october['balance_date']=='2026-10-19'
    assert october['plan']['balance_warning']['quantidade']==0
    assert get('/months/summary?year=2026&month=11')['money_now']==1000
    assert get('/assets/summary?year=2026&month=10')['accounts_total']==968.96  # inclui R$300 restritos, fora do livre


def test_semanticamente_mesma_previsao_nao_vira_saldo_duas_vezes(case):
    w=case; w['apply'](w['build']()); get=w['get']; c=w['client']
    refund=next(t for t in get('/transactions?year=2026&month=10') if t['description']=='Reembolso pontual')
    assert refund['amount_paid'] is None
    before=get('/months/summary?year=2026&month=10')
    for _ in range(2):
        r=c.patch(f"/transactions/{refund['id']}",json=dict(date='2026-10-20',amount_paid=550,
            amount_planned=None,account_id=w['aggregate'],occurred_at='2026-10-20T15:00:00Z'))
        assert r.status_code==200,r.text
    after=get('/months/summary?year=2026&month=10')
    assert after['money_now']==before['money_now']+550 and after['to_receive']==1420
    assert get('/budgets/summary?year=2026&month=10')['caixa']['entrou']==1494.34


def test_aporte_previsto_nao_e_consumo_nem_posicao_e_confirma_uma_vez(case):
    w=case; w['apply'](w['build']()); get=w['get']; c=w['client']
    before=get('/months/summary?year=2026&month=10')
    cash_before=get('/budgets/summary?year=2026&month=10')['caixa']
    assets=get('/assets/summary?year=2026&month=10')
    p=w['post']('/investments/plans',dict(type='contribution',amount=400,date='2026-10-28',
        asset_id=w['asset'],account_id=w['aggregate'],category_id=w['investment']))
    assert get('/months/summary?year=2026&month=10')['money_now']==before['money_now']
    assert get('/months/summary?year=2026&month=10')['to_invest']==400
    assert get('/assets/summary?year=2026&month=10')==assets
    data={k:p[k] for k in ['type','amount','date','asset_id','account_id','category_id','description']}
    assert c.patch(f"/investments/plans/{p['id']}",json={**data,'amount':350}).status_code==200
    results=[w['post'](f"/investments/plans/{p['id']}/confirm",dict(date='2026-10-20')) for _ in range(2)]
    assert results[0]['movement_id']==results[1]['movement_id']
    assert get('/months/summary?year=2026&month=10')['money_now']==pytest.approx(before['money_now']-350)
    budget=get('/budgets/summary?year=2026&month=10')['caixa']
    assert budget['gasto_total']==cash_before['gasto_total']
    assert budget['entrou']==944.34
    p2=w['post']('/investments/plans',dict(type='contribution',amount=400,date='2026-10-28'))
    realized=get('/investments/movements')
    w['post'](f"/investments/plans/{p2['id']}/cancel",{})
    assert get('/investments/movements')==realized


@pytest.mark.parametrize('url,env',[
    ('postgresql://owner:dummy@remote.neon.tech/db','production'),
    ('postgresql://postgres@127.0.0.1:54329/financeiro_cotidiano','test'),
    ('postgresql://postgres@127.0.0.1:54329/sentavos_reconciliacao_20261020','production'),
])
def test_producao_e_banco_local_cotidiano_bloqueados(url,env):
    with pytest.raises(ValueError): local_only(url,env)
