-- ============================================================
-- Bootstrap de roles e permissões do banco (IDEMPOTENTE).
-- Executar como SUPERUSUÁRIO (dev/CI) via scripts/bootstrap_db.py.
-- NÃO contém schema: as tabelas/políticas entram via Alembic.
--
-- Modelo de permissões:
--   app_runtime    -> login usado SOMENTE pela API. Sem superuser, sem
--                     BYPASSRLS, sem CREATEROLE/CREATEDB.
--   app_migration  -> login usado SOMENTE pelo Alembic/seed. Dono dos
--                     objetos; sem superuser e sem BYPASSRLS.
--   app_functions  -> role NOLOGIN + BYPASSRLS, proprietária das funções
--                     SECURITY DEFINER. Só é alcançável pelas próprias
--                     funções estreitas (app_migration é membro para
--                     criar/removê-las durante migrações).
-- ============================================================

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_runtime') THEN
    CREATE ROLE app_runtime LOGIN PASSWORD 'app_runtime_pw';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_migration') THEN
    CREATE ROLE app_migration LOGIN PASSWORD 'app_migration_pw';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_functions') THEN
    CREATE ROLE app_functions NOLOGIN BYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_unprivileged') THEN
    CREATE ROLE app_unprivileged LOGIN PASSWORD 'app_unprivileged_pw';
  END IF;
END
$$;

-- Hardening (reforça mesmo que as roles já existam).
ALTER ROLE app_runtime NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
ALTER ROLE app_migration NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
ALTER ROLE app_functions NOSUPERUSER NOCREATEDB NOCREATEROLE NOLOGIN;
ALTER ROLE app_unprivileged NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;

-- app_migration cria/destroi as funções definer (SET ROLE app_functions).
GRANT app_functions TO app_migration;

-- Conexão: somente as roles de aplicação/migração.
-- Usa current_database() para funcionar em QUALQUER banco (inclusive o
-- descartável usado no teste de ciclo de migrations).
DO $$
BEGIN
  EXECUTE 'REVOKE ALL ON DATABASE ' || quote_ident(current_database()) || ' FROM PUBLIC';
  EXECUTE 'GRANT CONNECT ON DATABASE ' || quote_ident(current_database()) || ' TO app_runtime, app_migration, app_unprivileged';
  EXECUTE 'GRANT CREATE ON DATABASE ' || quote_ident(current_database()) || ' TO app_migration';
END
$$;

-- A tabela de versão do Alembic foi criada na E0 antes destas roles existirem:
-- transfere a posse para a role de migração (idempotente).
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'alembic_version'
  ) THEN
    EXECUTE 'ALTER TABLE public.alembic_version OWNER TO app_migration';
  END IF;
END
$$;

-- Schema public: runtime só USAGE; migration cria objetos.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO app_runtime, app_migration;
GRANT CREATE ON SCHEMA public TO app_migration;
-- Requisito do PostgreSQL para ALTER ... OWNER: a nova dona das funções
-- definer precisa de CREATE no schema. app_functions é NOLOGIN e só é
-- alcançável via SET ROLE pela role de migração.
GRANT CREATE ON SCHEMA public TO app_functions;

-- Tudo que a migration criar já nasce com os grants de runtime corretos.
ALTER DEFAULT PRIVILEGES FOR ROLE app_migration IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE app_migration IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO app_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE app_migration IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO app_runtime;
-- Funções definer criadas com SET ROLE app_functions também ficam acessíveis.
ALTER DEFAULT PRIVILEGES FOR ROLE app_functions IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO app_runtime;
