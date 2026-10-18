# ADR 0005 — Núcleo de autenticação (E1.2)

- **Data:** 2026-10-17
- **Status:** implementado e testado

## Decisões implementadas

- **JWT**: HS256 explícito; claims obrigatórias `sub`, `tenant_id`, `iss`, `aud`,
  `iat`, `exp`, `jti`; `verify_iat`; rejeição de `alg=none`/algoritmos não
  permitidos (whitelist no decode).
- **Senha**: Argon2id; mínimo 10 caracteres + zxcvbn (score ≥ 3) — sem regras de
  composição (D4).
- **Cadastro**: `auth_signup_user` cria tenant+usuário+perfil+consentimentos+token
  de verificação **atomicamente**; duplicata → resposta externa idêntica (sem
  revelar existência e sem envio de e-mail).
- **Verificação bloqueante**: login só após `email_verified_at` (marcado pela
  definer `auth_mark_email_verified`); token de uso único (hash, expiração 24 h).
- **Sessões**: refresh opaco (SHA-256 no banco), família com expiração **fixa** de
  30 dias, rotação com `revoked_at`/`replaced_by`, reuso detectado → **família
  inteira revogada**; logout (sessão) e logout-all (todas).
- **Cookies**: refresh em `HttpOnly; SameSite=Lax; Path=/api/v1/auth`, `Secure`
  somente em produção; access token apenas no corpo (memória no frontend).
- **Rate limiting**: slowapi em memória (1 instância — limitação documentada):
  signup/login 5/min; refresh/logout/verificação 10/min.
- **E-mail**: interface `EmailProvider` + `FakeEmailProvider` (nenhum SMTP real;
  adaptador SMTP na E1.4).
- **Contexto**: `TenantContextMiddleware` (ASGI) decodifica o Bearer no event
  loop e propaga os ContextVars aos workers; dependência `get_current_auth`
  apenas valida presença de contexto (fail-closed). Tenant **nunca** vem de
  parâmetro do cliente.
- **Correções da auditoria E1.1** (migration `c20d386c8723`): runtime sem UPDATE
  em colunas sensíveis de `users` (só `updated_at`); `refresh_tokens` só
  `revoked_at`/`replaced_by`; `single_use_tokens` só `used_at`; PUBLIC sem
  EXECUTE nos helpers; default privileges sem EXECUTE público; `app_unprivileged`
  para provar negações.

## Limitações

- Rate limit em memória: válido para uma instância (multi-instância exige
  backend compartilhado — decisão futura).
- Recuperação de senha: E1.3. SMTP real: E1.4. Frontend: E1.5.
