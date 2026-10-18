"""Testes de configuração (fail-fast e parsing)."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_parse_comma_separated_cors() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://u:p@localhost:5432/db",
        jwt_secret_key="secret",
        cors_origins="http://localhost:5173, http://192.168.0.10:5173",
    )
    assert settings.cors_origins == ["http://localhost:5173", "http://192.168.0.10:5173"]


def test_missing_required_env_vars_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_defaults_are_applied() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://u:p@localhost:5432/db",
        jwt_secret_key="secret",
    )
    assert settings.access_token_expire_minutes == 15
    assert settings.cors_origins == ["http://localhost:5173"]
    assert settings.environment == "development"
