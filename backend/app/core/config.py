"""Configuração da aplicação.

Todas as variáveis de ambiente são lidas aqui. A aplicação falha na
inicialização (fail-fast) se uma variável obrigatória estiver ausente.

Arquivos ``.env`` aceitos (o primeiro que existir): ``backend/.env`` e
``.env`` na raiz do monorepo. Variáveis de ambiente do processo têm
precedência sobre os arquivos.
"""

from functools import lru_cache
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Nail Studio API"
    environment: str = "development"
    database_url: str
    jwt_secret_key: str
    access_token_expire_minutes: int = 15
    cors_origins: list[str] = ["http://localhost:5173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: Any) -> Any:
        """Aceita lista JSON ou string separada por vírgulas."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    # pydantic-settings lê as variáveis de ambiente em runtime; o mypy
    # não enxerga essa leitura e acusa os campos obrigatórios.
    return Settings()  # type: ignore[call-arg]
