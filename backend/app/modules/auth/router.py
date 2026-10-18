"""Rotas do núcleo de autenticação (E1.2)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core.config import Settings, get_settings
from app.core.email import EmailProvider, get_email_provider
from app.core.rate_limit import limiter
from app.modules.auth import service
from app.modules.auth.cookies import (
    clear_refresh_cookie,
    read_refresh_cookie,
    set_refresh_cookie,
)
from app.modules.auth.deps import DbSession, get_current_auth
from app.modules.auth.schemas import LoginRequest, SignupRequest, VerificationConfirmRequest

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

EmailDep = Annotated[EmailProvider, Depends(get_email_provider)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
AuthDep = Annotated[dict[str, Any], Depends(get_current_auth)]


@router.post("/signup", status_code=202)
@limiter.limit("5/minute")
def signup(
    request: Request,
    body: SignupRequest,
    session: DbSession,
    provider: EmailDep,
    settings: SettingsDep,
) -> dict[str, str]:
    service.signup(session=session, request=body, provider=provider, settings=settings)
    return {"message": service.SIGNUP_MESSAGE}


@router.post("/verification/confirm")
@limiter.limit("10/minute")
def verification_confirm(
    request: Request, body: VerificationConfirmRequest, session: DbSession
) -> dict[str, str]:
    service.confirm_email(session=session, token=body.token)
    return {"message": "E-mail verificado com sucesso."}


@router.post("/login")
@limiter.limit("5/minute")
def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    session: DbSession,
    settings: SettingsDep,
) -> dict[str, Any]:
    access_token, raw_refresh, expires_at = service.login(
        session=session, request=body, settings=settings
    )
    set_refresh_cookie(
        response,
        raw_refresh,
        max_age_seconds=settings.refresh_token_expire_days * 24 * 60 * 60,
        secure=settings.cookie_secure,
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
        "refresh_expires_at": expires_at.isoformat(),
    }


@router.post("/refresh")
@limiter.limit("10/minute")
def refresh(
    request: Request,
    response: Response,
    session: DbSession,
    settings: SettingsDep,
) -> dict[str, Any]:
    try:
        access_token, new_raw, expires_at = service.refresh(
            session=session, raw_token=read_refresh_cookie(request), settings=settings
        )
    except HTTPException:
        clear_refresh_cookie(response, secure=settings.cookie_secure)
        raise
    set_refresh_cookie(
        response,
        new_raw,
        max_age_seconds=settings.refresh_token_expire_days * 24 * 60 * 60,
        secure=settings.cookie_secure,
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
        "refresh_expires_at": expires_at.isoformat(),
    }


@router.post("/logout", status_code=204)
@limiter.limit("10/minute")
def logout(
    request: Request,
    response: Response,
    session: DbSession,
    settings: SettingsDep,
) -> None:
    service.logout(session=session, raw_token=read_refresh_cookie(request))
    clear_refresh_cookie(response, secure=settings.cookie_secure)


@router.post("/logout-all", status_code=204)
@limiter.limit("10/minute")
def logout_all(
    request: Request,
    response: Response,
    session: DbSession,
    settings: SettingsDep,
    _auth: AuthDep,
) -> None:
    service.logout_all(session=session)
    clear_refresh_cookie(response, secure=settings.cookie_secure)
