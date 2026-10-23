"""Regressões de outubro: dados fictícios, sem confirmar saldo bancário real."""
import datetime as dt

import pytest
from sqlmodel import select

from app.models import AuditEvent, Transaction
from scripts.reconciliar_outubro_2026 import fingerprint, reconcile, state

NOW = dt.datetime(2026, 10, 23, 21, tzinfo=dt.timezone.utc)


@pytest.fixture
def caso(client, monkeypatch):
    for name in ("app.dominio.tempo.agora", "app.dominio.contas.agora"):
        monkeypatch.setattr(name, lambda: NOW)
    for name in ("app.planejamento.hoje", "app.dominio.tempo.hoje_local"):
        monkeypatch.setattr(name, lambda: NOW.date())

    def post(path, **data):
        r = client.post(path, json=data)
        assert r.status_code == 200, r.text
        return r.json()

    expense = post("/categories", name="Despesas", type="expense", color="#c5b289", icon="x")["id"]
    income = post("/categories", name="Entradas", type="income", color="#c5b289", icon="x")["id"]
    invest = post("/categories", name="Investimentos", type="investment", color="#c5b289", icon="x")["id"]
    account = post("/accounts", name="Nubank", type="checking")["id"]
    asset = post("/assets", name="Caixinha Nubank", asset_class="fixed_income")["id"]
    return client, post, expense, income, invest, account, asset


def month(c):
    return c.get("/months/summary?year=2026&month=10").json()


def investment(c):
    return c.get("/investments/summary?year=2026&month=10").json()


def observed(c, asset, value, day, **extra):
    r = c.put("/assets/snapshots", json=dict(asset_id=asset, year=2026, month=10,
        value=value, observed_on=f"2026-10-{day:02d}", **extra))
    assert r.status_code == 200, r.text
    return r.json()


def test_reembolso_ja_incluido_no_saldo_nao_entra_duas_vezes(caso):
    c, post, _, income, _, account, _ = caso
    post("/transactions", description="Santander recebido", date="2026-10-22", category_id=income,
         amount_paid=551, account_id=account, payment_method="cash", occurred_at="2026-10-22T14:00:00Z")
    post(f"/accounts/{account}/snapshots", balance=1214.71, observed_at="2026-10-22T15:00:00Z")
    assert month(c)["money_now"] == 1214.71
    assert c.get(f"/accounts/{account}").json()["movements_after"] == 0
    assert month(c)["balance_kind"] == "observado"


def test_saldo_antigo_e_movimentos_sem_conta_explicam_limite(caso):
    c, post, _, income, _, account, _ = caso
    post(f"/accounts/{account}/snapshots", balance=684.39, observed_at="2026-10-11T21:45:00Z")
    post("/transactions", description="Recebimento sem banco", date="2026-10-22", category_id=income, amount_paid=720)
    r = month(c)
    assert r["money_now"] == 684.39 and r["balance_date"] == "2026-10-11"
    assert r["balance_pending"] and r["projected"] is None
    assert c.get("/accounts/summary").json()["maybe_incomplete"]


@pytest.mark.parametrize("assigned", [True, False])
def test_mesmo_dia_sem_hora_e_pendente_sem_somar_reembolso(caso, assigned):
    c, post, _, income, _, account, _ = caso
    post(f"/accounts/{account}/snapshots", balance=1214.71, observed_at="2026-10-22T15:00:00Z")
    post("/transactions", description="Recebimento sem hora", date="2026-10-22", category_id=income,
         amount_paid=551, account_id=account if assigned else None)
    r = month(c)
    assert r["money_now"] == 1214.71 and r["balance_pending"] and r["projected"] is None


def test_futuro_sem_conta_nao_contamina_qualidade_de_hoje(caso):
    c, post, expense, _, _, account, _ = caso
    post(f"/accounts/{account}/snapshots", balance=1000, observed_at="2026-10-22T15:00:00Z")
    post("/transactions", description="Futuro indevido", date="2026-10-28", category_id=expense, amount_paid=100)
    assert c.get("/accounts/summary").json()["unassigned_movements"] == 0
    assert month(c)["balance_pending"] is False


def test_agregado_e_conta_individual_nao_prometem_total_duplicado(caso):
    c, post, _, _, _, account, _ = caso
    aggregate = post("/accounts", name="Saldo agregado", type="reconciliation")["id"]
    for aid in (aggregate, account):
        post(f"/accounts/{aid}/snapshots", balance=668.96, observed_at="2026-10-22T15:00:00Z")
    r = month(c)
    assert r["money_now"] is None and r["projected"] is None and r["balance_pending"]
    assert any("agregado" in reason for reason in r["reasons"])
    assert c.get("/accounts/summary").json()["possible_overlap"]
    # O titular pode excluir explicitamente o agregado do dinheiro livre.
    assert c.patch(f"/accounts/{aggregate}", json={"include_in_planning":False}).status_code == 200
    r = month(c)
    assert r["money_now"] == 668.96 and r["balance_pending"] is False


