# Account Lifecycle & Security — Phase 1 Report

**Status:** implementation is prepared for review; local checks passed on 2026-11-27. CI and the pull request are pending publication of the branch.

## 1. Executive summary

Phase 1 adds configurable public registration, email verification, purpose-scoped single-use tokens, an encrypted transactional email outbox, SMTP/Mailpit and fake providers, and granular rate limiting. Existing administrator-provisioned users remain active after migration and are not falsely marked as email-verified. Pending users receive no authenticated session before verification.

## 2. Implemented architecture

- `User.status` is the canonical lifecycle state; `is_active` remains for compatibility and a database check constraint prevents disagreement.
- Legacy `is_active=true/false` rows migrate to `active/disabled`; `email_verified_at` remains `NULL` for all legacy rows.
- Only `email_verification` tokens are used in this phase. Raw tokens are generated with 256 bits of entropy, stored as SHA-256 hashes, and consumed with one conditional `UPDATE ... RETURNING` operation.
- Registration writes the user, token, and AES-256-GCM encrypted outbox payload in the same PostgreSQL transaction. Celery dispatch happens after commit; a scheduled sweeper reclaims pending or lease-expired messages.
- Verification links use a URL fragment, so the token is not sent in the browser's GET request or in frontend access logs. The page removes it from the address bar and sends it only after a user click.

## 3. User model and migration

Added `status` and `email_verified_at`. The migration is `e2f3a4b5c6d7`, directly after `d1e2f3a4b5c6`. It creates `account_action_tokens` and `email_outbox`; it does not drop or rewrite users, profiles, or sessions on upgrade. Downgrade of this revision removes only the new tables and columns.

`password_changed_at` was not added because password change/reset is excluded from this phase. Existing active accounts continue to authenticate while `email_verified_at` is null.

## 4. Tokens and email outbox

`AccountActionToken` supports future purposes structurally; only email verification is used. Old active tokens for the same user and purpose are revoked when a replacement is issued. Tokens expire after the configured `EMAIL_VERIFICATION_TTL_HOURS` (24 hours by default).

`EmailOutbox` stores only encrypted temporary payloads, with key versions and AES-GCM associated data bound to the outbox ID and template. Successful delivery or terminal retry failure clears the encrypted payload. Claiming uses `FOR UPDATE SKIP LOCKED`, a lease, bounded retries, and backoff.

`EmailProvider` has `FakeEmailProvider` and `SMTPEmailProvider`. The development Compose stack supplies Mailpit at `127.0.0.1:1025` (SMTP) and `127.0.0.1:8025` (web UI). Set `MAIL_PROVIDER=smtp` for Mailpit; the checked-in backend environment example uses this local-only, unauthenticated configuration. Production rejects the fake provider and requires TLS or SSL for SMTP.

## 5. Celery

The task `app.workers.email_tasks.deliver_outbox_email` handles a dispatched message. `sweep_email_outbox` is scheduled every 60 seconds through Celery Beat and recovers dispatch failures and expired leases. Run the worker and Beat separately using the backend environment and commands `celery -A app.workers.celery_app.celery_app worker` and `celery -A app.workers.celery_app.celery_app beat`.

## 6. Endpoints and frontend

- `POST /api/v1/auth/register` returns a uniform `202`; public registration is controlled by `AUTH_PUBLIC_REGISTRATION_ENABLED`.
- `POST /api/v1/auth/verify-email` atomically consumes a valid token and activates the pending account.
- `POST /api/v1/auth/resend-verification` returns a uniform `202` for existing, missing, active, or disabled accounts.
- The frontend adds `/register`, `/verify-email`, and `/verification-sent`; it preserves the existing `AuthProvider`, API client, CSRF memory behavior, cookies, and credentials handling.

## 7. Rate limiting

