"""Simular mês: saldo + entradas − saídas, e o que NÃO pode entrar nessa conta.

O que este arquivo protege é a separação entre quatro coisas — realizado,
compromisso, reserva e simulação. Cada teste é uma forma de uma delas vazar pra
outra: a receita recebida contada de novo como futura, a hipótese que vira
lançamento, a reserva que derruba o patrimônio.
"""

import datetime as dt

import pytest

from app.tests.apoio_planejamento import HOJE, Montagem, item

D = dt.date


@pytest.fixture(name="m")
def montagem(client, monkeypatch):
    monkeypatch.setattr("app.planejamento.hoje", lambda: HOJE)
    return Montagem(client)


def test_saldo_atual_mais_entradas_menos_saidas(m):
    m.conta("Banco", 1000.0, dia=D(2026, 10, 8))
    salario = m.categoria("Salário", "income")
    casa = m.categoria("Casa")
    financiamento = m.categoria("Financiamento")

    m.lancar(salario, D(2026, 10, 15), previsto=720.0, descricao="Adiantamento")
    m.lancar(casa, D(2026, 10, 20), previsto=60.0, descricao="Internet")
    m.compromisso(financiamento, 200.0, D(2026, 10, 25), parcelas=3)

    mes = m.mes()["months"][0]
    assert mes["opening"] == 1000.0
    assert mes["income"] == 720.0
    assert mes["expense"] == 260.0
    assert mes["projected"] == 1460.0
    assert mes["reserved"] == 0.0
    assert mes["available"] == 1460.0
    # O grau de certeza não se mistura: o compromisso é confirmado, o previsto
    # avulso é estimativa.
    assert mes["by_certainty"]["confirmado"] == 200.0
    assert mes["by_certainty"]["estimado"] == 60.0
    assert mes["by_source"]["parcelado"] == 200.0
    assert mes["by_source"]["previsto"] == 60.0


def test_receita_recebida_nao_entra_de_novo(m):
    """O salário que já caiu está no saldo; somá-lo como futuro seria contar duas vezes."""
    m.conta("Banco", 1500.0, dia=HOJE)
    salario = m.categoria("Salário", "income")
    recebido = m.lancar(salario, D(2026, 10, 6), pago=944.34, descricao="Salário")

    # A recorrência do salário (estimada) tem uma ocorrência em outubro.
    c = m.compromisso(salario, 940.0, D(2026, 10, 5), descricao="Salário", confirmed=False)
    antes = m.mes()["months"][0]
    # Sem baixa, ela ainda conta — e conta como vencida: dia 5 já passou.
    assert antes["income"] == 940.0
    assert item(antes, f"compromisso:{c['id']}:1")["status"] == "vencido"

    r = m.c.post(
        f"/commitments/{c['id']}/ocorrencias/1/vincular",
        json={"transaction_id": recebido["id"]},
    )
    assert r.status_code == 200, r.text

    depois = m.mes()["months"][0]
    assert depois["income"] == 0.0
    assert depois["projected"] == 1500.0
    linha = item(depois, f"compromisso:{c['id']}:1")
    assert linha["status"] == "pago" and linha["remaining"] == 0.0
    # O lançamento realizado em si nunca vira item do planejamento.
    assert not [i for i in depois["items"] if i["key"] == f"lancamento:{recebido['id']}"]


def test_despesa_paga_nao_entra_de_novo(m):
    m.conta("Banco", 3000.0, dia=HOJE)
    moto = m.categoria("Moto")
    c = m.compromisso(moto, 618.08, D(2026, 10, 9), parcelas=2)

    antes = m.mes()["months"][0]
    assert antes["expense"] == 618.08
    assert antes["overdue"] == 618.08  # venceu ontem, sem baixa

    lancamentos = m.quantos_lancamentos()
    assert m.pagar(c["id"], 1, data=HOJE).status_code == 200
    assert m.quantos_lancamentos() == lancamentos + 1

    depois = m.mes()["months"][0]
    assert depois["expense"] == 0.0
    assert depois["overdue"] == 0.0
    assert item(depois, f"compromisso:{c['id']}:1")["status"] == "pago"


