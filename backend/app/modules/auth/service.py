"""Serviços do núcleo de autenticação (E1.2).

Padrão de contexto transacional: operações que conhecem o usuário desde o
início (logout-all) recebem o contexto da dependência. Operações que
descobrem o usuário no meio do caminho (login, refresh, verificação) fazem
o lookup definer PRIMEIRO (sem contexto), commitam, então estabelecem o
contexto e executam as mutações numa NOVA transação — garantindo que o
``SET LOCAL`` do evento `begin` seja aplicado às mutações.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.email import EmailProvider
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    sha256_hash,
    verify_password,
)
from app.core.tenant import (
    TenantContext,
    reset_tenant_context,
    reset_user_context,
    set_tenant_context,
    set_user_context,
)
from app.modules.auth.passwords import WeakPasswordError, validate_password_strength
from app.modules.auth.schemas import LoginRequest, SignupRequest

INVALID_CREDENTIALS_DETAIL = "E-mail ou senha inválidos."
SIGNUP_MESSAGE = "Se o e-mail informado for válido, você receberá um link de verificação."
INVALID_TOKEN_DETAIL = "Token inválido ou expirado."
SESSION_INVALID_DETAIL = "Sessão inválida ou expirada."

# Hash de timing constante para login com e-mail inexistente (anti-enumeração).
_DUMMY_HASH = hash_password("dummy-password-for-timing-equalization")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def signup(
    *, session: Session, request: SignupRequest, provider: EmailProvider, settings: Settings
) -> None:
    """Cria tenant+usuário+perfil+consentimentos+token de verificação atomicamente.

    A resposta HTTP é sempre uniforme: e-mail duplicado não é revelado.
    """
    email = normalize_email(request.email)
    try:
        validate_password_strength(request.password)
    except WeakPasswordError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    password_hash = hash_password(request.password)
    raw_token, token_hash = generate_refresh_token()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.verification_token_expire_minutes)
    try:
        session.execute(
            text(
                "SELECT auth_signup_user(:email, :password_hash, :display_name, :phone,"
                " :timezone, :terms_version, :privacy_version,"
                " :token_hash, :token_expires_at)"
            ),
            {
                "email": email,
                "password_hash": password_hash,
                "display_name": request.display_name,
                "phone": request.phone,
                "timezone": request.timezone,
                "terms_version": request.terms_version,
                "privacy_version": request.privacy_version,
                "token_hash": token_hash,
                "token_expires_at": expires_at,
            },
        )
        session.commit()
    except IntegrityError:
        # E-mail já cadastrado: resposta externa idêntica, sem envio de e-mail.
        session.rollback()
        return
    link = f"{settings.frontend_url}/verificar-email?token={raw_token}"
    provider.send(
        to=email,
        subject="Verifique seu e-mail — Nail Studio Manager",
        text_body=(
            f"Olá, {request.display_name}!\n\n"
            "Confirme seu e-mail clicando no link abaixo (válido por 24 horas):\n"
            f"{link}\n\nSe você não criou esta conta, ignore esta mensagem."
        ),
    )


def confirm_email(*, session: Session, token: str) -> None:
    """Consome o token de uso único e marca o e-mail como verificado."""
    token_hash = sha256_hash(token)
    row = (
        session.execute(
            text(
                "SELECT id, user_id, purpose, expires_at, used_at "
                "FROM auth_lookup_single_use_token(:token_hash)"
            ),
            {"token_hash": token_hash},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_TOKEN_DETAIL)
    if (
        row["purpose"] != "email_verification"
        or row["used_at"] is not None
        or row["expires_at"] <= datetime.now(UTC)
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_TOKEN_DETAIL)
    user_id = str(row["user_id"])
    session.commit()  # encerra a transação do lookup (sem contexto)

    user_token = set_user_context(user_id)
    try:
        session.execute(
            text("UPDATE single_use_tokens SET used_at = now() WHERE id = :id"),
            {"id": row["id"]},
        )
        session.execute(text("SELECT auth_mark_email_verified(:user_id)"), {"user_id": user_id})
        session.commit()
    finally:
        reset_user_context(user_token)


def login(
    *, session: Session, request: LoginRequest, settings: Settings
) -> tuple[str, str, datetime]:
    """Valida credenciais e cria a sessão (família de refresh).

    Retorna ``(access_token, raw_refresh, expires_at_absoluto)``.
    """
    email = normalize_email(request.email)
    row = (
        session.execute(
            text(
                "SELECT id, tenant_id, password_hash, email_verified_at, is_active "
                "FROM auth_lookup_user_by_email(:email)"
            ),
            {"email": email},
        )
        .mappings()
        .first()
    )
    if row is None:
        verify_password(request.password, _DUMMY_HASH)  # equaliza o tempo
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS_DETAIL
        )
    if not verify_password(request.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS_DETAIL
        )
    if not row["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS_DETAIL
        )
    if row["email_verified_at"] is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "EMAIL_NOT_VERIFIED",
                "message": "Confirme seu e-mail antes de entrar.",
            },
        )
    session.commit()  # encerra a transação do lookup (sem contexto)

    user_id = str(row["id"])
    tenant_id = str(row["tenant_id"])
    user_token = set_user_context(user_id)
    tenant_token = set_tenant_context(TenantContext(tenant_id=tenant_id, source="login"))
    try:
        raw_refresh, refresh_hash = generate_refresh_token()
        family_id = uuid4()
        expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
        session.execute(
            text(
                "INSERT INTO refresh_tokens (user_id, token_hash, family_id, expires_at) "
                "VALUES (:user_id, :token_hash, :family_id, :expires_at)"
            ),
            {
                "user_id": user_id,
                "token_hash": refresh_hash,
                "family_id": str(family_id),
                "expires_at": expires_at,
            },
        )
        session.commit()
    finally:
        reset_tenant_context(tenant_token)
        reset_user_context(user_token)

    access_token = create_access_token(
        subject=user_id,
        tenant_id=tenant_id,
        secret=settings.jwt_secret_key,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        expires_minutes=settings.access_token_expire_minutes,
    )
    return access_token, raw_refresh, expires_at


def refresh(
    *, session: Session, raw_token: str | None, settings: Settings
) -> tuple[str, str, datetime]:
    """Rota rotativa com detecção de reuso (revoga a família inteira)."""
    if raw_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=SESSION_INVALID_DETAIL)
    token_hash = sha256_hash(raw_token)
    row = (
        session.execute(
            text(
                "SELECT id, user_id, tenant_id, family_id, expires_at, revoked_at, replaced_by "
                "FROM auth_lookup_refresh_token(:token_hash)"
            ),
            {"token_hash": token_hash},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=SESSION_INVALID_DETAIL)
    now = datetime.now(UTC)
    if row["expires_at"] <= now:
        session.commit()
        user_token = set_user_context(str(row["user_id"]))
        try:
            session.execute(
                text("UPDATE refresh_tokens SET revoked_at = now() WHERE id = :id"),
                {"id": row["id"]},
            )
            session.commit()
        finally:
            reset_user_context(user_token)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=SESSION_INVALID_DETAIL)
    if row["revoked_at"] is not None or row["replaced_by"] is not None:
        # Reuso detectado: revoga TODA a família.
        session.commit()
        user_token = set_user_context(str(row["user_id"]))
        try:
            session.execute(
                text(
                    "UPDATE refresh_tokens SET revoked_at = now() "
                    "WHERE family_id = :family_id AND revoked_at IS NULL"
                ),
                {"family_id": row["family_id"]},
            )
            session.commit()
        finally:
            reset_user_context(user_token)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=SESSION_INVALID_DETAIL)

    # Rotação ATÔMICA no banco (função definer): só o primeiro request que
    # encontrar a linha não-rotacionada vence; concorrentes recebem false e
    # caem no caminho de reuso (família revogada). Não depende de contexto.
    session.commit()
    new_id = uuid4()
    new_raw, new_hash = generate_refresh_token()
    rotated = session.execute(
        text("SELECT auth_rotate_refresh_token(:old_id, :new_id, :new_hash)"),
        {"old_id": row["id"], "new_id": str(new_id), "new_hash": new_hash},
    ).scalar_one()
    session.commit()
    if not rotated:
        user_token = set_user_context(str(row["user_id"]))
        try:
            session.execute(
                text(
                    "UPDATE refresh_tokens SET revoked_at = now() "
                    "WHERE family_id = :family_id AND revoked_at IS NULL"
                ),
                {"family_id": row["family_id"]},
            )
            session.commit()
        finally:
            reset_user_context(user_token)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=SESSION_INVALID_DETAIL)

    access_token = create_access_token(
        subject=str(row["user_id"]),
        tenant_id=str(row["tenant_id"]),
        secret=settings.jwt_secret_key,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        expires_minutes=settings.access_token_expire_minutes,
    )
    return access_token, new_raw, row["expires_at"]


def logout(*, session: Session, raw_token: str | None) -> None:
    """Revoga a família da sessão atual (idempotente)."""
    if raw_token is None:
        return
    token_hash = sha256_hash(raw_token)
    row = (
        session.execute(
            text("SELECT id, user_id, family_id FROM auth_lookup_refresh_token(:token_hash)"),
            {"token_hash": token_hash},
        )
        .mappings()
        .first()
    )
    if row is None:
        session.commit()
        return
    session.commit()
    user_token = set_user_context(str(row["user_id"]))
    try:
        session.execute(
            text(
                "UPDATE refresh_tokens SET revoked_at = now() "
                "WHERE family_id = :family_id AND revoked_at IS NULL"
            ),
            {"family_id": row["family_id"]},
        )
        session.commit()
    finally:
        reset_user_context(user_token)


def logout_all(*, session: Session) -> None:
    """Revoga TODAS as sessões do usuário autenticado (contexto já estabelecido)."""
    session.execute(text("DELETE FROM refresh_tokens WHERE user_id = app_current_user_id()"))
    session.commit()


__all__ = [
    "confirm_email",
    "login",
    "logout",
    "logout_all",
    "normalize_email",
    "refresh",
    "signup",
]
