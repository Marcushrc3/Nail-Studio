"""Wiring transacional do contexto (app.core.db) contra PostgreSQL real.

Prova que ``SET LOCAL`` é aplicado no início da transação a partir dos
ContextVars e que a MESMA conexão física reutilizada pelo pool volta
fail-closed na transação seguinte (sem vazamento de contexto).
"""

import os

from sqlalchemy import text

from app.core.db import create_engine_from_url
from app.core.tenant import (
    TenantContext,
    reset_tenant_context,
    reset_user_context,
    set_tenant_context,
    set_user_context,
)


def test_set_local_applied_per_transaction_and_cleared_on_pool_reuse(
    seeded_users: dict[str, dict[str, str]],
) -> None:
    user_a = seeded_users["a"]
    engine = create_engine_from_url(os.environ["RUNTIME_DATABASE_URL"], pool_size=1, max_overflow=0)

    token_tenant = set_tenant_context(TenantContext(tenant_id=user_a["tenant_id"], source="test"))
    token_user = set_user_context(user_a["user_id"])
    try:
        with engine.connect() as connection:
            with connection.begin():
                pid_a = connection.execute(text("SELECT pg_backend_pid()")).scalar_one()
                guc = connection.execute(
                    text("SELECT current_setting('app.current_user_id', true)")
                ).scalar_one()
                rows = connection.execute(text("SELECT id FROM users")).all()
                assert guc == user_a["user_id"]
                assert [str(row[0]) for row in rows] == [user_a["user_id"]]
    finally:
        reset_user_context(token_user)
        reset_tenant_context(token_tenant)

    # Mesma conexão física (pool_size=1), nova transação, sem contexto.
    with engine.connect() as connection:
        with connection.begin():
            pid_b = connection.execute(text("SELECT pg_backend_pid()")).scalar_one()
            leftover = connection.execute(
                text("SELECT current_setting('app.current_user_id', true)")
            ).scalar_one()
            rows = connection.execute(text("SELECT count(*) FROM users")).scalar_one()
    assert pid_b == pid_a
    # GUCs customizados do PostgreSQL revertem para '' (não NULL) após o
    # SET LOCAL expirar; as políticas usam NULLIF, então continuam
    # fail-closed — o que importa é o count abaixo.
    assert leftover in (None, "")
    assert rows == 0
    engine.dispose()
