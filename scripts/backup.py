"""Copia tudo o que é de uma conta pra um JSON em backups/.

    uv run python -m scripts.backup --usuario sjunior1557@gmail.com

Existia dentro de `reorganizar_categorias.py`, que precisava dele antes de
reescrever a categoria de centenas de lançamentos. Saiu de lá porque backup é
sempre a mesma coisa e nunca é sobre um script só — e porque toda operação que
mexe em dado real deveria poder começar com uma linha.

## Por que ele lê o schema do banco, e não os modelos

A primeira versão lia pelos modelos do SQLModel e quebrou na hora de usar:
o backup é tirado ANTES da migração, e naquele instante o código já tem colunas
que o banco ainda não tem (`column transactions.payment_method does not exist`).

Um backup que só funciona depois da migração é inútil exatamente quando ele
importa. Então aqui se pergunta ao banco quais tabelas e colunas existem e se lê
o que houver. Assim ele serve antes, depois e entre migrações — e continua
servindo quando o modelo andar de novo.

Só lê: `SELECT` e um arquivo local. Nada é escrito no banco.
"""

import argparse
import datetime as dt
import decimal
import json
import os
import sys

import sqlalchemy as sa

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine  # noqa: E402

# Da mais externa pra mais interna, que é a ordem de dependência. Não importa
# pro JSON; importa pra quem for restaurar à mão algum dia. Tabela que ainda não
# existe no banco é simplesmente pulada.
TABELAS = [
    "categories",
    "transactions",
    "budgets",
    "assets",
    "asset_snapshots",
    "cards",
    "purchases",
    "invoices",
    "invoice_payments",
]


def json_seguro(valor):
    """Data, hora e Decimal não são JSON. O resto passa direto."""
    if isinstance(valor, (dt.date, dt.datetime)):
        return valor.isoformat()
    if isinstance(valor, decimal.Decimal):
        return float(valor)
    return valor


def copiar(conexao, email: str) -> dict:
    inspetor = sa.inspect(conexao)
    existentes = set(inspetor.get_table_names())

    dono = conexao.execute(
        sa.text("SELECT id, email FROM users WHERE email = :e"), {"e": email}
    ).first()
    if dono is None:
        raise LookupError(email)

    dados = {
        "conta": dono.email,
        "gerado_em": dt.datetime.now(dt.timezone.utc).isoformat(),
        # O schema vai junto: sem ele, quem for restaurar não sabe de qual
        # formato este backup é. Foi o que faltou pra descobrir de cara que a
        # produção não tinha `payment_method` ainda.
        "schema": {},
    }

    for tabela in TABELAS:
        if tabela not in existentes:
            dados[tabela] = []
            continue

        colunas = [c["name"] for c in inspetor.get_columns(tabela)]
        dados["schema"][tabela] = colunas

        linhas = conexao.execute(
            sa.text(f"SELECT * FROM {tabela} WHERE user_id = :dono ORDER BY id"),
            {"dono": dono.id},
        ).mappings().all()
        dados[tabela] = [
            {chave: json_seguro(valor) for chave, valor in linha.items()}
            for linha in linhas
        ]

    return dados


def gravar(dados: dict, rotulo: str) -> str:
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pasta = os.path.join(raiz, "backups")
    os.makedirs(pasta, exist_ok=True)
    marca = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    caminho = os.path.join(pasta, f"{rotulo}-{marca}.json")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    return caminho


def salvar(session, dono, rotulo: str = "backup") -> str:
    """Atalho para os scripts que já têm sessão aberta."""
    return gravar(copiar(session.connection(), dono.email), rotulo)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--usuario", required=True, help="e-mail da conta")
    ap.add_argument("--rotulo", default="backup", help="prefixo do arquivo")
    args = ap.parse_args()

    with engine.connect() as conexao:
        try:
            dados = copiar(conexao, args.usuario.strip().lower())
        except LookupError as e:
            print(f"Conta não encontrada: {e}", file=sys.stderr)
            return 1

    caminho = gravar(dados, args.rotulo)

    print(f"Backup de {args.usuario}: {caminho}")
    for tabela in TABELAS:
        marca = "" if tabela in dados["schema"] else "  (tabela ainda não existe)"
        print(f"   {tabela:18} {len(dados[tabela]):>5}{marca}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
