"""Infraestrutura de contexto do tenant (E0).

Define APENAS o transporte do contexto da profissional autenticada do
request até a camada de dados, usando um ``ContextVar`` (estado por
request/task, sem estado persistente na conexão do pool).

Não há autenticação real na E0: o contexto é estabelecido por
dependência/middleware e, nos testes, por principals sintéticos
(ver ``backend/tests/isolation/``). O fail-closed é intencional:
request sem contexto é negado (401), nunca aberto.
"""

from contextvars import ContextVar, Token
from dataclasses import dataclass

from fastapi import HTTPException, status


class TenantContextError(RuntimeError):
    """Contexto de tenant ausente onde era obrigatório."""


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: str
    source: str


_current_tenant: ContextVar[TenantContext | None] = ContextVar("current_tenant", default=None)
_current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)


def set_tenant_context(context: TenantContext) -> Token[TenantContext | None]:
    """Estabelece o contexto do tenant para a duração do request."""
    return _current_tenant.set(context)


def reset_tenant_context(token: Token[TenantContext | None]) -> None:
    """Restaura o contexto anterior (chamar no fim do request)."""
    try:
        _current_tenant.reset(token)
    except ValueError:
        # Mesmo caso de reset_user_context: contexto de execução diferente.
        return


def get_tenant_context() -> TenantContext:
    context = _current_tenant.get()
    if context is None:
        raise TenantContextError("Nenhum contexto de tenant estabelecido para este request.")
    return context


def get_tenant_context_or_none() -> TenantContext | None:
    """Versão opcional usada pelo wiring transacional (db.py)."""
    return _current_tenant.get()


def set_user_context(user_id: str) -> Token[str | None]:
    """Estabelece o id do usuário autenticado para a duração do request."""
    return _current_user_id.set(user_id)


def reset_user_context(token: Token[str | None]) -> None:
    """Restaura o contexto de usuário anterior (chamar no fim do request)."""
    try:
        _current_user_id.reset(token)
    except ValueError:
        # Token criado em outro Context (ex.: limpeza de dependência executada
        # no event loop, enquanto o valor foi setado no worker thread). O
        # Context do worker é descartado ao fim do request, então não há vazamento.
        return


def get_user_id_or_none() -> str | None:
    """Versão opcional usada pelo wiring transacional (db.py)."""
    return _current_user_id.get()


def require_tenant() -> TenantContext:
    """Dependência FastAPI: retorna o tenant atual ou responde 401 (fail-closed)."""
    try:
        return get_tenant_context()
    except TenantContextError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não autenticado.",
        ) from exc
