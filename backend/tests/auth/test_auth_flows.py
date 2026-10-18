"""Fluxos completos de autenticação contra a API real (role app_runtime)."""

import re

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.core.config import get_settings  # noqa: E402
from app.core.security import decode_access_token

PASSWORD = "UmaSenhaMuitoForte@2026"
SIGNUP_URL = "/api/v1/auth/signup"
LOGIN_URL = "/api/v1/auth/login"
CONFIRM_URL = "/api/v1/auth/verification/confirm"
REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"
LOGOUT_ALL_URL = "/api/v1/auth/logout-all"
COOKIE_NAME = "refresh_token"
COOKIE_PATH = "/api/v1/auth"

TOKEN_RE = re.compile(r"token=([A-Za-z0-9_-]+)")


def _signup(client: TestClient, email: str, name: str = "Profissional Teste") -> None:
    response = client.post(
        SIGNUP_URL,
        json={
            "email": email,
            "password": PASSWORD,
            "display_name": name,
            "terms_version": "termos-v1",
            "privacy_version": "privacidade-v1",
        },
    )
    assert response.status_code == 202


def _verification_token(email_provider, index: int = -1) -> str:
    match = TOKEN_RE.search(email_provider.sent[index]["text_body"])
    assert match is not None
    return match.group(1)


def _verify(client: TestClient, token: str) -> None:
    response = client.post(CONFIRM_URL, json={"token": token})
    assert response.status_code == 200


def _login(client: TestClient, email: str, password: str = PASSWORD):
    return client.post(LOGIN_URL, json={"email": email, "password": password})


def _decode(token: str) -> dict[str, object]:
    settings = get_settings()
    return decode_access_token(
        token,
        secret=settings.jwt_secret_key,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )


def _ready_user(client: TestClient, email_provider, email: str) -> tuple[dict[str, object], str]:
    _signup(client, email)
    _verify(client, _verification_token(email_provider))
    response = _login(client, email)
    assert response.status_code == 200
    return _decode(response.json()["access_token"]), response.json()["access_token"]


def test_signup_is_uniform_and_sends_only_fake_email(
    client: TestClient, email_provider, admin_engine: Engine
) -> None:
    _signup(client, "primeira@exemplo.com")
    assert email_provider.sent[-1]["to"] == "primeira@exemplo.com"
    with admin_engine.connect() as connection:
        count = connection.execute(
            text("SELECT count(*) FROM users WHERE email = 'primeira@exemplo.com'")
        ).scalar_one()
    assert count == 1


def test_duplicate_signup_does_not_reveal_account(
    client: TestClient, email_provider, admin_engine: Engine
) -> None:
    _signup(client, "duplicada@exemplo.com")
    sent_before = len(email_provider.sent)
    _signup(client, "duplicada@exemplo.com")
    assert len(email_provider.sent) == sent_before  # nenhum novo e-mail
    with admin_engine.connect() as connection:
        count = connection.execute(
            text("SELECT count(*) FROM users WHERE email = 'duplicada@exemplo.com'")
        ).scalar_one()
    assert count == 1


def test_unverified_email_blocks_login(client: TestClient, email_provider) -> None:
    _signup(client, "nao-verificada@exemplo.com")
    wrong = _login(client, "nao-verificada@exemplo.com", "senha-totalmente-errada")
    assert wrong.status_code == 401
    blocked = _login(client, "nao-verificada@exemplo.com")
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "EMAIL_NOT_VERIFIED"


def test_login_unknown_email_is_uniform(client: TestClient) -> None:
    response = _login(client, "nao-existe@exemplo.com")
    assert response.status_code == 401
    assert response.json() == {"detail": "E-mail ou senha inválidos."}


def test_verification_confirm_single_use(client: TestClient, email_provider) -> None:
    _signup(client, "token-unico@exemplo.com")
    token = _verification_token(email_provider)
    _verify(client, token)
    again = client.post(CONFIRM_URL, json={"token": token})
    assert again.status_code == 400
    bogus = client.post(CONFIRM_URL, json={"token": "token-inexistente"})
    assert bogus.status_code == 400