def test_hipotese_nunca_cria_lancamento(m):
    m.conta("Banco", 2000.0, dia=HOJE)
    lancamentos = m.quantos_lancamentos()
    gasto_antes = m.c.get("/budgets/summary?year=2026&month=10").json()["caixa"]

    # Simulação avulsa: calcula e esquece.
    r = m.c.post(
        "/planning/simulate",
        json={
            "year": 2026, "month": 10,
            "extras": [{"kind": "saida", "description": "Equipamento", "amount": 500.0, "date": "2026-10-20"}],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["months"][0]["available"] == 1500.0

    # Cenário salvo: os itens dele moram no cenário, não nos lançamentos.
    s = m.c.post("/scenarios", json={"name": "Viagem"}).json()
    m.c.post(
        f"/scenarios/{s['id']}/items",
        json={"kind": "saida", "description": "Hotel", "amount": 800.0, "date": "2026-10-25"},
    )
    assert m.mes(cenario=s["id"])["months"][0]["available"] == 1200.0

    assert m.quantos_lancamentos() == lancamentos
    assert m.c.get("/budgets/summary?year=2026&month=10").json()["caixa"] == gasto_antes
    # E a base continua sendo a base.
    assert m.mes()["months"][0]["available"] == 2000.0


def test_reserva_reduz_o_disponivel_e_nao_o_patrimonio(m):
    m.conta("Banco", 2000.0, dia=HOJE)
    m.reservar(688.31, HOJE, descricao="Reserva")

    mes = m.mes()["months"][0]
    assert mes["projected"] == 2000.0
    assert mes["reserved"] == 688.31
    assert mes["available"] == round(2000.0 - 688.31, 2)

    patrimonio = m.c.get("/assets/summary?year=2026&month=10").json()
    assert patrimonio["net_worth"] == 2000.0
    caixa = m.c.get("/budgets/summary?year=2026&month=10").json()["caixa"]
    assert caixa["gasto_total"] == 0.0 and caixa["carteira"] == 0.0


def test_cenario_duplicado_e_independente(m):
    m.conta("Banco", 1000.0, dia=HOJE)
    s = m.c.post("/scenarios", json={"name": "Conservador"}).json()
    m.c.post(
        f"/scenarios/{s['id']}/items",
        json={"kind": "saida", "description": "Imprevisto", "amount": 100.0, "date": "2026-10-20"},
    )
    copia = m.c.post(f"/scenarios/{s['id']}/duplicar", json={}).json()
    assert copia["name"] == "Conservador (cópia)"
    assert len(copia["items"]) == 1

    # Mexer na cópia não mexe no original.
    item_copia = copia["items"][0]
    m.c.patch(f"/scenarios/{copia['id']}/items/{item_copia['id']}", json={"amount": 400.0})
    assert m.mes(cenario=s["id"])["months"][0]["available"] == 900.0
    assert m.mes(cenario=copia["id"])["months"][0]["available"] == 600.0

    renomeado = m.c.patch(f"/scenarios/{copia['id']}", json={"name": "Apertado"}).json()
    assert renomeado["name"] == "Apertado"


def test_cenario_excluido_nao_mexe_em_dado_real(m):
    m.conta("Banco", 1000.0, dia=HOJE)
    casa = m.categoria("Casa")
    m.lancar(casa, D(2026, 10, 20), previsto=60.0)
    base_antes = m.mes()["months"][0]

    s = m.c.post("/scenarios", json={"name": "Teste"}).json()
    m.c.post(
        f"/scenarios/{s['id']}/items",
        json={"kind": "entrada", "description": "Bônus", "amount": 5000.0, "date": "2026-10-28"},
    )
    assert m.c.delete(f"/scenarios/{s['id']}").status_code == 200
    assert m.c.get(f"/scenarios/{s['id']}").status_code == 404
    assert m.c.get("/scenarios").json() == []
    assert m.mes()["months"][0] == base_antes


def test_cenario_ajusta_item_real_sem_tocar_nele(m):
    """Simular "e se eu cancelar a academia" é zerar ela SÓ no cenário."""
    m.conta("Banco", 1000.0, dia=HOJE)
    saude = m.categoria("Saúde")
    c = m.compromisso(saude, 120.0, D(2026, 10, 22), descricao="Academia")
    chave = f"compromisso:{c['id']}:1"

    s = m.c.post("/scenarios", json={"name": "Sem academia"}).json()
    r = m.c.post(
        f"/scenarios/{s['id']}/items",
        json={"kind": "saida", "description": "Academia", "amount": 0.0, "date": "2026-10-22", "ref": chave},
    )
    assert r.status_code == 200, r.text

    no_cenario = m.mes(cenario=s["id"])["months"][0]
    linha = item(no_cenario, chave)
    assert linha["remaining"] == 0.0 and linha["original_amount"] == 120.0
    assert no_cenario["expense"] == 0.0
    # Fora dele, a academia continua lá.
    assert m.mes()["months"][0]["expense"] == 120.0
    assert m.c.get(f"/commitments/{c['id']}").json()["amount"] == 120.0


def test_comparacao_base_e_cenario(m):
    m.conta("Banco", 1000.0, dia=HOJE)
    s = m.c.post("/scenarios", json={"name": "Guardar 500"}).json()
    m.c.post(
        f"/scenarios/{s['id']}/items",
        json={"kind": "reserva", "description": "Guardar", "amount": 500.0, "date": "2026-10-15"},
    )
    r = m.c.get(f"/planning/compare?year=2026&month=10&scenario_id={s['id']}")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["base"]["available"] == 1000.0
    assert corpo["scenario"]["available"] == 500.0
    # Guardar não é gastar: o saldo projetado é o mesmo, muda o disponível.
    assert corpo["diff"] == {"projected": 0.0, "expense": 0.0, "income": 0.0, "reserved": 500.0, "available": -500.0}


def test_mes_vazio(m):
    corpo = m.mes()
    mes = corpo["months"][0]
    assert corpo["balance_warning"]["sem_contas"] is True
    for campo in ("opening", "income", "expense", "projected", "reserved", "available"):
        assert mes[campo] == 0.0
    assert mes["items"] == [] and mes["reserves"] == []


def test_mes_passado_e_recusado(m):
    r = m.c.get("/planning/month?year=2026&month=9")
    assert r.status_code == 400


def test_mes_futuro_parte_do_projetado_do_anterior(m):
    m.conta("Banco", 1000.0, dia=HOJE)
    casa = m.categoria("Casa")
    m.lancar(casa, D(2026, 10, 20), previsto=100.0)
    m.lancar(casa, D(2026, 11, 20), previsto=50.0)

    meses = m.horizonte(3)
    assert [(x["year"], x["month"]) for x in meses] == [(2026, 10), (2026, 11), (2026, 12)]
    assert meses[0]["projected"] == 900.0
    assert meses[1]["opening"] == 900.0 and meses[1]["opening_source"] == "projecao"
    assert meses[1]["projected"] == 850.0
    assert meses[2]["opening"] == 850.0


def test_aviso_lista_o_que_aconteceu_depois_do_saldo_sem_aplicar(m):
    """Saldo de 08/10 e uma saída lançada em 10/10: avisa, não desconta.

    O app não sabe de qual conta a saída saiu. Descontar por conta própria seria
    inventar um ajuste pra fazer bater.
    """
    m.conta("Banco", 8393.0, dia=D(2026, 10, 8))
    moto = m.categoria("Moto")
    m.lancar(moto, D(2026, 10, 10), pago=7000.0, descricao="Entrada da moto")

    corpo = m.mes()
    assert corpo["months"][0]["opening"] == 8393.0
    aviso = corpo["balance_warning"]
    assert aviso["desde"] == "2026-10-08"
    assert aviso["saidas"] == 7000.0
    assert aviso["quantidade"] == 1
    assert aviso["movimentos"][0]["description"] == "Entrada da moto"


def test_saldo_de_mes_passado_fica_fora_do_saldo_de_partida(m):
    """Saldo de setembro não é o de hoje: aparece marcado, mas não soma."""
    m.conta("Banco", 500.0, ano=2026, mes=9)

    corpo = m.mes()

    assert corpo["months"][0]["opening"] == 0.0
    banco = corpo["accounts"][0]
    assert banco["stale"] is True
    assert (banco["value"], banco["as_of"]) == (500.0, "2026-09")
    aviso = corpo["balance_warning"]
    assert aviso["desatualizado"] is True
    assert aviso["contas_desatualizadas"] == ["Banco"]
    # O que ficou fora não define o "desde" dos movimentos.
    assert aviso["desde"] is None


def test_saldo_agregado_observado_e_o_ponto_de_partida(m):
    """O caso de outubro/2026: R$ 684,39 conhecidos em 11/10, sem divisão por
    banco, e as contas com saldo de setembro ficando de fora."""
    m.conta("Conta", 176.56, ano=2026, mes=9)
    m.conta("Nubank", 5262.23, ano=2026, mes=9, classe="fixed_income", planejamento=True)
    m.conta("Saldo agregado", 684.39, dia=HOJE)
    adiantamento = m.categoria("Adiantamento", "income")
    meta = m.categoria("Meta", "income")
    m.lancar(adiantamento, D(2026, 10, 15), previsto=720.0, descricao="Adiantamento")
    m.lancar(meta, D(2026, 10, 20), previsto=700.0, descricao="Meta")

    corpo = m.mes()

    mes = corpo["months"][0]
    assert mes["opening"] == 684.39
    assert mes["income"] == 1420.0
    assert mes["projected"] == 2104.39
    assert mes["available"] == 2104.39
    assert sorted(corpo["balance_warning"]["contas_desatualizadas"]) == ["Conta", "Nubank"]
    assert corpo["balance_warning"]["desde"] == HOJE.isoformat()


def test_so_as_contas_marcadas_entram(m):
    m.conta("Conta corrente", 100.0, dia=HOJE)  # classe Conta: entra sem marcar
    m.conta("Caixinha", 900.0, dia=HOJE, classe="fixed_income")  # não entra sem marcar
    m.conta("Corretora", 5000.0, dia=HOJE, classe="equity", planejamento=False)
    divida = m.conta("Financiamento", 13000.0, dia=HOJE, classe="debt", planejamento=True)

    corpo = m.mes()
    assert corpo["months"][0]["opening"] == 100.0
    # Dívida nunca é dinheiro disponível, nem marcada.
    assert divida not in [c["asset_id"] for c in corpo["accounts"]]

    caixinha = next(c for c in corpo["accounts"] if c["name"] == "Caixinha")
    m.c.patch(f"/assets/{caixinha['asset_id']}", json={"include_in_planning": True})
    assert m.mes()["months"][0]["opening"] == 1000.0


def test_investimento_previsto_e_reserva_e_nao_saida(m):
    """"Guardar 400 este mês" tira do disponível, não do saldo nem do patrimônio."""
    m.conta("Banco", 1000.0, dia=HOJE)
    reserva = m.categoria("Reserva", "investment")
    m.lancar(reserva, D(2026, 10, 20), previsto=400.0, descricao="Aporte")

    meses = m.horizonte(2)
    assert meses[0]["expense"] == 0.0
    assert meses[0]["projected"] == 1000.0
    assert meses[0]["reserved"] == 400.0
    # Continua separado no mês seguinte: o dinheiro foi guardado, não voltou.
    assert meses[1]["reserved"] == 400.0


def test_previsto_de_mes_passado_nao_vira_divida(m):
    """Um "MOTO 650" previsto em maio e nunca pago não aparece em outubro."""
    m.conta("Banco", 1000.0, dia=HOJE)
    transporte = m.categoria("Transporte")
    m.lancar(transporte, D(2026, 5, 1), previsto=650.0, descricao="Moto")
    assert m.mes()["months"][0]["expense"] == 0.0


def test_simular_na_conta_de_demonstracao_e_permitido_e_nao_grava(cliente_de, criar_usuario, monkeypatch):
    monkeypatch.setattr("app.planejamento.hoje", lambda: HOJE)
    demo = criar_usuario("demo-plano@exemplo.com", "Demo", "senha-do-demo-12345", read_only=True)
    c = cliente_de(demo)
    r = c.post(
        "/planning/simulate",
        json={"year": 2026, "month": 10, "extras": [
            {"kind": "saida", "description": "x", "amount": 10.0, "date": "2026-10-20"}
        ]},
    )
    assert r.status_code == 200
    assert c.get("/transactions").json() == []


def test_tipos_da_migracao_0006_sao_os_que_o_orm_grava():
    """A suíte monta o banco com create_all e nunca roda migração. Sem este
    teste, um enum divergente na 0006 só apareceria em produção — a armadilha
    que quase passou na 0004 e na 0005."""
    import importlib.util
    import pathlib

    import sqlalchemy as sa

    from app.models import Commitment, ReconciliationItem, ScenarioItem

    caminho = pathlib.Path(__file__).parents[2] / "migrations" / "versions" / "0006_planejamento.py"
    spec = importlib.util.spec_from_file_location("m0006", caminho)
    migracao = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migracao)

    # finalidade: o MESMO tipo nativo da 0005, pelo nome.
    tipo = Commitment.__table__.c.finalidade.type
    assert isinstance(tipo, sa.Enum)
    assert tipo.name == migracao.finalidade.name == "finalidade"
    assert tipo.enums == migracao.finalidade.enums == ["PESSOAL", "FAMILIA", "EMPRESA"]

    # Os novos: VARCHAR com o NOME do membro, sem tipo no Postgres.
    for coluna, classe in (
        (ScenarioItem.__table__.c.kind, migracao.ScenarioItemKind),
        (ReconciliationItem.__table__.c.kind, migracao.ReconciliationKind),
        (ReconciliationItem.__table__.c.status, migracao.ReconciliationStatus),
    ):
        do_modelo = coluna.type
        da_migracao = migracao.enum_texto(classe)
        assert do_modelo.native_enum is False and da_migracao.native_enum is False
        assert do_modelo.enums == da_migracao.enums == [m.name for m in classe]
        assert do_modelo.length == da_migracao.length
