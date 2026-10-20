"""Compara uma branch de recuperação Neon ao backup pré-release, só leitura."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import sqlalchemy as sa
from dotenv import dotenv_values

from scripts.reconciliar_essencial_20261019 import inventory_matches

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--branch-id", required=True)
    args = parser.parse_args()
    assert args.branch_id.startswith("br-")
    content = args.baseline.read_bytes()
    assert hashlib.sha256(content).hexdigest() == args.sha256
    baseline = json.loads(content)
    recovery_url = os.environ["NEON_RECOVERY_DATABASE_URL"]
    production_url = dotenv_values(ROOT / ".env.production.local")["DATABASE_URL"]
    recovery = sa.engine.make_url(recovery_url)
    production = sa.engine.make_url(production_url)
    assert recovery.host and recovery.host.endswith("neon.tech")
    assert recovery.host != production.host and recovery.database == production.database
    with sa.create_engine(recovery_url, pool_pre_ping=True).connect() as conn:
        conn.execute(sa.text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        assert conn.scalar(sa.text("SELECT current_database()")) == recovery.database
        inventory_matches(conn, baseline)
        assert conn.scalar(sa.text("SELECT version_num FROM alembic_version")) == "0013_abatimento_compromisso"
        assert conn.scalar(sa.text("SELECT count(*) FROM financial_accounts WHERE user_id=1")) == 4
        assert conn.scalar(sa.text("SELECT amount_paid FROM transactions WHERE user_id=1 AND id=1168")) == 5.8
        assert conn.scalar(sa.text("SELECT total_amount FROM purchases WHERE user_id=1 AND id=49")) == 5.8
    print(json.dumps({"verified": True, "branch_id": args.branch_id,
                      "tables": len(baseline["tables"]),
                      "rows": sum(map(len, baseline["tables"].values())),
                      "baseline_sha256": args.sha256}))


if __name__ == "__main__":
    main()
