# Relatório técnico — VagaNexo Profile Engine v1.0

## 1. Resumo

Objetivo: implementar a fundação funcional do **VagaNexo Profile Engine**, com estrutura de dados relacional, migração Alembic, schemas Pydantic, serviços de negócio, API REST e testes automatizados para o perfil profissional do candidato.

Data e horário: 25/11/2026, 22:33 −03:00, referente à última execução completa da bateria de validação.

Branch utilizada: `feat/profile-engine`, criada a partir de `main` no commit `dc422b1ad6e85b2a88b7ffdf58135d48dc62e633`.

Situação inicial verificada:

| Item | Valor |
| --- | --- |
| Working tree | Limpa |
| Branch | `main`, sincronizada com `origin/main` |
| Remoto | `https://github.com/lucasn782/VagaNexo.git` |
| Últimos commits | `dc422b1 docs: add Git checkpoint report`, `d04524d chore: initialize VagaNexo infrastructure` |
| PostgreSQL | Container `vaganexo-postgres`, porta `127.0.0.1:5433` |
| Tabelas no banco `vaganexo` | Nenhuma |
| `alembic_version` | Ausente |
| pgvector | `0.8.7` presente |
| Docker | Parado no início da sessão; iniciado sem alterar a configuração |

Nenhum arquivo `.env` foi modificado. Nenhuma credencial, senha ou token foi incluído em código, relatório ou documentação.

## 2. Arquitetura

### 2.1. Arquivos criados

Modelos:

- `backend/app/models/enums.py`
- `backend/app/models/mixins.py`
- `backend/app/models/candidate_profile.py`
- `backend/app/models/education.py`
- `backend/app/models/experience.py`
- `backend/app/models/skill.py`
- `backend/app/models/certification.py`
- `backend/app/models/language.py`
- `backend/app/models/project.py`
- `backend/app/models/preference.py`
- `backend/app/models/resume_document.py`

Schemas:

- `backend/app/schemas/common.py`
- `backend/app/schemas/profile.py`
- `backend/app/schemas/education.py`
- `backend/app/schemas/experience.py`
- `backend/app/schemas/skill.py`
- `backend/app/schemas/certification.py`
- `backend/app/schemas/language.py`
- `backend/app/schemas/project.py`
- `backend/app/schemas/preference.py`
- `backend/app/schemas/resume_document.py`

Serviço e persistência:

- `backend/app/profile/service.py`
- `backend/app/profile/validators.py`
- `backend/app/profile/exceptions.py`
- `backend/app/database/dependencies.py`
- `backend/app/api/routes/profiles.py`
- `backend/alembic/versions/bdd3fb3a0174_create_profile_engine_tables.py`

Testes:

- `backend/tests/conftest.py`
- `backend/tests/unit/test_profile_models.py`
- `backend/tests/unit/test_profile_schemas.py`
- `backend/tests/unit/test_profile_service.py`
- `backend/tests/integration/test_profile_api.py`

Documentação:

- `docs/architecture/PROFILE_ENGINE.md`
- `docs/development/PROFILE_ENGINE_REPORT.md` (este relatório)

### 2.2. Arquivos modificados

- `backend/app/main.py`: registro do roteador de perfis, CORS e handlers de erro.
- `backend/app/core/config.py`: lista `cors_origins` com os endereços locais do frontend.
- `backend/app/database/session.py`: engine central e `SessionLocal`.
- `backend/app/database/__init__.py`: reexports da camada de persistência.
- `backend/app/models/base.py`: convenção de nomes de constraints e índices.
- `backend/app/models/__init__.py`: importação de todos os modelos.
- `backend/app/schemas/__init__.py`: reexports dos schemas.
- `backend/alembic/env.py`: importação de `app.models` e `compare_type=True`.
- `README.md`: tabela de endpoints e referência à documentação do módulo.
- `docs/architecture/overview.md`: menção ao Profile Engine.

Arquivos existentes preservados: `health.py`, `core/logging.py`, `workers/celery_app.py`, `pyproject.toml`, `alembic.ini`, `uv.lock`, `infrastructure/compose.yaml` e todos os `.env`.

### 2.3. Estrutura dos módulos

```text
backend/app/
├── api/routes/profiles.py
├── core/config.py
├── database/
│   ├── __init__.py
│   ├── dependencies.py
│   └── session.py
├── models/          (9 tabelas + enums + mixins)
├── schemas/         (entrada, atualização e saída)
├── profile/
│   ├── exceptions.py
│   ├── service.py
│   └── validators.py
└── main.py
```

