# Relatório de Validação Técnica — PR #4

## 1. Resumo executivo

O PR #4 (`feat/auth-multitenancy` → `main`) foi validado de forma independente em 27/11/2026. A execução de CI informada (`46048253674`) já estava concluída com **3/3 jobs aprovados** para o commit `c3543a5`.

A auditoria de código encontrou **um defeito real de integração** entre backend e frontend no fluxo de renovação de CSRF: o frontend só repetia a requisição quando o detalhe do erro era `"CSRF validation failed"`, mas o backend respondia `"invalid or missing CSRF token"`. A retentativa documentada em `SECURITY_AUDIT.md` nunca era acionada. A correção mínima foi aplicada, um teste de contrato foi adicionado e o commit `10054ee` foi enviado sem force push.

Após a correção:

- O PR #4 permanece **aberto**, com base `main` e head `feat/auth-multitenancy`.
- O novo commit `10054ee` foi validado pelo CI **3/3 jobs aprovados** (execução `46049820066`).
- A suíte local passou com **127 testes aprovados, 1 ignorado** e **85% de cobertura**.
- Ruff, formatação, Mypy, ESLint, typegen, TypeScript, build de produção e migrações passaram.
- O isolamento multiusuário e os controles de CSRF/Origin/rate limiting foram verificados.
- Nenhum merge, squash, rebase, force push, reset destrutivo ou exclusão de branch foi executado.
- O banco `vaganexo` não foi usado em testes ou migrações.

**Avaliação:** tecnicamente pronto para revisão e possível merge, condicionado apenas à revisão humana. O commit que adiciona este relatório é exclusivamente documental e não altera código executável.

---

## 2. Identificação do PR, branches e commits

