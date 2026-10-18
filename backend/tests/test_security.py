"""Testes de unidade das primitivas de segurança (E0).

Não há rotas nem tabelas de autenticação nesta etapa — apenas os
utilitários aprovados no ADR 0002.
"""

from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest

from app.core.security import (
    ACCESS_TOKEN_ALGORITHM,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)

SECRET = "test-secret-with-at-least-32-bytes-length-0000000000000000"
WRONG_SECRET = "another-secret-with-at-least-32-bytes-length-000000000000"


def test_password_hash_and_verify_roundtrip() -> None:
    hashed = hash_password("senha-forte-123")
    assert hashed != "senha-forte-123"
    assert verify_password("senha-forte-123", hashed) is True


def test_verify_rejects_wrong_password() -> None:
    hashed = hash_password("senha-forte-123")
    assert verify_password("senha-errada", hashed) is False


def test_verify_handles_malformed_hash() -> None:
    assert verify_password("qualquer", "nao-e-um-hash-argon2") is False


def test_access_token_roundtrip() -> None:
    token = create_access_token(subject="user-1", secret=SECRET, expires_minutes=15)
    payload = decode_access_token(token, secret=SECRET)
    assert payload["sub"] == "user-1"
    assert payload["type"] == "access"


def test_expired_access_token_is_rejected() -> None:
    token = create_access_token(subject="user-1", secret=SECRET, expires_minutes=-1)
    with pytest.raises(pyjwt.PyJWTError):
        decode_access_token(token, secret=SECRET)


def test_token_with_wrong_secret_is_rejected() -> None:
    token = create_access_token(subject="user-1", secret=SECRET, expires_minutes=15)
    with pytest.raises(pyjwt.PyJWTError):
        decode_access_token(token, secret=WRONG_SECRET)


def test_token_with_wrong_type_is_rejected() -> None:
    now = datetime.now(UTC)
    token = pyjwt.encode(
        {
            "sub": "user-1",
            "type": "refresh",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        SECRET,
        algorithm=ACCESS_TOKEN_ALGORITHM,
    )
    with pytest.raises(ValueError, match="Tipo de token inválido"):
        decode_access_token(token, secret=SECRET)


def test_refresh_token_is_opaque_and_hashed() -> None:
    raw, hashed = generate_refresh_token()
    assert raw != hashed
    assert len(raw) >= 48
    assert hash_refresh_token(raw) == hashed


def test_refresh_tokens_are_unique() -> None:
    raw_1, hashed_1 = generate_refresh_token()
    raw_2, hashed_2 = generate_refresh_token()
    assert raw_1 != raw_2
    assert hashed_1 != hashed_2
