"""Fixtures dos testes de autenticação.

IMPORTANTE: a API sob teste usa a URL de RUNTIME (app_runtime), para que os
fluxos reais passem pelas políticas RLS e restrições colunares — nunca por
uma role administrativa.
"""

import os

os.environ["DATABASE_URL"] = os.environ.get(
    "RUNTIME_DATABASE_URL",
    "postgresql+psycopg://app_runtime:app_runtime_pw@localhost:5432/nail_studio",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import Settings, get_settings  # noqa: E402
from app.core.db import get_engine  # noqa: E402
from app.core.email import FakeEmailProvider, get_email_provider  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _clean_test_users(admin_engine):
    """Remove resíduos de execuções anteriores (nunca os usuários seedados)."""
    delete = text(
        "DELETE FROM users WHERE email LIKE '%@exemplo.com' "
        "AND email NOT IN ('ana@exemplo.com', 'bia@exemplo.com')"
    )
    with admin_engine.begin() as connection:
        connection.execute(delete)
    yield
    with admin_engine.begin() as connection:
        connection.execute(delete)


@pytest.fixture()
def email_provider() -> FakeEmailProvider:
    return FakeEmailProvider()


@pytest.fixture()
def client(email_provider: FakeEmailProvider) -> TestClient:
    get_settings.cache_clear()
    get_engine.cache_clear()
    app = create_app()
    app.state.limiter.reset()
    app.dependency_overrides[get_email_provider] = lambda: email_provider
    return TestClient(app)


@pytest.fixture()
def settings() -> Settings:
    return get_settings()
