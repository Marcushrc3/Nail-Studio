# Nail Studio Manager

Aplicação web mobile-first (SaaS) para gestão de Nail Designers: agenda, clientes, serviços,
financeiro e comunicação via WhatsApp. Interface em português brasileiro.

**Status atual: E0 (fundação técnica) concluída.** Nenhuma funcionalidade de negócio foi
implementada ainda — veja [docs/status-implementacao.md](docs/status-implementacao.md) para o
que está implementado, testado e pendente.

## Stack

| Camada | Tecnologia |
|---|---|
| Frontend | React 19, TypeScript (estrito), Vite, Tailwind CSS 4 |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.x (psycopg v3), Alembic |
| Banco | PostgreSQL 16 (desenvolvimento via Docker Compose) |
| Qualidade | ruff, mypy, pytest · ESLint, Prettier, tsc, Vitest · GitHub Actions + gitleaks |

## Pré-requisitos

- **Docker Desktop** (PostgreSQL local).
- **uv** — `winget install --id astral-sh.uv --scope user`.
- **Node.js 20+** e **pnpm** — `winget install --id OpenJS.NodeJS.LTS --scope user` e
  `winget install --id pnpm.pnpm --scope user`.

> Se você já tinha um Node antigo em `E:\Node`, o Node 24 instalado pelo winget fica em
> `%LOCALAPPDATA%\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_*\node-v24.*-win-x64`.
> Reinicie o VS Code após a instalação para o PATH ser atualizado, ou rode:
> `$env:Path = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.20.0-win-x64;" + $env:Path`

## Como executar localmente (Windows / PowerShell)

```powershell
# 1. Configurar variáveis de ambiente (só na primeira vez)
Copy-Item .env.example .env

# 2. Subir o PostgreSQL (apenas o banco; frontend e backend rodam nativos)
docker compose up -d db

# 2.1 Bootstrap de roles/permissões do banco (idempotente; exige superusuário)
cd backend
uv sync
uv run python scripts/bootstrap_db.py

# 3. Aplicar migrations
uv run alembic upgrade head

# 4. Backend (terminal 1)
uv run uvicorn app.main:app --reload --port 8000

# 5. Frontend (terminal 2)
cd frontend
pnpm install
pnpm dev
```

- API: http://localhost:8000 · docs interativas: http://localhost:8000/docs
- Frontend: http://localhost:5173 (a página exibe o estado da API)
- Health check com verificação real do banco: `GET /health` (200 = ok, 503 = banco indisponível)

## Qualidade (gates)

Backend (em `backend/`):

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run pytest
```

Frontend (em `frontend/`):

```powershell
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

## CI e varredura de segredos

`.github/workflows/ci.yml` executa todos os gates acima em cada push/PR, com PostgreSQL de
serviço no job do backend, e roda **gitleaks** para detectar segredos versionados.

## Documentação

- [docs/status-implementacao.md](docs/status-implementacao.md) — o que existe, o que foi testado, o que falta.
- [docs/adr/](docs/adr/) — registros de decisão de arquitetura (ADRs).

## Estrutura do monorepo

```
nail-studio-manager/
├── backend/        # FastAPI + SQLAlchemy + Alembic (monólito modular)
├── frontend/       # React + TypeScript + Vite + Tailwind
├── e2e/            # Playwright (a partir da E4)
├── docs/           # ADRs e status de implementação
├── .github/        # CI (GitHub Actions + gitleaks)
└── docker-compose.yml  # PostgreSQL de desenvolvimento
```
