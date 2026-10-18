"""Tentativas de acesso entre tenants devem ser negadas."""

from fastapi.testclient import TestClient

from tests.isolation.app import SYNTHETIC_TENANT_HEADER

HEADER_A = {SYNTHETIC_TENANT_HEADER: "tenant-a"}
HEADER_B = {SYNTHETIC_TENANT_HEADER: "tenant-b"}


def test_tenant_b_cannot_list_see_or_update_tenant_a(harness_client: TestClient) -> None:
    created = harness_client.post("/probes?payload=segredo-da-a", headers=HEADER_A)
    assert created.status_code == 200
    probe_id = created.json()["id"]

    # Listagem: B não vê nada de A.
    listed = harness_client.get("/probes", headers=HEADER_B)
    assert listed.status_code == 200
    assert listed.json() == []

    # Leitura direta por id: 404, sem revelar a existência do recurso.
    fetched = harness_client.get(f"/probes/{probe_id}", headers=HEADER_B)
    assert fetched.status_code == 404

    # Atualização: 404 e o dado de A permanece intacto.
    updated = harness_client.patch(f"/probes/{probe_id}?payload=hack", headers=HEADER_B)
    assert updated.status_code == 404

    own = harness_client.get(f"/probes/{probe_id}", headers=HEADER_A)
    assert own.status_code == 200
    assert own.json()["payload"] == "segredo-da-a"


def test_tenant_a_does_not_see_tenant_b_data(harness_client: TestClient) -> None:
    # Tenant ids próprios deste teste, para não depender do estado criado
    # por outros testes (a tabela do harness é compartilhada por sessão).
    header_1 = {SYNTHETIC_TENANT_HEADER: "isolated-tenant-1"}
    header_2 = {SYNTHETIC_TENANT_HEADER: "isolated-tenant-2"}
    harness_client.post("/probes?payload=item-b", headers=header_2)
    listed = harness_client.get("/probes", headers=header_1)
    assert listed.status_code == 200
    assert listed.json() == []
