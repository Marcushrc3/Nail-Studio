"""Aplicação FastAPI — Nail Studio Manager (E0).

Nesta etapa existem apenas a configuração validada (fail-fast) e o health
check. Funcionalidades de negócio entram a partir da E1.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request

from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.modules.auth.middleware import TenantContextMiddleware
from app.modules.auth.router import router as auth_router


async def _rate_limit_handler(request: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Muitas tentativas. Aguarde um instante e tente novamente."},
    )


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, version="0.1.0")
    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
    application.add_middleware(TenantContextMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health_router)
    application.include_router(auth_router)
    return application


app = create_app()
