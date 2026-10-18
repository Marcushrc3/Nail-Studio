"""auth foundation: contas, sessoes, verificacao, consentimento e RLS

Revision ID: d09eb36d6b7d
Revises: caa064efaae1
Create Date: 2026-10-17 22:02:33.937568

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "d09eb36d6b7d"
down_revision = "caa064efaae1"
branch_labels = None
depends_on = None

# Helpers de contexto (GUCs transacionais). São SECURITY INVOKER e pertencem
# à role de migração; a app só precisa de EXECUTE (garantido pelo bootstrap).
HELPERS = [
    """
    CREATE FUNCTION app_current_user_id()
    RETURNS uuid
    LANGUAGE sql STABLE
    AS $$
        SELECT NULLIF(current_setting('app.current_user_id', true), '')::uuid
    $$;
    """,
    """
    CREATE FUNCTION app_current_tenant_id()
    RETURNS uuid
    LANGUAGE sql STABLE
    AS $$
        SELECT NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
    $$;
    """,
]

# Funções SECURITY DEFINER (owner: app_functions, NOLOGIN + BYPASSRLS).
# Retornam somente os campos necessários; REVOKE de PUBLIC e EXECUTE só
# para app_runtime. search_path fixo para evitar hijacking de objetos.
DEFINER_FUNCTIONS = [
    """
    CREATE FUNCTION auth_lookup_user_by_email(p_email citext)
    RETURNS TABLE(
        id uuid,
        tenant_id uuid,
        password_hash text,
        email_verified_at timestamptz,
        is_active boolean
    )
    LANGUAGE sql STABLE
    SECURITY DEFINER
    SET search_path = public, pg_catalog
    AS $$
        SELECT u.id, u.tenant_id, u.password_hash, u.email_verified_at, u.is_active
        FROM users u
        WHERE u.email = p_email
        LIMIT 1;
    $$;
    """,
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
    """,
    """
    CREATE FUNCTION auth_lookup_single_use_token(p_token_hash text)
    RETURNS TABLE(
        id uuid,
        user_id uuid,
        purpose token_purpose,
        expires_at timestamptz,
        used_at timestamptz
    )
    LANGUAGE sql STABLE
    SECURITY DEFINER
    SET search_path = public, pg_catalog
    AS $$
        SELECT t.id, t.user_id, t.purpose, t.expires_at, t.used_at
        FROM single_use_tokens t
        WHERE t.token_hash = p_token_hash
        LIMIT 1;
    $$;
    """,
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

        RETURN v_user_id;
    END;
    $$;
    """,
]

RLS_TABLES = [
    "tenants",
    "users",
    "profiles",
    "refresh_tokens",
    "single_use_tokens",
    "consent_records",
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("email_verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])

    op.create_table(
        "profiles",
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column(
            "timezone", sa.Text(), nullable=False, server_default=sa.text("'America/Sao_Paulo'")
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("replaced_by", sa.Uuid(), sa.ForeignKey("refresh_tokens.id"), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])

    op.create_table(
        "single_use_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "purpose",
            postgresql.ENUM("email_verification", "password_reset", name="token_purpose"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_single_use_tokens_user_id", "single_use_tokens", ["user_id"])

    op.create_table(
        "consent_records",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "document_type",
            postgresql.ENUM("terms", "privacy", name="consent_type"),
            nullable=False,
        ),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column(
            "accepted_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "user_id", "document_type", "version", name="uq_consent_user_document_version"
        ),
    )

    # Helpers de contexto (SECURITY INVOKER, owner app_migration).
    for helper in HELPERS:
        op.execute(helper)

    # Funções definer: criadas pela role de migração e transferidas para
    # app_functions (NOLOGIN + BYPASSRLS). app_migration é membro de ambas as
    # roles, então pode conceder/transferir sem dar CREATE à app_functions.
    for ddl in DEFINER_FUNCTIONS:
        op.execute(ddl)
        name = ddl.split("CREATE FUNCTION ")[1].split("(")[0].strip()
        op.execute(f"REVOKE ALL ON FUNCTION {name} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {name} TO app_runtime")
        op.execute(f"ALTER FUNCTION {name} OWNER TO app_functions")

    # RLS fail-closed em todas as tabelas.
    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    op.execute(
        """
        CREATE POLICY tenants_self_select ON tenants
        FOR SELECT TO app_runtime
        USING (id = app_current_tenant_id());
        """
    )
    op.execute(
        """
        CREATE POLICY users_self_select ON users
        FOR SELECT TO app_runtime
        USING (id = app_current_user_id());
        """
    )
    op.execute(
        """
        CREATE POLICY users_self_update ON users
        FOR UPDATE TO app_runtime
        USING (id = app_current_user_id())
        WITH CHECK (id = app_current_user_id());
        """
    )
    op.execute(
        """
        CREATE POLICY profiles_self_select ON profiles
        FOR SELECT TO app_runtime
        USING (user_id = app_current_user_id());
        """
    )
    op.execute(
        """
        CREATE POLICY profiles_self_update ON profiles
        FOR UPDATE TO app_runtime
        USING (user_id = app_current_user_id())
        WITH CHECK (user_id = app_current_user_id());
        """
    )
    op.execute(
        """
        CREATE POLICY refresh_tokens_self_select ON refresh_tokens
        FOR SELECT TO app_runtime
        USING (user_id = app_current_user_id());
        """
    )
    op.execute(
        """
        CREATE POLICY refresh_tokens_self_update ON refresh_tokens
        FOR UPDATE TO app_runtime
        USING (user_id = app_current_user_id())
        WITH CHECK (user_id = app_current_user_id());
        """
    )
    op.execute(
        """
        CREATE POLICY refresh_tokens_self_insert ON refresh_tokens
        FOR INSERT TO app_runtime
        WITH CHECK (user_id = app_current_user_id());
        """
    )
    op.execute(
        """
        CREATE POLICY refresh_tokens_self_delete ON refresh_tokens
        FOR DELETE TO app_runtime
        USING (user_id = app_current_user_id());
        """
    )
    op.execute(
        """
        CREATE POLICY single_use_tokens_self_select ON single_use_tokens
        FOR SELECT TO app_runtime
        USING (user_id = app_current_user_id());
        """
    )
    op.execute(
        """
        CREATE POLICY single_use_tokens_self_update ON single_use_tokens
        FOR UPDATE TO app_runtime
        USING (user_id = app_current_user_id())
        WITH CHECK (user_id = app_current_user_id());
        """
    )
    op.execute(
        """
        CREATE POLICY consent_records_self_select ON consent_records
        FOR SELECT TO app_runtime
        USING (user_id = app_current_user_id());
        """
    )

    # Grants mínimos para app_functions (dona das funções definer, NOLOGIN).
    # São EXATAMENTE os acessos que as funções definer precisam executar:
    #   auth_lookup_user_by_email      -> SELECT users
    #   auth_lookup_refresh_token      -> SELECT refresh_tokens
    #   auth_lookup_single_use_token   -> SELECT single_use_tokens
    #   auth_signup_user               -> INSERT tenants/users/profiles/consents
    # NOTA (PG15+): RETURNING exige SELECT nas colunas retornadas.
    op.execute("GRANT SELECT, INSERT ON TABLE tenants TO app_functions")
    op.execute("GRANT SELECT, INSERT ON TABLE users TO app_functions")
    op.execute("GRANT INSERT ON TABLE profiles TO app_functions")
    op.execute("GRANT SELECT ON TABLE refresh_tokens TO app_functions")
    op.execute("GRANT SELECT ON TABLE single_use_tokens TO app_functions")
    op.execute("GRANT INSERT ON TABLE consent_records TO app_functions")


def downgrade() -> None:
    # 1. Funções definer (owner app_functions; a role de migração é membro).
    op.execute("SET ROLE app_functions")
    op.execute(
        "DROP FUNCTION IF EXISTS auth_signup_user(citext, text, text, text, text, text, text)"
    )
    op.execute("DROP FUNCTION IF EXISTS auth_lookup_user_by_email(citext)")
    op.execute("DROP FUNCTION IF EXISTS auth_lookup_refresh_token(text)")
    op.execute("DROP FUNCTION IF EXISTS auth_lookup_single_use_token(text)")
    op.execute("RESET ROLE")

    # 2. Tabelas (as políticas RLS caem junto).
    for table in reversed(RLS_TABLES):
        op.drop_table(table)

    # 3. Funções auxiliares de contexto (só após as políticas desaparecerem).
    op.execute("DROP FUNCTION IF EXISTS app_current_user_id()")
    op.execute("DROP FUNCTION IF EXISTS app_current_tenant_id()")

    postgresql.ENUM("consent_type", name="consent_type").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM("token_purpose", name="token_purpose").drop(op.get_bind(), checkfirst=True)
    # A extensão citext é recurso compartilhado do cluster: permanece instalada.
