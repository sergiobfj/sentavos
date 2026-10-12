"""Em que ambiente o código roda, e a trava contra produção por acidente.

`APP_ENV` é `development`, `test` ou `production`. Sem a variável:
  - no Render (que define `RENDER=true` no serviço) é produção — derrubar a API
    por falta de uma variável seria pior que o risco que ela evita;
  - em qualquer outro lugar é `development`.

A trava: banco que não é local (SQLite ou localhost) é tratado como produção.
  - `development` ou `test` com banco remoto: recusa, sempre.
  - `production` no Render: segue (é o servidor).
  - `production` numa ferramenta local (script, alembic, uvicorn na máquina):
    exige TAMBÉM `ALLOW_PRODUCTION_DATABASE=true`. Duas escolhas deliberadas —
    o arquivo de produção e a permissão na linha de comando —, nunca uma só.

O caso que motivou: o `.env` da máquina apontava pro Neon de produção, e
qualquer `python -c "import app.main"` local abria conexão com ele.
"""

import os
import sys

from sqlalchemy.engine import make_url

AMBIENTES = {"development", "test", "production"}
HOSTS_LOCAIS = {"localhost", "127.0.0.1", "::1"}


class AmbienteInvalido(RuntimeError):
    """Configuração de ambiente que não pode seguir."""


def no_render() -> bool:
    return bool(os.getenv("RENDER"))


def app_env() -> str:
    bruto = (os.getenv("APP_ENV") or "").strip().lower()
    if not bruto:
        return "production" if no_render() else "development"
    if bruto not in AMBIENTES:
        raise AmbienteInvalido(f"APP_ENV={bruto!r} não existe. Use development, test ou production.")
    return bruto


def banco_local(url: str) -> bool:
    u = make_url(url)
    if u.get_backend_name() == "sqlite":
        return True
    return (u.host or "") in HOSTS_LOCAIS


def descrever(url: str) -> str:
    """Host e banco, sem usuário nem senha — o que pode aparecer em log."""
    u = make_url(url)
    if u.get_backend_name() == "sqlite":
        return f"sqlite:{u.database or ':memory:'}"
    return f"{u.get_backend_name()}://{u.host}:{u.port or ''}/{u.database}"


def verificar_banco(url: str) -> str:
    """Recusa a combinação perigosa; devolve o ambiente efetivo."""
    ambiente = app_env()
    if banco_local(url):
        return ambiente
    if ambiente != "production":
        raise AmbienteInvalido(
            f"APP_ENV={ambiente} apontando para um banco remoto ({descrever(url)}). "
            "Fora de produção o banco é local. Para operar a produção de propósito, use o "
            "arquivo de produção (APP_ENV=production) e ALLOW_PRODUCTION_DATABASE=true."
        )
    if no_render():
        return ambiente
    if (os.getenv("ALLOW_PRODUCTION_DATABASE") or "").strip().lower() != "true":
        raise AmbienteInvalido(
            f"Ferramenta local conectando na PRODUÇÃO ({descrever(url)}) sem "
            "ALLOW_PRODUCTION_DATABASE=true. Isso nunca acontece por acidente: passe a "
            "permissão na linha de comando, só quando for de propósito."
        )
    print(f"!! PRODUÇÃO: {descrever(url)} (APP_ENV=production, permissão explícita)", file=sys.stderr)
    return ambiente