### 2.4. Responsabilidades

| Componente | Responsabilidade |
| --- | --- |
| Modelos SQLAlchemy | Estrutura relacional, FKs, constraints, índices e relacionamentos |
| Schemas Pydantic | Contrato de entrada/saída, validação de tipos, URLs, datas e faixas |
| `ProfileService` | Transações, escopo por perfil, conflitos e regras de proveniência |
| `validators.py` | Regras puras: normalização de competência, períodos, salários, CEFR |
| Rotas FastAPI | Contrato HTTP, status codes, `response_model` e injeção de sessão |
| `database/` | Engine Psycopg 3, `SessionLocal` e dependência `get_db` |
| `main.py` | Roteamento, CORS e tradução de erros de domínio/persistência |

A lógica de negócio não importa FastAPI. As rotas apenas chamam o serviço.

## 3. Banco de dados

### 3.1. Tabelas implementadas

1. `candidate_profiles`
2. `educations`
3. `work_experiences`
4. `skills`
5. `certifications`
6. `languages`
7. `projects`
8. `job_preferences`
9. `resume_documents`

Todas usam UUID como chave primária, timestamps com timezone e nomes determinísticos de constraints.

### 3.2. Campos principais

- `candidate_profiles`: `full_name`, `professional_headline`, `professional_summary`, `email`, `phone`, `city`, `state`, `country`, `linkedin_url`, `github_url`, `portfolio_url`, `created_at`, `updated_at`.
- `educations`: `institution`, `degree`, `field_of_study`, `start_date`, `end_date`, `is_current`, `description`.
- `work_experiences`: `company`, `job_title`, `employment_type`, `location`, `start_date`, `end_date`, `is_current`, `description`, `achievements` (JSONB).
- `skills`: `name`, `normalized_name`, `category`, `proficiency_level`, `years_experience`, `last_used`, `description`.
- `certifications`: `name`, `issuing_organization`, `issue_date`, `expiration_date`, `credential_id`, `credential_url`.
- `languages`: `language`, `proficiency_level`, `proficiency_framework`, `cefr_level`.
- `projects`: `name`, `description`, `role`, `project_url`, `start_date`, `end_date`, `technologies` (JSONB), `project_type`.
- `job_preferences`: listas JSONB de cargos, locais, modalidades e vínculos; faixa salarial; moeda; relocação; senioridade.
- `resume_documents`: `original_filename`, `media_type`, `file_size`, `sha256_hash`, `storage_key`, `parsing_status`, `uploaded_at`.

Os fatos profissionais também possuem `source_type`, `validation_status`, `source_document_id`, `confidence_score`, `created_at` e `updated_at`.

### 3.3. Relacionamentos

- 9 FKs de filhos para `candidate_profiles` com `ON DELETE CASCADE`.
- 6 FKs de fatos para `resume_documents` com `ON DELETE SET NULL`.
- `job_preferences.candidate_profile_id` é único (um para um).
- Total: 14 foreign keys.

### 3.4. Constraints

- 42 check constraints, incluindo:
  - `full_name` não vazio;
  - ordem de datas em formação, experiência, certificação e projeto;
  - `is_current` sem `end_date`;
  - faixa salarial e valores não negativos;
  - `confidence_score` entre 0 e 1;
  - `years_experience` entre 0 e 80;
  - `cefr_level` somente com framework `cefr`;
  - hash SHA-256 com 64 caracteres hexadecimais;
  - valores permitidos dos enums.
- 5 unique constraints:
  - `skills (candidate_profile_id, normalized_name)`;
  - `languages (candidate_profile_id, language)`;
  - `job_preferences (candidate_profile_id)`;
  - `resume_documents (storage_key)`;
  - `resume_documents (candidate_profile_id, sha256_hash)`.

### 3.5. Índices

31 índices no conjunto das tabelas do módulo, incluindo:

- `email` e `full_name` em `candidate_profiles`;
- `candidate_profile_id` em todas as tabelas filhas;
- `source_document_id` em todas as entidades com proveniência;
- `normalized_name` em `skills`.

### 3.6. Migrações

