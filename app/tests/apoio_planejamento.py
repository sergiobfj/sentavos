"""Montagem comum dos testes de planejamento, compromisso, reserva e conferência.

Não é um arquivo de teste (o pytest só coleta `test_*`). Existe porque os quatro
arquivos novos montam o mesmo mundo — categoria, conta com saldo, cartão,
compromisso — e cada um repetindo isso à mão era o lugar onde um deles ia
divergir dos outros sem ninguém perceber.

"Hoje" é fixo nestes testes: 10/10/2026, o dia de referência do planejamento de
outubro. Vencida e pendente dependem do dia, e um teste com `date.today()` aqui
envelheceria sozinho — foi o que aconteceu com dois testes de fatura.
"""

import datetime as dt

HOJE = dt.date(2026, 10, 10)


class Montagem:
    def __init__(self, client):
        self.c = client

    # ---------- Básico ----------

    def categoria(self, nome: str, tipo: str = "expense") -> int:
        r = self.c.post("/categories", json={"name": nome, "type": tipo, "color": "#3987e5", "icon": "x"})
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def conta(self, nome: str, saldo: float | None, ano: int = 2026, mes: int = 10,
              dia: dt.date | None = None, classe: str = "checking", planejamento: bool | None = None) -> int:
        corpo = {"name": nome, "asset_class": classe}
        if planejamento is not None:
            corpo["include_in_planning"] = planejamento
        r = self.c.post("/assets", json=corpo)
        assert r.status_code == 200, r.text
        aid = r.json()["id"]
        if saldo is not None:
            snap = {"asset_id": aid, "year": ano, "month": mes, "value": saldo}
            if dia is not None:
                snap["observed_on"] = dia.isoformat()
            r = self.c.put("/assets/snapshots", json=snap)
            assert r.status_code == 200, r.text
        return aid

    def lancar(self, categoria_id: int, data: dt.date, pago: float | None = None,
               previsto: float | None = None, descricao: str = "Lançamento") -> dict:
        r = self.c.post(
            "/transactions",
            json={
                "date": data.isoformat(),
                "description": descricao,
                "amount_paid": pago,
                "amount_planned": previsto,
                "category_id": categoria_id,
                "payment_method": "cash",
            },
        )
        assert r.status_code == 200, r.text
        return r.json()

    def cartao(self, nome: str = "Cartão", fecha: int = 25, vence: int = 2) -> int:
        r = self.c.post("/cards", json={"name": nome, "closing_day": fecha, "due_day": vence})
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def comprar(self, cartao_id: int, categoria_id: int, valor: float, data: dt.date,
                parcelas: int = 1, descricao: str = "Compra") -> dict:
        r = self.c.post(
            "/purchases",
            json={
                "card_id": cartao_id,
                "category_id": categoria_id,
                "description": descricao,
                "total_amount": valor,
                "installments": parcelas,
                "purchase_date": data.isoformat(),
            },
        )
        assert r.status_code == 200, r.text
        return r.json()

    # ---------- Planejamento ----------

    def compromisso(self, categoria_id: int, valor: float, primeira: dt.date,
                    parcelas: int | None = None, descricao: str = "Compromisso", **extra) -> dict:
        corpo = {
            "description": descricao,
            "category_id": categoria_id,
            "amount": valor,
            "first_due": primeira.isoformat(),
            "installments": parcelas,
            **{k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in extra.items()},
        }
        r = self.c.post("/commitments", json=corpo)
        assert r.status_code == 200, r.text
        return r.json()

    def pagar(self, cid: int, numero: int, data: dt.date | None = None, valor: float | None = None):
        corpo = {}
        if data is not None:
            corpo["date"] = data.isoformat()
        if valor is not None:
            corpo["amount"] = valor
        return self.c.post(f"/commitments/{cid}/ocorrencias/{numero}/pagar", json=corpo)

    def reservar(self, valor: float, desde: dt.date, cid: int | None = None, numero: int | None = None,
                 descricao: str | None = None) -> dict:
        corpo = {"amount": valor, "created_on": desde.isoformat(), "description": descricao}
        if cid is not None:
            corpo["commitment_id"] = cid
            corpo["commitment_no"] = numero
        r = self.c.post("/provisions", json=corpo)
        assert r.status_code == 200, r.text
        return r.json()

    def mes(self, ano: int = 2026, mes: int = 10, cenario: int | None = None) -> dict:
        url = f"/planning/month?year={ano}&month={mes}"
        if cenario is not None:
            url += f"&scenario_id={cenario}"
        r = self.c.get(url)
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert len(corpo["months"]) == 1
        return corpo

    def horizonte(self, meses: int = 6, cenario: int | None = None) -> list[dict]:
        url = f"/planning/horizon?months={meses}" + (f"&scenario_id={cenario}" if cenario else "")
        r = self.c.get(url)
        assert r.status_code == 200, r.text
        return r.json()["months"]

    def quantos_lancamentos(self) -> int:
        return len(self.c.get("/transactions").json())


def item(mes: dict, chave_parcial: str) -> dict:
    """O item do mês cuja chave começa com `chave_parcial` (há de existir um só)."""
    achados = [i for i in mes["items"] if i["key"].startswith(chave_parcial)]
    assert len(achados) == 1, (chave_parcial, [i["key"] for i in mes["items"]])
    return achados[0]
