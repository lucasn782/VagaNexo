# PR #5 — Relatório de validação técnica

**Data:** 27/11/2026
**Branch:** `feat/account-lifecycle-security`
**Base:** `main` (`0076d069e5365cb631a2e51171dfe72bb971f1c0`)
**Head auditado inicialmente:** `df6360ffaf65f432624fe4acff76bce9e2e72c78`
**Merge:** não executado.

## 1. Resumo executivo

A revisão independente confirmou defeitos em fencing da Outbox, concorrência de emissão/consumo de tokens, descarte de mensagens obsoletas, configuração de chave AEAD e validação de certificados SMTP. As causas foram corrigidas nesta branch e cobertas por testes, incluindo transações PostgreSQL independentes. Os guardas de testes agora permitem somente `vaganexo_test` e `vaganexo_migration_test` e conferem `current_database()` antes de migração/truncamento.

Backend, migrações, frontend, lint, tipos e build local passaram. A suíte local terminou com **141 passed, 1 skipped e 85% de cobertura**. O CI verde consultado pertence ao head antigo `df6360f`; a execução do head final ainda precisa ser confirmada após o push. O PR #5 não foi integrado.

**Conclusão provisória:** pronto com limitações documentadas, sujeita ao CI do head final e à revisão humana.

## 2. Estado inicial e GitHub

