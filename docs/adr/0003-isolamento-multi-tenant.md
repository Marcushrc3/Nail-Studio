# ADR 0003 — Isolamento de dados entre profissionais (multi-tenant)

- **Data:** 2026-10-17
- **Status:** aprovado (RLS implementado na E1)

## Decisão

1. **Camada de aplicação (obrigatória, desde a E0):** toda tabela de negócio terá `owner_id`
   referenciando a conta; todo acesso passa por repositório que injeta o filtro do tenant;
   constraints de unicidade sempre compostas por `owner_id`. Request sem contexto de tenant é
   negado (fail-closed).
2. **Camada de banco (E1):** PostgreSQL **RLS** como defesa em profundidade, com
   `SET LOCAL app.current_user_id` aplicado **no início de cada transação** (nunca `SET` no
   nível da conexão) e resetado no commit/rollback; role de bypass exclusiva para Alembic/seed.
3. **Testes:** harness cross-tenant obrigatório no CI — prova que um tenant não lê/altera dados
   de outro e que o contexto não vaza entre requests que reutilizam a mesma conexão do pool.

## Mecanismo da E0

`backend/app/core/tenant.py` define `TenantContext` (dataclass imutável), um `ContextVar`
(estado por request/task, sem estado persistente na conexão do pool) e a dependência
`require_tenant()` que responde **401** quando não há contexto.

O harness em `backend/tests/isolation/` usa principals **sintéticos** (header
`X-Synthetic-Tenant-Id`) e uma tabela criada/removida por fixtures de teste — nunca por
migrations. Ele demonstra o padrão de scoping da aplicação; **não** substitui autenticação
real (E1) nem RLS (E1).

## Limitação conhecida (documentada)

Na E0, o isolamento é demonstrado pela camada de aplicação. A garantia imposta pelo banco
(RLS) entra na E1; o critério "isolamento garantido por banco" não é declarado aprovado antes
disso.