| Item | Valor |
| --- | --- |
| Arquivo | `backend/alembic/versions/bdd3fb3a0174_create_profile_engine_tables.py` |
| Revisão | `bdd3fb3a0174` |
| Revisão anterior | Nenhuma (`base`) |
| `upgrade` | Cria as 9 tabelas, FKs, checks, uniques e índices |
| `downgrade` | Remove somente índices e tabelas do Profile Engine |

Validações executadas:

```text
uv run alembic upgrade head   -> bdd3fb3a0174 aplicada no banco vaganexo
uv run alembic current        -> bdd3fb3a0174 (head)
uv run alembic history        -> <base> -> bdd3fb3a0174 (head)
```

O ciclo `upgrade → downgrade base → upgrade` também foi executado com sucesso no banco isolado `vaganexo_test`. Nenhum `DROP DATABASE`, `DROP TABLE` ou `Base.metadata.drop_all()` foi executado no banco principal.

Verificação posterior no banco `vaganexo`:

- 9 tabelas do módulo + `alembic_version`;
- 14 FKs;
- 42 checks;
- 5 uniques;
- 31 índices;
- extensão `vector` 0.8.7 preservada;
- todas as tabelas com 0 registros antes dos testes manuais, que foram executados no banco isolado.

## 4. APIs

Prefixo: `/api/v1/profiles`. Todas as rotas usam `response_model`, injeção de sessão e transações do serviço.

### 4.1. Endpoints implementados

| Método | Caminho | Status | Função |
| --- | --- | --- | --- |
| POST | `/api/v1/profiles` | 201 | Criar perfil |
| GET | `/api/v1/profiles/{profile_id}` | 200 | Consultar perfil com relacionamentos |
| PATCH | `/api/v1/profiles/{profile_id}` | 200 | Atualizar perfil |
| GET | `/api/v1/profiles/{profile_id}/educations` | 200 | Listar formações |
| POST | `/api/v1/profiles/{profile_id}/educations` | 201 | Criar formação |
| PATCH | `/api/v1/profiles/{profile_id}/educations/{item_id}` | 200 | Atualizar formação |
| DELETE | `/api/v1/profiles/{profile_id}/educations/{item_id}` | 204 | Remover formação |
| GET/POST | `/api/v1/profiles/{profile_id}/experiences` | 200/201 | Listar/criar experiências |
| PATCH/DELETE | `/api/v1/profiles/{profile_id}/experiences/{item_id}` | 200/204 | Atualizar/remover experiência |
| GET/POST | `/api/v1/profiles/{profile_id}/skills` | 200/201 | Listar/criar competências |
| PATCH/DELETE | `/api/v1/profiles/{profile_id}/skills/{item_id}` | 200/204 | Atualizar/remover competência |
| GET/POST | `/api/v1/profiles/{profile_id}/certifications` | 200/201 | Listar/criar certificações |
| PATCH/DELETE | `/api/v1/profiles/{profile_id}/certifications/{item_id}` | 200/204 | Atualizar/remover certificação |
| GET/POST | `/api/v1/profiles/{profile_id}/languages` | 200/201 | Listar/criar idiomas |
| PATCH/DELETE | `/api/v1/profiles/{profile_id}/languages/{item_id}` | 200/204 | Atualizar/remover idioma |
| GET/POST | `/api/v1/profiles/{profile_id}/projects` | 200/201 | Listar/criar projetos |
| PATCH/DELETE | `/api/v1/profiles/{profile_id}/projects/{item_id}` | 200/204 | Atualizar/remover projeto |
| GET | `/api/v1/profiles/{profile_id}/preferences` | 200/404 | Consultar preferências |
| PUT | `/api/v1/profiles/{profile_id}/preferences` | 200 | Criar/atualizar preferências |
| GET/POST | `/api/v1/profiles/{profile_id}/resume-documents` | 200/201 | Listar/registrar metadados |
| GET/PATCH/DELETE | `/api/v1/profiles/{profile_id}/resume-documents/{document_id}` | 200/204 | Consultar/atualizar/remover metadados |
| POST | `/api/v1/profiles/{profile_id}/validation/{resource}/{item_id}/confirm` | 200 | Confirmar registro |
| POST | `/api/v1/profiles/{profile_id}/validation/{resource}/{item_id}/reject` | 200 | Rejeitar registro |

`resource` aceita `educations`, `experiences`, `skills`, `certifications`, `languages` e `projects`.

### 4.2. Exemplo de resposta

Criação de competência:

