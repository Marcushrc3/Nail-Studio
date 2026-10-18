"""Testes de configuração (fail-fast, parsing e validação de produção)."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

SECRET_32 = "test-secret-with-at-least-32-bytes-length"


def test_settings_parse_comma_separated_cors() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://u:p@localhost:5432/db",
        jwt_secret_key=SECRET_32,
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
        jwt_secret_key=SECRET_32,
    )
    assert settings.access_token_expire_minutes == 15
    assert settings.refresh_token_expire_days == 30
    assert settings.cors_origins == ["http://localhost:5173"]
    assert settings.environment == "development"
    assert settings.cookie_secure is False


def test_short_jwt_secret_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://u:p@localhost:5432/db",
            jwt_secret_key="curto",
        )


def test_production_rejects_dev_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="desenvolvimento"):
        Settings(
            _env_file=None,
            environment="production",
            database_url="postgresql+psycopg://prod:forte@db:5432/app",
            jwt_secret_key="dev-only-insecure-secret-change-in-production",
        )


def test_production_rejects_dev_database_credentials() -> None:
    with pytest.raises(ValidationError, match="Credenciais de banco"):
        Settings(
            _env_file=None,
            environment="production",
            database_url="postgresql+psycopg://nail_studio:nail_studio@db:5432/app",
            jwt_secret_key=SECRET_32,
        )


def test_production_rejects_fake_email_provider() -> None:
    with pytest.raises(ValidationError, match="EMAIL_PROVIDER"):
        Settings(
            _env_file=None,
            environment="production",
            database_url="postgresql+psycopg://prod:forte@db:5432/app",
            jwt_secret_key=SECRET_32,
        )


def test_production_accepts_strong_configuration() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        database_url="postgresql+psycopg://prod:senha-forte@db:5432/app",
        jwt_secret_key=SECRET_32,
        email_provider="smtp",
    )
    assert settings.cookie_secure is True
