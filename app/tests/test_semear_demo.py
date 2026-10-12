"""O demo público continua coerente com as regras: o que ele mostra no mês
corrente é o que o app diria de uma conta de verdade com os mesmos dados.

Roda o gerador de verdade (sem subprocess) num SQLite de teste. O "hoje" é o
do Brasil nos dois lados (gerador e app), então o teste não depende do fuso de
quem roda.
"""

from app.dominio.tempo import hoje_local
from scripts.semear_demo import semear


def test_demo_mes_corrente(session, criar_usuario, cliente_de):
    demo = criar_usuario("demo@exemplo.com", "Demo", "senha-do-demo-12345", read_only=True)
    semear(demo, session)
    c = cliente_de(demo)
    hoje = hoje_local()
    mes = {"year": hoje.year, "month": hoje.month}

    contas = c.get("/accounts/summary").json()
    assert sorted(a["name"] for a in contas["accounts"]) == ["Carteira digital", "Conta corrente"]
    assert contas["unassigned_movements"] == 0
    # A transferência não cria nem some com dinheiro.
    saldos = {a["name"]: a["balance"] for a in contas["accounts"]}
    assert round(sum(saldos.values()), 2) == contas["total"]

    inv = c.get("/investments/summary", params=mes).json()
    assert (inv["contributed"], inv["redeemed"], inv["unlinked"]) == (600.0, 300.0, 0)
    rendeu = {i["name"]: (i["yield_status"], i["yield_amount"]) for i in inv["items"]}
    assert rendeu["Reserva de emergência"] == ("apurado", 52.0)
    assert rendeu["Tesouro Selic"] == ("apurado", 95.0)

    caixa = c.get("/budgets/summary", params=mes).json()["caixa"]
    assert caixa["aquisicoes"] == 1850.0
    assert round(caixa["custo_de_vida"] + caixa["aquisicoes"] + caixa["financeiro"], 2) == caixa["gasto_total"]

    codigos = {i["code"] for i in c.get(f"/months/{hoje:%Y-%m}/health").json()["issues"]}
    assert not codigos & {"MISSING_ACCOUNT", "UNLINKED_INVESTMENT", "BALANCE_DIFFERENCE"}

    # O ativo antigo saiu do mês corrente: o patrimônio não conta a conta duas vezes.
    pat = c.get("/assets/summary", params=mes).json()
    assert "Conta corrente" not in {i["name"] for i in pat["items"]}
    assert {a["name"] for a in pat["accounts"]} == {"Conta corrente", "Carteira digital"}

    # E continua somente-leitura.
    assert c.post("/accounts", json={"name": "X", "type": "cash"}).status_code == 403
