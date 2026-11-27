# Relatório de Auditoria de Segurança — Autenticação, Autorização e CI/CD

## 1. Escopo

Auditoria independente realizada na branch `feat/auth-multitenancy` (baseada em `feat/resume-import`, commit `6a66837cf839a86f6227329c90862577e17b3be3`) cobrindo:

- Identidade, hashing Argon2id e normalização de e-mail (`backend/app/auth/security.py`, `backend/app/models/user.py`).
- Sessões opacas e ciclo de vida (`backend/app/auth/service.py`, `backend/app/models/auth_session.py`).
- Endpoints de autenticação, cookies, CSRF, Origin e CORS (`backend/app/api/routes/auth.py`, `backend/app/auth/dependencies.py`, `backend/app/main.py`).
- Rate limiting e tratamento de IP (`backend/app/auth/rate_limit.py`, `backend/app/core/config.py`).
- Autorização multiusuário em rotas e serviços (`backend/app/api/routes/profiles.py`, `backend/app/api/routes/resume_documents.py`, `backend/app/profile/service.py`, `backend/app/resume_import/service.py`).
- Provisionamento administrativo (`backend/app/cli.py`).
- Integração frontend (`frontend/src/lib/api.ts`, `frontend/src/components/auth/auth-provider.tsx`, `frontend/src/app/login/page.tsx`).

## 2. Vulnerabilidades e fragilidades identificadas e corrigidas

| Severidade | Componente | Cenário / Causa raiz | Correção aplicada | Teste de regressão |
| --- | --- | --- | --- | --- |
| **Alta** | `ProfileService` / `ResumeImportService` (`backend/app/profile/service.py`) | Ausência de validação em tempo de execução para `user_id` no construtor. Caso `None` fosse passado, `CandidateProfile.user_id == self.user_id` geraria `IS NULL`, expondo perfis legados sem proprietário. | Validação estrita `isinstance(user_id, uuid.UUID)` no `__init__` (falha fechada com `InvalidProfileDataError`) e reforço com `CandidateProfile.user_id.is_not(None)` nas consultas. | `test_profile_and_resume_services_fail_closed_on_missing_user_id` |
| **Alta** | `validate_origin()` (`backend/app/auth/dependencies.py`) e `GET /api/v1/auth/csrf` | `if not origin: return` tratava `Origin: ""` como ausente, ignorava `Referer` quando `Origin` não era enviado e permitia ausência de `Origin`/`Referer` em produção, além de não validar `Origin` em `GET /csrf`. | Rejeição imediata de `Origin: ""`, `Origin: null` e origens inválidas; validação de `Referer` quando `Origin` está ausente; falha fechada em `APP_ENV=production` quando ambos faltam; validação de origem em `GET /csrf`. | `test_origin_null_empty_malformed_referer_and_production_fail_closed` |
| **Média** | `AuthService.claim_profile()` (`backend/app/auth/service.py`) | Padrão *check-then-act* (`SELECT` seguido de `UPDATE`) permitia condição de corrida entre duas execuções simultâneas de `claim-profile`, possibilitando sobrescrita silenciosa de proprietário. | Atualização condicional atômica `UPDATE candidate_profiles SET user_id = :uid WHERE id = :pid AND user_id IS NULL RETURNING id`, retornando `ConflictError` se já atribuído. | `test_cli_create_user_and_claim_profile` |
| **Média** | Frontend CSRF (`frontend/src/lib/api.ts`) | Chamadas simultâneas a `ensureCsrfToken()` disparavam múltiplas requisições a `GET /api/v1/auth/csrf`, sobrescrevendo `csrf_token_hash` no banco e invalidando a requisição concorrente com `403`. | Deduplicação de chamadas em andamento via `inFlightCsrfPromise` e retentativa única controlada quando outra aba rotacionar o token CSRF (`detail === "CSRF validation failed"`). | Build/TypeScript/ESLint validados; contrato backend em `test_auth_api.py` |
| **Baixa** | `AuthService.authenticate()` (`backend/app/auth/security.py`, `service.py`) | Ausência de rehash controlado caso os parâmetros de Argon2id sejam elevados no futuro. | Adição de `needs_rehash()` (`PasswordHasher.check_needs_rehash`) e atualização automática do hash no login bem-sucedido. | `test_authenticate_rehashes_password_when_needed` |

## 3. Garantias verificadas diretamente no código

- **Argon2id e identidade**: `argon2.PasswordHasher()` (Argon2id, 64 MiB, `time_cost=3`, `parallelism=4`), `dummy_verify_password()` para mitigar enumeração por tempo, normalização com `strip().casefold()`, unicidade no PostgreSQL, rejeição de contas inativas e mensagens genéricas no login.
- **Schemas estritos**: `APIModel` configura `extra="forbid"`, rejeitando `user_id` enviado pelo cliente com `422`.
- **Sessões opacas**: tokens de 256 bits (`secrets.token_urlsafe(32)`), apenas hashes SHA-256 no banco, expiração absoluta e revogação imediata no logout.
- **Rate limiting e spoofing de IP**: script Lua atômico no Redis com chaves `auth:rl:ip:*` e `auth:rl:acct:*` (SHA-256 truncado, sem e-mail em texto puro), falha fechada (`503`) em produção quando Redis está indisponível e `_client_ip()` ignorando `X-Forwarded-For`, `X-Real-IP` e `Forwarded` salvo quando o peer pertence a `AUTH_TRUSTED_PROXIES` (vazio por padrão). Comprovado por `test_ip_rate_limit_cannot_be_bypassed_by_spoofed_forwarding_headers`.
- **Autorização multiusuário**: todas as 39 rotas de perfil e currículo em `profiles.py` e `resume_documents.py` exigem sessão ativa, `require_owned_profile` e `ProfileService` / `ResumeImportService` vinculados ao `user_id` autenticado, retornando `404` para recursos de terceiros ou perfis legados.

## 4. Limitações residuais e pendências para produção

A aplicação **não deve ser exposta diretamente à internet** sem atender aos requisitos operacionais abaixo:

1. **HTTPS / TLS e proxy reverso**: obrigatório em produção com `APP_ENV=production` (ativa `Secure` nos cookies e falha fechada no Redis) e `CORS_ORIGINS` restrito ao domínio real. Configurar `AUTH_TRUSTED_PROXIES` somente se houver proxy reverso confiável na frente do Uvicorn.
2. **Segredos externos e infraestrutura**: `DATABASE_URL`, `REDIS_URL` e demais credenciais gerenciados fora do repositório; Redis operacional com alta disponibilidade; banco com acesso restrito, backups e criptografia em repouso.
3. **Ciclo de vida de contas**: não há verificação de e-mail, recuperação de senha, cadastro público, MFA ou SSO nesta etapa.
4. **Limpeza de sessões**: `auth_sessions` não possui job periódico de expurgo de sessões expiradas/revogadas antigas (pendência operacional para evitar crescimento contínuo da tabela em produção).
5. **Proteção de dados pessoais**: textos extraídos em `resume_extractions` e arquivos em `storage/` requerem política de retenção, exclusão e criptografia compatível com LGPD/GDPR antes de operação pública.
6. **Observabilidade**: adicionar monitoramento e alertas para picos de `401`, `403`, `429` e `503` em `/api/v1/auth/*`.
