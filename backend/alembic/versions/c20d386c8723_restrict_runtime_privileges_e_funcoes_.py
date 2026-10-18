"""restrict runtime privileges e funcoes de verificacao

Revision ID: c20d386c8723
Revises: d09eb36d6b7d
Create Date: 2026-10-17 22:26:19.404582

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "c20d386c8723"
down_revision = "d09eb36d6b7d"
branch_labels = None
depends_on = None

OLD_SIGNUP_SIGNATURE = "auth_signup_user(citext, text, text, text, text, text, text)"

SIGNUP_V2 = """
CREATE FUNCTION auth_signup_user(
    p_email citext,
    p_password_hash text,
    p_display_name text,
    p_phone text,
    p_timezone text,
    p_terms_version text,
    p_privacy_version text,
    p_verification_token_hash text,
    p_verification_expires_at timestamptz
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
DECLARE
    v_tenant_id uuid;
    v_user_id uuid;
BEGIN
    INSERT INTO tenants DEFAULT VALUES
    RETURNING id INTO v_tenant_id;

    INSERT INTO users (tenant_id, email, password_hash)
    VALUES (v_tenant_id, p_email, p_password_hash)
    RETURNING id INTO v_user_id;

    INSERT INTO profiles (user_id, display_name, phone, timezone)
    VALUES (v_user_id, p_display_name, p_phone, p_timezone);

    INSERT INTO consent_records (user_id, document_type, version)
    VALUES
        (v_user_id, 'terms', p_terms_version),
        (v_user_id, 'privacy', p_privacy_version);

    INSERT INTO single_use_tokens (user_id, purpose, token_hash, expires_at)
    VALUES (v_user_id, 'email_verification', p_verification_token_hash, p_verification_expires_at);

    RETURN v_user_id;
END;
$$;
"""

MARK_VERIFIED = """
CREATE FUNCTION auth_mark_email_verified(p_user_id uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
BEGIN
    UPDATE users
    SET email_verified_at = COALESCE(email_verified_at, now()),
        updated_at = now()
    WHERE id = p_user_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Usuário não encontrado.';
    END IF;
END;
$$;
"""

REFRESH_LOOKUP_V2 = """
CREATE FUNCTION auth_lookup_refresh_token(p_token_hash text)
RETURNS TABLE(
    id uuid,
    user_id uuid,
    tenant_id uuid,
    family_id uuid,
    expires_at timestamptz,
    revoked_at timestamptz,
    replaced_by uuid
)
LANGUAGE sql STABLE
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
    SELECT r.id, r.user_id, u.tenant_id, r.family_id, r.expires_at, r.revoked_at, r.replaced_by
    FROM refresh_tokens r
    JOIN users u ON u.id = r.user_id
    WHERE r.token_hash = p_token_hash
    LIMIT 1;
$$;
"""


def _replace_definer(old_name: str, new_ddl: str, new_signature: str) -> None:
    """Remove a versão antiga e cria a nova como app_functions (mínimos grants)."""
    op.execute("SET ROLE app_functions")
    op.execute(f"DROP FUNCTION IF EXISTS {old_name}")
    op.execute("RESET ROLE")
    op.execute(new_ddl)
    op.execute(f"REVOKE ALL ON FUNCTION {new_signature} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {new_signature} TO app_runtime")
    op.execute(f"ALTER FUNCTION {new_signature} OWNER TO app_functions")


def upgrade() -> None:
    # 1) PUBLIC perde EXECUTE nos helpers de contexto.
    op.execute("REVOKE ALL ON FUNCTION app_current_user_id() FROM PUBLIC")
    op.execute("REVOKE ALL ON FUNCTION app_current_tenant_id() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app_current_user_id() TO app_runtime")
    op.execute("GRANT EXECUTE ON FUNCTION app_current_tenant_id() TO app_runtime")

    # 2) Funções futuras não nascem públicas por padrão.
    op.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE app_migration IN SCHEMA public "
        "REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE app_functions IN SCHEMA public "
        "REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC"
    )

    # 3) users: runtime não insere/apaga e só atualiza updated_at.
    op.execute("REVOKE INSERT, UPDATE, DELETE ON TABLE users FROM app_runtime")
    op.execute("GRANT UPDATE (updated_at) ON TABLE users TO app_runtime")

    # 4) refresh_tokens: runtime só mexe em revoked_at/replaced_by.
    op.execute("REVOKE UPDATE ON TABLE refresh_tokens FROM app_runtime")
    op.execute("GRANT UPDATE (revoked_at, replaced_by) ON TABLE refresh_tokens TO app_runtime")

    # 5) single_use_tokens: runtime só marca used_at.
    op.execute("REVOKE UPDATE ON TABLE single_use_tokens FROM app_runtime")
    op.execute("GRANT UPDATE (used_at) ON TABLE single_use_tokens TO app_runtime")

    # 6) app_functions precisa dos privilégios mínimos das novas funções.
    op.execute("GRANT INSERT ON TABLE single_use_tokens TO app_functions")
    op.execute("GRANT UPDATE (email_verified_at, updated_at) ON TABLE users TO app_functions")

    # 7) Signup agora cria o token de verificação atomicamente.
    _replace_definer(
        OLD_SIGNUP_SIGNATURE,
        SIGNUP_V2,
        "auth_signup_user(citext, text, text, text, text, text, text, text, timestamptz)",
    )

    # 8) Marcação de e-mail verificado (sem UPDATE direto pelo runtime).
    _replace_definer(
        "auth_mark_email_verified(uuid)",
        MARK_VERIFIED,
        "auth_mark_email_verified(uuid)",
    )

    # 9) Lookup de refresh agora retorna o tenant do usuário (para o JWT).
    _replace_definer(
        "auth_lookup_refresh_token(text)",
        REFRESH_LOOKUP_V2,
        "auth_lookup_refresh_token(text)",
    )


def downgrade() -> None:
    op.execute("SET ROLE app_functions")
    op.execute("DROP FUNCTION IF EXISTS auth_mark_email_verified(uuid)")
    op.execute("DROP FUNCTION IF EXISTS auth_lookup_refresh_token(text)")
    op.execute(
        "DROP FUNCTION IF EXISTS auth_signup_user("
        "citext, text, text, text, text, text, text, text, timestamptz)"
    )
    op.execute("RESET ROLE")

    # Recria a versão original do signup e do lookup de refresh.
    op.execute(
        """
        CREATE FUNCTION auth_signup_user(
            p_email citext,
            p_password_hash text,
            p_display_name text,
            p_phone text,
            p_timezone text,
            p_terms_version text,
            p_privacy_version text
        )
        RETURNS uuid
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public, pg_catalog
        AS $$
        DECLARE
            v_tenant_id uuid;
            v_user_id uuid;
        BEGIN
            INSERT INTO tenants DEFAULT VALUES RETURNING id INTO v_tenant_id;
            INSERT INTO users (tenant_id, email, password_hash)
            VALUES (v_tenant_id, p_email, p_password_hash) RETURNING id INTO v_user_id;
            INSERT INTO profiles (user_id, display_name, phone, timezone)
            VALUES (v_user_id, p_display_name, p_phone, p_timezone);
            INSERT INTO consent_records (user_id, document_type, version)
            VALUES (v_user_id, 'terms', p_terms_version),
                   (v_user_id, 'privacy', p_privacy_version);
            RETURN v_user_id;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE FUNCTION auth_lookup_refresh_token(p_token_hash text)
        RETURNS TABLE(
            id uuid,
            user_id uuid,
            family_id uuid,
            expires_at timestamptz,
            revoked_at timestamptz,
            replaced_by uuid
        )
        LANGUAGE sql STABLE
        SECURITY DEFINER
        SET search_path = public, pg_catalog
        AS $$
            SELECT r.id, r.user_id, r.family_id, r.expires_at, r.revoked_at, r.replaced_by
            FROM refresh_tokens r
            WHERE r.token_hash = p_token_hash
            LIMIT 1;
        $$;
        """
    )
    for signature in (
        "auth_signup_user(citext, text, text, text, text, text, text)",
        "auth_lookup_refresh_token(text)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO app_runtime")
        op.execute(f"ALTER FUNCTION {signature} OWNER TO app_functions")

    # Restaura privilégios originais do runtime.
    op.execute("GRANT INSERT, UPDATE, DELETE ON TABLE users TO app_runtime")
    op.execute("GRANT UPDATE ON TABLE refresh_tokens TO app_runtime")
    op.execute("GRANT UPDATE ON TABLE single_use_tokens TO app_runtime")
    op.execute("REVOKE INSERT ON TABLE single_use_tokens FROM app_functions")
    op.execute("REVOKE UPDATE (email_verified_at, updated_at) ON TABLE users FROM app_functions")
    op.execute("GRANT EXECUTE ON FUNCTION app_current_user_id() TO PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app_current_tenant_id() TO PUBLIC")
    op.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE app_migration IN SCHEMA public "
        "GRANT EXECUTE ON FUNCTIONS TO PUBLIC"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE app_functions IN SCHEMA public "
        "GRANT EXECUTE ON FUNCTIONS TO PUBLIC"
    )
