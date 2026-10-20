"""Conferência de outubro: revisar e aplicar, item a item.

A montagem reproduz a FORMA do outubro real — salário já recebido, um aporte
de 800 na caixinha, parcela de cartão de dentista, faturas pagas — com
descrições genéricas. Os valores são os do enunciado, porque é deles que os
testes falam: a entrada de R$ 7.000 não pode duplicar, a viagem cancelada não
vira gasto, os R$ 688,31 de reserva não viram despesa.

O que nenhum teste aqui aceita: um item da conferência criando dado sozinho.
Toda criação é uma chamada explícita, que é o toque do dono na tela.
"""

import datetime as dt

import pytest

from app.tests.apoio_planejamento import HOJE, Montagem

D = dt.date


@pytest.fixture(name="m")
def montagem(client, monkeypatch):
    monkeypatch.setattr("app.planejamento.hoje", lambda: HOJE)
    return Montagem(client)


@pytest.fixture(name="outubro")
def outubro_fixture(m):
    """O mês como ele está antes da conferência."""
    ids = {
        "salario": m.categoria("Salário", "income"),
        "caixinha": m.categoria("Caixinha", "investment"),
        "saude": m.categoria("Cuidado pessoal"),
        "moto": m.categoria("Moto"),
        "transporte": m.categoria("Transporte"),
    }
    m.conta("Banco", 2972.0, dia=D(2026, 10, 8), planejamento=True)
    ids["tx_salario"] = m.lancar(ids["salario"], D(2026, 10, 6), pago=944.34, descricao="Salário")["id"]
    ids["tx_caixinha"] = m.lancar(ids["caixinha"], D(2026, 10, 6), pago=800.0, descricao="Caixinha")["id"]
    familia = m.cartao("Cartão família")
    m.comprar(familia, ids["saude"], 561.0, D(2026, 9, 23), parcelas=5, descricao="Dentista")
    return ids


