# Auditoria de segurança — Account Lifecycle & Security v1.0, Fase 1

**Data:** 27/11/2026
**Alvo inicial:** PR #5, commit `df6360ffaf65f432624fe4acff76bce9e2e72c78`
**Branch de trabalho:** `feat/account-lifecycle-security`

## 1. Escopo e modelo de ameaças

Revisão independente das alterações do PR #5: contas novas/legadas, cadastro e enumeração, sessões, tokens, criptografia AES-256-GCM da Outbox, leases e Celery, SMTP, rate limiting, frontend, migrações e integrações com os módulos anteriores.

Foram considerados atacantes remotos sem acesso autenticado, abuso de credenciais/token, chamadas concorrentes, leitura isolada de banco ou Redis, worker atrasado/duplicado, rede SMTP hostil, scanner automático de links e falha de infraestrutura. Não se presumiu acesso de escrita ao banco nem comprometimento do host.

## 2. Metodologia e ambiente

- Diff completo `origin/main...HEAD`, histórico e estado do Git; inspeção de implementações e testes.
- Reprodução/regressões com PostgreSQL via conexões independentes e suíte local.
- Testes restritos a `vaganexo_test` e `vaganexo_migration_test`; `current_database()` conferido antes dos testes destrutivos.
- Ruff, formatter, Mypy, pytest e validações do frontend.
- CI pré-auditoria consultado pelo conector GitHub; o CLI `gh` foi impedido por credencial local inválida e proxy inacessível.
- Nenhum envio real de e-mail. Nenhum conteúdo de `.env` ou credenciais foi exibido.

## 3. Achados

| ID | Severidade | Componente | Resultado |
|---|---|---|---|
| SEC-01 | HIGH | `SMTPEmailProvider` | STARTTLS sem contexto explícito usava `ssl._create_stdlib_context()` no Python local, cujo `verify_mode` é `CERT_NONE`; certificado do relay não era validado. Corrigido com `ssl.create_default_context()` também para SMTP_SSL e teste que exige `CERT_REQUIRED`/hostname. |
| SEC-02 | MEDIUM | `OutboxCrypto` | Chave de fallback estática previsível cifrava payloads em desenvolvimento quando configuração estava vazia. Leitura do banco mais chave pública do código permitiria recuperar tokens ainda válidos. Removido o fallback; ausência/formato/tamanho inválido falham fechados. Testes cobrem configuração e adulteração AEAD. |
| SEC-03 | MEDIUM | Claim da Outbox | Worker A podia terminar após expiração e substituir estado escrito pelo worker B; o estado era gravado por ORM sem validar ownership da lease. Reproduzido com claims independentes; corrigido com coluna `claim_token` e UPDATE condicionado por estado/claim. Regressão concorrente e lease expirada adicionadas. |
| SEC-04 | MEDIUM | Emissão e consumo de tokens | Reenvios simultâneos não serializavam por usuário; verificar consumia token sem lock de conta coordenado com reenvio/suspensão. Corrigido com ordem de lock `User → AccountActionToken`, relendo status e mantendo UPDATE condicional atômico. Teste PostgreSQL com duas transações prova um único consumo. |
| SEC-05 | MEDIUM | Mensagens antigas da Outbox | Mensagem já revogada/expirada/consumida ainda podia enviar link sem validade. Corrigido: worker valida conta pendente e token ativo sob lock; mensagem obsoleta vai a FAILED e o payload cifrado é limpo. Teste verifica zero mensagens enviadas. |
| SEC-06 | LOW | Guardas de testes | Sufixo `*_test` aceitava databases não autorizados; o teste geral também poderia usar `vaganexo_migration_test` por override. Corrigido com allowlist exata, limite do fixture geral a `vaganexo_test`, verificação efetiva de `current_database()` e checagem prévia no teste Alembic. |

Não houve achado CRITICAL. Nenhum achado HIGH ou MEDIUM permanece sem correção no código auditado.

## 4. Avaliação dos controles

### 4.1 Ciclo de vida e autorização

`status` e `is_active` têm constraint de consistência. Login, restauração de sessão e dependências verificam status ativo e `is_active`. Cadastro público começa pendente/inativo, não cria sessão e não aceita status ou `email_verified_at` do cliente. Migração mantém contas previamente ativas/inativas sem inventar verificação do e-mail. CLI de provisionamento permanece funcional.

### 4.2 Cadastro e enumeração

Cadastro responde `202` genérico para e-mails ativos/ausentes/duplicados. Duplicidade concorrente é tratada após violação única, com rollback e sem detalhe SQL. Cadastro pendente pode provocar emissão/reenvio; embora corpo/status permaneçam genéricos, tempo e efeito de e-mail podem diferir por estado. Rate limit reduz abuso, mas não há prova de equivalência temporal completa.

### 4.3 Tokens