| Item | Valor |
|---|---|
| Repositório | `lucasn782/VagaNexo` |
| PR | [#4](https://github.com/lucasn782/VagaNexo/pull/4) |
| Título | `feat: add multi-user authentication and profile ownership` |
| Estado | `open` |
| Base | `main` |
| Head | `feat/auth-multitenancy` |
| SHA base | `1f167d783e2ad6f65973e114cd24356b6a630e54` |
| SHA original do head | `c3543a5db872c49968ad95ab1536c1ba621d3b94` |
| SHA validado após correção | `10054ee8d4099eeb1a1d4a1fa16e37a512336277` |
| Commits à frente da `main` | 4 (commit de código validado `10054ee`) |
| Arquivos alterados (commit `10054ee`) | 41 |
| Linhas (commit `10054ee`) | `+3344 / -105` |
| Mergeable | `true` |
| Mergeable state | `clean` |
| Merge executado | Não |

Commits do PR:

1. `e26eaeb` — `feat: add multi-user authentication and profile ownership`
2. `75c48ef` — `fix: harden auth origin, service fail-closed checks, and add CI`
3. `c3543a5` — `fix: ensure Linux POSIX storage tests and Next.js typegen run cleanly in CI`
4. `10054ee` — `fix: align CSRF retry contract between backend and frontend`

O commit deste relatório é um commit documental subsequente, sem alteração de código executável; o SHA final do head é o exibido no PR.

---

## 3. Situação dos três jobs do GitHub Actions

### Execução validada após a correção

- **Run:** [46049820066](https://github.com/lucasn782/VagaNexo/actions/runs/46049820066)
- **Evento:** `pull_request`
- **SHA:** `10054ee8d4099eeb1a1d4a1fa16e37a512336277`
- **Status:** `completed`
- **Conclusão:** `success`

| Job | Conclusão | Início | Fim | Etapas relevantes |
|---|---|---|---|---|
| Backend (Linux / PostgreSQL 17 + Redis 7) | **PASS** | 18:29:15Z | 18:30:20Z | Containers, POSIX `dir_fd` + TOCTOU, suíte completa com cobertura, Ruff lint, Ruff format, Mypy — todas aprovadas |
| Backend Filesystem & Unit Checks (Windows) | **PASS** | 18:29:15Z | 18:29:56Z | Testes de filesystem, parsers, validador, normalizador, schemas e health — aprovados |
| Frontend (Next.js / TypeScript / ESLint) | **PASS** | 18:29:15Z | 18:29:45Z | ESLint, `next typegen`, `tsc --noEmit`, build de produção — aprovados |

Nenhuma etapa falhou. Não houve falha externa de serviço.

### Execução anterior informada

- **Run:** [46048253674](https://github.com/lucasn782/VagaNexo/actions/runs/46048253674)
- **SHA:** `c3543a5db872c49968ad95ab1536c1ba621d3b94`
- **Conclusão:** `success` — 3/3 jobs aprovados.

Essa execução permanece como evidência histórica do commit original. A aprovação final do head corrigido é a execução `46049820066`.

---

## 4. Resultados das validações locais

### Backend

| Verificação | Comando | Resultado |
|---|---|---|
| Suíte completa | `python -m pytest` | **127 passed, 1 skipped**, cobertura **85%** |
| Ruff lint | `python -m ruff check .` | **PASS** — `All checks passed!` |
| Ruff format | `python -m ruff format --check .` | **PASS** — `96 files already formatted` |
| Mypy | `python -m mypy app` | **PASS** — `Success: no issues found in 73 source files` |
| Migração de autenticação | `pytest tests/integration/test_auth_migrations.py -v` | **PASS** — 1 teste aprovado |
| Cadeia Alembic | `alembic heads` / `alembic history` | **PASS** — head única `d1e2f3a4b5c6` |

O teste ignorado é o teste POSIX real de `dir_fd`, executado apenas no job Linux do CI. No CI Linux ele foi aprovado.

### Frontend

| Verificação | Comando | Resultado |
|---|---|---|
| ESLint | `npm run lint` | **PASS** |
| Typegen Next.js | `npx next typegen` | **PASS** — tipos gerados |
| TypeScript | `npx tsc --noEmit` | **PASS** |
| Build de produção | `npm run build` | **PASS** — rotas `/`, `/_not-found` e `/login` |

### Infraestrutura e bancos

| Item | Resultado |
|---|---|
| `vaganexo-postgres` | `healthy`, `127.0.0.1:5433` |
| `vaganexo-redis` | `healthy`, `127.0.0.1:6379`, `PONG` |
| Banco de testes | `vaganexo_test` |
| Banco descartável de migração | `vaganexo_migration_test` |
| Banco principal `vaganexo` | **Não utilizado** em testes ou migrações |
| `docker compose down -v` | Não executado |
| Volumes Docker | Preservados |

---

## 5. Resultado da auditoria de segurança

### Autenticação e credenciais — PASS

- Argon2id via `argon2-cffi`; hash verificado com `$argon2id$`.
- Comparação de senha com `PasswordHasher.verify`.
- `dummy_verify_password()` executado quando a conta não existe.
- Mensagem genérica `invalid email or password` para senha errada, conta inexistente e conta inativa.
- Rehash automático com `check_needs_rehash` no login bem-sucedido.
- E-mail normalizado com `strip().casefold()` e restrição de unicidade no PostgreSQL.
- `user_id` enviado pelo cliente é rejeitado por `extra="forbid"` (`422`).

### Sessões — PASS

- Tokens opacos de 256 bits (`secrets.token_urlsafe(32)`).
- Apenas hashes SHA-256 de sessão e CSRF persistidos.
- Expiração absoluta e revogação via `revoked_at`.
- Cookie `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure` em produção.
- Logout revoga a sessão e o token deixa de funcionar (`401`).
- Nenhum token de autenticação é persistido em `localStorage` ou `sessionStorage`.

### Isolamento multiusuário — PASS

- `require_owned_profile` exige `CandidateProfile.user_id == current_user.id`.
- Perfis de terceiros e perfis legados com `user_id IS NULL` retornam `404`.
- `ProfileService` exige `uuid.UUID` no construtor e aplica filtro por proprietário.
- `ResumeImportService` delega ao `ProfileService` vinculado ao usuário autenticado.
- Rotas de upload, leitura, atualização e exclusão de currículo validam propriedade.
- Matriz de rotas coberta por `test_profile_ownership.py` (anônimo `401`, cruzado `404`).
- `claim_profile` usa `UPDATE ... WHERE user_id IS NULL RETURNING id` atômico.

### CSRF e Origin — PASS

- Mutações exigem `X-CSRF-Token` validado com `hmac.compare_digest`.
- `Origin` é validado contra `CORS_ORIGINS`.
- `Referer` é validado quando `Origin` está ausente.
- `Origin` ausente, vazio, `null` ou malformado é rejeitado.
- Em produção, ausência de `Origin` e `Referer` falha fechada (`403`).
- `GET /api/v1/auth/csrf` valida origem antes de rotacionar o token.
- Tokens CSRF permanecem apenas em memória no frontend.

### Rate limiting — PASS

- Redis com script Lua atômico (`INCR` + `EXPIRE`).
- Limite por IP e por conta normalizada.
- Chaves derivadas por SHA-256, sem e-mail em texto puro.
- Cabeçalhos de encaminhamento só são considerados quando o peer pertence a `AUTH_TRUSTED_PROXIES` (vazio por padrão).
- Produção falha fechada (`503`) se o Redis estiver indisponível; desenvolvimento usa fallback local.

### Migrações — PASS

Cadeia verificada:

```text
bdd3fb3a0174
    ↓
c8d9e0f1a2b3
    ↓
d1e2f3a4b5c6 (head)
```

O teste `test_auth_migration_preserves_legacy_profiles_and_downgrades_cleanly` comprovou:

- upgrade até `c8d9e0f1a2b3`;
- inserção de perfil legado;
- upgrade até `d1e2f3a4b5c6`;
- preservação do perfil com `user_id = NULL`;
- criação de usuário, claim e sessão;
- downgrade até `c8d9e0f1a2b3` sem perda do perfil;
- re-upgrade até `head`.

Não há associação automática de perfis por e-mail encontrado em currículo.

### Frontend — PASS

- Sessão restaurada via `GET /api/v1/auth/me`.
- Login, logout e tratamento de sessão expirada.
- Redirecionamento para `/login` quando não autenticado.
- `credentials: "include"` em todas as chamadas.
- CSRF apenas em memória.
- Erros da API não expõem stack trace, hash ou token.
- Build de produção aprovado.

---

## 6. Problemas encontrados

### Defeito 1 — Contrato de retentativa CSRF divergente (corrigido)

**Severidade:** média (funcional/segurança operacional).

**Evidência:**

- `frontend/src/lib/api.ts` repetia a requisição apenas quando `detail === "CSRF validation failed"`.
- `backend/app/auth/exceptions.py` respondia `detail = "invalid or missing CSRF token"`.
- `docs/development/SECURITY_AUDIT.md` documentava a retentativa usando o texto esperado pelo frontend.

**Impacto:** quando outra aba ou requisição concorrente rotacionava o token CSRF, a requisição recebia `403` e a retentativa automática nunca acontecia. O usuário precisava recarregar a página para voltar a mutar dados.

**Causa raiz:** divergência entre o contrato de erro do backend e a condição implementada no frontend.

### Defeito 2 — Deduplicação CSRF anulada ao limpar o token (corrigido)

**Severidade:** baixa (condição de corrida).

**Evidência:** `clearInMemoryCsrfToken()` também definia `inFlightCsrfPromise = null`. Com duas requisições concorrentes recebendo `403`, cada uma podia iniciar uma nova chamada a `/csrf`, rotacionando o token e invalidando a outra.

**Correção:** a limpeza agora remove apenas o token em memória e preserva a promessa em andamento, mantendo a deduplicação documentada.

Nenhuma falha crítica ou alta foi encontrada. Nenhum controle de segurança foi enfraquecido para fazer testes passarem.

---

## 7. Correções implementadas

| Arquivo | Alteração |
|---|---|
| `backend/app/auth/exceptions.py` | `CSRFError.detail` alterado para `"CSRF validation failed"`, com comentário de sincronização com o frontend |
| `frontend/src/lib/api.ts` | `clearInMemoryCsrfToken()` não descarta mais a promessa de CSRF em andamento |
| `backend/tests/integration/test_auth_api.py` | Teste de contrato verifica o detalhe exato `"CSRF validation failed"` em requisições sem CSRF e com CSRF inválido |
| `docs/development/PR4_VALIDATION_REPORT.md` | Este relatório |

Não houve alteração cosmética sem necessidade, redução de cobertura, desabilitação de verificação, `skip`/`xfail` para ocultar falha ou enfraquecimento de controle de segurança.

---

## 8. Arquivos alterados nesta validação

```text
backend/app/auth/exceptions.py
backend/tests/integration/test_auth_api.py
frontend/src/lib/api.ts
docs/development/PR4_VALIDATION_REPORT.md
```

O diff total do PR continua restrito a autenticação, autorização, propriedade de perfis, integração com Profile Engine/Resume Importer, testes, documentação e CI.

---

## 9. Commits criados

| SHA | Mensagem | Escopo |
|---|---|---|
| `10054ee` | `fix: align CSRF retry contract between backend and frontend` | 3 arquivos de código/teste; 9 inserções, 3 remoções |
| commit documental subsequente | Adiciona este relatório | Apenas documentação |

O push foi normal para `origin/feat/auth-multitenancy`, sem force push. O PR #4 recebeu o commit e disparou nova execução de CI.

---

## 10. Pendências e limitações

1. **Revisão humana:** o merge continua reservado ao usuário; nenhum merge foi executado.
2. **Limitações de produto já documentadas:** sem verificação de e-mail, recuperação de senha, cadastro público, MFA ou SSO.
3. **Expurgo de sessões:** não há job periódico para remover sessões expiradas/revogadas antigas.
4. **Rate limiting:** tentativas bem-sucedidas também incrementam o contador; após o limite na janela, um login legítimo pode receber `429`. Não é falha de segurança, mas é um ajuste futuro recomendável.
5. **Produção:** exige TLS, `CORS_ORIGINS` restrito, Redis operacional, segredos externos, política de retenção e monitoramento.
6. **Commit documental:** não altera código executável; a execução de CI correspondente é registrada no PR.

---

## 11. Avaliação final de prontidão para merge

| Critério | Estado |
|---|---|
| PR #4 aberto e direcionado à `main` | **PASS** |
| Head corresponde à branch `feat/auth-multitenancy` | **PASS** |
| Commit original `c3543a5` preservado no histórico | **PASS** |
| Commit corretivo `10054ee` enviado sem force push | **PASS** |
| Diff restrito ao escopo de autenticação/CI | **PASS** |
| Sem conflitos com `main` (`mergeable_state = clean`) | **PASS** |
| CI Backend Linux | **PASS** |
| CI Backend Windows | **PASS** |
| CI Frontend | **PASS** |
| Suíte backend local | **PASS** — 127 passed, 1 skipped |
| Cobertura backend | **PASS** — 85% |
| Ruff lint/format | **PASS** |
| Mypy | **PASS** |
| Migração upgrade/downgrade/re-upgrade | **PASS** |
| Isolamento multiusuário | **PASS** |
| CSRF/Origin e contrato de retentativa | **PASS** |
| Rate limiting | **PASS** |
| Frontend lint/typegen/tsc/build | **PASS** |
| Working tree limpo após commits | **PASS** |
| PR #2 e PR #3 preservados | **PASS** |
| Merge executado | **NOT APPLICABLE** — reservado ao usuário |
| Banco principal `vaganexo` utilizado | **NOT APPLICABLE** — não acessado |

**Conclusão:** o PR #4 está tecnicamente validado, com a correção comprovada e CI 3/3 aprovado para o commit de código `10054ee`. Permanece aberto e sem merge, pronto para revisão e decisão de integração pelo usuário.