@pytest.mark.parametrize("day,pending", [(22, True), (23, True), (24, False)])
def test_aporte_550_e_posicao_observada_sao_independentes(caso, day, pending):
    c, post, _, _, invest, account, asset = caso
    post(f"/accounts/{account}/snapshots", balance=1214.71, observed_at="2026-10-22T15:00:00Z")
    post("/investments/movements", type="contribution", amount=550, date="2026-10-23",
         asset_id=asset, account_id=account, category_id=invest, occurred_at=NOW.isoformat())
    observed(c, asset, 550 if day >= 23 else 0, day)
    r = investment(c)
    assert r["contributed"] == 550 and r["redeemed"] == 0
    assert r["items"][0]["position_pending"] is pending
    assert r["total"] == (550 if day >= 23 else 0)  # nunca 1100
    assert month(c)["money_now"] == 664.71
    assert c.get("/budgets/summary?year=2026&month=10").json()["caixa"]["gasto_total"] == 0


def test_aporte_previsto_confirmado_uma_vez_sem_inventar_posicao(caso):
    c, post, _, _, invest, account, asset = caso
    post(f"/accounts/{account}/snapshots", balance=1214.71, observed_at="2026-10-22T15:00:00Z")
    p = post("/investments/plans", type="contribution", amount=550, date="2026-10-23",
             asset_id=asset, account_id=account, category_id=invest)
    assert investment(c)["contributed"] == 0 and month(c)["money_now"] == 1214.71
    first = post(f"/investments/plans/{p['id']}/confirm", date="2026-10-23")
    assert post(f"/investments/plans/{p['id']}/confirm", date="2026-10-23")["movement_id"] == first["movement_id"]
    assert len(c.get("/investments/movements").json()) == 1
    r = investment(c)
    assert r["contributed"] == 550 and r["items"][0]["has_observation"] is False and r["position_pending"]
    health = c.get("/months/2026-10/health").json()
    assert health["state"] != "conciliado"
    assert any(i["code"] == "INVESTMENT_BALANCE_PENDING" for i in health["issues"])
    post(f"/accounts/{account}/snapshots", balance=664.71, observed_at="2026-10-23T21:01:00Z")
    assert month(c)["money_now"] == 664.71  # já inclui o aporte


def test_mercado_pago_preserva_800_zero_observado_resgate_desconhecido(caso):
    c, post, _, _, invest, account, asset = caso
    mp = post("/assets", name="Caixinha Mercado Pago", asset_class="fixed_income")["id"]
    post("/investments/movements", type="contribution", amount=800, date="2026-10-06", asset_id=mp, category_id=invest)
    observed(c, mp, 0, 22, reconciliation_note="Hunter: resgate sem valor/data comprovados")
    post("/investments/movements", type="contribution", amount=550, date="2026-10-23",
         asset_id=asset, account_id=account, category_id=invest)
    r = investment(c)
    assert (r["contributed"], r["redeemed"], r["yield_amount"]) == (1350, 0, None)
    assert next(i for i in r["items"] if i["asset_id"] == mp)["value"] == 0


def family(c, post, expense):
    card = post("/cards", name="Nubank Família", closing_day=25, due_day=2, finalidade="familia")["id"]
    purchase = post("/purchases", description="Consultório Michele", card_id=card, category_id=expense,
                    total_amount=561, installments=5, purchase_date="2026-09-10")
    rows = c.get("/transactions?year=2026&month=10").json()
    row = next(t for t in rows if t["purchase_id"] == purchase["id"] and t["installment_no"] == 2)
    return card, purchase, row


def test_responsabilidade_parcela_familia_sem_mover_compra_ou_pagar_fatura(caso, session):
    c, post, expense, _, _, account, _ = caso
    card, purchase, row = family(c, post, expense)
    post(f"/accounts/{account}/snapshots", balance=1000, observed_at="2026-10-22T15:00:00Z")
    for _ in range(2):
        r = c.patch(f"/transactions/{row['id']}/responsabilidade", json={"finalidade": "pessoal"})
        assert r.status_code == 200, r.text
    assert r.json()["card_id"] == card and r.json()["amount_paid"] == 112.2
    assert c.get(f"/purchases/{purchase['id']}").json()["finalidade"] == "familia"
    # Editar descrição da compra não pode apagar a responsabilidade individual.
    assert c.patch(f"/purchases/{purchase['id']}", json={"description": "Consultório Michele preservado"}).status_code == 200
    rows = session.exec(select(Transaction).where(Transaction.purchase_id == purchase["id"])).all()
    assert [t.installment_no for t in rows if t.finalidade == "pessoal"] == [2]
    assert len(session.exec(select(AuditEvent).where(AuditEvent.action == "parcela.responsabilidade")).all()) == 1
    assert c.get(f"/invoices/{row['invoice_id']}").json()["paid"] == 0
    assert month(c)["money_now"] == 1000


