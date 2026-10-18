"""Políticas RLS executadas com a role REAL de runtime (app_runtime).

Nenhum teste deste módulo usa superusuário: a conexão é sempre
``app_runtime``, exatamente a role usada pela aplicação. Isso comprova que
as políticas protegem de verdade, e não apenas por inspeção de DDL.
"""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError


def _set_context(connection, *, user_id: str, tenant_id: str) -> None:
    connection.execute(
        text("SELECT set_config('app.current_user_id', :value, true)"),
        {"value": user_id},
    )
    connection.execute(
        text("SELECT set_config('app.current_tenant_id', :value, true)"),
        {"value": tenant_id},
    )


def test_runtime_role_is_least_privilege(runtime_engine: Engine) -> None:
    with runtime_engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb "
                "FROM pg_roles WHERE rolname = current_user"
            )
        ).one()
    assert row == (False, False, False, False)


def test_no_context_is_fail_closed(runtime_engine: Engine) -> None:
    with runtime_engine.connect() as connection:
        counts = connection.execute(
            text(
                "SELECT "
                "(SELECT count(*) FROM tenants), "
                "(SELECT count(*) FROM users), "
                "(SELECT count(*) FROM profiles), "
                "(SELECT count(*) FROM refresh_tokens), "
                "(SELECT count(*) FROM single_use_tokens), "
                "(SELECT count(*) FROM consent_records)"
            )
        ).one()
    assert counts == (0, 0, 0, 0, 0, 0)


def test_tenant_sees_only_own_rows(
    runtime_engine: Engine, seeded_users: dict[str, dict[str, str]]
) -> None:
    user_a = seeded_users["a"]
    with runtime_engine.connect() as connection:
        with connection.begin():
            _set_context(connection, user_id=user_a["user_id"], tenant_id=user_a["tenant_id"])
            rows = connection.execute(text("SELECT id, tenant_id, email FROM users")).all()
            tenants = connection.execute(text("SELECT id FROM tenants")).all()
    assert len(rows) == 1
    assert str(rows[0][0]) == user_a["user_id"]
    assert str(rows[0][1]) == user_a["tenant_id"]
    assert len(tenants) == 1
    assert str(tenants[0][0]) == user_a["tenant_id"]


def test_context_does_not_leak_between_transactions(
    runtime_engine: Engine, seeded_users: dict[str, dict[str, str]]
) -> None:
    """SET LOCAL morre no commit: uma nova transação volta a ser fail-closed."""
    user_a = seeded_users["a"]
    with runtime_engine.connect() as connection:
        with connection.begin():
            _set_context(connection, user_id=user_a["user_id"], tenant_id=user_a["tenant_id"])
        with connection.begin():
            counts = connection.execute(
                text("SELECT (SELECT count(*) FROM users), (SELECT count(*) FROM tenants)")
            ).one()
    assert counts == (0, 0)


def test_cross_tenant_update_is_denied(
    runtime_engine: Engine, seeded_users: dict[str, dict[str, str]]
) -> None:
    user_a, user_b = seeded_users["a"], seeded_users["b"]
    with runtime_engine.connect() as connection:
        with connection.begin():
            _set_context(connection, user_id=user_a["user_id"], tenant_id=user_a["tenant_id"])
            result = connection.execute(
                text("UPDATE users SET updated_at = now() WHERE id = :other"),
                {"other": user_b["user_id"]},
            )
            assert result.rowcount == 0
            result_profiles = connection.execute(
                text("DELETE FROM profiles WHERE user_id = :other"),
                {"other": user_b["user_id"]},
            )
            assert result_profiles.rowcount == 0


def test_cross_tenant_insert_into_users_is_rejected(
    runtime_engine: Engine, seeded_users: dict[str, dict[str, str]]
) -> None:
    """Sem policy de INSERT em users, qualquer INSERT do runtime é negado."""
    user_a = seeded_users["a"]
    with runtime_engine.connect() as connection:
        with connection.begin():
            _set_context(connection, user_id=user_a["user_id"], tenant_id=user_a["tenant_id"])
            with pytest.raises(ProgrammingError):
                connection.execute(
                    text(
                        "INSERT INTO users (tenant_id, email, password_hash) "
                        "VALUES (:tenant, 'invasor@exemplo.com', 'x')"
                    ),
                    {"tenant": user_a["tenant_id"]},
                )


def test_policies_use_the_right_guc_per_table(
    runtime_engine: Engine, seeded_users: dict[str, dict[str, str]]
) -> None:
    """Cada política usa o seu GUC: users segue o usuário; tenants segue o tenant.

    A combinação "usuário A + tenant B" não acontece na aplicação (o tenant é
    sempre derivado do usuário autenticado), mas prova que as políticas não
    misturam os contextos.
    """
    user_a, user_b = seeded_users["a"], seeded_users["b"]
    with runtime_engine.connect() as connection:
        with connection.begin():
            tenant_b = connection.execute(
                text("SELECT tenant_id FROM auth_lookup_user_by_email(:email)"),
                {"email": user_b["email"]},
            ).scalar_one()
            _set_context(connection, user_id=user_a["user_id"], tenant_id=str(tenant_b))
            users = connection.execute(text("SELECT id FROM users")).all()
            tenants = connection.execute(text("SELECT id FROM tenants")).all()
    assert [str(row[0]) for row in users] == [user_a["user_id"]]
    assert [str(row[0]) for row in tenants] == [str(tenant_b)]