- Login failures count only after invalid credentials; successful login clears the per-account/per-IP counter and does not add a failure.
- Redis keys contain truncated SHA-256 identifiers rather than raw emails or IP addresses.
- Default login failure limits: 5 for the same account/IP pair and 20 per IP per 5 minutes; the account-wide counter is capped at four times the account/IP threshold to limit third-party lockout abuse.
- Registration defaults to 5 requests/IP/hour; resend defaults to 3 requests/IP and account/15 minutes; general auth traffic defaults to 60 requests/IP/minute.
- Redis uses atomic `INCR`/`EXPIRE` Lua operations for counters and fails closed with `503` in production. The process-local fallback is limited to non-production. Forwarded client IP is considered only when the direct peer matches `AUTH_TRUSTED_PROXIES`.

## 8. Validation evidence

| Check | Result | Evidence |
|---|---|---|
| Backend lifecycle/API/auth tests | PASS (earlier worktree snapshot) | Lifecycle API, existing auth API, and auth service tests: 17 passed before the final email URL/test updates. |
| Full backend suite | PASS | GitHub Actions CI run 16: 130 passed, 1 skipped (14.49s). The run used disposable CI PostgreSQL/Redis services. |
| Ruff lint | PASS | `uv run ruff check app tests`. |
| Ruff format | PASS | `uv run ruff format --check app tests`. |
| Mypy | PASS | `uv run mypy app`: 80 source files, no issues. |
| Frontend ESLint | PASS | `npm run lint` after final frontend changes. |
| Next.js type generation | PASS | `npx next typegen` after final frontend changes. |
| TypeScript | PASS | `npx tsc --noEmit` after final frontend changes. |
| Production frontend build | PASS | `npm run build`; all six app routes generated after the fragment-based token change. |
| Isolated migration upgrade/downgrade/re-upgrade | PASS | Covered by the migration integration test in CI run 16, including existing profile ownership and session preservation. |
| CI | PASS | Run 16 completed all 3 jobs successfully: Linux backend, Windows backend, and frontend. |
| Pull request | PASS | [PR #5](https://github.com/lucasn782/VagaNexo/pull/5) is open against `main`; no automatic merge is enabled. |

## 9. Security audit summary

- **Enumeration:** registration and resend messages are generic; concurrent duplicate creation is handled without exposing database constraint details.
- **Brute force / DoS:** success no longer increments login failure counters; account limits combine account/IP with a bounded global account counter.
- **Replay:** token consumption is purpose-scoped, expiry-checked, atomic, and single-use.
- **Token leakage:** raw tokens are not persisted in token rows or logs; outbox payloads are encrypted and cleared after send/final failure; links place the token in a fragment.
- **CSRF / Origin:** new mutating routes use the existing strict Origin/Referer validation. They do not issue authenticated sessions.
- **Host header:** verification URLs are built from configured `APP_PUBLIC_BASE_URL` only.
- **SMTP secrets:** credentials are loaded from settings and SMTP exceptions are sanitized before outbox logging. Tests use a fake provider; no real email was sent.
- **Multiuser isolation:** existing session and ownership dependencies now require canonical active status; pending accounts cannot log in or restore authenticated sessions.

## 10. Files changed

Changes cover backend lifecycle models, migration, token and outbox services, email adapters and Celery tasks, auth routes/rate limiter/configuration, lifecycle API and migration tests, frontend registration/verification flows, Compose Mailpit, CI branch triggers, and this report. `PR4_MERGE_REPORT.md` remains untracked and is excluded from commits.

## 11. Commits and CI

The architecture document was committed as `docs: add account lifecycle architecture` (`6c1137349f6ee993c654a08eed1470b004cfca8c`). Implementation is committed as `feat: add account lifecycle and email verification` (`b42bd5c`), with the migration assertion correction in `016779e`. This report and the refined fragment-token decision are committed separately. CI run 16 passed all jobs. No merge is planned.

## 12. Limitations and Phase 2

- Password reset/change, session management, MFA, and SSO remain out of scope.
- The outbox uses a development fallback encryption key outside production; production must configure a versioned `EMAIL_OUTBOX_ENCRYPTION_KEYS` keyring and external SMTP credentials.
- Worker and Beat are launched as separate Celery processes; Compose provides the local Mailpit service but does not package the Python application into worker containers.
- Concurrent token consumption is atomic in PostgreSQL; an explicit two-request concurrency stress test remains to be added before claiming that acceptance criterion as tested.
- **Fase 2:** password recovery and change, session inventory/revocation, and session cleanup.
