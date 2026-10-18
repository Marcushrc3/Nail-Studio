"""Ciclo completo de migrations em banco descartável.

Executa o Alembic REAL (subprocesso, como faria o CI) com a role de
migração: upgrade -> downgrade -> upgrade -> check. O banco é criado e
destruído pelo teste; nenhum banco existente é tocado.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import Engine, make_url, text

BACKEND_DIR = Path(__file__).resolve().parents[2]
SCRATCH_DB = "nail_studio_migration_test"


def _alembic(*args: str, url: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["DATABASE_URL"] = url
    env["MIGRATION_DATABASE_URL"] = url
    env.setdefault("JWT_SECRET_KEY", "ci-test-secret-with-at-least-32-bytes")
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.fixture(scope="module")
def scratch_db_url(admin_engine: Engine) -> str:
    base = make_url(os.environ["MIGRATION_DATABASE_URL"]).set(database=SCRATCH_DB)
    scratch = base.render_as_string(hide_password=False)
    admin_base = make_url(os.environ["TEST_ADMIN_DATABASE_URL"]).set(database=SCRATCH_DB)
    scratch_admin = admin_base.render_as_string(hide_password=False)
    with admin_engine.connect() as connection:
        connection = connection.execution_options(isolation_level="AUTOCOMMIT")
        connection.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB}"))
        connection.execute(text(f"CREATE DATABASE {SCRATCH_DB}"))
    # O bootstrap é por-banco: aplica no scratch as mesmas permissões do dev.
    bootstrap = subprocess.run(
        [sys.executable, "scripts/bootstrap_db.py"],
        cwd=BACKEND_DIR,
        env={**os.environ, "BOOTSTRAP_DATABASE_URL": scratch_admin},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert bootstrap.returncode == 0, bootstrap.stderr
    yield scratch
    with admin_engine.connect() as connection:
        connection = connection.execution_options(isolation_level="AUTOCOMMIT")
        connection.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB}"))


def test_upgrade_downgrade_upgrade_and_schema_smoke(scratch_db_url: str) -> None:
    up = _alembic("upgrade", "head", url=scratch_db_url)
    assert up.returncode == 0, up.stderr

    down = _alembic("downgrade", "base", url=scratch_db_url)
    assert down.returncode == 0, down.stderr

    up_again = _alembic("upgrade", "head", url=scratch_db_url)
    assert up_again.returncode == 0, up_again.stderr

    # LIMITAÇÃO documentada: `alembic check` compara o banco com o metadata
    # dos modelos SQLAlchemy, que ainda não existem na E1.1 (metadata vazio
    # acusaria as tabelas como removidas). O drift check entra na E1.2, junto
    # com os modelos. Aqui validamos a estrutura criada pela migration.
    import sqlalchemy as sa

    smoke = sa.create_engine(scratch_db_url)
    with smoke.connect() as connection:
        tables = connection.execute(
            sa.text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
        ).scalar_one()
        policies = connection.execute(
            sa.text("SELECT count(*) FROM pg_policies WHERE schemaname = 'public'")
        ).scalar_one()
        functions = connection.execute(
            sa.text(
                "SELECT count(*) FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner "
                "WHERE p.proname LIKE 'auth_%' AND r.rolname = 'app_functions'"
            )
        ).scalar_one()
        version = connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    smoke.dispose()
    assert tables == 7  # 6 tabelas de negócio + alembic_version
    assert policies == 12
    assert functions == 5
    assert version == "c20d386c8723"