```json
{
  "id": "2b0f4a6e-6f0b-4d5f-9f2e-1a2b3c4d5e6f",
  "candidate_profile_id": "16bda8c3-15c4-4c2d-9e67-e4bfbc8ac878",
  "name": "Python",
  "normalized_name": "python",
  "category": "technical",
  "proficiency_level": "advanced",
  "years_experience": 6.0,
  "last_used": null,
  "description": null,
  "source_type": "manual",
  "validation_status": "confirmed",
  "source_document_id": null,
  "confidence_score": null,
  "created_at": "2026-11-25T22:31:13.000000Z",
  "updated_at": "2026-11-25T22:31:13.000000Z"
}
```

Erro padronizado:

```json
{ "detail": "profile not found" }
```

### 4.3. Regras de validação aplicadas

- 404 para perfil inexistente ou registro que não pertence ao perfil.
- 409 para competência, idioma ou documento duplicado.
- 422 para datas invertidas, salário invertido, URL inválida, confiança fora de 0–1, CEFR sem framework e tentativa de criar registro `document`/`ai` já confirmado.
- 204 para exclusões bem-sucedidas.
- 500 genérico para falhas de persistência, sem expor SQL ou detalhes do PostgreSQL.
- Nenhum identificador ou dado pessoal é registrado em log pela aplicação.

### 4.4. Proveniência e confirmação

- Manual sem estado explícito: `confirmed`.
- `document` ou `ai`: sempre inicia `pending`.
- `ai` com `validation_status=confirmed` no payload: HTTP 422.
- Atualização de origem para `document`/`ai`: volta para `pending`.
- `source_document_id` é validado contra o perfil.
- A confirmação só ocorre por endpoint explícito, que representa ação do usuário. Nenhum pipeline de IA está implementado ou autorizado a chamar esse endpoint.

## 5. Testes

| Teste | Resultado |
| --- | --- |
| SQLAlchemy | APROVADO |
| Alembic | APROVADO |
| PostgreSQL | APROVADO |
| Schemas Pydantic | APROVADO |
| APIs REST | APROVADO |
| Pytest | APROVADO |
| Ruff | APROVADO |
| Mypy | APROVADO |
| FastAPI /health | APROVADO |
| Frontend build | APROVADO |

Detalhamento:

| Verificação | Resultado |
| --- | --- |
| `uv sync` | 127 pacotes resolvidos, 105 verificados |
| `uv run alembic upgrade head` | Migração aplicada; `current` = `bdd3fb3a0174 (head)` |
| `uv run alembic downgrade base` / `upgrade head` | Aprovado no banco isolado `vaganexo_test` |
| `uv run pytest -v` | 60 testes aprovados; cobertura de `app` 93% |
| `uv run ruff check .` | `All checks passed!` |
| `uv run mypy app` | `Success: no issues found in 48 source files` |
| `GET /health` | HTTP 200 com `{"status":"healthy","application":"VagaNexo AI"}` |
| `GET /docs` | HTTP 200 |
| `GET /openapi.json` | 20 caminhos totais, 19 sob `/api/v1/profiles` |
| Criação/consulta/atualização de perfil | Aprovado via HTTP real |
| Criação de competência e experiência | Aprovado via HTTP real |
| Preferências (PUT/GET) | Aprovado via HTTP real |
| Payload inválido | HTTP 422 |
| Perfil inexistente | HTTP 404 |
| `npm run lint` | Aprovado |
| `npx tsc --noEmit` | Aprovado |
| `npm run build` | Next.js 16.4.6 compilou as rotas `/` e `/_not-found` |

Os testes de API manuais foram executados com o Uvicorn apontando para `vaganexo_test`, não para o banco principal.

## 6. Problemas

### 6.1. Docker Desktop parado no início

Causa: o daemon não estava em execução, então a porta 5433 não respondia e o primeiro `alembic current` falhou por timeout de conexão.

Correção: o Docker Desktop foi iniciado; os containers `vaganexo-postgres` e `vaganexo-redis` ficaram `healthy`. Nenhuma configuração, porta ou volume foi alterado.

### 6.2. Check de confiança ausente na primeira migração

Causa: o `CHECK` de `confidence_score` estava declarado dentro de `mapped_column`. O autogenerate do Alembic não renderiza esse tipo de constraint de coluna.

Correção: o check foi movido para o `__table_args__` das seis entidades com proveniência, e a migração foi regenerada. O banco foi validado com 42 checks, incluindo `ck_<tabela>_confidence_score_range`.

### 6.3. Saída de log tratada como erro pelo PowerShell

