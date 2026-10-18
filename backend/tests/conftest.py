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
os.environ.setdefault(
    "TEST_ADMIN_DATABASE_URL",
    "postgresql+psycopg://nail_studio:nail_studio@localhost:5432/nail_studio",
)
os.environ.setdefault(
    "RUNTIME_DATABASE_URL",
    "postgresql+psycopg://app_runtime:app_runtime_pw@localhost:5432/nail_studio",
)
os.environ.setdefault(
    "MIGRATION_DATABASE_URL",
    "postgresql+psycopg://app_migration:app_migration_pw@localhost:5432/nail_studio",
)
os.environ.setdefault(
    "UNPRIVILEGED_DATABASE_URL",
    "postgresql+psycopg://app_unprivileged:app_unprivileged_pw@localhost:5432/nail_studio",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, create_engine, text  # noqa: E402

from app.core.db import create_engine_from_url  # noqa: E402
from app.main import app  # noqa: E402
from tests.isolation.app import build_app  # noqa: E402
from tests.isolation.db import DROP_DDL, PROBE_DDL  # noqa: E402


@pytest.fixture(scope="session")
def engine() -> Engine:
    """Engine administrativo usado pelos testes E0 (tabela de harness etc.)."""
    return create_engine(os.environ["TEST_ADMIN_DATABASE_URL"], pool_pre_ping=True)


@pytest.fixture(scope="session")
def single_connection_engine() -> Engine:
    """Engine com pool de UMA conexão (harness E0; usa a URL administrativa)."""
    return create_engine(os.environ["TEST_ADMIN_DATABASE_URL"], pool_size=1, max_overflow=0)


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


@pytest.fixture(scope="session")
def runtime_engine() -> Engine:
    """Engine conectado como a role REAL de runtime (app_runtime), sujeita a RLS."""
    return create_engine_from_url(os.environ["RUNTIME_DATABASE_URL"])


@pytest.fixture(scope="session")
def unprivileged_engine() -> Engine:
    """Engine sem NENHUM privilégio (só CONNECT), para provar negações."""
    return create_engine(os.environ["UNPRIVILEGED_DATABASE_URL"], pool_pre_ping=True)


@pytest.fixture(scope="session")
def admin_engine() -> Engine:
    """Engine administrativo apenas para testes (cria/remove banco descartável)."""
    return create_engine(os.environ["TEST_ADMIN_DATABASE_URL"], pool_pre_ping=True)


@pytest.fixture(scope="session")
def seeded_users(runtime_engine: Engine, admin_engine: Engine) -> dict[str, dict[str, str]]:
    """Duas contas reais criadas pela função definer executada como app_runtime.

    Requer que as migrations da E1.1 já tenham sido aplicadas no banco de
    desenvolvimento/CI (o CI executa ``alembic upgrade head`` antes do pytest).
    Idempotente entre execuções: remove resíduos antes e depois (via engine
    administrativo, que não participa dos testes de RLS).
    """
    emails = ("ana@exemplo.com", "bia@exemplo.com")
    with admin_engine.begin() as connection:
        connection.execute(
            text("DELETE FROM users WHERE email IN (:a, :b)"),
            {"a": emails[0], "b": emails[1]},
        )
    with runtime_engine.begin() as connection:
        user_a = connection.execute(
            text(
                "SELECT auth_signup_user("
                "'ana@exemplo.com', 'hash-ana', 'Ana Profissional',"
                " '+5511999990001', 'America/Sao_Paulo', 'termos-v1', 'privacidade-v1',"
                " 'verif-hash-a', now() + interval '1 day')"
            )
        ).scalar_one()
        user_b = connection.execute(
            text(
                "SELECT auth_signup_user("
                "'bia@exemplo.com', 'hash-bia', 'Bia Profissional',"
                " '+5511999990002', 'America/Sao_Paulo', 'termos-v1', 'privacidade-v1',"
                " 'verif-hash-b', now() + interval '1 day')"
            )
        ).scalar_one()
    with runtime_engine.connect() as connection:
        tenant_a = connection.execute(
            text("SELECT tenant_id FROM auth_lookup_user_by_email('ana@exemplo.com')")
        ).scalar_one()
    yield {
        "a": {
            "user_id": str(user_a),
            "tenant_id": str(tenant_a),
            "email": "ana@exemplo.com",
        },
        "b": {
            "user_id": str(user_b),
            "email": "bia@exemplo.com",
        },
    }
    with admin_engine.begin() as connection:
        connection.execute(
            text("DELETE FROM users WHERE email IN (:a, :b)"),
            {"a": emails[0], "b": emails[1]},
        )
