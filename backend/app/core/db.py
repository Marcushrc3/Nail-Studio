"""Configuração do engine e da sessão do SQLAlchemy.

E0: apenas infraestrutura de conexão. Nenhum modelo de negócio existe
ainda (as tabelas entram a partir da E1, via Alembic).
"""

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def create_engine_from_url(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True)


@lru_cache
def get_engine() -> Engine:
    return create_engine_from_url(get_settings().database_url)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
