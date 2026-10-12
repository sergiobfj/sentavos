"""O script de migração assistida: seco não grava, aplicar é idempotente,
desfazer devolve o estado anterior — e um id trocado no plano para tudo.

Roda o `Plano` direto na sessão de teste (sem subprocess nem backup): o que se
testa é a regra de cada ação, não o argparse.
"""

import datetime as dt

import pytest
from sqlmodel import select

from app.models import AuditEvent
from app.tests.apoio_planejamento import Montagem
from scripts.foundation_v3 import Plano

HOJE = dt.date(2026, 10, 11)
D = dt.date


@pytest.fixture(name="m")
def montagem(client, monkeypatch):
    monkeypatch.setattr("app.planejamento.hoje", lambda: HOJE)
    return Montagem(client)


@pytest.fixture(name="base")
def outubro(m):
    moto = m.categoria("Moto")
    invest = m.categoria("Investimento", "investment")
    entrada = m.lancar(moto, D(2026, 10, 10), pago=7000.0, descricao="Entrada da Hunter 350")
    hunter = m.compromisso(moto, 618.08, D(2026, 10, 5), parcelas=48, descricao="Financiamento Hunter 350")
    m.pagar(hunter["id"], 1, D(2026, 10, 5))
    aporte = m.lancar(invest, D(2026, 10, 6), pago=800.0, descricao="Caixinha - Mercado Pago")
    m.conta("Mercado Pago", 0.0, classe="fixed_income")
    m.conta("Saldo agregado", 684.39, dia=D(2026, 10, 11))
    return {
        "acoes": [
            {"tipo": "criar_conta", "name": "Nubank", "type": "checking"},
            {"tipo": "agregado_para_conta", "asset": "Saldo agregado", "observed_at": "2026-10-11T18:45:00-03:00"},
            {"tipo": "renomear_ativo", "asset": "Mercado Pago", "name": "Caixinha Mercado Pago"},
            # Usa o nome NOVO: no seco o renome não foi gravado e ainda assim resolve.
            {"tipo": "movimento_investimento", "transaction_id": aporte["id"], "asset": "Caixinha Mercado Pago",
             "type": "contribution"},
            {"tipo": "natureza_lancamento", "transaction_id": entrada["id"], "nature": "asset_acquisition",
             "confere": {"amount_paid": 7000.0, "description": "Entrada da Hunter 350"}},
            {"tipo": "natureza_compromisso", "commitment_id": hunter["id"], "nature": "financial",
             "confere": {"amount": 618.08}},
        ],
    }


def caixa(m) -> dict:
    return m.c.get("/budgets/summary", params={"year": 2026, "month": 10}).json()["caixa"]


def rodar(session, dono, acoes, aplicar=True, desfazer=False) -> int:
    p = Plano(session, dono, aplicar)
    p.desfazer() if desfazer else p.executar(acoes)
    if aplicar:
        session.commit()
    else:
        session.rollback()
    return p.feitas


def test_seco_nao_grava(m, base, session, dono):
    antes = caixa(m)
    assert rodar(session, dono, base["acoes"], aplicar=False) == 0
    assert caixa(m) == antes
    assert m.c.get("/accounts").json() == []


def test_aplicar_desfazer_e_idempotencia(m, base, session, dono):
    antes = caixa(m)
    assert rodar(session, dono, base["acoes"]) == 6
    depois = caixa(m)
    # Natureza não muda o gasto total nem o saldo do mês.
    assert (depois["gasto_total"], depois["carteira"]) == (antes["gasto_total"], antes["carteira"])
    assert (depois["custo_de_vida"], depois["aquisicoes"], depois["financeiro"]) == (0.0, 7000.0, 618.08)
    assert {c["name"] for c in m.c.get("/accounts").json()} == {"Nubank", "Saldo agregado"}

    assert rodar(session, dono, base["acoes"]) == 0  # de novo: nada a fazer

    rodar(session, dono, [], desfazer=True)
    assert caixa(m) == antes
    assert m.c.get("/accounts").json() == []
    assert {a["name"] for a in m.c.get("/assets").json()} == {"Mercado Pago", "Saldo agregado"}
    assert rodar(session, dono, [], desfazer=True) == 0  # desfazer de novo: nada
    # Nada some do rastro: o que foi feito e o que foi desfeito ficam.
    assert session.exec(select(AuditEvent).where(AuditEvent.action == "foundation_v3.desfeito")).all()


def test_id_trocado_no_plano_para_sem_gravar(m, base, session, dono):
    errada = dict(base["acoes"][4], confere={"amount_paid": 500.61})
    with pytest.raises(SystemExit, match="o plano esperava"):
        rodar(session, dono, [errada])
    session.rollback()
    assert caixa(m)["aquisicoes"] == 0.0
