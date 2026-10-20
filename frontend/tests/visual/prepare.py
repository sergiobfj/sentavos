"""Cria apenas usuários sintéticos no Postgres local para a revisão visual V2.

Da raiz: .venv/Scripts/python.exe frontend/tests/visual/prepare.py
Não remove nem altera usuários ou registros anteriores.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[3]
source = (root / "frontend/tests/refino/prepare.py").read_text(encoding="utf-8")
source = source.replace(".local/refino-users.json", ".local/visual-v2-users.json")
exec(compile(source, str(root / "frontend/tests/refino/prepare.py"), "exec"), {
    "__file__": str(root / "frontend/tests/refino/prepare.py"),
    "__name__": "__main__",
})
