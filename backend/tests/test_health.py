"""Testes do health check.

O caminho de sucesso exige PostgreSQL real (docker compose) — é um teste
de integração e falha se o banco não estiver de pé. O caminho de falha usa
um engine apontando para uma porta inacessível.
"""

from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine

from app.api.health import get_health_engine


def test_health_returns_200_with_real_database(client: TestClient, engine: Engine) -> None:
    app = client.app
    app.dependency_overrides[get_health_engine] = lambda: engine
    try:
        response = client.get("/health")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_returns_503_when_database_unreachable(client: TestClient) -> None:
    bad_engine = create_engine(
        "postgresql+psycopg://nobody:nothing@127.0.0.1:59999/none",
        connect_args={"connect_timeout": 2},
    )
    app = client.app
    app.dependency_overrides[get_health_engine] = lambda: bad_engine
    try:
        response = client.get("/health")
    finally:
        app.dependency_overrides.clear()
        bad_engine.dispose()
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "error"}
