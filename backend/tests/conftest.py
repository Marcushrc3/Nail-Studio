"""Fixtures globais de infraestrutura (E0).

ATENÇÃO: as variáveis de ambiente são definidas ANTES de qualquer import
de ``app``, pois a configuração é lida uma única vez por processo.
"""

import os
from collections.abc import Iterator

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://nail_studio:nail_studio@localhost:5432/nail_studio",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-not-for-production")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, create_engine  # noqa: E402

from app.main import app  # noqa: E402
from tests.isolation.app import build_app  # noqa: E402
from tests.isolation.db import DROP_DDL, PROBE_DDL  # noqa: E402


@pytest.fixture(scope="session")
def engine() -> Engine:
    """Engine padrão para os testes que exigem banco real (docker compose)."""
    return create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)


@pytest.fixture(scope="session")
def single_connection_engine() -> Engine:
    """Engine com pool de UMA conexão, para o teste de reutilização do pool."""
    return create_engine(os.environ["DATABASE_URL"], pool_size=1, max_overflow=0)


@pytest.fixture(scope="session")
def _probe_table(engine: Engine) -> Iterator[None]:
    """Tabela sintética do harness de isolamento.

    Criada e removida por fixtures de teste — NUNCA por migrations.
    """
    with engine.begin() as connection:
        connection.execute(PROBE_DDL)
    yield
    with engine.begin() as connection:
        connection.execute(DROP_DDL)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="session")
def harness_client(engine: Engine, _probe_table: None) -> TestClient:
    """Cliente do harness de isolamento (principals sintéticos)."""
    return TestClient(build_app(engine))
