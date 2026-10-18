"""Privilégios de banco: negações provadas com as roles REAIS.

Cobre os três itens da auditoria E1.1: app_runtime não assume app_functions;
role sem privilégios não executa funções privilegiadas; restrições colunares
impedem o runtime de alterar colunas sensíveis.
"""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError

SET_ROLE_SQL = "SET ROLE app_functions"


def test_runtime_cannot_set_role_app_functions(runtime_engine: Engine) -> None:
    with runtime_engine.connect() as connection:
        with pytest.raises(ProgrammingError, match="app_functions"):
            connection.exec_driver_sql(SET_ROLE_SQL)


def test_unprivileged_role_cannot_execute_definer_functions(
    unprivileged_engine: Engine,
) -> None:
    with unprivileged_engine.connect() as connection:
        with pytest.raises(ProgrammingError):
            connection.execute(text("SELECT id FROM auth_lookup_user_by_email('x@y.com')"))


def test_unprivileged_role_cannot_execute_context_helpers(
    unprivileged_engine: Engine,
) -> None:
    with unprivileged_engine.connect() as connection:
        with pytest.raises(ProgrammingError):
            connection.execute(text("SELECT app_current_user_id()"))


def test_unprivileged_role_cannot_read_business_tables(
    unprivileged_engine: Engine,
) -> None:
    with unprivileged_engine.connect() as connection:
        with pytest.raises(ProgrammingError):
            connection.execute(text("SELECT count(*) FROM users"))


def test_runtime_can_still_execute_definer_functions(runtime_engine: Engine) -> None:
    with runtime_engine.connect() as connection:
        rows = connection.execute(
            text("SELECT id FROM auth_lookup_user_by_email('ninguem@exemplo.com')")
        ).all()
    assert rows == []


def _context(connection, user_id: str) -> None:
    connection.execute(
        text("SELECT set_config('app.current_user_id', :value, true)"),
        {"value": user_id},
    )


def test_runtime_cannot_update_sensitive_user_columns(
    runtime_engine: Engine, seeded_users: dict[str, dict[str, str]]
) -> None:
    user_a = seeded_users["a"]
    with runtime_engine.connect() as connection:
        with connection.begin():
            _context(connection, user_a["user_id"])
            with pytest.raises(ProgrammingError):
                connection.execute(
                    text("UPDATE users SET email_verified_at = now() WHERE id = :id"),
                    {"id": user_a["user_id"]},
                )
        with connection.begin():
            _context(connection, user_a["user_id"])
            with pytest.raises(ProgrammingError):
                connection.execute(
                    text("UPDATE users SET tenant_id = :t WHERE id = :id"),
                    {"t": "00000000-0000-0000-0000-000000000000", "id": user_a["user_id"]},
                )
        with connection.begin():
            _context(connection, user_a["user_id"])
            result = connection.execute(
                text("UPDATE users SET updated_at = now() WHERE id = :id"),
                {"id": user_a["user_id"]},
            )
            assert result.rowcount == 1


def test_runtime_cannot_extend_refresh_expiry(
    runtime_engine: Engine, seeded_users: dict[str, dict[str, str]]
) -> None:
    user_a = seeded_users["a"]
    with runtime_engine.connect() as connection:
        with connection.begin():
            _context(connection, user_a["user_id"])
            row_id = connection.execute(
                text(
                    "INSERT INTO refresh_tokens (user_id, token_hash, family_id, expires_at) "
                    "VALUES (:user, 'hash-priv-teste', '00000000-0000-0000-0000-000000000001',"
                    " now() + interval '1 day') RETURNING id"
                ),
                {"user": user_a["user_id"]},
            ).scalar_one()
        with connection.begin():
            _context(connection, user_a["user_id"])
            with pytest.raises(ProgrammingError):
                connection.execute(
                    text(
                        "UPDATE refresh_tokens SET expires_at = now() + interval '1 year' "
                        "WHERE id = :id"
                    ),
                    {"id": row_id},
                )
        with connection.begin():
            _context(connection, user_a["user_id"])
            result = connection.execute(
                text("UPDATE refresh_tokens SET revoked_at = now() WHERE id = :id"),
                {"id": row_id},
            )
            assert result.rowcount == 1


def test_runtime_cannot_change_token_purpose(
    runtime_engine: Engine, seeded_users: dict[str, dict[str, str]]
) -> None:
    with runtime_engine.connect() as connection:
        with connection.begin():
            _context(connection, seeded_users["a"]["user_id"])
            with pytest.raises(ProgrammingError):
                connection.execute(
                    text(
                        "UPDATE single_use_tokens SET purpose = 'password_reset' "
                        "WHERE token_hash = 'verif-hash-a'"
                    )
                )
        with connection.begin():
            _context(connection, seeded_users["a"]["user_id"])
            result = connection.execute(
                text(
                    "UPDATE single_use_tokens SET used_at = now() WHERE token_hash = 'verif-hash-a'"
                )
            )
            assert result.rowcount == 1
