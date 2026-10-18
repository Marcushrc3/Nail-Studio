"""Aplicação de teste do harness de isolamento (E0).

Usa principals SINTÉTICOS (header ``X-Synthetic-Tenant-Id``) para exercitar
o mecanismo de contexto de tenant e o padrão de scoping no acesso a dados.
NÃO é autenticação real (entra na E1) e nada aqui pertence ao domínio do
produto.

O endpoint ``/db-connection-id`` existe apenas para evidenciar, nos testes,
que a MESMA conexão física do pool atende tenants diferentes sem estado
residual — reforçando que não usamos ``SET`` no nível da conexão.
"""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from sqlalchemy import Engine, text

from app.core.tenant import (
    TenantContext,
    require_tenant,
    reset_tenant_context,
    set_tenant_context,
)

SYNTHETIC_TENANT_HEADER = "X-Synthetic-Tenant-Id"

TenantDep = Annotated[TenantContext, Depends(require_tenant)]


def build_app(engine: Engine) -> FastAPI:
    application = FastAPI(title="isolation-harness")

    @application.middleware("http")
    async def synthetic_principal(request: Request, call_next) -> Response:  # type: ignore[no-untyped-call]
        tenant_id = request.headers.get(SYNTHETIC_TENANT_HEADER)
        if tenant_id is None:
            return await call_next(request)
        token = set_tenant_context(TenantContext(tenant_id=tenant_id, source="synthetic-header"))
        try:
            return await call_next(request)
        finally:
            reset_tenant_context(token)

    @application.get("/whoami")
    def whoami(tenant: TenantDep) -> dict[str, str]:
        return {"tenant_id": tenant.tenant_id, "source": tenant.source}

    @application.post("/probes")
    def create_probe(payload: str, tenant: TenantDep) -> dict[str, str]:
        probe_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO isolation_probe (id, tenant_id, payload) "
                    "VALUES (:id, :tenant_id, :payload)"
                ),
                {"id": probe_id, "tenant_id": tenant.tenant_id, "payload": payload},
            )
        return {"id": str(probe_id)}

    @application.get("/probes")
    def list_probes(tenant: TenantDep) -> list[dict[str, str]]:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT id, payload FROM isolation_probe "
                    "WHERE tenant_id = :tenant_id ORDER BY payload"
                ),
                {"tenant_id": tenant.tenant_id},
            ).mappings()
            return [{"id": str(row["id"]), "payload": row["payload"]} for row in rows]

    @application.get("/probes/{probe_id}")
    def get_probe(probe_id: UUID, tenant: TenantDep) -> dict[str, str]:
        with engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT id, payload FROM isolation_probe "
                        "WHERE id = :id AND tenant_id = :tenant_id"
                    ),
                    {"id": probe_id, "tenant_id": tenant.tenant_id},
                )
                .mappings()
                .first()
            )
        if row is None:
            raise HTTPException(status_code=404, detail="Recurso não encontrado.")
        return {"id": str(row["id"]), "payload": row["payload"]}

    @application.patch("/probes/{probe_id}")
    def update_probe(probe_id: UUID, payload: str, tenant: TenantDep) -> dict[str, str]:
        with engine.begin() as connection:
            result = connection.execute(
                text(
                    "UPDATE isolation_probe SET payload = :payload "
                    "WHERE id = :id AND tenant_id = :tenant_id"
                ),
                {"payload": payload, "id": probe_id, "tenant_id": tenant.tenant_id},
            )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Recurso não encontrado.")
        return {"id": str(probe_id)}

    @application.get("/db-connection-id")
    def db_connection_id(tenant: TenantDep) -> dict[str, str | None]:
        with engine.connect() as connection:
            pid = connection.execute(text("SELECT pg_backend_pid() AS pid")).scalar_one()
            setting = connection.execute(
                text("SELECT current_setting('app.current_tenant', true) AS value")
            ).scalar_one()
        return {
            "pid": str(pid),
            "app_current_tenant": None if setting is None else str(setting),
        }

    return application
