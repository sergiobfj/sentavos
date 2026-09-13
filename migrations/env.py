"""Configuração do Alembic.

A URL do banco vem do ambiente, não do alembic.ini. É o mesmo motivo de sempre:
a string de conexão é segredo e não entra no repositório — e assim `alembic
upgrade` na sua máquina e no Render leem exatamente a mesma variável que a API.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# Importar os modelos é o que popula o SQLModel.metadata. Sem isto o
# autogenerate acha que o banco inteiro é para ser apagado.
from app import models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

url = os.getenv("DATABASE_URL")
if not url:
    raise RuntimeError("DATABASE_URL não configurada. Veja o .env.example.")
config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Sem isto o Alembic não percebe mudança de tipo de coluna nem de
            # nulidade, que é metade do que uma migração costuma precisar.
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
