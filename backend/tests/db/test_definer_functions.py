"""Funções SECURITY DEFINER executadas pela role real app_runtime.

Comprovam que o único caminho de dados disponível ao runtime antes de
existir contexto são as funções estreitas (login, refresh, tokens de uso
único, signup) — nunca leitura direta das tabelas.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError


def test_lookup_user_by_email_returns_own_row(
    runtime_engine: Engine, seeded_users: dict[str, dict[str, str]]
) -> None:
    user_a = seeded_users["a"]
    with runtime_engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT id, tenant_id, password_hash, email_verified_at, is_active "
                "FROM auth_lookup_user_by_email(:email)"
            ),
            {"email": user_a["email"]},
        ).one()
    assert str(row[0]) == user_a["user_id"]
    assert row[2] == "hash-ana"
    assert row[3] is None
    assert row[4] is True


def test_lookup_unknown_email_returns_empty(runtime_engine: Engine) -> None:
    with runtime_engine.connect() as connection:
        result = connection.execute(
            text("SELECT id FROM auth_lookup_user_by_email(:email)"),
            {"email": "ninguem@exemplo.com"},
        ).all()
    assert result == []


def test_lookup_functions_are_narrow_and_not_direct_reads(
    runtime_engine: Engine, seeded_users: dict[str, dict[str, str]]
) -> None:
    """Sem contexto, a leitura direta é negada; os lookups definer funcionam."""
    with runtime_engine.connect() as connection:
        direct = connection.execute(text("SELECT count(*) FROM users")).scalar_one()
        refresh_rows = connection.execute(
            text("SELECT id FROM auth_lookup_refresh_token(:hash)"),
            {"hash": "hash-inexistente"},
        ).all()
        single_use_rows = connection.execute(
            text("SELECT id FROM auth_lookup_single_use_token(:hash)"),
            {"hash": "hash-inexistente"},
        ).all()
    assert direct == 0
    assert refresh_rows == []
    assert single_use_rows == []


def test_refresh_token_lookup_requires_real_row(
    runtime_engine: Engine, seeded_users: dict[str, dict[str, str]]
) -> None:
    user_a = seeded_users["a"]
    token_hash = "hash-refresh-teste-123"
    with runtime_engine.connect() as connection:
        with connection.begin():
            connection.execute(
                text("SELECT set_config('app.current_user_id', :value, true)"),
                {"value": user_a["user_id"]},
            )
            connection.execute(
                text(
                    "INSERT INTO refresh_tokens (user_id, token_hash, family_id, expires_at) "
                    "VALUES (:user, :hash, :family, :expires)"
                ),
                {
                    "user": user_a["user_id"],
                    "hash": token_hash,
                    "family": str(uuid4()),
                    "expires": datetime.now(UTC) + timedelta(days=30),
                },
            )
        row = connection.execute(
            text("SELECT user_id, revoked_at FROM auth_lookup_refresh_token(:hash)"),
            {"hash": token_hash},
        ).one()
    assert str(row[0]) == user_a["user_id"]
    assert row[1] is None


def test_signup_via_definer_and_duplicate_rejection(
    runtime_engine: Engine, admin_engine: Engine
) -> None:
    email = f"carla-{uuid4().hex[:8]}@exemplo.com"
    try:
        with runtime_engine.connect() as connection:
            with connection.begin():
                new_id = connection.execute(
                    text(
                        "SELECT auth_signup_user(:email, 'hash-carla', "
                        "'Carla', NULL, 'America/Sao_Paulo', 'termos-v1', 'privacidade-v1',"
                        " 'verif-hash-carla', now() + interval '1 day')"
                    ),
                    {"email": email},
                ).scalar_one()
            with pytest.raises(IntegrityError):
                with connection.begin():
                    connection.execute(
                        text(
                            "SELECT auth_signup_user(:email, 'hash-carla', "
                            "'Carla', NULL, 'America/Sao_Paulo', 'termos-v1', 'privacidade-v1',"
                            " 'verif-hash-carla', now() + interval '1 day')"
                        ),
                        {"email": email},
                    )
            # A nova conta enxerga apenas os próprios dados.
            with connection.begin():
                connection.execute(
                    text("SELECT set_config('app.current_user_id', :value, true)"),
                    {"value": str(new_id)},
                )
                rows = connection.execute(text("SELECT id FROM users")).all()
                consents = connection.execute(
                    text("SELECT document_type FROM consent_records ORDER BY document_type")
                ).all()
        assert len(rows) == 1
        # Ordem do enum consent_type (definição): terms, privacy.
        assert [row[0] for row in consents] == ["terms", "privacy"]
    finally:
        with admin_engine.begin() as connection:
            connection.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})
