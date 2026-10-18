# Status de implementação — E0 (fundação técnica)

**Data:** 2026-10-17 · **Estado:** E0 concluída e verificada localmente.
Nenhuma funcionalidade de negócio foi implementada.

## Critérios de aceite da E0 — verificação

| # | Critério | Estado | Evidência (executado em 2026-10-17) |
|---|---|---|---|
| 1 | Backend FastAPI inicializa com configuração validada | ✅ Implementado e testado | Startup valida `DATABASE_URL` e `JWT_SECRET_KEY` (fail-fast); teste em `tests/test_config.py` |
| 2 | `GET /health` verifica conectividade real com PostgreSQL | ✅ Implementado e testado | `curl http://127.0.0.1:8000/health` → `200 {"status":"ok","database":"ok"}`; caminho de falha (503) testado com banco inacessível |
| 3 | Frontend React + TS estrito apresenta o estado da API | ✅ Implementado e testado | `src/App.tsx` consulta `/health`; 3 testes Vitest passando; validação visual em `http://localhost:5173` mostrando "API conectada — banco de dados OK" |
| 4 | PostgreSQL via Docker Compose, sem obrigar app em container | ✅ Configurado / ⚠️ verificado com alternativa | `docker-compose.yml` criado; Docker não está instalado nesta máquina, então a verificação usou binários portáteis oficiais do PostgreSQL 16.9 em `E:\Temp\pgsql` (mesma imagem/versão) |
| 5 | Alembic aplica baseline vazia em banco novo; nenhuma tabela de negócio | ✅ Implementado e testado | `alembic upgrade head` em banco vazio; `SELECT * FROM information_schema.tables` → apenas `alembic_version`; `alembic check` → "No new upgrade operations detected" |
| 6 | Testes, lint e typecheck configurados e executáveis | ✅ Implementado e testado | Backend: `ruff` ✓, `ruff format --check` ✓, `mypy` ✓, `pytest` **19 passed** ✓. Frontend: `eslint` ✓, `tsc -b` ✓, `vitest` **3 passed** ✓, `vite build` ✓ |
| 7 | GitHub Actions executa os gates com PostgreSQL disponível | ✅ Configurado / ⚠️ não executado (requer repositório no GitHub) | `.github/workflows/ci.yml` com 3 jobs (backend + frontend + secrets) |
| 8 | Varredura de segredos configurada | ✅ Configurado / ⚠️ não executado localmente | Job `secrets-scan` com **gitleaks** no CI |
| 9 | README documenta instalação e execução em Windows | ✅ Implementado | Comandos PowerShell passo a passo; comandos testados nesta máquina |
| 10 | Documentação distingue implementado, testado e pendente | ✅ Implementado | Este documento + ADRs em `docs/adr/` |

## Harness de isolamento (requisito especial da E0)

`backend/tests/isolation/` usa principals **sintéticos** (header `X-Synthetic-Tenant-Id`)
e a tabela `isolation_probe`, criada e removida por **fixtures de teste** (nunca por
migrations). Cobre, com PostgreSQL real:

- **Contexto por request**: cada request vê o tenant do seu principal; sem contexto → 401 (fail-closed).
- **Acesso cross-tenant**: listagem vazia, leitura 404 e atualização 404 para dados de outro tenant.
- **Reutilização do pool**: com `pool_size=1`, a **mesma conexão física** (evidenciada por
  `pg_backend_pid`) atende tenants diferentes sem vazamento de dados nem estado residual
  (`current_setting('app.current_tenant', true)` = nulo).

**Limitação honesta:** o harness prova o isolamento da **camada de aplicação**. A garantia
imposta pelo banco (PostgreSQL RLS) está aprovada para a **E1** e ainda não existe — o critério
"isolamento garantido por banco" NÃO é declarado aprovado (ver ADR 0003).

## O que já está pronto para a E1 (sem rotas, sem tabelas)

- `backend/app/core/security.py`: Argon2id (hash/verify), access token JWT HS256,
  refresh token opaco com hash SHA-256 — 8 testes de unidade.
- `backend/app/core/tenant.py`: `TenantContext`, `ContextVar` e `require_tenant()` (401 fail-closed).

## Pendências explícitas (não implementadas, por decisão)

- Login, verificação de e-mail e recuperação de senha → **E1**.
- Tabelas de negócio (`users`, `refresh_tokens`, `clients`, `services`, etc.) → **E1+**.
- PostgreSQL RLS por transação (`SET LOCAL`) → **E1**.
- CRUD, agenda, financeiro, relatórios, links WhatsApp, PWA instalável → **E2–E7**.
- Decisão de hospedagem de produção → gate anterior ao primeiro deploy.

## Notas do ambiente de verificação (2026-10-17)

- Ferramentas instaladas via winget (escopo de usuário): Node 24.20.0, uv 0.13.1, pnpm 12.11.2.
  Um Node 14 antigo existe em `E:\Node` e tem precedência no PATH — o Node 24 precisa vir
  antes (reinicie o VS Code após instalar; veja README).
- **Docker não está instalado** nesta máquina. A verificação do item 4 usou PostgreSQL 16.9
  portátil oficial em `E:\Temp\pgsql` (start/stop documentados abaixo). Quando o Docker for
  instalado, `docker compose up -d db` deve ser o caminho padrão.
- O disco `C:` estava **cheio (0 GB livres)** durante a execução; caches de build foram
  redirecionados para `E:\Temp`/`E:\uv-cache`/`E:\npm-cache` como contorno. Recomenda-se
  limpar o disco (ex.: `hiberfil.sys` de ~6,4 GB via `powercfg /h off`, Limpeza de Disco).

### Comandos do PostgreSQL portátil (apenas para verificação sem Docker)

```powershell
# iniciar (uma vez baixado e extraído em E:\Temp\pgsql, cluster em E:\Temp\pgdata)
& "E:\Temp\pgsql\bin\pg_ctl.exe" -D E:\Temp\pgdata -l E:\Temp\pglog.txt -o "-p 5432" start
# parar
& "E:\Temp\pgsql\bin\pg_ctl.exe" -D E:\Temp\pgdata stop -m fast
```
