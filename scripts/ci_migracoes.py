"""Teste de migração em Postgres de verdade (CI, ou local com o Postgres de dev).

    uv run python -m scripts.ci_migracoes postgresql://postgres:postgres@localhost:5432

1. Banco vazio: upgrade head → downgrade até 0007 → upgrade head de novo.
2. Base representativa: a fixture FICTÍCIA de `app/tests/fixtures/base_0007.json`
   (demo + casos de borda, gerada no schema 0007) é carregada em 0007 e migrada
   até head; a mesma fixture é carregada direto num banco já em head. Os dois
   têm de dar exatamente os mesmos números (scripts/regressao.py) e as mesmas
   contagens: migrar não pode mudar o que os dados dizem.

Nenhum dado real entra aqui. O ensaio com a cópia da produção é do release.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import sqlalchemy as sa

RAIZ = Path(__file__).resolve().parents[1]
FIXTURE = RAIZ / "app" / "tests" / "fixtures" / "base_0007.json"
BASE_DA_FIXTURE = "0007_conciliacao_saldo"  # o schema em que a fixture foi gerada


def rodar(url: str, *args: str) -> str:
    env = {**os.environ, "DATABASE_URL": url, "APP_ENV": "test", "PYTHONIOENCODING": "utf-8"}
    env.pop("ALLOW_PRODUCTION_DATABASE", None)
    r = subprocess.run([sys.executable, *args], env=env, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
    if r.returncode > 255 and not (r.stdout or r.stderr):
        # Processo morto antes do Python começar (visto no Windows, código
        # 0xC000xxxx, sem saída nenhuma): não é falha do comando. Uma segunda
        # tentativa, só nesse caso — erro de verdade sempre tem saída.
        r = subprocess.run([sys.executable, *args], env=env, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        print(r.stdout[-3000:], r.stderr[-6000:])
        raise SystemExit(f"falhou (código {r.returncode}): {' '.join(args)}")
    return r.stdout


def recriar(base: str, nome: str) -> str:
    admin = sa.create_engine(f"{base}/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(sa.text(f'DROP DATABASE IF EXISTS "{nome}"'))
        c.execute(sa.text(f'CREATE DATABASE "{nome}"'))
    admin.dispose()
    return f"{base}/{nome}"


def versao(url: str) -> str:
    e = sa.create_engine(url)
    with e.connect() as c:
        v = c.execute(sa.text("select version_num from alembic_version")).scalar()
    e.dispose()
    return v


def contagens(url: str) -> dict[str, int]:
    e = sa.create_engine(url)
    with e.connect() as c:
        tabelas = sa.inspect(c).get_table_names()
        r = {t: c.execute(sa.text(f'select count(*) from "{t}"')).scalar() for t in sorted(tabelas) if t != "alembic_version"}
    e.dispose()
    return r


def main() -> int:
    base = sys.argv[1].rstrip("/")
    alembic = ["-m", "alembic"]

    print("== banco vazio: sobe, desce até 0007, sobe", flush=True)
    vazio = recriar(base, "ci_vazio")
    rodar(vazio, *alembic, "upgrade", "head")
    head = versao(vazio)
    rodar(vazio, *alembic, "downgrade", BASE_DA_FIXTURE)
    assert versao(vazio) == BASE_DA_FIXTURE
    rodar(vazio, *alembic, "upgrade", "head")
    assert versao(vazio) == head
    print("   ok, head =", head, flush=True)

    print("== fixture 0007 → head × fixture carregada direto em head", flush=True)
    migrado = recriar(base, "ci_migrado")
    rodar(migrado, *alembic, "upgrade", BASE_DA_FIXTURE)
    rodar(migrado, "-m", "scripts.regressao", "carregar", str(FIXTURE))
    rodar(migrado, *alembic, "upgrade", "head")
    direto = recriar(base, "ci_direto")
    rodar(direto, *alembic, "upgrade", "head")
    rodar(direto, "-m", "scripts.regressao", "carregar", str(FIXTURE))

    esperado = {t: len(v) for t, v in json.load(open(FIXTURE, encoding="utf-8")).items() if isinstance(v, list)}
    c_migrado, c_direto = contagens(migrado), contagens(direto)
    for t, n in esperado.items():
        assert c_migrado.get(t) == n, f"{t}: fixture {n}, migrado {c_migrado.get(t)}"
    assert c_migrado == c_direto, (c_migrado, c_direto)
    print("   contagens iguais:", sum(esperado.values()), "linhas", flush=True)

    with tempfile.TemporaryDirectory() as tmp:
        a, b = os.path.join(tmp, "migrado.json"), os.path.join(tmp, "direto.json")
        rodar(migrado, "-m", "scripts.regressao", "despejar", a)
        rodar(direto, "-m", "scripts.regressao", "despejar", b)
        saida = subprocess.run([sys.executable, "-m", "scripts.regressao", "comparar", a, b],
                               cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
        print(saida.stdout, flush=True)
        if saida.returncode:
            return 1
    print("migrações ok", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
