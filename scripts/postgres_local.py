"""Postgres de desenvolvimento na máquina, sem instalar nada.

    uv run --with pgserver python -m scripts.postgres_local start
    uv run --with pgserver python -m scripts.postgres_local stop
    uv run --with pgserver python -m scripts.postgres_local status

Usa os binários que vêm no pacote `pgserver` (Postgres 16). Porta fixa 54329,
só em 127.0.0.1, dados em `.local/postgres` (fora do git). Cria os bancos
`sentavos_dev` (o do `.env`) e `sentavos_test` (pra quem quiser rodar a suíte
em Postgres: TEST_DATABASE_URL). Banco local é o que o ambiente development
aceita — ver app/ambiente.py.
"""

import argparse
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DADOS = RAIZ / ".local" / "postgres"
LOG = RAIZ / ".local" / "postgres.log"
PORTA = 54329
BANCOS = ("sentavos_dev", "sentavos_test")


def _pg():
    try:
        import pgserver  # noqa: F401
    except ImportError:
        sys.exit("Rode com: uv run --with pgserver python -m scripts.postgres_local ...")
    import pgserver
    return pgserver


def rodando(pg) -> bool:
    try:
        pg.pg_ctl(["status"], pgdata=DADOS)
        return True
    except Exception:
        return False


def start() -> None:
    pg = _pg()
    DADOS.parent.mkdir(exist_ok=True)
    if not (DADOS / "PG_VERSION").exists():
        DADOS.mkdir(exist_ok=True)
        pg.initdb(["--auth=trust", "--encoding=UTF8", "-U", "postgres"], pgdata=DADOS)
        print("cluster criado em", DADOS)
    if not rodando(pg):
        pg.pg_ctl(["-w", "-l", str(LOG), "-o", f"-p {PORTA} -h 127.0.0.1", "start"], pgdata=DADOS)
    import sqlalchemy as sa

    motor = sa.create_engine(f"postgresql://postgres@127.0.0.1:{PORTA}/postgres", isolation_level="AUTOCOMMIT")
    with motor.connect() as c:
        existentes = {r[0] for r in c.execute(sa.text("select datname from pg_database"))}
        for banco in BANCOS:
            if banco not in existentes:
                c.execute(sa.text(f'create database "{banco}"'))
                print("banco criado:", banco)
    motor.dispose()
    print(f"Postgres local no ar: postgresql://postgres@127.0.0.1:{PORTA}/sentavos_dev")


def stop() -> None:
    pg = _pg()
    if rodando(pg):
        pg.pg_ctl(["-w", "stop"], pgdata=DADOS)
    print("Postgres local parado.")


def status() -> None:
    pg = _pg()
    print("rodando" if rodando(pg) else "parado", f"(porta {PORTA}, dados em {DADOS})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("acao", choices=["start", "stop", "status"])
    acao = ap.parse_args().acao
    os.chdir(RAIZ)
    {"start": start, "stop": stop, "status": status}[acao]()
