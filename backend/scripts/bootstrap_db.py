"""Aplica o bootstrap de roles/permissões do banco (idempotente).

Uso (a partir de ``backend/``):

    uv run python scripts/bootstrap_db.py

Conecta como superusuário usando ``BOOTSTRAP_DATABASE_URL``. Em dev, o
superusuário do Docker Compose é ``nail_studio``; no PostgreSQL portátil
local é ``postgres`` (ajuste a variável).

Nenhum segredo real deve estar aqui — apenas valores de desenvolvimento
documentados no ``.env.example``.
"""

import os
from pathlib import Path

from sqlalchemy import create_engine

SQL_FILE = Path(__file__).with_name("bootstrap_db.sql")

DEFAULT_URL = "postgresql+psycopg://nail_studio:nail_studio@localhost:5432/nail_studio"


def main() -> int:
    url = os.environ.get("BOOTSTRAP_DATABASE_URL", DEFAULT_URL)
    statements = SQL_FILE.read_text(encoding="utf-8")
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        connection.exec_driver_sql(statements)
    engine.dispose()
    print("Bootstrap de roles concluído (idempotente).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