def test_pagamento_parcial_familia_e_transferencia_sao_fluxos_distintos(caso):
    c, post, expense, _, _, account, _ = caso
    card, _, row = family(c, post, expense)
    post("/purchases", description="Outra compra Família", card_id=card, category_id=expense,
         total_amount=200, installments=1, purchase_date="2026-10-01")
    post(f"/accounts/{account}/snapshots", balance=1000, observed_at="2026-10-22T15:00:00Z")
    other = post("/accounts", name="Conta destino sob mesmo titular", type="checking")["id"]
    post("/transfers", from_account_id=account, to_account_id=other, amount=112.2, date="2026-10-23", occurred_at=NOW.isoformat())
    assert c.get(f"/invoices/{row['invoice_id']}").json()["paid"] == 0
    post(f"/invoices/{row['invoice_id']}/payments", amount=112.2, date="2026-10-23", account_id=account, occurred_at=NOW.isoformat())
    inv = c.get(f"/invoices/{row['invoice_id']}").json()
    assert inv["remaining"] == 200 and inv["status"] != "paga"
    assert month(c)["money_now"] == 775.6  # duas operações reais distintas


def test_tres_compras_pessoais_uma_parcela_por_compra_sem_reduzir_caixa(caso):
    c, post, expense, _, _, account, _ = caso
    post(f"/accounts/{account}/snapshots", balance=1214.71, observed_at="2026-10-22T15:00:00Z")
    card = post("/cards", name="Nubank pessoal", closing_day=25, due_day=2, finalidade="pessoal")["id"]
    ids = []
    for description, amount in [("Transporte", 60.85), ("Patinetes Jet", 22.17), ("Almoço com Bia", 40)]:
        ids.append(post("/purchases", description=description, total_amount=amount, installments=1,
                        purchase_date="2026-10-23", card_id=card, category_id=expense)["id"])
    rows = c.get("/transactions?year=2026&month=10").json()
    assert len(rows) == 3 and {t["purchase_id"] for t in rows} == set(ids)
    assert all(t["payment_method"] == "credit" and t["account_id"] is None for t in rows)
    inv = c.get(f"/invoices/{rows[0]['invoice_id']}").json()
    assert inv["total"] == 123.02 and inv["due_date"] == "2026-11-02"
    assert month(c)["money_now"] == 1214.71


def test_script_responsabilidade_seco_idempotente_com_precondicao(caso, session, dono):
    c, post, expense, _, _, _, _ = caso
    _, _, row = family(c, post, expense)
    original = session.get(Transaction, row["id"])
    op = dict(kind="update", table="transactions", id=original.id, expected=state(original),
              after={"finalidade": "pessoal"}, reason="Responsabilidade da parcela 2/5",
              evidence="Fixture sintética; não é comprovante real", confidence="confirmado na fixture", cash_effect="nenhum")
    plan = dict(user_id=dono.id, period="2026-10", baseline_sha256=fingerprint(session, dono), operations=[op])
    dry = reconcile(session, dono, plan)
    assert dry["dry_run"] and len(dry["changes"]) == 1 and original.finalidade == "familia"
    applied = reconcile(session, dono, plan, apply=True)
    # A CLI confirma a conexão externa: o evento já deve estar no banco antes
    # de um Session.commit (autoflush=False impede um falso positivo no teste).
    with session.no_autoflush:
        assert session.exec(select(AuditEvent).where(AuditEvent.action == "reconciliacao.outubro_2026")).first() is not None
    session.commit()
    assert applied["backup"] and original.finalidade == "pessoal"
    assert reconcile(session, dono, plan, apply=True)["changes"] == []
    original.note = "Divergência depois do plano"
    session.add(original)
    session.commit()
    with pytest.raises(ValueError, match="precondição"):
        reconcile(session, dono, plan, apply=True)


def test_responsabilidade_isola_usuario_e_somente_leitura(caso, criar_usuario, cliente_de):
    c, post, expense, _, _, _, _ = caso
    _, _, row = family(c, post, expense)
    other = criar_usuario("outro-saldos@local.test", "Outro", "senha-local-segura")
    assert cliente_de(other).patch(f"/transactions/{row['id']}/responsabilidade", json={"finalidade":"pessoal"}).status_code == 404
    demo = criar_usuario("demo-saldos@local.test", "Demo", "senha-local-segura", read_only=True)
    assert cliente_de(demo).patch(f"/transactions/{row['id']}/responsabilidade", json={"finalidade":"pessoal"}).status_code == 403