Causa: `uv` e `alembic` escrevem `INFO` em `stderr`; o PowerShell 5.1 marca isso como erro nativo.

Correção: nenhuma alteração de código. Os comandos foram avaliados pelo efeito real (migração aplicada, testes aprovados), não pelo código de saída do wrapper.

### 6.4. Formatação da migração

Causa: o arquivo gerado pelo Alembic usa linhas longas e aspas simples.

Correção: `ruff format` foi aplicado ao arquivo. A migração foi reaplicada e o ciclo de downgrade/upgrade foi validado novamente.

### 6.5. Listagem de documentos usava coluna inexistente

Causa: a listagem genérica de registros filhos ordenava por `created_at`, mas `resume_documents` usa `uploaded_at`. O erro só aparecia ao chamar `GET /api/v1/profiles/{id}/resume-documents`; a suíte inicial cobria apenas criação e consulta por id.

Correção: o método `_list_children` passou a aceitar uma coluna de ordenação explícita, e a listagem de documentos usa `uploaded_at`. Um teste de integração foi adicionado para cobrir a listagem, elevando o total para 60 testes.

### 6.6. Campos obrigatórios nulos em atualizações

Causa: payloads de atualização com `null` explícito em um campo obrigatório chegavam ao banco e retornavam erro de persistência genérico, em vez de uma resposta de domínio.

Correção: o serviço valida campos obrigatórios em criação e atualização, retornando HTTP 422. Um teste unitário cobre o caso.

Pendências: nenhuma falha obrigatória permanece aberta.

## 7. Segurança

### 7.1. Credenciais

- Nenhuma senha, token ou URL de conexão foi adicionada ao código, ao relatório ou à documentação.
- `.env`, `backend/.env` e `frontend/.env.local` foram preservados e permanecem ignorados pelo Git.
- Os exemplos versionados continuam apenas com `change-me` ou campos vazios.
- `alembic.ini` mantém o placeholder, e a URL real vem do ambiente.
- A aplicação não imprime a URL de conexão.

### 7.2. Dados pessoais

- Nenhum dado pessoal é registrado em log.
- Erros de persistência retornam mensagem genérica, sem SQL, valores de coluna ou detalhes do PostgreSQL.
- O banco armazena somente dados necessários ao funcionamento do produto.
- Documentos curriculares são apenas metadados; nenhum binário é gravado no PostgreSQL.

### 7.3. Proteção dos registros

- Toda consulta, atualização e exclusão de registro filho exige simultaneamente `item_id` e `profile_id`.
- Um registro de outro perfil retorna 404, sem revelar sua existência.
- O escopo por perfil já está pronto para receber autorização por usuário no futuro.

### 7.4. Integridade das informações

- Fatos importados ou sugeridos por IA nascem `pending`.
- A confirmação exige ação explícita do usuário via API.
- `rejected` está previsto como estado que não deve alimentar a geração de currículos.
- O vínculo com `ResumeDocument` usa `ON DELETE SET NULL`, preservando o fato profissional.
- A exclusão do perfil usa `CASCADE` apenas no banco, sem apagar arquivos do storage.

## 8. Próximos passos

1. Implementar upload controlado para `storage/uploads`, com cálculo de SHA-256 no servidor e registro de metadados.
2. Implementar extração de PDF/DOCX gerando registros com `source_type=document` e `validation_status=pending`.
3. Criar interface de revisão para confirmar, editar ou rejeitar informações pendentes.
4. Integrar Ollama/LM Studio somente após a revisão humana, sempre com `source_type=ai` e `pending`.
5. Implementar autenticação e isolamento multiusuário, mantendo o escopo por perfil já aplicado.
6. Implementar geração de currículos considerando apenas registros `confirmed`.
7. Adicionar paginação e filtros nas listagens quando o volume justificar.
8. Avaliar endpoint explícito de exclusão de perfil, com política para arquivos do storage.
9. Configurar CORS e variáveis de produção por ambiente.
10. Adicionar observabilidade sem registrar dados pessoais.

## 9. Conclusão

O Profile Engine v1.0 está implementado e validado: modelos, migração, schemas, API, proveniência, confirmação explícita e testes automatizados. O endpoint `/health` continua operacional, o frontend compila sem alterações funcionais e a branch `main` não foi modificada. O commit da etapa foi criado na branch `feat/profile-engine` com a mensagem `feat: implement professional profile engine foundation`.
