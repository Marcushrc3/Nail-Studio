# ADR 0004 — Permissões de banco e RLS (E1.1)

- **Data:** 2026-10-17
- **Status:** implementado e testado

## Modelo de permissões

| Role | Login | Superuser | BYPASSRLS | Uso |
|---|---|---|---|---|
| `app_runtime` | sim | não | **não** | Apenas a API (runtime) |
| `app_migration` | sim | não | **não** | Apenas Alembic/seed; dona dos objetos |
| `app_functions` | **não** | não | sim (confinado) | Dona das funções SECURITY DEFINER |

- Bootstrap idempotente em `backend/scripts/bootstrap_db.sql` (+ runner Python),
  executado **uma vez** como superusuário por banco (usa `current_database()`).
- Objetos criados pela migration nascem com grants corretos via
  `ALTER DEFAULT PRIVILEGES FOR ROLE app_migration`.
- `alembic_version` é transferida para `app_migration` no bootstrap (foi criada
  na E0 antes das roles existirem).

## RLS e contexto transacional

- Todas as 6 tabelas com `ENABLE + FORCE ROW LEVEL SECURITY`; políticas self-only
  para `app_runtime` baseadas em GUCs `app.current_user_id` / `app.current_tenant_id`.
- GUCs aplicados com `set_config(..., true)` (equivalente a `SET LOCAL`) no evento
  `begin` do SQLAlchemy (`app/core/db.py::create_engine_from_url`): o valor morre
  no commit/rollback e a conexão volta limpa ao pool (provado por teste).
- GUC customizado sem valor retorna `''` após o `SET LOCAL` expirar; as funções de
  contexto usam `NULLIF(..., '')` → políticas permanecem fail-closed.
- O cliente **nunca** escolhe o tenant: ele será derivado do usuário autenticado
  (JWT) na E1.2. Hoje não há endpoint que leia tenant de input do cliente.

## Funções SECURITY DEFINER (o "ovo-e-galinha")

Login/refresh/tokens de uso único precisam ler dados **antes** de existir
contexto. Funções estreitas resolvem isso sem abrir leitura direta:

- `auth_lookup_user_by_email`, `auth_lookup_refresh_token`,
  `auth_lookup_single_use_token`, `auth_signup_user` (cria tenant+user+profile+
  consentimentos atomicamente).
- **Dona:** `app_functions` — `NOLOGIN` + `BYPASSRLS`, sem `CREATE` além do schema
  (necessário para receber a posse via `ALTER ... OWNER`), alcançável apenas por
  `SET ROLE` da role de migração e pelas próprias funções. `REVOKE FROM PUBLIC`,
  `EXECUTE` somente para `app_runtime`, `SET search_path` fixo.
- **Grants de dados mínimos** para `app_functions` (somente o que as funções usam;
  `RETURNING` exige `SELECT` nas colunas retornadas — PG15+).

## Limitações documentadas

- `alembic check` (drift) só será significativo quando existirem modelos
  SQLAlchemy (E1.2+); hoje o ciclo de migrations é validado por upgrade →
  downgrade → upgrade + smoke estrutural (7 tabelas, 12 políticas, 4 funções)
  em banco descartável (`tests/db/test_migrations_cycle.py`).
- Concorrência simultânea entre requests ainda não testada (E1.6).
- Sem endpoints ainda: o harness E0 usa principals sintéticos e não é produção.
