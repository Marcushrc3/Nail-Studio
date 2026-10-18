"""Testes de unidade das primitivas de segurança (E0/E1.2).

Cobre Argon2id, refresh opaco e o JWT com claims completas, incluindo os
casos negativos obrigatórios (alg=none, algoritmo errado, claims ausentes,
iat futuro, token expirado, iss/aud errados).
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
    sha256_hash,
    verify_password,
)

SECRET = "test-secret-with-at-least-32-bytes-length-0000000000000000"
WRONG_SECRET = "another-secret-with-at-least-32-bytes-length-000000000000"
ISSUER = "nail-studio-api"
AUDIENCE = "nail-studio-web"


def _make_access_token(**overrides: object) -> str:
    params: dict[str, object] = {
        "subject": "user-1",
        "tenant_id": "11111111-1111-1111-1111-111111111111",
        "secret": SECRET,
        "issuer": ISSUER,
        "audience": AUDIENCE,
        "expires_minutes": 15,
    }
    params.update(overrides)
    return create_access_token(**params)


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
    token = _make_access_token()
    payload = decode_access_token(token, secret=SECRET, issuer=ISSUER, audience=AUDIENCE)
    assert payload["sub"] == "user-1"
    assert payload["type"] == "access"
    assert payload["tenant_id"] == "11111111-1111-1111-1111-111111111111"
    assert payload["iss"] == ISSUER
    assert payload["aud"] == AUDIENCE
    assert payload["jti"]


def test_expired_access_token_is_rejected() -> None:
    token = _make_access_token(expires_minutes=-1)
    with pytest.raises(pyjwt.PyJWTError):
        decode_access_token(token, secret=SECRET, issuer=ISSUER, audience=AUDIENCE)


def test_token_with_wrong_secret_is_rejected() -> None:
    token = _make_access_token()
    with pytest.raises(pyjwt.PyJWTError):
        decode_access_token(token, secret=WRONG_SECRET, issuer=ISSUER, audience=AUDIENCE)


def test_token_with_alg_none_is_rejected() -> None:
    import base64
    import json

    def _b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    now = datetime.now(UTC)
    header = _b64(b'{"alg": "none", "typ": "JWT"}')
    payload = _b64(
        json.dumps(
            {
                "sub": "user-1",
                "tenant_id": "11111111-1111-1111-1111-111111111111",
                "type": "access",
                "iss": ISSUER,
                "aud": AUDIENCE,
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=15)).timestamp()),
                "jti": "jti-1",
            }
        ).encode()
    )
    token = f"{header}.{payload}."
    with pytest.raises(pyjwt.InvalidAlgorithmError):
        decode_access_token(token, secret=SECRET, issuer=ISSUER, audience=AUDIENCE)


def test_token_with_wrong_algorithm_is_rejected() -> None:
    now = datetime.now(UTC)
    token = pyjwt.encode(
        {
            "sub": "user-1",
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "type": "access",
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": now,
            "exp": now + timedelta(minutes=15),
            "jti": "jti-1",
        },
        SECRET,
        algorithm="HS384",
    )
    with pytest.raises(pyjwt.InvalidAlgorithmError):
        decode_access_token(token, secret=SECRET, issuer=ISSUER, audience=AUDIENCE)


def test_token_with_missing_required_claims_is_rejected() -> None:
    now = datetime.now(UTC)
    token = pyjwt.encode(
        {
            "sub": "user-1",
            "type": "access",
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": now,
            "exp": now + timedelta(minutes=15),
        },
        SECRET,
        algorithm=ACCESS_TOKEN_ALGORITHM,
    )
    with pytest.raises(pyjwt.MissingRequiredClaimError):
        decode_access_token(token, secret=SECRET, issuer=ISSUER, audience=AUDIENCE)


def test_token_with_future_iat_is_rejected() -> None:
    now = datetime.now(UTC)
    token = pyjwt.encode(
        {
            "sub": "user-1",
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "type": "access",
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": now + timedelta(hours=1),
            "exp": now + timedelta(hours=2),
            "jti": "jti-1",
        },
        SECRET,
        algorithm=ACCESS_TOKEN_ALGORITHM,
    )
    with pytest.raises(pyjwt.ImmatureSignatureError):
        decode_access_token(token, secret=SECRET, issuer=ISSUER, audience=AUDIENCE)


def test_token_with_wrong_issuer_is_rejected() -> None:
    token = _make_access_token(issuer="outro-emissor")
    with pytest.raises(pyjwt.InvalidIssuerError):
        decode_access_token(token, secret=SECRET, issuer=ISSUER, audience=AUDIENCE)


def test_token_with_wrong_audience_is_rejected() -> None:
    token = _make_access_token(audience="outro-aud")
    with pytest.raises(pyjwt.InvalidAudienceError):
        decode_access_token(token, secret=SECRET, issuer=ISSUER, audience=AUDIENCE)


def test_token_with_wrong_type_is_rejected() -> None:
    now = datetime.now(UTC)
    token = pyjwt.encode(
        {
            "sub": "user-1",
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "type": "refresh",
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "jti": "jti-1",
        },
        SECRET,
        algorithm=ACCESS_TOKEN_ALGORITHM,
    )
    with pytest.raises(ValueError, match="Tipo de token inválido"):
        decode_access_token(token, secret=SECRET, issuer=ISSUER, audience=AUDIENCE)


def test_refresh_token_is_opaque_and_hashed() -> None:
    raw, hashed = generate_refresh_token()
    assert raw != hashed
    assert len(raw) >= 48
    assert hash_refresh_token(raw) == hashed
    assert sha256_hash(raw) == hashed


def test_refresh_tokens_are_unique() -> None:
    raw_1, hashed_1 = generate_refresh_token()
    raw_2, hashed_2 = generate_refresh_token()
    assert raw_1 != raw_2
    assert hashed_1 != hashed_2