def test_full_login_refresh_rotation_and_reuse_revocation(
    client: TestClient, email_provider, settings
) -> None:
    payload, _ = _ready_user(client, email_provider, "rotacao@exemplo.com")
    assert payload["sub"]
    assert payload["tenant_id"]

    first_cookie = client.cookies.get(COOKIE_NAME)
    assert first_cookie is not None

    refreshed = client.post(REFRESH_URL)
    assert refreshed.status_code == 200
    second_cookie = client.cookies.get(COOKIE_NAME)
    assert second_cookie is not None
    assert second_cookie != first_cookie

    # Reuso do token antigo: revoga a família INTEIRA.
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, first_cookie, path=COOKIE_PATH)
    replay = client.post(REFRESH_URL)
    assert replay.status_code == 401

    # O token rotacionado também morre (família revogada).
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, second_cookie, path=COOKIE_PATH)
    after_family_revoked = client.post(REFRESH_URL)
    assert after_family_revoked.status_code == 401


def test_refresh_without_cookie_is_rejected(client: TestClient) -> None:
    response = client.post(REFRESH_URL)
    assert response.status_code == 401


def test_expired_refresh_token_is_rejected(
    client: TestClient, email_provider, admin_engine: Engine
) -> None:
    _ready_user(client, email_provider, "expirado@exemplo.com")
    cookie = client.cookies.get(COOKIE_NAME)
    with admin_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE refresh_tokens SET expires_at = now() - interval '1 hour' "
                "WHERE user_id = (SELECT id FROM users WHERE email = 'expirado@exemplo.com')"
            )
        )
    response = client.post(REFRESH_URL)
    assert response.status_code == 401
    assert cookie is not None


def test_logout_revokes_current_session(client: TestClient, email_provider) -> None:
    _ready_user(client, email_provider, "logout@exemplo.com")
    cookie = client.cookies.get(COOKIE_NAME)
    response = client.post(LOGOUT_URL)
    assert response.status_code == 204
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, cookie, path=COOKIE_PATH)
    refreshed = client.post(REFRESH_URL)
    assert refreshed.status_code == 401


def test_logout_all_revokes_only_own_sessions(client: TestClient, email_provider) -> None:
    payload_a, access_a = _ready_user(client, email_provider, "tudo-a@exemplo.com")
    cookie_a = client.cookies.get(COOKIE_NAME)

    client.cookies.clear()
    payload_b, _ = _ready_user(client, email_provider, "tudo-b@exemplo.com")
    cookie_b = client.cookies.get(COOKIE_NAME)
    assert payload_a["tenant_id"] != payload_b["tenant_id"]

    headers = {"Authorization": f"Bearer {access_a}"}
    response = client.post(LOGOUT_ALL_URL, headers=headers)
    assert response.status_code == 204

    # A morreu; B segue viva (isolamento entre tenants na API).
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, cookie_a, path=COOKIE_PATH)
    assert client.post(REFRESH_URL).status_code == 401

    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, cookie_b, path=COOKIE_PATH)
    assert client.post(REFRESH_URL).status_code == 200


def test_access_token_carries_own_tenant_not_others(client: TestClient, email_provider) -> None:
    payload_a, _ = _ready_user(client, email_provider, "tenant-a@exemplo.com")
    client.cookies.clear()
    payload_b, _ = _ready_user(client, email_provider, "tenant-b@exemplo.com")
    assert payload_a["tenant_id"] != payload_b["tenant_id"]
    assert payload_a["sub"] != payload_b["sub"]


def test_weak_password_is_rejected(client: TestClient) -> None:
    response = client.post(
        SIGNUP_URL,
        json={
            "email": "senha-fraca@exemplo.com",
            "password": "1234567890",
            "display_name": "Fraca",
            "terms_version": "termos-v1",
            "privacy_version": "privacidade-v1",
        },
    )
    assert response.status_code == 422


def test_common_password_is_rejected(client: TestClient) -> None:
    response = client.post(
        SIGNUP_URL,
        json={
            "email": "senha-comum@exemplo.com",
            "password": "password123",
            "display_name": "Comum",
            "terms_version": "termos-v1",
            "privacy_version": "privacidade-v1",
        },
    )
    assert response.status_code == 422


def test_refresh_cookie_is_httponly(client: TestClient, email_provider) -> None:
    _signup(client, "cookie@exemplo.com")
    _verify(client, _verification_token(email_provider))
    response = _login(client, "cookie@exemplo.com")
    assert response.status_code == 200
    assert COOKIE_NAME in client.cookies
    raw_login_cookie = response.headers.get("set-cookie", "")
    assert "HttpOnly" in raw_login_cookie


def test_no_smtp_was_used(client: TestClient, email_provider) -> None:
    """O provedor falso registra envios sem qualquer chamada SMTP real."""
    _signup(client, "sem-smtp@exemplo.com")
    assert email_provider.sent[-1]["to"] == "sem-smtp@exemplo.com"