def _item(m: Montagem, descricao: str, valor: float | None, tipo: str, data: D | None = None, **extra) -> dict:
    corpo = {"year": 2026, "month": 10, "description": descricao, "amount": valor, "kind": tipo, **extra}
    if data is not None:
        corpo["date"] = data.isoformat()
    r = m.c.post("/reconciliation", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def _lista(m: Montagem) -> dict:
    r = m.c.get("/reconciliation?year=2026&month=10")
    assert r.status_code == 200, r.text
    return r.json()


def test_itens_incertos_nao_sao_importados(m, outubro):
    """Adicionar candidatos não cria lançamento, compromisso nem reserva."""
    lancamentos = m.quantos_lancamentos()
    plano_antes = m.mes()["months"][0]
    for descricao, valor in (
        ("Academia", 120.0), ("Internet", 60.0), ("Uber", 80.0), ("Consórcio antigo", 479.38),
        ("Emplacamento", 908.0), ("Seguro do financiamento", 1488.0), ("Proteção", 94.0),
    ):
        _item(m, descricao, valor, "saida", question="foi pago?")

    lista = _lista(m)
    assert lista["counts"]["pendente"] == 7
    assert m.quantos_lancamentos() == lancamentos
    assert m.c.get("/commitments").json() == []
    assert m.c.get("/provisions").json() == []
    assert m.mes()["months"][0] == plano_antes


def test_entrada_de_7000_criada_uma_vez(m, outubro):
    item = _item(m, "Entrada da moto", 7000.0, "saida", category_hint="Moto")
    assert item["candidates"] == []  # ainda não existe nada parecido

    lancamentos = m.quantos_lancamentos()
    r = m.c.post(
        f"/reconciliation/{item['id']}/lancamento",
        json={"date": "2026-10-09", "description": "Entrada da moto", "amount_paid": 7000.0,
              "category_id": outubro["moto"]},
    )
    assert r.status_code == 200, r.text
    resolvido = r.json()
    assert resolvido["status"] == "resolvido"
    assert resolvido["linked"]["kind"] == "lancamento" and resolvido["linked"]["amount"] == 7000.0
    assert m.quantos_lancamentos() == lancamentos + 1

    # Um segundo item igual (o handoff repetido) aponta pro lançamento que já
    # existe — marcado como já usado — em vez de convidar a criar outro.
    repetido = _item(m, "Entrada da moto", 7000.0, "saida")
    sugestao = repetido["candidates"][0]
    assert sugestao["id"] == resolvido["transaction_id"]
    assert "mesmo valor" in sugestao["reasons"] and sugestao["used"] is True


def test_segundo_toque_na_conferencia_nao_cria_outra_saida(m, outubro):
    item = _item(m, "Internet", 60.0, "obrigacao")
    dados = {"date": "2026-10-19", "description": "Internet", "amount_paid": 60.0,
             "category_id": outubro["moto"]}
    primeiro = m.c.post(f"/reconciliation/{item['id']}/lancamento", json=dados)
    assert primeiro.status_code == 200, primeiro.text
    quantidade = m.quantos_lancamentos()
    segundo = m.c.post(f"/reconciliation/{item['id']}/lancamento", json=dados)
    assert segundo.status_code == 409
    assert m.quantos_lancamentos() == quantidade


def test_entrada_de_7000_que_ja_existe_e_vinculada_sem_duplicar(m, outubro):
    existente = m.lancar(outubro["moto"], D(2026, 10, 9), pago=7000.0, descricao="Entrada moto")
    item = _item(m, "Entrada da moto", 7000.0, "saida")
    assert item["candidates"][0]["id"] == existente["id"]

    lancamentos = m.quantos_lancamentos()
    r = m.c.post(f"/reconciliation/{item['id']}/vincular", json={"transaction_id": existente["id"]})
    assert r.status_code == 200 and r.json()["status"] == "resolvido"
    assert m.quantos_lancamentos() == lancamentos


def test_equipamentos_500_61_pela_data_exata(m, outubro):
    existente = m.lancar(outubro["moto"], D(2026, 10, 10), pago=500.61, descricao="Pix loja")
    item = _item(m, "Equipamentos", 500.61, "saida", data=D(2026, 10, 10))
    sugestao = item["candidates"][0]
    assert sugestao["id"] == existente["id"]
    assert "mesmo valor" in sugestao["reasons"] and "mesma data" in sugestao["reasons"]
    # Só sugere: nada foi vinculado.
    assert _lista(m)["items"][0]["status"] == "pendente"


def test_viagem_cancelada_nao_vira_gasto(m, outubro):
    item = _item(m, "Viagem", 350.0, "saida", suggestion="Cancelada")
    lancamentos = m.quantos_lancamentos()
    r = m.c.patch(f"/reconciliation/{item['id']}", json={"status": "ignorado", "note": "viagem cancelada"})
    assert r.status_code == 200 and r.json()["status"] == "ignorado"
    assert m.quantos_lancamentos() == lancamentos
    assert m.c.get("/budgets/summary?year=2026&month=10").json()["caixa"]["gasto_total"] == 112.2


def test_reserva_de_688_31_nao_vira_despesa(m, outubro):
    item = _item(m, "Reserva planejada", 688.31, "reserva")
    gasto = m.c.get("/budgets/summary?year=2026&month=10").json()["caixa"]["gasto_total"]
    disponivel = m.mes()["months"][0]["available"]

    dados = {"amount": 688.31, "description": "Reserva", "created_on": "2026-10-10"}
    r = m.c.post(f"/reconciliation/{item['id']}/reserva", json=dados)
    assert r.status_code == 200, r.text
    assert r.json()["linked"]["kind"] == "reserva"
    assert m.c.get("/budgets/summary?year=2026&month=10").json()["caixa"]["gasto_total"] == gasto
    assert m.mes()["months"][0]["available"] == round(disponivel - 688.31, 2)
    assert m.c.post(f"/reconciliation/{item['id']}/reserva", json=dados).status_code == 409
    assert m.mes()["months"][0]["available"] == round(disponivel - 688.31, 2)


def test_saldo_observado_de_709_39_nao_vira_receita(m, outubro):
    item = _item(m, "Saldo depois da compra", 709.39, "saldo")
    assert item["candidates"] == []
    m.c.patch(f"/reconciliation/{item['id']}", json={"status": "ignorado", "note": "é saldo, não lançamento"})
    caixa = m.c.get("/budgets/summary?year=2026&month=10").json()["caixa"]
    assert caixa["entrou"] == 944.34  # só o salário que de fato caiu


def test_provisoes_de_1241_08_nao_sao_gasto_de_outubro(m, outubro):
    item = _item(m, "Provisões somadas", 1241.08, "reserva")
    m.c.post(f"/reconciliation/{item['id']}/reserva", json={"amount": 1241.08, "description": "Provisões"})
    resumo = m.c.get("/budgets/summary?year=2026&month=10").json()
    assert resumo["totals"]["expense"]["paid"] == 112.2
    assert m.c.get("/reports/categories?year=2026&month=10").json()["total"] == 112.2


def test_salario_previsto_encontra_o_que_ja_caiu(m, outubro):
    item = _item(m, "Salário dia 5", 940.0, "entrada")
    sugestao = item["candidates"][0]
    assert sugestao["id"] == outubro["tx_salario"]
    assert any("quase igual" in motivo for motivo in sugestao["reasons"])


def test_dentista_sugere_a_parcela_do_cartao(m, outubro):
    item = _item(m, "Dentista", 112.0, "saida")
    sugestao = item["candidates"][0]
    assert sugestao["kind"] == "parcela"
    assert "parcela 2/5" in sugestao["detail"]


def test_valor_de_fatura_sugere_a_fatura(m, outubro):
    item = _item(m, "Cartão família", 112.2, "saida", question="composição?")
    assert any(c["kind"] == "fatura" for c in item["candidates"])


def test_oitocentos_guardados_aponta_pro_aporte_existente(m, outubro):
    item = _item(m, "Guardado na caixinha", 800.0, "reserva")
    assert item["candidates"][0]["id"] == outubro["tx_caixinha"]


def test_obrigacao_criada_pela_conferencia(m, outubro):
    item = _item(m, "Financiamento da moto", 618.08, "obrigacao",
                 prefill={"installments": 48, "first_due": "2026-11-09"})
    assert item["prefill"]["installments"] == 48
    dados = {"description": "Financiamento da moto", "category_id": outubro["moto"],
             "amount": 618.08, "first_due": "2026-11-09", "installments": 48}
    r = m.c.post(f"/reconciliation/{item['id']}/compromisso", json=dados)
    assert r.status_code == 200, r.text
    assert r.json()["linked"]["kind"] == "compromisso"
    assert len(m.c.get("/commitments").json()) == 1
    assert m.c.post(f"/reconciliation/{item['id']}/compromisso", json=dados).status_code == 409
    assert len(m.c.get("/commitments").json()) == 1

    # O mesmo contrato citado de novo sugere o compromisso já cadastrado.
    de_novo = _item(m, "Financiamento moto", 618.08, "obrigacao")
    assert de_novo["candidates"][0]["kind"] == "compromisso"
    assert de_novo["candidates"][0]["used"] is True


def test_reabrir_solta_o_vinculo_sem_apagar_o_lancamento(m, outubro):
    item = _item(m, "Salário", 940.0, "entrada")
    m.c.post(f"/reconciliation/{item['id']}/vincular", json={"transaction_id": outubro["tx_salario"]})
    r = m.c.patch(f"/reconciliation/{item['id']}", json={"status": "pendente"})
    assert r.json()["status"] == "pendente" and r.json()["transaction_id"] is None
    assert m.c.get(f"/transactions/{outubro['tx_salario']}").status_code == 200


def test_vinculo_perdido_volta_a_ser_pendencia(m, outubro):
    criado = m.lancar(outubro["moto"], D(2026, 10, 9), pago=50.0, descricao="Trava")
    item = _item(m, "Trava", 50.0, "saida")
    m.c.post(f"/reconciliation/{item['id']}/vincular", json={"transaction_id": criado["id"]})
    m.c.delete(f"/transactions/{criado['id']}")

    lista = _lista(m)
    assert lista["items"][0]["link_missing"] is True
    assert lista["counts"]["pendente"] == 1 and lista["counts"]["resolvido"] == 0

    dados = {"date": "2026-10-19", "description": "Trava", "amount_paid": 50.0,
             "category_id": outubro["moto"]}
    assert m.c.post(f"/reconciliation/{item['id']}/lancamento", json=dados).status_code == 409
    reaberto = m.c.patch(f"/reconciliation/{item['id']}", json={"status": "pendente"})
    assert reaberto.status_code == 200 and reaberto.json()["transaction_id"] is None
    assert m.c.post(f"/reconciliation/{item['id']}/lancamento", json=dados).status_code == 200


def test_conferencia_nao_cria_compra_no_cartao(m, outubro):
    item = _item(m, "Emplacamento", 908.0, "saida")
    r = m.c.post(
        f"/reconciliation/{item['id']}/lancamento",
        json={"date": "2026-10-10", "description": "x", "amount_paid": 908.0,
              "category_id": outubro["moto"], "payment_method": "credit"},
    )
    assert r.status_code == 400


def test_previsto_pela_conferencia_entra_no_planejamento_como_estimado(m, outubro):
    item = _item(m, "Adiantamento", 720.0, "entrada")
    r = m.c.post(
        f"/reconciliation/{item['id']}/lancamento",
        json={"date": "2026-10-15", "description": "Adiantamento", "amount_planned": 720.0,
              "category_id": outubro["salario"]},
    )
    assert r.status_code == 200
    mes = m.mes()["months"][0]
    assert mes["income"] == 720.0
    # Previsto não é dinheiro: o "entrou" do mês não muda.
    assert m.c.get("/budgets/summary?year=2026&month=10").json()["caixa"]["entrou"] == 944.34


def test_coincidencia_de_valor_nao_vira_sugestao(m, outubro):
    """Casos vistos nos dados reais: valor parecido, coisa diferente."""
    assinaturas = m.categoria("Assinaturas")
    m.lancar(assinaturas, D(2026, 9, 23), pago=121.40, descricao="Ferramenta de e-mail")
    cartao = m.cartao("Cartão pessoal")
    m.comprar(cartao, assinaturas, 500.63, D(2026, 9, 20), descricao="Compras de setembro")

    assert _item(m, "Academia", 120.0, "saida")["candidates"] == []
    assert _item(m, "Equipamentos", 500.61, "saida", data=D(2026, 10, 10))["candidates"] == []
    # Mesma descrição com valor muito longe também não: R$ 944 não é R$ 720.
    assert _item(m, "Salário do dia 15", 720.0, "entrada")["candidates"] == []
