"""Regressão de números: carregar uma base num banco LOCAL, despejar tudo, comparar.

    uv run python -m scripts.regressao carregar base.json [outra.json ...]
    uv run python -m scripts.regressao despejar saida.json
    uv run python -m scripts.regressao comparar antes.json depois.json [--corte 2026-10]

O banco é o DATABASE_URL do ambiente (local; ver app/ambiente.py). `carregar`
recusa banco remoto de qualquer jeito. `despejar` lê pelas rotas da API —
resumo do mês, faturas, patrimônio, séries, roscas, planejamento — pra todas
as contas do banco. `comparar` olha só as chaves do primeiro arquivo (campo
novo depois não é divergência) e, com `--corte`, falha se algo ANTES do mês
de corte mudou: é a prova de que o passado não foi reescrito.

É o que o CI usa no teste de migração (fixture fictícia) e o que o ensaio de
release usa com a cópia local dos backups reais — esses nunca saem da máquina.
"""

import argparse
import datetime as dt
import json
import os
import sys
from collections import Counter

ORDEM = [
    # Ordem de dependência: conta antes de lançamento, pagamento e transferência;
    # lançamento e ativo antes do movimento de investimento.
    "categories", "financial_accounts", "cards", "purchases", "invoices", "commitments", "transactions",
    "invoice_payments", "budgets", "assets", "asset_snapshots", "account_balance_snapshots", "transfers",
    "investment_movements", "investment_plans", "commitment_skips", "provisions", "scenarios", "scenario_items",
    "reconciliation_items", "audit_events",
]
MESES = [(2025 + (7 + i) // 12, (7 + i) % 12 + 1) for i in range(24)]  # 2025-08 .. 2027-07


def carregar(arquivos: list[str]) -> None:
    import sqlalchemy as sa

    from app.ambiente import banco_local
    from app.auth import gerar_hash

    url = os.environ["DATABASE_URL"]
    if not banco_local(url):
        sys.exit("carregar só escreve em banco local.")
    engine = sa.create_engine(url)
    meta = sa.MetaData()
    meta.reflect(bind=engine)

    def converter(col, v):
        if v is None:
            return None
        if isinstance(col.type, sa.DateTime):
            return dt.datetime.fromisoformat(v)
        if isinstance(col.type, sa.Date):
            return dt.date.fromisoformat(v[:10])
        return v

    senha = gerar_hash("senha-local-123")
    with engine.begin() as dst:
        for arq in arquivos:
            dados = json.load(open(arq, encoding="utf-8"))
            donos = {linha["user_id"] for t in ORDEM for linha in dados.get(t, [])}
            assert len(donos) == 1, (arq, donos)
            uid = donos.pop()
            email = dados["conta"]
            usuarios = meta.tables["users"]
            linha_u = {
                "id": uid, "email": email, "name": email.split("@")[0], "password_hash": senha,
                "read_only": email.startswith("demo@"), "cdi_annual": dados.get("cdi_annual", 14.63),
                "created_at": dt.datetime(2026, 1, 1),
            }
            dst.execute(usuarios.insert(), [{k: v for k, v in linha_u.items() if k in usuarios.c}])
            for t in ORDEM:
                if t not in meta.tables:
                    continue
                tabela = meta.tables[t]
                linhas = [
                    {k: converter(tabela.c[k], v) for k, v in linha.items() if k in tabela.c}
                    for linha in dados.get(t, [])
                ]
                if linhas:
                    dst.execute(tabela.insert(), linhas)
            print(f"{email}: " + ", ".join(f"{t} {len(dados.get(t, []))}" for t in ORDEM if dados.get(t)))
        if engine.dialect.name == "postgresql":
            for t in ["users"] + [t for t in ORDEM if t in meta.tables]:
                dst.execute(sa.text(
                    f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), COALESCE((SELECT MAX(id) FROM {t}), 1))"
                ))


