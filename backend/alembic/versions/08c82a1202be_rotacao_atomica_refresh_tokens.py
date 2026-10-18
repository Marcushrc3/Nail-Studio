"""rotacao-atomica-refresh-tokens

Revision ID: 08c82a1202be
Revises: c20d386c8723
Create Date: 2026-10-17 22:47:07.799776

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "08c82a1202be"
down_revision = "c20d386c8723"
branch_labels = None
depends_on = None

ROTATE_FUNCTION = """
CREATE FUNCTION auth_rotate_refresh_token(
    p_old_id uuid,
    p_new_id uuid,
    p_new_token_hash text
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
DECLARE
    v_user_id uuid;
    v_family_id uuid;
    v_expires_at timestamptz;
BEGIN
    -- A FK replaced_by é deferível; a checagem ocorre no commit, quando o
    -- sucessor já foi inserido.
    EXECUTE 'SET CONSTRAINTS refresh_tokens_replaced_by_fkey DEFERRED';

    -- UPDATE atômico: só o primeiro a chegar encontra a linha "não rotacionada".
    UPDATE refresh_tokens
    SET revoked_at = now(), replaced_by = p_new_id
    WHERE id = p_old_id
      AND revoked_at IS NULL
      AND replaced_by IS NULL
      AND expires_at > now()
    RETURNING user_id, family_id, expires_at
    INTO v_user_id, v_family_id, v_expires_at;

    IF NOT FOUND THEN
        RETURN false;
    END IF;

    INSERT INTO refresh_tokens (id, user_id, token_hash, family_id, expires_at)
    VALUES (p_new_id, v_user_id, p_new_token_hash, v_family_id, v_expires_at);

    RETURN true;
END;
$$;
"""


def upgrade() -> None:
    # FK deferível: o sucessor só precisa existir no commit da transação
    # (necessário para a rotação atômica UPDATE-then-INSERT).
    op.execute("ALTER TABLE refresh_tokens DROP CONSTRAINT refresh_tokens_replaced_by_fkey")
    op.execute(
        "ALTER TABLE refresh_tokens ADD CONSTRAINT refresh_tokens_replaced_by_fkey "
        "FOREIGN KEY (replaced_by) REFERENCES refresh_tokens(id) "
        "DEFERRABLE INITIALLY IMMEDIATE"
    )

    # Grants mínimos para a função definer de rotação.
    op.execute("GRANT UPDATE (revoked_at, replaced_by) ON TABLE refresh_tokens TO app_functions")
    op.execute("GRANT INSERT ON TABLE refresh_tokens TO app_functions")

    op.execute(ROTATE_FUNCTION)
    op.execute("REVOKE ALL ON FUNCTION auth_rotate_refresh_token(uuid, uuid, text) FROM PUBLIC")
    op.execute(
        "GRANT EXECUTE ON FUNCTION auth_rotate_refresh_token(uuid, uuid, text) TO app_runtime"
    )
    op.execute("ALTER FUNCTION auth_rotate_refresh_token(uuid, uuid, text) OWNER TO app_functions")


def downgrade() -> None:
    op.execute("SET ROLE app_functions")
    op.execute("DROP FUNCTION IF EXISTS auth_rotate_refresh_token(uuid, uuid, text)")
    op.execute("RESET ROLE")
    op.execute("REVOKE UPDATE (revoked_at, replaced_by) ON TABLE refresh_tokens FROM app_functions")
    op.execute("REVOKE INSERT ON TABLE refresh_tokens FROM app_functions")
    op.execute("ALTER TABLE refresh_tokens DROP CONSTRAINT refresh_tokens_replaced_by_fkey")
    op.execute(
        "ALTER TABLE refresh_tokens ADD CONSTRAINT refresh_tokens_replaced_by_fkey "
        "FOREIGN KEY (replaced_by) REFERENCES refresh_tokens(id)"
    )
