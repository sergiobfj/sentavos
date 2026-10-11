import datetime as dt

import pytest


def criar_ativo(client, name="Nubank", asset_class="checking"):
    return client.post(
        "/assets", json={"name": name, "asset_class": asset_class}
    ).json()


def lancar_saldo(client, asset_id, value, year=2026, month=7):
    return client.put(
        "/assets/snapshots",
        json={"asset_id": asset_id, "year": year, "month": month, "value": value},
    )


def resumo(client, year=2026, month=7):
    return client.get("/assets/summary", params={"year": year, "month": month})


def test_cria_ativo(client):
    r = client.post("/assets", json={"name": "Tesouro Selic", "asset_class": "fixed_income"})

    assert r.status_code == 200
    assert r.json()["asset_class"] == "fixed_income"


def test_classe_invalida_da_422(client):
    assert client.post("/assets", json={"name": "X", "asset_class": "nft"}).status_code == 422


def test_put_saldo_sobrescreve_em_vez_de_duplicar(client):
    ativo = criar_ativo(client)
    primeiro = lancar_saldo(client, ativo["id"], 1000).json()
    segundo = lancar_saldo(client, ativo["id"], 1200).json()

    assert segundo["id"] == primeiro["id"]
    assert segundo["value"] == 1200
    assert len(client.get("/assets/snapshots").json()) == 1


def test_saldo_de_ativo_inexistente_da_400(client):
    assert lancar_saldo(client, 999, 100).status_code == 400


def test_summary_traz_saldo_do_mes(client):
    ativo = criar_ativo(client)
    lancar_saldo(client, ativo["id"], 1000)

    item = resumo(client).json()["items"][0]

    assert item["value"] == 1000
    assert item["as_of"] == "2026-07"
    assert item["snapshot_id"] is not None


def test_summary_herda_saldo_do_mes_anterior(client):
    # O ponto do estoque: mês sem lançamento continua valendo o último saldo,
    # em vez de zerar o patrimônio de quem não atualizou.
    ativo = criar_ativo(client)
    lancar_saldo(client, ativo["id"], 1000, month=5)

    item = resumo(client, month=7).json()["items"][0]

    assert item["value"] == 1000
    assert item["as_of"] == "2026-05"
    # Sem id porque o valor não é deste mês — não há o que editar em julho.
    assert item["snapshot_id"] is None


def test_summary_ignora_saldo_de_mes_futuro(client):
    ativo = criar_ativo(client)
    lancar_saldo(client, ativo["id"], 1000, month=6)
    lancar_saldo(client, ativo["id"], 9999, month=8)

    item = resumo(client, month=7).json()["items"][0]

    assert item["value"] == 1000


def test_summary_calcula_variacao_no_mes(client):
    ativo = criar_ativo(client)
    lancar_saldo(client, ativo["id"], 1000, month=6)
    lancar_saldo(client, ativo["id"], 1250, month=7)

    item = resumo(client, month=7).json()["items"][0]

    assert item["previous"] == 1000
    assert item["change"] == 250



def test_saldo_de_conferencia_marca_so_o_proprio_mes(client):
    # A caixinha foi usada numa compra e o valor do resgate não está no
    # extrato: o saldo de hoje é conhecido, o rendimento do mês não.
    ativo = criar_ativo(client, name="Caixinha", asset_class="fixed_income")
    lancar_saldo(client, ativo["id"], 1458.15, month=9)
    r = client.put(
        "/assets/snapshots",
        json={"asset_id": ativo["id"], "year": 2026, "month": 10, "value": 0,
              "reconciliation_note": "  Caixinha usada na compra;\n resgate não conciliado "},
    )
    assert r.status_code == 200
    assert r.json()["reconciliation_note"] == "Caixinha usada na compra; resgate não conciliado"

    outubro = resumo(client, month=10).json()
    item = outubro["items"][0]
    assert item["reconciliation_note"] == "Caixinha usada na compra; resgate não conciliado"
    # A nota não mexe em número nenhum: saldo, variação e patrimônio são os de sempre.
    assert (item["value"], item["previous"], item["change"]) == (0, 1458.15, -1458.15)
    assert outubro["net_worth"] == 0

    # Novembro herda o saldo, não a dúvida de outubro.
    assert resumo(client, month=11).json()["items"][0]["reconciliation_note"] is None
    assert resumo(client, month=9).json()["items"][0]["reconciliation_note"] is None


