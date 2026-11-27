# VagaNexo Authentication & Multi-User Ownership

## 1. Modelo de identidade

- Entidade **`User`** (`users`): `id` (UUID), `email` (`VARCHAR(320)`, único, normalizado com `strip().casefold()`), `password_hash` (`VARCHAR(255)`, Argon2id via `argon2-cffi`), `is_active` (`BOOLEAN`), `created_at` e `updated_at`.
- `User` é independente de `CandidateProfile`: um usuário pode possuir múltiplos perfis profissionais, e o e-mail de contato cadastrado no perfil **não** é usado como identidade de autenticação.
- Cadastro público irrestrito está **desabilitado** nesta etapa. O provisionamento ocorre via CLI administrativa local (`python -m app.cli create-user`).

## 2. Ciclo de vida das sessões

- Entidade **`AuthSession`** (`auth_sessions`): `id` (UUID), `user_id` (FK `users.id` com `ON DELETE CASCADE`), `token_hash` (SHA-256 único), `csrf_token_hash` (SHA-256), `created_at`, `last_seen_at`, `expires_at` e `revoked_at`.
- Tokens opacos de sessão e CSRF são gerados com `secrets.token_urlsafe(32)` (256 bits de entropia). Apenas os hashes SHA-256 são persistidos no PostgreSQL.
- Expiração absoluta configurável via `AUTH_SESSION_TTL_SECONDS` (padrão `604800` = 7 dias).
- Logout (`POST /api/v1/auth/logout`) revoga a sessão (`revoked_at`), remove o cookie e impede reutilização posterior.

## 3. Cookies, CSRF e CORS

- Cookie opaco: `vaganexo_session` (`HttpOnly`, `SameSite=Lax`, `Path=/`, sem `Domain`; `Secure` obrigatório quando `APP_ENV=production` ou `AUTH_COOKIE_SECURE=true`).
- Todas as operações de alteração de estado (`POST`, `PUT`, `PATCH`, `DELETE`) exigem cabeçalho `X-CSRF-Token` validado por `hmac.compare_digest` contra `csrf_token_hash`, além de validação do cabeçalho `Origin` contra `CORS_ORIGINS`.
- `CORSMiddleware` configurado com `allow_credentials=True` apenas para `CORS_ORIGINS`, métodos explícitos (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS`) e cabeçalhos explícitos (`Content-Type`, `X-CSRF-Token`, `Accept`).
- No frontend Next.js, requisições usam `credentials: "include"` e o token CSRF é mantido exclusivamente em memória (nunca em `localStorage` ou `sessionStorage`).

## 4. Rate limiting

- `RedisLoginRateLimiter` usa script Lua atômico (`INCR` + `EXPIRE` na primeira tentativa) no Redis para limitar tentativas por IP e por identificador de conta normalizado, ambos armazenados como hashes SHA-256 truncados (`auth:rl:ip:*` e `auth:rl:acct:*`).
- Janela e limite configuráveis (`AUTH_LOGIN_RATE_LIMIT_MAX_ATTEMPTS=5`, `AUTH_LOGIN_RATE_LIMIT_WINDOW_SECONDS=300`).
- Quando `APP_ENV=production` e o Redis está indisponível, o sistema falha fechado (`503 Service Unavailable`). Em desenvolvimento/testes, usa fallback local em memória com aviso em log.

## 5. Propriedade dos perfis e dados legados

- `candidate_profiles.user_id` (`FK -> users.id`, `ON DELETE SET NULL`, indexado) identifica o proprietário.
- O cliente não pode informar `user_id` na criação ou atualização (`extra="forbid"` nos schemas Pydantic); o servidor associa `current_user.id` no `ProfileService.create_profile()`.
- **Dados legados**: a migração `d1e2f3a4b5c6` mantém `candidate_profiles.user_id` anulável para preservar perfis anteriores sem atribuição automática. Perfis com `user_id IS NULL` permanecem inacessíveis pelas APIs (`404 Not Found`) até atribuição explícita via CLI local (`python -m app.cli claim-profile --profile-id <UUID> --email <EMAIL>`), que exige confirmação interativa e recusa sobrescrever proprietário já atribuído.

## 6. Proteção das APIs e serviços

- Todas as rotas sob `/api/v1/profiles` e `/api/v1/profiles/{profile_id}/resume-documents` exigem sessão ativa (`get_current_active_user`), verificação de propriedade (`require_owned_profile`, retornando `404` para recursos de terceiros ou legados sem proprietário) e proteção CSRF/Origin em mutações (`require_csrf_user`).
- `ProfileService(session, user_id=...)` e `ResumeImportService(session, storage, user_id=...)` filtram consultas de perfil explicitamente por `CandidateProfile.user_id == self.user_id`.

## 7. Variáveis de ambiente e execução local

- `AUTH_SESSION_COOKIE_NAME` (padrão `vaganexo_session`)
- `AUTH_SESSION_TTL_SECONDS` (padrão `604800`)
- `AUTH_COOKIE_SECURE` (opcional; padrão `true` em `production`)
- `AUTH_LOGIN_RATE_LIMIT_MAX_ATTEMPTS` (padrão `5`)
- `AUTH_LOGIN_RATE_LIMIT_WINDOW_SECONDS` (padrão `300`)

Provisionamento local:

```powershell
cd backend
uv run alembic upgrade head
uv run python -m app.cli create-user --email dev@example.com
uv run python -m app.cli claim-profile --profile-id <UUID> --email dev@example.com
```

## 8. Limitações de produção

- Não há fluxo de verificação de e-mail, recuperação de senha, cadastro público, MFA ou SSO nesta etapa.
- A exposição pública em HTTPS requer proxy reverso TLS com `APP_ENV=production` (ativando `Secure` nos cookies e fail-closed no Redis rate limiter) e `CORS_ORIGINS` restrito ao domínio real do frontend.
