"""Rate limiting (slowapi, armazenamento em memória)."""

from fastapi.testclient import TestClient


def test_login_is_rate_limited(client: TestClient) -> None:
    statuses = []
    for _ in range(6):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "alvo@exemplo.com", "password": "qualquer-senha"},
        )
        statuses.append(response.status_code)
    assert statuses[:5] == [401] * 5
    assert statuses[5] == 429
    assert (
        "Muitas tentativas"
        in client.post(
            "/api/v1/auth/login",
            json={"email": "alvo@exemplo.com", "password": "qualquer-senha"},
        ).json()["detail"]
    )