def test_lancar_o_saldo_de_novo_sem_nota_nao_apaga_a_nota(client):
    ativo = criar_ativo(client, name="Caixinha", asset_class="fixed_income")
    put = lambda **extra: client.put(
        "/assets/snapshots",
        json={"asset_id": ativo["id"], "year": 2026, "month": 7, "value": 10, **extra},
    )
    put(reconciliation_note="resgate não conciliado")

    # A tela de saldo não manda nota: corrigir o valor mantém o motivo.
    assert put().json()["reconciliation_note"] == "resgate não conciliado"
    # Mandar nula, de propósito, tira.
    assert put(reconciliation_note=None).json()["reconciliation_note"] is None
    assert resumo(client).json()["items"][0]["reconciliation_note"] is None

def test_variacao_em_janeiro_olha_dezembro_anterior(client):
    ativo = criar_ativo(client)
    lancar_saldo(client, ativo["id"], 800, year=2025, month=12)
    lancar_saldo(client, ativo["id"], 900, year=2026, month=1)

    item = resumo(client, year=2026, month=1).json()["items"][0]

    assert item["previous"] == 800
    assert item["change"] == 100


def test_ativo_sem_saldo_nenhum_fica_zerado(client):
    criar_ativo(client)

    item = resumo(client).json()["items"][0]

    assert (item["value"], item["previous"], item["change"]) == (0, 0, 0)
    assert item["as_of"] is None


def test_divida_subtrai_do_patrimonio_liquido(client):
    conta = criar_ativo(client, name="Nubank", asset_class="checking")
    imovel = criar_ativo(client, name="Apê", asset_class="real_estate")
    financiamento = criar_ativo(client, name="Financiamento", asset_class="debt")
    lancar_saldo(client, conta["id"], 5000)
    lancar_saldo(client, imovel["id"], 300000)
    lancar_saldo(client, financiamento["id"], 180000)

    data = resumo(client).json()

    assert data["assets"] == 305000
    assert data["liabilities"] == 180000
    assert data["net_worth"] == 125000


def test_divida_vem_marcada_como_passivo(client):
    criar_ativo(client, name="Cartão", asset_class="debt")

    item = resumo(client).json()["items"][0]

    assert item["liability"] is True


def test_patrimonio_liquido_anterior_para_comparar(client):
    conta = criar_ativo(client)
    lancar_saldo(client, conta["id"], 1000, month=6)
    lancar_saldo(client, conta["id"], 1500, month=7)

    data = resumo(client, month=7).json()

    assert data["previous_net_worth"] == 1000
    assert data["net_worth"] == 1500


def test_summary_agrupa_por_classe(client):
    acoes = criar_ativo(client, name="Ações", asset_class="equity")
    cripto = criar_ativo(client, name="BTC", asset_class="crypto")
    lancar_saldo(client, acoes["id"], 7000)
    lancar_saldo(client, cripto["id"], 3000)

    by_class = resumo(client).json()["by_class"]

    assert by_class["equity"]["value"] == 7000
    assert by_class["crypto"]["value"] == 3000
    # Classe sem ativo nenhum ainda aparece zerada, pra tela não checar chave.
    assert by_class["vehicle"] == {"value": 0, "previous": 0}


def test_summary_exige_ano_e_mes(client):
    assert client.get("/assets/summary").status_code == 422


def test_patch_altera_ativo(client):
    ativo = criar_ativo(client)

    r = client.patch(f"/assets/{ativo['id']}", json={"name": "Nubank CDB"})

    assert r.status_code == 200
    assert r.json()["name"] == "Nubank CDB"


def test_delete_ativo_leva_os_saldos(client):
    ativo = criar_ativo(client)
    lancar_saldo(client, ativo["id"], 1000, month=6)
    lancar_saldo(client, ativo["id"], 1100, month=7)

    assert client.delete(f"/assets/{ativo['id']}").status_code == 200
    assert client.get("/assets").json() == []
    # Saldo órfão apontando pra ativo que não existe mais quebraria o summary.
    assert client.get("/assets/snapshots").json() == []


