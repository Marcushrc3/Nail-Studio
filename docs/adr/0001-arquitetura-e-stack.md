# ADR 0001 — Arquitetura e stack da fundação (E0)

- **Data:** 2026-10-17
- **Status:** aprovado

## Decisões aprovadas (baseline)

- SaaS com várias profissionais, cada uma com conta e dados isolados.
- Frontend: React + TypeScript + Vite, mobile-first, interface em pt-BR, evolução para PWA.
- Backend: Python + FastAPI, monólito modular (um pacote por domínio em `app/modules/`).
- Banco: PostgreSQL 16 com SQLAlchemy 2.x (engine **síncrono**, driver `psycopg` v3) e Alembic.
- Repositório: monorepo com `backend/` e `frontend/`.
- Valores monetários em centavos inteiros (nenhuma tabela de negócio criada na E0).
- Links `wa.me` com texto preenchido, sem envio automático de mensagens.
- **Sem Supabase** (backend e autenticação próprios).
- Sem microsserviços, Redis ou filas dedicadas (sem justificativa de volume).

## Decisões da E0

- Engine SQLAlchemy síncrono com `pool_pre_ping=True` (simplicidade; o volume do MVP não
  justifica async).
- Configuração via `pydantic-settings` com fail-fast (falha na inicialização se variável
  obrigatória ausente); `.env` aceito em `backend/.env` ou na raiz.
- CORS configurável por variável de ambiente (lista separada por vírgulas).
- Contrato da API será gerado do OpenAPI para o frontend (`openapi-typescript`) quando houver
  endpoints de domínio — nenhum cliente gerado ainda na E0.
- Hospedagem de produção **adiada** para um gate anterior ao primeiro deploy (ver ADR em aberto).

## Consequências

- Desenvolvimento local: PostgreSQL via Docker Compose; frontend e backend nativos.
- Migrations são a fonte da verdade do schema; nenhuma tabela de negócio antes da E1.
