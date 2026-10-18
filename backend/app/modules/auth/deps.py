"""Dependências de autenticação.

O tenant NUNCA vem de parâmetro do cliente: o contexto é estabelecido pelo
middleware a partir do access token validado (claims ``sub`` e ``tenant_id``)
e propagado ao contexto transacional. Esta dependência apenas VALIDA a
presença do contexto (fail-closed) para rotas protegidas.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.tenant import get_tenant_context_or_none, get_user_id_or_none

DbSession = Annotated[Session, Depends(get_db)]

UNAUTHORIZED_DETAIL = "Não autenticado."


def get_current_auth() -> dict[str, str]:
    """Exige contexto de usuário/tenant estabelecido pelo middleware."""
    user_id = get_user_id_or_none()
    tenant = get_tenant_context_or_none()
    if user_id is None or tenant is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=UNAUTHORIZED_DETAIL)
    return {"user_id": user_id, "tenant_id": tenant.tenant_id}
