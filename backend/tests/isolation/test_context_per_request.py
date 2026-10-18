"""Contexto de tenant por request (principal sintético)."""

from fastapi.testclient import TestClient

from tests.isolation.app import SYNTHETIC_TENANT_HEADER


def test_whoami_reflects_tenant_of_each_request(harness_client: TestClient) -> None:
    response_a = harness_client.get("/whoami", headers={SYNTHETIC_TENANT_HEADER: "tenant-a"})
    assert response_a.status_code == 200
    assert response_a.json() == {
        "tenant_id": "tenant-a",
        "source": "synthetic-header",
    }

    response_b = harness_client.get("/whoami", headers={SYNTHETIC_TENANT_HEADER: "tenant-b"})
    assert response_b.status_code == 200
    assert response_b.json()["tenant_id"] == "tenant-b"


def test_request_without_tenant_is_denied_fail_closed(harness_client: TestClient) -> None:
    response = harness_client.get("/whoami")
    assert response.status_code == 401
