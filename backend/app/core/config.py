"""Configuração da aplicação.

Todas as variáveis de ambiente são lidas aqui. A aplicação falha na
inicialização (fail-fast) se uma variável obrigatória estiver ausente.

Arquivos ``.env`` aceitos (o primeiro que existir): ``backend/.env`` e
``.env`` na raiz do monorepo. Variáveis de ambiente do processo têm
precedência sobre os arquivos.
"""

from functools import lru_cache
from typing import Any

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SECRETS = {"dev-only-insecure-secret-change-in-production"}
_DEV_CREDENTIALS_MARKERS = ("nail_studio:nail_studio", "app_runtime_pw", "app_migration_pw")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Nail Studio API"
    environment: str = "development"
    database_url: str
    migration_database_url: str | None = None
    jwt_secret_key: str
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    verification_token_expire_minutes: int = 24 * 60
    jwt_issuer: str = "nail-studio-api"
    jwt_audience: str = "nail-studio-web"
    terms_version: str = "termos-v1"
    privacy_version: str = "privacidade-v1"
    frontend_url: str = "http://localhost:5173"
    email_provider: str = "fake"
    cors_origins: list[str] = ["http://localhost:5173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: Any) -> Any:
        """Aceita lista JSON ou string separada por vírgulas."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("jwt_secret_key")
    @classmethod
    def _check_secret_length(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("JWT_SECRET_KEY deve ter pelo menos 32 caracteres.")
        return value

    @model_validator(mode="after")
    def _check_production(self) -> "Settings":
        if self.environment != "production":
            return self
        if self.jwt_secret_key in _DEV_SECRETS:
            raise ValueError("Segredo JWT de desenvolvimento não é permitido em produção.")
        if any(marker in self.database_url for marker in _DEV_CREDENTIALS_MARKERS):
            raise ValueError(
                "Credenciais de banco padrão de desenvolvimento não são permitidas em produção."
            )
        if self.email_provider == "fake":
            raise ValueError("EMAIL_PROVIDER=fake não é permitido em produção.")
        return self

    @property
    def cookie_secure(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    # pydantic-settings lê as variáveis de ambiente em runtime; o mypy
    # não enxerga essa leitura e acusa os campos obrigatórios.
    return Settings()  # type: ignore[call-arg]
