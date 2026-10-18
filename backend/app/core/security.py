"""Primitivas de segurança preparadas na E0.

Apenas utilitários testados por unidade. NÃO há rotas de autenticação nem
tabelas de usuário/sessão nesta etapa (E1).

Decisão aprovada (ADR 0002): e-mail + senha com Argon2id; access token JWT
de curta duração; refresh token opaco, rotativo e armazenado apenas como
hash SHA-256.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

_password_hasher = PasswordHasher()

ACCESS_TOKEN_TYPE = "access"
ACCESS_TOKEN_ALGORITHM = "HS256"
REQUIRED_ACCESS_CLAIMS = ["sub", "tenant_id", "iss", "aud", "iat", "exp", "jti"]


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def create_access_token(
    *,
    subject: str,
    tenant_id: str,
    secret: str,
    issuer: str,
    audience: str,
    expires_minutes: int,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "tenant_id": tenant_id,
        "type": ACCESS_TOKEN_TYPE,
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, secret, algorithm=ACCESS_TOKEN_ALGORITHM)


def decode_access_token(token: str, *, secret: str, issuer: str, audience: str) -> dict[str, Any]:
    """Valida assinatura, algoritmo, claims obrigatórias, iss/aud, iat e exp.

    Lança ``jwt.PyJWTError`` para assinatura/expiracão/claims inválidas e
    ``ValueError`` se o tipo do token não for ``access``.
    """
    payload = jwt.decode(
        token,
        secret,
        algorithms=[ACCESS_TOKEN_ALGORITHM],
        issuer=issuer,
        audience=audience,
        options={"require": REQUIRED_ACCESS_CLAIMS, "verify_iat": True},
    )
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise ValueError("Tipo de token inválido.")
    return payload


def generate_refresh_token() -> tuple[str, str]:
    """Gera um refresh token opaco.

    Retorna ``(token_bruto, hash_sha256)``. Somente o hash deve ser
    persistido; o token bruto vai para o cookie do cliente.
    """
    raw = secrets.token_urlsafe(48)
    return raw, sha256_hash(raw)


def hash_refresh_token(raw_token: str) -> str:
    return sha256_hash(raw_token)


def sha256_hash(value: str) -> str:
    """Hash SHA-256 hex usado para refresh tokens e tokens de uso único."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