def test_delete_saldo_solta_o_mes(client):
    ativo = criar_ativo(client)
    snap = lancar_saldo(client, ativo["id"], 1000).json()

    assert client.delete(f"/assets/snapshots/{snap['id']}").status_code == 200
    assert client.get("/assets/snapshots").json() == []


def test_rotas_inexistentes_dao_404(client):
    assert client.patch("/assets/999", json={"name": "x"}).status_code == 404
    assert client.delete("/assets/999").status_code == 404
    assert client.delete("/assets/snapshots/999").status_code == 404


# ---------- Saldo de hoje × último saldo conhecido ----------
# "Hoje" fixo em 11/10/2026: a regra depende do mês corrente.

HOJE = dt.date(2026, 10, 11)


def por_nome(corpo, nome):
    return next(i for i in corpo["items"] if i["name"] == nome)


def test_saldo_de_setembro_nao_soma_no_patrimonio_de_outubro(client, monkeypatch):
    """O Nubank de setembro aparece, com a data, mas não finge ser de hoje."""
    monkeypatch.setattr("app.planejamento.hoje", lambda: HOJE)
    nubank = criar_ativo(client, name="Nubank", asset_class="fixed_income")
    caixinha = criar_ativo(client, name="Caixinha", asset_class="fixed_income")
    agregado = criar_ativo(client, name="Saldo agregado", asset_class="checking")
    lancar_saldo(client, nubank["id"], 5262.23, month=9)
    lancar_saldo(client, caixinha["id"], 1458.15, month=9)
    lancar_saldo(client, caixinha["id"], 0, month=10)
    lancar_saldo(client, agregado["id"], 684.39, month=10)

    outubro = resumo(client, month=10).json()
    nb = por_nome(outubro, "Nubank")
    assert nb["stale"] is True
    assert (nb["value"], nb["as_of"]) == (5262.23, "2026-09")
    assert por_nome(outubro, "Caixinha")["stale"] is False
    # Só o que foi atualizado em outubro soma.
    assert outubro["assets"] == 684.39
    assert outubro["net_worth"] == 684.39
    assert outubro["by_class"]["fixed_income"]["value"] == 0
    assert (outubro["stale_count"], outubro["stale_assets"]) == (1, 5262.23)
    # O mês anterior é passado: o retrato de setembro, inteiro.
    assert outubro["previous_net_worth"] == pytest.approx(6720.38)


def test_mes_passado_continua_lendo_o_ultimo_saldo_conhecido(client, monkeypatch):
    """Setembro (e antes) não muda: lá o saldo herdado é o retrato histórico."""
    monkeypatch.setattr("app.planejamento.hoje", lambda: HOJE)
    ativo = criar_ativo(client, name="Nubank", asset_class="fixed_income")
    lancar_saldo(client, ativo["id"], 5262.23, month=7)

    setembro = resumo(client, month=9).json()

    item = setembro["items"][0]
    assert item["stale"] is False
    assert (item["value"], item["as_of"]) == (5262.23, "2026-07")
    assert setembro["net_worth"] == 5262.23
    assert setembro["stale_count"] == 0


def test_saldo_do_mes_corrente_vale_nos_meses_seguintes(client, monkeypatch):
    """Novembro projeta o saldo de outubro (o de hoje); o de setembro, não."""
    monkeypatch.setattr("app.planejamento.hoje", lambda: HOJE)
    agregado = criar_ativo(client, name="Saldo agregado", asset_class="checking")
    conta = criar_ativo(client, name="Conta", asset_class="checking")
    lancar_saldo(client, agregado["id"], 684.39, month=10)
    lancar_saldo(client, conta["id"], 176.56, month=9)

    novembro = resumo(client, month=11).json()

    assert por_nome(novembro, "Saldo agregado")["stale"] is False
    assert por_nome(novembro, "Conta")["stale"] is True
    assert novembro["net_worth"] == 684.39
    # Outubro, visto de novembro, também deixa a Conta de setembro de fora.
    assert novembro["previous_net_worth"] == 684.39
