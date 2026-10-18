"""Ambiente de migrações do Alembic.

A URL de conexão vem das settings da aplicação (variável de ambiente
``DATABASE_URL``), nunca de um valor fixo neste arquivo.
"""

from logging.config import fileConfig

from sqlalchemy import MetaData, engine_from_config, pool

from alembic import context
from app.core.config import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
# Migrations rodam com a role de migração; runtime usa database_url.
config.set_main_option("sqlalchemy.url", settings.migration_database_url or settings.database_url)

# E0/E1.1: ainda não há modelos declarativos. O metadata vazio é intencional.
# LIMITAÇÃO: `alembic check` (drift) só será significativo quando os modelos
# SQLAlchemy existirem (E1.2+); com metadata vazio ele acusaria as tabelas
# do banco como removidas. O ciclo upgrade/downgrade continua validado em
# tests/db/test_migrations_cycle.py.
target_metadata = MetaData()


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
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
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
