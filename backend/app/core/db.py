"""Configuração do engine e da sessão do SQLAlchemy.

E0: apenas infraestrutura de conexão. Nenhum modelo de negócio existe
ainda (as tabelas entram a partir da E1, via Alembic).
"""

from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.tenant import get_tenant_context_or_none, get_user_id_or_none


def _set_local_auth_context(connection: Connection, *args: Any, **kwargs: Any) -> None:
    """Aplica o contexto de tenant/usuário com ``SET LOCAL`` no início da transação.

    ``set_config(..., true)`` equivale a ``SET LOCAL``: o valor morre no
    commit/rollback e a conexão volta limpa ao pool. Request sem contexto
    não seta nada -> as políticas RLS negam tudo (fail-closed).
    """
    tenant = get_tenant_context_or_none()
    if tenant is not None:
        connection.execute(
            text("SELECT set_config('app.current_tenant_id', :value, true)"),
            {"value": str(tenant.tenant_id)},
        )
    user_id = get_user_id_or_none()
    if user_id is not None:
        connection.execute(
            text("SELECT set_config('app.current_user_id', :value, true)"),
            {"value": user_id},
        )


def create_engine_from_url(url: str, **kwargs: Any) -> Engine:
    engine = create_engine(url, pool_pre_ping=True, **kwargs)
    event.listen(engine, "begin", _set_local_auth_context)
    return engine


@lru_cache
def get_engine() -> Engine:
    return create_engine_from_url(get_settings().database_url)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Dependência FastAPI: sessão por request, fechada ao final."""
    session = create_session_factory(get_engine())()
    try:
        yield session
    finally:
        session.close()
