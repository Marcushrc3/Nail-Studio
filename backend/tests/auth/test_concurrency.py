"""Testes de concorrência do núcleo de autenticação (determinísticos).

Cada par de requisições é sincronizado com uma Barrier antes do disparo;
as asserções valem para TODAS as intercalações possíveis, sem sleeps.
"""

import threading

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import create_engine_from_url
from app.core.email import get_email_provider
from app.core.security import create_access_token, decode_access_token

COOKIE_NAME = "refresh_token"
COOKIE_PATH = "/api/v1/auth"
REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"
LOGOUT_ALL_URL = "/api/v1/auth/logout-all"
PASSWORD = "UmaSenhaMuitoForte@2026"


def _run_pair(actions: list) -> list:
    """Executa duas funções em threads sincronizadas; retorna os resultados."""
    barrier = threading.Barrier(2)
    results: list = []

    def worker(action) -> None:
        barrier.wait()
        results.append(action())

    threads = [threading.Thread(target=worker, args=(action,)) for action in actions]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def _cookie_from_response(response) -> str | None:
    header = response.headers.get("set-cookie")
    if not header:
        return None
    return header.split(";")[0].split("=", 1)[1]


def _signup_verify_login(app, email: str) -> tuple[TestClient, str, str, str]:
    """Cria usuário pronto; retorna (client, access_token, cookie, user_claims)."""
    client = TestClient(app)
    client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": PASSWORD,
            "display_name": "Concorrente",
            "terms_version": "termos-v1",
            "privacy_version": "privacidade-v1",
        },
    )
    token = _extract_verification_token(app)
    client.post("/api/v1/auth/verification/confirm", json={"token": token})
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    access = response.json()["access_token"]
    cookie = client.cookies.get(COOKIE_NAME)
    settings = get_settings()
    claims = decode_access_token(
        access,
        secret=settings.jwt_secret_key,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )
    return client, access, cookie, claims


def _extract_verification_token(app) -> str:
    provider = app.dependency_overrides[get_email_provider]()
    body = provider.sent[-1]["text_body"]
    return body.split("token=")[1].split("\n")[0].strip()


def _count_active_rows(admin_engine, email: str) -> int:
    with admin_engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT count(*) FROM refresh_tokens "
                "WHERE user_id = (SELECT id FROM users WHERE email = :e) "
                "AND revoked_at IS NULL"
            ),
            {"e": email},
        ).scalar_one()


def test_concurrent_refresh_same_token_has_single_winner(
    client: TestClient, email_provider, admin_engine
) -> None:
    """Dois refreshes com o MESMO token: exatamente um 200; família termina revogada."""
    _, _, cookie, _ = _signup_verify_login(client.app, "concorrente-1@exemplo.com")

    def refresh_action():
        response = TestClient(client.app).post(
            REFRESH_URL, headers={"Cookie": f"{COOKIE_NAME}={cookie}"}
        )
        return response.status_code, _cookie_from_response(response)

    statuses = sorted(status for status, _ in _run_pair([refresh_action, refresh_action]))
    assert statuses == [200, 401]

    # Nenhuma sessão ativa sobrevive: a família foi revogada.
    assert _count_active_rows(admin_engine, "concorrente-1@exemplo.com") == 0


def test_concurrent_refresh_and_logout_no_session_survives(
    client: TestClient, email_provider, admin_engine
) -> None:
    """Refresh concorrente com logout: nenhuma sessão permanece válida."""
    _, _, cookie, _ = _signup_verify_login(client.app, "concorrente-2@exemplo.com")

    def refresh_action():
        response = TestClient(client.app).post(
            REFRESH_URL, headers={"Cookie": f"{COOKIE_NAME}={cookie}"}
        )
        return response.status_code, _cookie_from_response(response)

    def logout_action():
        return (
            TestClient(client.app)
            .post(LOGOUT_URL, headers={"Cookie": f"{COOKIE_NAME}={cookie}"})
            .status_code
        )

    results = _run_pair([refresh_action, logout_action])
    refresh_status, new_cookie = next(
        (item for item in results if isinstance(item, tuple)), (None, None)
    )
    assert refresh_status in (200, 401)

    # Nem o cookie original nem o sucessor (se emitido) sobrevivem.
    for candidate in {cookie, new_cookie}:
        if candidate:
            response = TestClient(client.app).post(
                REFRESH_URL, headers={"Cookie": f"{COOKIE_NAME}={candidate}"}
            )
            assert response.status_code == 401
    assert _count_active_rows(admin_engine, "concorrente-2@exemplo.com") == 0


