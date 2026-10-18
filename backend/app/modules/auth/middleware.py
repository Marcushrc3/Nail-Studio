"""Middleware de contexto de tenant/usuário (ASGI).

Decodifica o access token do header ``Authorization`` no contexto do event
loop e estabelece os ContextVars, que se propagam para os workers do
endpoint (qualquerio.to_thread copia o contexto). Request sem token válido
segue SEM contexto: rotas protegidas respondem 401 via dependência
(fail-closed) e rotas públicas (signup/login/refresh) funcionam normalmente.
"""

from __future__ import annotations

import jwt as pyjwt
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.core.tenant import (
    TenantContext,
    reset_tenant_context,
    reset_user_context,
    set_tenant_context,
    set_user_context,
)


class TenantContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        tenant_token = None
        user_token = None
        auth_header = Headers(scope=scope).get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            raw_token = auth_header[7:].strip()
            settings = get_settings()
            try:
                payload = decode_access_token(
                    raw_token,
                    secret=settings.jwt_secret_key,
                    issuer=settings.jwt_issuer,
                    audience=settings.jwt_audience,
                )
                tenant_token = set_tenant_context(
                    TenantContext(tenant_id=str(payload["tenant_id"]), source="access-token")
                )
                user_token = set_user_context(str(payload["sub"]))
            except (ValueError, pyjwt.PyJWTError):
                # Token inválido: segue sem contexto (fail-closed).
                pass
        try:
            await self.app(scope, receive, send)
        finally:
            if user_token is not None:
                reset_user_context(user_token)
            if tenant_token is not None:
                reset_tenant_context(tenant_token)