| Item | Estado verificado |
|---|---|
| PR | [#5](https://github.com/lucasn782/VagaNexo/pull/5), aberto, não draft, não merged |
| Base/head | `main` ← `feat/account-lifecycle-security` |
| SHA base/head | `0076d069e5365cb631a2e51171dfe72bb971f1c0` / `df6360ffaf65f432624fe4acff76bce9e2e72c78` |
| Mergeability | `mergeable=true` |
| Reviews | Nenhuma revisão submetida |
| Diff original | 39 arquivos; +2743 / −71; `git diff --check` limpo |
| CI inicial | [Run 46063943921](https://github.com/lucasn782/VagaNexo/actions/runs/46063943921), 3/3 jobs aprovados |

O `gh auth status` foi tentado como solicitado, mas o CLI reportou a credencial local inválida e o proxy de rede recusou a conexão com `api.github.com`. Metadados, reviews, jobs e logs do PR foram conferidos pelo conector GitHub.

O único skip Linux do run inicial é `test_windows_real_junction_rejection_without_simulation`, condicionado por `os.name != "nt"`. O job Windows inclui o mesmo arquivo e executou a verificação real de junction; seu único skip foi o teste POSIX `test_toctou_real_posix_pinned_descriptor_survives_rename`, condicionado à disponibilidade de `dir_fd` POSIX. A execução Linux separada desse teste terminou aprovada.

## 3. Diff e arquivos

A revisão cobriu os 39 arquivos do PR contra `origin/main`: ciclo de vida, modelos, migrações, rotas, rate limiter, criptografia/outbox, Celery, configuração, frontend, infraestrutura, testes e documentação. A revisão adicional nesta branch adiciona uma migração de fencing, testes e relatórios. `git diff --check` foi verificado após as alterações.

Não foram encontrados segredos reais nos arquivos adicionados/revisados. A verificação foi revisão do diff; não havia scanner dedicado de segredos instalado/validado.

## 4. Testes locais

| Verificação | Resultado |
|---|---|
| Banco real antes dos testes | `current_database() = vaganexo_test` |
| Backend pytest | **141 passed, 1 skipped** |
| Cobertura backend | **85%** |
| Skip local | Teste POSIX de descriptor pinning, `skipif(not _SUPPORTS_POSIX_PINNING)` no Windows |
| Ruff lint | PASS |
| Ruff format check | PASS — 102 arquivos formatados |
| Mypy | PASS — 80 módulos |
| Migrações | PASS no teste de integração; upgrade, downgrade e re-upgrade em `vaganexo_migration_test` |
| ESLint | PASS |
| Next.js typegen | PASS |
| TypeScript | PASS |
| Build frontend | PASS — rotas `/`, `/login`, `/register`, `/verification-sent`, `/verify-email` |

Os testes de concorrência usam conexões PostgreSQL independentes: duas transações consumindo um token, dois workers reivindicando uma mensagem, e a recuperação de uma lease expirada. A migração existente preserva usuário ativo/inativo legado, perfil e sessão através do ciclo de upgrade/downgrade/re-upgrade.

## 5. Correções feitas

- Tokens: locks ordenados por usuário antes de token em emissão, reenvio e consumo. A verificação relê o estado atual do usuário sob lock; não ativa contas suspensas/desativadas.
- Outbox: novo `claim_token` aleatório por lease; atualizações condicionais impedem workers antigos de sobrescrever a aquisição atual. Mensagens revogadas, expiradas, consumidas ou sem conta pendente são encerradas e têm payload cifrado apagado.
- Criptografia: removida a chave estática de desenvolvimento. Configuração ausente ou inválida agora falha em todos os ambientes; `.env.example` documenta geração de chave própria.
- SMTP: STARTTLS e SMTP_SSL usam contexto padrão com validação de CA e hostname; combinação simultânea de SSL e STARTTLS é rejeitada.
- Banco de testes: removido o aceite amplo de qualquer nome `*_test`; allowlist exata, guardas antes de `TRUNCATE`/Alembic e confirmação de `current_database()`.

## 6. Regressões e limitações

- Testes backend existentes para Profile Engine, Resume Importer, ownership, sessões, CSRF, Origin e CLI passaram na suíte completa.
- Frontend não possui script nem framework de testes E2E no `package.json`; não houve navegação de browser automatizada para o fluxo completo. API lifecycle é coberta por integração, e o frontend passou lint/typecheck/build.
- SMTP real não foi usado e nenhum e-mail real foi enviado. Testes verificam contextos/caminho TLS por mocks e a Outbox por provedor fake.
- `uv audit` resolveu 132 pacotes com `--no-cache`, mas o serviço OSV ficou inacessível no ambiente de rede/proxy e as tentativas foram interrompidas; sem scanner de vulnerabilidades de dependências concluído. Não se declara ausência de CVEs.
- Redis indisponível em produção falha fechado conforme código e testes existentes; não foi executado cenário com Redis real caindo durante carga.
- O limite geral é 60 requisições/IP/minuto e limita a admissão por IP, mas requisições concorrentes podem passar o pré-check antes do Argon2 até esse teto. Mitigação global distribuída e calibração sob carga permanecem recomendadas.
- A semântica do SMTP é pelo menos uma tentativa, não exatamente uma entrega: timeout após aceitação pode causar duplicação da mesma mensagem/token; token permanece de uso único.
- Worker e Beat precisam ser implantados como processos separados; Compose local não define containers de aplicação para eles.

## 7. Banco, arquivos locais e PR4

Antes da suíte, a conexão real apontou para `vaganexo_test`. O teste de migração checa a URL alvo exata `vaganexo_migration_test`, conecta e compara `current_database()` antes de aplicar migrações; as funções de DROP recusam qualquer outro nome. O banco `vaganexo` não foi conectado, migrado, truncado ou removido. Nenhum volume foi removido.

`docs/development/PR4_MERGE_REPORT.md` continua não rastreado e fora do diff. SHA-256 esperado, inicial e ao final da auditoria: `2B6AA1AFDBCDB75B5E6F9EE6C3616325CF93BA2D15DCD16D582698CC2537EB91`.

## 8. Estado final e recomendação

Os novos commits, push e execução do CI para o head final são **PENDING** até a publicação e verificação da branch. Nenhum merge será executado nesta tarefa.

**READY WITH DOCUMENTED LIMITATIONS**, condicionado a CI 3/3 verde para o head publicado e revisão humana. Não há achado crítico ou alto pendente. A recomendação segue sujeita à limitação de auditoria automatizada de dependências e à ausência de E2E do frontend, explicitadas acima.
