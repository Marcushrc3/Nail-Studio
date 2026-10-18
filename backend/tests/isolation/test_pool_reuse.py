"""Reutilização da MESMA conexão do pool por tenants diferentes.

Com ``pool_size=1``, requests sequenciais de tenants diferentes usam a
mesma conexão física (evidenciado por ``pg_backend_pid``). O teste prova
que: (a) cada tenant vê apenas seus dados; (b) nenhum estado de tenant
fica persistido na conexão (não usamos ``SET`` no nível da conexão).
"""

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from tests.isolation.app import SYNTHETIC_TENANT_HEADER, build_app

HEADER_A = {SYNTHETIC_TENANT_HEADER: "pool-tenant-a"}
HEADER_B = {SYNTHETIC_TENANT_HEADER: "pool-tenant-b"}


def test_same_pooled_connection_serves_different_tenants_without_leak(
    single_connection_engine: Engine,
) -> None:
    client = TestClient(build_app(single_connection_engine))

    # Tenant A cria um recurso e registra o pid da conexão usada.
    created = client.post("/probes?payload=item-a", headers=HEADER_A)
    assert created.status_code == 200
    pid_a = client.get("/db-connection-id", headers=HEADER_A).json()["pid"]

    # Tenant B usa a MESMA conexão física e não vê nada de A.
    pid_b = client.get("/db-connection-id", headers=HEADER_B).json()["pid"]
    assert pid_b == pid_a
    listed_b = client.get("/probes", headers=HEADER_B)
    assert listed_b.json() == []

    # Nenhum estado persistente de tenant na conexão reutilizada.
    connection_state = client.get("/db-connection-id", headers=HEADER_B).json()
    assert connection_state["app_current_tenant"] is None

    # Tenant A continua vendo apenas o que é seu.
    listed_a = client.get("/probes", headers=HEADER_A)
    assert [item["payload"] for item in listed_a.json()] == ["item-a"]