Tokens são gerados com `secrets.token_urlsafe(32)`, armazenados como SHA-256, purpose-scoped, expirados, revogáveis e consumidos por UPDATE condicional/RETURNING na mesma transação da ativação. Duas sessões PostgreSQL concorrentes confirmaram uma única conclusão bem-sucedida. A trava de conta impede que verificação reative suspensão/desativação e estabelece ordem consistente contra reenvio.

### 4.4 Criptografia e Outbox

AES-256-GCM usa nonce aleatório de 96 bits, tag autenticada, AAD com ID/template e key version. Testes verificam ciphertext/nonce/AAD/chave/versão incorretos. `EMAIL_OUTBOX_ENCRYPTION_KEYS` agora é obrigatória e não existe default de chave. Payload é apagado após sucesso, falha terminal ou descarte obsoleto.

`FOR UPDATE SKIP LOCKED` evita reivindicação simultânea normal. A lease carrega token de fencing; worker velho não pode atualizar a linha depois de nova claim. Há teste real de dois workers paralelos e de lease expirada. Não existe entrega SMTP exatamente uma vez: timeout posterior à aceitação pode duplicar e-mail, mas não cria token novo nem torna token consumido reutilizável.

### 4.5 SMTP, links e scanners

Em produção, Fake provider é recusado e TLS/SSL é obrigatório. Contexto SSL verifica CA e hostname; configuração TLS+SSL simultânea é rejeitada. Mensagem usa valores do servidor e domínio de `APP_PUBLIC_BASE_URL`, sem depender de Host/X-Forwarded-Host/Origin/Referer. Link usa fragmento; `GET` não consome token; página remove fragmento do histórico e exige clique explícito; layout define `Referrer-Policy: no-referrer`. Nenhum SMTP real foi contatado.

### 4.6 Rate limiting e proxies

Redis usa Lua para `INCR`+TTL, chaves derivadas e fail-closed em produção. Testes cobrem falha Redis, limites e forwarding forjado quando não há proxy confiável configurado. O `general_auth` de 60/IP/minuto impõe teto por fonte, mas até 60 requisições concorrentes podem atravessar o pré-check antes da verificação Argon2; várias fontes podem distribuir carga. É risco residual de disponibilidade/configuração a calibrar com proxy/WAF e métricas reais.

### 4.7 Frontend

CSRF fica em memória, cookies seguem `credentials: include`, token de confirmação é capturado de fragmento e removido da barra/histórico. API não consome tokens em GET. Não há testes E2E/browser no frontend; foram executados ESLint, typegen, TypeScript e build.

### 4.8 Migrações e módulos anteriores

Cadeia auditada: `bdd3fb3a0174 → c8d9e0f1a2b3 → d1e2f3a4b5c6 → e2f3a4b5c6d7 → f3a4b5c6d7e8`. Migração de lifecycle preserva perfis/sessões e mapeia ativos/inativos. Novo downgrade remove claim token; downgrade total do lifecycle remove dados específicos da feature e deixa contas pendentes como inativas no schema antigo, sem autorizá-las.

Suíte completa inclui regressões de Profile Engine, Resume Importer, sessões, CSRF/Origin, CLI e isolamento multiusuário. CI Windows mantém cobertura de filesystem/junction; CI Linux valida dir_fd/TOCTOU POSIX.

## 5. Dependências, infraestrutura e limitações

- Dependências Python estão travadas em `uv.lock` e frontend em `package-lock.json`; compatibilidade atual verificada no Python 3.13/Windows e Linux via CI.
- Auditoria CVE dedicada não foi concluída: `uv audit --locked --no-cache` resolveu 132 pacotes, mas não conseguiu acessar o serviço OSV por falha de rede/proxy; as tentativas foram interrompidas. Vulnerabilidades conhecidas não são declaradas ausentes.
- Mailpit expõe apenas portas loopback no Compose local. PostgreSQL/Redis e volume nomeado permanecem sem alteração. Celery worker e Beat são executáveis separados, não serviços de aplicação incluídos no Compose.
- SMTP, queda de Redis real sob carga e teste funcional com browser permanecem sem validação end-to-end.

## 6. Riscos residuais e recomendações

1. Executar scanner de dependências (Python e npm) em ambiente com acesso ao advisory database e registrar resultado no CI.
2. Adicionar E2E/browser para cadastro → mensagem fake → clique explícito → login, incluindo expirado e reutilizado.
3. Calibrar limite geral de autenticação com métricas; considerar admissão de concorrência por IP/serviço em produção.
4. Garantir operação monitorada de worker/Beat, rotação/backup das chaves versionadas e alertas para mensagens FAILED.
5. Considerar volume e retenção da Outbox/token table, incluindo limpeza periódica em fase futura.

## 7. Avaliação

**Sem CRITICAL/HIGH pendente.** Os defeitos comprovados MEDIUM foram corrigidos e os testes correspondentes passaram em PostgreSQL real de teste. A avaliação é **READY WITH DOCUMENTED LIMITATIONS**, condicionada ao CI do head final após push e à revisão humana. A decisão de merge pertence ao usuário; nenhum merge foi executado.
