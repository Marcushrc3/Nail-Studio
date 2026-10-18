# ADR 0002 — Autenticação e sessões (design aprovado, implementação na E1)

- **Data:** 2026-10-17
- **Status:** aprovado (implementação na E1)

## Decisão

- Credencial: **e-mail + senha** (OTP/magic link ficam como 2FA opcional futura).
- Hash de senha: **Argon2id** (`argon2-cffi`).
- Access token: **JWT HS256 de curta duração** (15 min), mantido **em memória** no frontend —
  nunca em `localStorage`.
- Refresh token: **opaco e rotativo**, armazenado **apenas como hash SHA-256** no banco,
  entregue em cookie `HttpOnly; Secure; SameSite=Lax` com path restrito à rota de refresh.
  Reuso de token já rotacionado revoga a sessão inteira.
- Verificação de e-mail (bloqueante) e recuperação de senha: **na E1**.
- Cadastro self-service (E1): registra versão e timestamp de aceite dos Termos e da Política
  de Privacidade; rate limiting e mensagens uniformes contra enumeração.

## O que já existe na E0

Apenas primitivas testadas por unidade em `backend/app/core/security.py`
(sem rotas, sem tabelas): hash/verificação Argon2id, criação/decodificação de access token,
geração de refresh token opaco + hash.

## Consequências / dependências para a E1

- Provedor SMTP e domínio remetente com SPF/DKIM/DMARC (decisão pendente).
- Tabelas `users` e `refresh_tokens` (migrations da E1).
- Envio de e-mail via `BackgroundTasks` (sem fila dedicada).