def test_concurrent_refresh_and_logout_all_no_session_survives(
    client: TestClient, email_provider, admin_engine
) -> None:
    """Refresh concorrente com logout-all: nenhuma sessão permanece válida."""
    _, access, cookie, _ = _signup_verify_login(client.app, "concorrente-3@exemplo.com")

    def refresh_action():
        response = TestClient(client.app).post(
            REFRESH_URL, headers={"Cookie": f"{COOKIE_NAME}={cookie}"}
        )
        return response.status_code, _cookie_from_response(response)

    def logout_all_action():
        return (
            TestClient(client.app)
            .post(LOGOUT_ALL_URL, headers={"Authorization": f"Bearer {access}"})
            .status_code
        )

    results = _run_pair([refresh_action, logout_all_action])
    refresh_status, new_cookie = next(
        (item for item in results if isinstance(item, tuple)), (None, None)
    )
    assert refresh_status in (200, 401)

    for candidate in {cookie, new_cookie}:
        if candidate:
            response = TestClient(client.app).post(
                REFRESH_URL, headers={"Cookie": f"{COOKIE_NAME}={candidate}"}
            )
            assert response.status_code == 401
    assert _count_active_rows(admin_engine, "concorrente-3@exemplo.com") == 0


def test_concurrent_refresh_two_users_no_cross_contamination(
    client: TestClient, email_provider, admin_engine, monkeypatch
) -> None:
    """Dois usuários/tenants simultâneos, pool de UMA conexão: sem contaminação."""
    app = client.app
    _, _, cookie_a, claims_a = _signup_verify_login(app, "conc-a@exemplo.com")
    _, _, cookie_b, claims_b = _signup_verify_login(app, "conc-b@exemplo.com")
    assert claims_a["tenant_id"] != claims_b["tenant_id"]

    pool1 = create_engine_from_url(
        "postgresql+psycopg://app_runtime:app_runtime_pw@localhost:5432/nail_studio",
        pool_size=1,
        max_overflow=0,
    )
    import app.core.db as db_module

    monkeypatch.setattr(db_module, "get_engine", lambda: pool1)

    def refresh_with(cookie: str):
        response = TestClient(app).post(REFRESH_URL, headers={"Cookie": f"{COOKIE_NAME}={cookie}"})
        return response.status_code, response.json().get("access_token")

    results = _run_pair([lambda: refresh_with(cookie_a), lambda: refresh_with(cookie_b)])
    assert sorted(status for status, _ in results) == [200, 200]

    settings = get_settings()
    subjects = {
        decode_access_token(
            token,
            secret=settings.jwt_secret_key,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )["sub"]
        for _, token in results
    }
    assert subjects == {claims_a["sub"], claims_b["sub"]}


def test_invalid_or_expired_jwt_never_sets_context(client: TestClient, email_provider) -> None:
    """JWT inválido/expirado/ausente: rotas protegidas respondem 401."""
    _, _, cookie, _ = _signup_verify_login(client.app, "conc-ctx@exemplo.com")

    garbage = client.post(LOGOUT_ALL_URL, headers={"Authorization": "Bearer lixo"})
    assert garbage.status_code == 401

    settings = get_settings()
    expired = create_access_token(
        subject="00000000-0000-0000-0000-000000000001",
        tenant_id="00000000-0000-0000-0000-000000000000",
        secret=settings.jwt_secret_key,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        expires_minutes=-1,
    )
    assert (
        client.post(LOGOUT_ALL_URL, headers={"Authorization": f"Bearer {expired}"}).status_code
        == 401
    )
    assert client.post(LOGOUT_ALL_URL).status_code == 401

    # A sessão legítima segue intacta (contexto de request não vazou).
    response = client.post(REFRESH_URL, headers={"Cookie": f"{COOKIE_NAME}={cookie}"})
    assert response.status_code == 200