def despejar(saida: str) -> None:
    from fastapi.testclient import TestClient
    from sqlmodel import Session, select

    import app.database as database
    import app.main as main
    from app.auth import require_user
    from app.database import get_session
    from app.main import app
    from app.models import User
    from app.security import zerar_limites

    # O banco já está no estado a testar: nada de migração no startup.
    database.create_db_and_tables = lambda: None
    main.create_db_and_tables = lambda: None

    resultado = {}
    with Session(database.engine) as s:
        app.dependency_overrides[get_session] = lambda: s
        for u in s.exec(select(User).order_by(User.id)).all():
            app.dependency_overrides[require_user] = lambda u=u: u
            c = TestClient(app)

            def get(url: str):
                zerar_limites()
                r = c.get(url)
                assert r.status_code == 200, (url, r.status_code, r.text[:300])
                return r.json()

            conta = {}
            for a, m in MESES:
                b = get(f"/budgets/summary?year={a}&month={m}")
                f = get(f"/invoices/summary?year={a}&month={m}")
                p = get(f"/assets/summary?year={a}&month={m}")
                conta[f"{a}-{m:02d}"] = {
                    "caixa": b["caixa"],
                    "totals": b["totals"],
                    "itens": {str(i["category_id"]): [i["budgeted"], i["planned"], i["paid"]] for i in b["items"]},
                    "faturas": {k: f[k] for k in ("due_this_month", "paid_this_month", "open_total")},
                    "faturas_cartoes": [[x["card_id"], x["open_total"], (x["current"] or {}).get("total"),
                                         (x["next"] or {}).get("total")] for x in f["cards"]],
                    "pagamentos": sorted(p_["amount"] for p_ in f["payments"]),
                    "patrimonio": {k: p[k] for k in ("assets", "liabilities", "net_worth", "previous_net_worth")},
                    "by_class": p["by_class"],
                }
            for fin in ("todos", "pessoal", "familia", "empresa"):
                conta[f"_serie_{fin}"] = get(f"/reports/monthly?from=2025-08&to=2027-07&finalidade={fin}")
                for a, m in MESES:
                    conta[f"{a}-{m:02d}"][f"rosca_{fin}"] = get(
                        f"/reports/categories?year={a}&month={m}&finalidade={fin}&top=12")
            conta["_faturas"] = get("/invoices?limite=120")
            conta["_categorias"] = [
                {k: x[k] for k in ("id", "name", "type", "archived", "transactions", "purchases", "budgets")}
                for x in get("/categories?incluir_arquivadas=1&incluir_uso=1")
            ]
            conta["_metas"] = get("/budgets")
            conta["_ativos"] = get("/assets")
            conta["_transacoes"] = sorted(
                [t["id"], t["date"], t["amount_paid"], t["amount_planned"], t["category_id"],
                 t.get("payment_method"), t.get("finalidade"), t.get("purchase_id"), t.get("invoice_id")]
                for t in get("/transactions")
            )
            plano = get("/planning/horizon?months=3")
            conta["_planejamento"] = [
                {k: m_[k] for k in ("year", "month", "opening", "income", "expense", "reserved", "available")}
                for m_ in plano["months"]
            ]
            resultado[u.email] = conta

    json.dump(resultado, open(saida, "w", encoding="utf-8"), indent=1, sort_keys=True, default=str)
    print("ok", saida, {k: len(v["_transacoes"]) for k, v in resultado.items()})


def comparar(antes_arq: str, depois_arq: str, corte: str | None) -> int:
    antes = json.load(open(antes_arq, encoding="utf-8"))
    depois = json.load(open(depois_arq, encoding="utf-8"))
    difs: list[tuple[str, object, object]] = []

    def cmp(a, b, caminho):
        if isinstance(a, dict):
            if not isinstance(b, dict):
                difs.append((caminho, a, b))
                return
            for k in a:
                cmp(a[k], b.get(k, "<ausente>") if isinstance(b, dict) else b, f"{caminho}/{k}")
        elif isinstance(a, list):
            if not isinstance(b, list) or len(a) != len(b):
                difs.append((caminho, f"lista {len(a)}", f"lista {len(b) if isinstance(b, list) else b}"))
                return
            for i, (x, y) in enumerate(zip(a, b)):
                cmp(x, y, f"{caminho}[{i}]")
        elif isinstance(a, float) and isinstance(b, (int, float)):
            if abs(a - b) > 0.005:
                difs.append((caminho, a, b))
        elif a != b:
            difs.append((caminho, a, b))

    cmp(antes, depois, "")
    onde = Counter()
    proibidas = []
    for caminho, a, b in difs:
        partes = caminho.split("/")
        conta, chave = partes[1], partes[2].split("[")[0]
        mes = chave if chave[:1].isdigit() else None
        if chave.startswith("_serie") and len(partes) > 3 and partes[3].startswith("months["):
            m = antes[conta][chave]["months"][int(partes[3][7:].split("]")[0])]
            mes = f"{m['year']}-{m['month']:02d}"
        onde[(conta, mes or chave)] += 1
        if corte and mes and mes < corte:
            proibidas.append((caminho, a, b))
    print("divergências:", len(difs))
    for (conta, lugar), n in sorted(onde.items()):
        print(f"  {conta:34} {lugar:24} {n}")
    if corte:
        print(f"antes de {corte}: {len(proibidas)}")
        for p in proibidas[:30]:
            print("   ", p)
        return 1 if proibidas else 0
    return 1 if difs else 0


if __name__ == "__main__":
    sys.path.insert(0, os.getcwd())
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("carregar").add_argument("arquivos", nargs="+")
    sub.add_parser("despejar").add_argument("saida")
    c = sub.add_parser("comparar")
    c.add_argument("antes")
    c.add_argument("depois")
    c.add_argument("--corte", help="YYYY-MM: nada antes deste mês pode mudar")
    args = ap.parse_args()
    if args.cmd == "carregar":
        carregar(args.arquivos)
    elif args.cmd == "despejar":
        despejar(args.saida)
    else:
        raise SystemExit(comparar(args.antes, args.depois, args.corte))
