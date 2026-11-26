# VagaNexo Profile Engine

## 1. Objetivo

O **VagaNexo Profile Engine** é o módulo responsável por armazenar, organizar, consultar e atualizar as informações profissionais do candidato. Ele é a fonte central que será consumida, nas próximas fases, pelos mecanismos de análise de compatibilidade, personalização de currículos e gerenciamento de candidaturas.

Esta versão entrega:

- modelo relacional completo em PostgreSQL 17;
- migração Alembic versionada;
- schemas Pydantic de entrada e saída;
- API REST sob `/api/v1/profiles`;
- rastreabilidade da origem das informações;
- endpoints explícitos de confirmação e rejeição;
- testes unitários e de integração.

Não fazem parte desta fase: upload real de arquivos, extração de currículos, IA, embeddings, busca semântica, autenticação e multiusuário.

## 2. Arquitetura

```text
backend/app/
├── api/routes/profiles.py      Rotas REST do Profile Engine
├── core/config.py              Configuração, incluindo origens CORS
├── database/
│   ├── session.py              Engine, SessionLocal e create_db_engine()
│   ├── dependencies.py         Dependência get_db() para FastAPI
│   └── __init__.py             Reexports da camada de persistência
├── models/
│   ├── base.py                 DeclarativeBase e convenção de nomes
│   ├── mixins.py               UUID, timestamps e proveniência
│   ├── enums.py                Enums e helper sa_enum()
│   ├── candidate_profile.py    Perfil principal
│   ├── education.py            Formação acadêmica
│   ├── experience.py           Experiência profissional
│   ├── skill.py                Competências
│   ├── certification.py        Certificações
│   ├── language.py             Idiomas
│   ├── project.py              Projetos
│   ├── preference.py           Preferências profissionais
│   └── resume_document.py      Metadados de currículos
├── schemas/                    Contratos Pydantic de entrada e saída
├── profile/
│   ├── service.py              Regras de negócio e transações
│   ├── validators.py           Validações de domínio
│   └── exceptions.py           Erros de domínio traduzidos para HTTP
└── main.py                     Aplicação FastAPI e handlers de erro
```

Responsabilidades:

| Componente | Responsabilidade |
| --- | --- |
| `models/` | Estrutura relacional, constraints, índices e relacionamentos |
| `schemas/` | Validação de entrada, serialização de saída e documentação OpenAPI |
| `profile/service.py` | Transações, escopo por perfil, regras de proveniência e conflitos |
| `profile/validators.py` | Regras puras reutilizáveis (datas, salários, normalização, origem) |
| `api/routes/profiles.py` | Contrato HTTP, status codes e injeção de dependências |
| `database/` | Engine, sessão e ciclo de vida da conexão |
| `main.py` | Registro das rotas, CORS e tratamento padronizado de erros |

A lógica de negócio não depende de FastAPI. As rotas apenas delegam ao `ProfileService`, o que preserva a separação necessária para adicionar autenticação e multiusuário no futuro.

## 3. Modelo de dados

Todas as tabelas usam `UUID` como chave primária e timestamps com timezone. Os nomes de constraints e índices seguem uma convenção central em `app/models/base.py`.

```text
candidate_profiles
├── 1:N educations
├── 1:N work_experiences
├── 1:N skills
├── 1:N certifications
├── 1:N languages
├── 1:N projects
├── 1:1 job_preferences
└── 1:N resume_documents

resume_documents
└── 1:N (opcional) educations, work_experiences, skills,
        certifications, languages e projects via source_document_id
```

### 3.1. Proveniência

As entidades que representam fatos profissionais (`educations`, `work_experiences`, `skills`, `certifications`, `languages` e `projects`) compartilham os campos:

| Campo | Tipo | Regra |
| --- | --- | --- |
| `source_type` | enum | `manual`, `document`, `ai` |
| `validation_status` | enum | `pending`, `confirmed`, `rejected` |
| `source_document_id` | UUID | FK para `resume_documents.id`, `ON DELETE SET NULL` |
| `confidence_score` | float | Entre 0 e 1, quando informado |
| `created_at` | timestamptz | Preenchido pelo banco |
| `updated_at` | timestamptz | Atualizado em cada alteração |

## 4. Relacionamentos e integridade

| Relação | FK | ON DELETE |
| --- | --- | --- |
| Filho → `candidate_profiles` | `candidate_profile_id` | `CASCADE` |
| Fato → `resume_documents` | `source_document_id` | `SET NULL` |

- A exclusão do perfil remove seus registros dependentes no banco, mas não toca em arquivos do sistema de arquivos.
- A exclusão de metadados de um documento mantém os fatos profissionais e apenas limpa a referência `source_document_id`.
- Documentos curriculares guardam somente metadados; nenhum conteúdo binário é persistido no PostgreSQL.
- As rotas sempre filtram por `profile_id` e `item_id`, impedindo acesso cruzado entre perfis.

## 5. Dicionário de dados

### 5.1. `candidate_profiles`

| Campo | Tipo | Obrigatório | Observação |
| --- | --- | --- | --- |
| `id` | UUID | sim | Chave primária |
| `full_name` | varchar(200) | sim | Não pode ser vazio |
| `professional_headline` | varchar(200) | não | Título profissional |
| `professional_summary` | text | não | Resumo profissional |
| `email` | varchar(320) | não | Índice de consulta |
| `phone` | varchar(40) | não | |
| `city` | varchar(120) | não | |
| `state` | varchar(120) | não | |
| `country` | varchar(120) | não | |
| `linkedin_url` | varchar(500) | não | URL HTTP(S) válida |
| `github_url` | varchar(500) | não | URL HTTP(S) válida |
| `portfolio_url` | varchar(500) | não | URL HTTP(S) válida |
| `created_at` | timestamptz | sim | |
| `updated_at` | timestamptz | sim | |

### 5.2. `educations`

| Campo | Tipo | Obrigatório | Observação |
| --- | --- | --- | --- |
| `id` | UUID | sim | |
| `candidate_profile_id` | UUID | sim | FK `CASCADE` |
| `institution` | varchar(200) | sim | |
| `degree` | varchar(200) | sim | |
| `field_of_study` | varchar(200) | não | |
| `start_date` | date | sim | |
| `end_date` | date | não | `>= start_date` |
| `is_current` | boolean | sim | Se verdadeiro, `end_date` deve ser nulo |
| `description` | text | não | |
| proveniência | — | — | Campos da seção 3.1 |

### 5.3. `work_experiences`

| Campo | Tipo | Obrigatório | Observação |
| --- | --- | --- | --- |
| `id` | UUID | sim | |
| `candidate_profile_id` | UUID | sim | FK `CASCADE` |
| `company` | varchar(200) | sim | |
| `job_title` | varchar(200) | sim | |
| `employment_type` | enum | sim | `full_time`, `part_time`, `internship`, `contract`, `temporary`, `freelance`, `other` |
| `location` | varchar(200) | não | |
| `start_date` | date | sim | |
| `end_date` | date | não | `>= start_date` |
| `is_current` | boolean | sim | Se verdadeiro, `end_date` deve ser nulo |
| `description` | text | não | Conteúdo original preservado |
| `achievements` | jsonb | não | Lista de realizações |
| proveniência | — | — | Campos da seção 3.1 |

Projetos acadêmicos ou pessoais não são convertidos automaticamente em experiências; eles pertencem à tabela `projects`.

### 5.4. `skills`

| Campo | Tipo | Obrigatório | Observação |
| --- | --- | --- | --- |
| `id` | UUID | sim | |
| `candidate_profile_id` | UUID | sim | FK `CASCADE` |
| `name` | varchar(120) | sim | Nome exibido |
| `normalized_name` | varchar(120) | sim | Gerado pelo servidor |
| `category` | enum | sim | `technical`, `behavioral`, `tools`, `domain`, `other` |
| `proficiency_level` | enum | sim | `beginner`, `intermediate`, `advanced`, `expert`, `unspecified` |
| `years_experience` | numeric(4,1) | não | Entre 0 e 80 |
| `last_used` | date | não | |
| `description` | text | não | |
| proveniência | — | — | Campos da seção 3.1 |

Restrições: `UNIQUE (candidate_profile_id, normalized_name)` e índice em `normalized_name`. A normalização remove acentos, caixa e espaços repetidos; por exemplo, `Comunicação` e `comunicacao` são a mesma competência.

### 5.5. `certifications`

| Campo | Tipo | Obrigatório | Observação |
| --- | --- | --- | --- |
| `id` | UUID | sim | |
| `candidate_profile_id` | UUID | sim | FK `CASCADE` |
| `name` | varchar(200) | sim | |
| `issuing_organization` | varchar(200) | sim | |
| `issue_date` | date | não | |
| `expiration_date` | date | não | `>= issue_date` |
| `credential_id` | varchar(200) | não | |
| `credential_url` | varchar(500) | não | URL HTTP(S) válida |
| proveniência | — | — | Campos da seção 3.1 |

### 5.6. `languages`

| Campo | Tipo | Obrigatório | Observação |
| --- | --- | --- | --- |
| `id` | UUID | sim | |
| `candidate_profile_id` | UUID | sim | FK `CASCADE` |
| `language` | varchar(80) | sim | Único por perfil (comparação sem caixa) |
| `proficiency_level` | enum | sim | `basic`, `intermediate`, `advanced`, `fluent`, `native`, `unspecified` |
| `proficiency_framework` | enum | não | `cefr`, `actfl`, `other` |
| `cefr_level` | enum | não | `A1`, `A2`, `B1`, `B2`, `C1`, `C2`; exige `cefr` |
| proveniência | — | — | Campos da seção 3.1 |

### 5.7. `projects`

| Campo | Tipo | Obrigatório | Observação |
| --- | --- | --- | --- |
| `id` | UUID | sim | |
| `candidate_profile_id` | UUID | sim | FK `CASCADE` |
| `name` | varchar(200) | sim | |
| `description` | text | não | |
| `role` | varchar(200) | não | |
| `project_url` | varchar(500) | não | URL HTTP(S) válida |
| `start_date` | date | não | |
| `end_date` | date | não | `>= start_date` |
| `technologies` | jsonb | não | Lista de tecnologias |
| `project_type` | enum | sim | `personal`, `academic`, `professional`, `open_source`, `other` |
| proveniência | — | — | Campos da seção 3.1 |

### 5.8. `job_preferences`

Relação um para um com `candidate_profiles` (`UNIQUE candidate_profile_id`).

| Campo | Tipo | Observação |
| --- | --- | --- |
| `id` | UUID | |
| `candidate_profile_id` | UUID | FK `CASCADE` |
| `preferred_job_titles` | jsonb | Lista de cargos |
| `preferred_locations` | jsonb | Lista de locais |
| `work_modes` | jsonb | `remote`, `hybrid`, `onsite` |
| `employment_types` | jsonb | `full_time`, `part_time`, `internship`, `contract`, `temporary`, `freelance`, `other` |
| `minimum_salary` | numeric(12,2) | `>= 0` |
| `maximum_salary` | numeric(12,2) | `>= 0` e `>= minimum_salary` |
| `salary_currency` | varchar(3) | Normalizada em maiúsculas |
| `willingness_to_relocate` | boolean | |
| `preferred_seniority` | enum | `intern`, `junior`, `mid`, `senior`, `lead`, `principal`, `director`, `executive`, `unspecified` |
| `created_at` / `updated_at` | timestamptz | |

As listas ficam em JSONB para permitir novas modalidades sem alterar o modelo central.

### 5.9. `resume_documents`

| Campo | Tipo | Observação |
| --- | --- | --- |
| `id` | UUID | |
| `candidate_profile_id` | UUID | FK `CASCADE` |
| `original_filename` | varchar(255) | Não pode ser vazio |
| `media_type` | varchar(100) | Ex.: `application/pdf` |
| `file_size` | bigint | `>= 0` |
| `sha256_hash` | varchar(64) | 64 caracteres hexadecimais minúsculos |
| `storage_key` | varchar(500) | Único, caminho relativo sem `..` |
| `parsing_status` | enum | `pending`, `processing`, `parsed`, `failed` |
| `uploaded_at` | timestamptz | |

Restrições: `UNIQUE storage_key` e `UNIQUE (candidate_profile_id, sha256_hash)`.

## 6. Regras de validação

- `full_name` não pode ser vazio nem apenas espaços.
- `end_date` não pode ser anterior a `start_date` em formação, experiência e projeto.
- `is_current = true` exige `end_date` nulo em formação e experiência.
- `expiration_date` não pode ser anterior a `issue_date` em certificações.
- `minimum_salary` não pode ser maior que `maximum_salary`; ambos não podem ser negativos.
- `confidence_score` deve estar entre 0 e 1.
- URLs devem ser absolutas com esquema HTTP ou HTTPS.
- `years_experience` deve estar entre 0 e 80.
- `cefr_level` só é aceito com `proficiency_framework = "cefr"`.
- Competências duplicadas no mesmo perfil retornam HTTP 409.
- Idiomas duplicados no mesmo perfil retornam HTTP 409, sem diferenciar caixa.
- Registros de um perfil não podem ser consultados, alterados ou removidos por outro perfil.
- Campos internos (`id`, `created_at`, `updated_at`, `normalized_name`) não são aceitos em payloads de atualização.

As validações existem em três camadas: Pydantic (contrato), serviço (regras de negócio) e banco (constraints). A camada de banco garante integridade mesmo fora da API.

## 7. Proveniência das informações

Cada fato profissional registra de onde veio:

| `source_type` | Uso |
| --- | --- |
| `manual` | Informação digitada pelo candidato |
| `document` | Informação extraída de um currículo importado |
| `ai` | Sugestão gerada por modelo de linguagem |

Regras aplicadas nesta fase:

1. Registro manual sem `validation_status` explícito nasce `confirmed`.
2. Registro com origem `document` ou `ai` nasce sempre `pending`.
3. Criar um registro `document` ou `ai` já como `confirmed` retorna HTTP 422.
4. Atualizar a origem para `document` ou `ai` força o estado de volta para `pending`.
5. Se um `source_document_id` é informado sem `source_type`, a origem é tratada como `document`.
6. O documento referenciado precisa pertencer ao mesmo perfil.
7. A única forma de tornar um registro `confirmed` é o endpoint explícito de confirmação, que representa uma ação do usuário.
8. Nenhum pipeline de IA está autorizado a chamar o endpoint de confirmação.

## 8. Estados de confirmação

| Estado | Significado | Uso futuro |
| --- | --- | --- |
| `pending` | Aguardando revisão do candidato | Não deve ser tratado como fato definitivo |
| `confirmed` | Confirmado pelo candidato | Pode ser usado na geração de currículos |
| `rejected` | Rejeitado pelo candidato | Deve ser excluído da geração de currículos |

Endpoints:

```text
POST /api/v1/profiles/{profile_id}/validation/{resource}/{item_id}/confirm
POST /api/v1/profiles/{profile_id}/validation/{resource}/{item_id}/reject
```

`resource` aceita: `educations`, `experiences`, `skills`, `certifications`, `languages`, `projects`.

Os endpoints são idempotentes: repetir a confirmação mantém `confirmed`; repetir a rejeição mantém `rejected`. A alteração de conteúdo não muda automaticamente o estado, exceto quando a origem passa a ser `document` ou `ai`, que força `pending`.

## 9. Migrações

A migração inicial é `bdd3fb3a0174_create_profile_engine_tables` e está em `backend/alembic/versions/`.

Ela cria:

- 9 tabelas do Profile Engine;
- 14 foreign keys;
- constraints de unicidade, checks de domínio e checks de enum;
- 31 índices, incluindo as colunas de consulta frequente;
- downgrade que remove somente as tabelas e índices criados por ela.

Comandos, executados em `backend`:

```powershell
uv run alembic upgrade head
uv run alembic current
uv run alembic history
```

O `alembic/env.py` importa `app.models`, garantindo que todo o metadata seja conhecido. A URL vem exclusivamente da configuração de ambiente; o `alembic.ini` versionado mantém apenas o placeholder `change-me`.

O downgrade foi validado em banco isolado (`vaganexo_test`) com `upgrade → downgrade base → upgrade`. Nenhum comando destrutivo foi executado no banco principal.

## 10. Endpoints

Prefixo: `/api/v1/profiles`.

### Perfil

| Método | Caminho | Status | Função |
| --- | --- | --- | --- |
| POST | `/` | 201 | Criar perfil |
| GET | `/{profile_id}` | 200 | Consultar perfil com registros relacionados |
| PATCH | `/{profile_id}` | 200 | Atualizar perfil |

### Formação, experiências, competências, certificações, idiomas e projetos

O mesmo padrão vale para `educations`, `experiences`, `skills`, `certifications`, `languages` e `projects`.

| Método | Caminho | Status | Função |
| --- | --- | --- | --- |
| GET | `/{profile_id}/{resource}` | 200 | Listar |
| POST | `/{profile_id}/{resource}` | 201 | Criar |
| PATCH | `/{profile_id}/{resource}/{item_id}` | 200 | Atualizar |
| DELETE | `/{profile_id}/{resource}/{item_id}` | 204 | Remover |

### Preferências

| Método | Caminho | Status | Função |
| --- | --- | --- | --- |
| GET | `/{profile_id}/preferences` | 200 / 404 | Consultar |
| PUT | `/{profile_id}/preferences` | 200 | Criar ou atualizar (upsert) |

### Documentos curriculares

| Método | Caminho | Status | Função |
| --- | --- | --- | --- |
| GET | `/{profile_id}/resume-documents` | 200 | Listar metadados |
| POST | `/{profile_id}/resume-documents` | 201 | Registrar metadados |
| GET | `/{profile_id}/resume-documents/{document_id}` | 200 | Consultar metadados |
| PATCH | `/{profile_id}/resume-documents/{document_id}` | 200 | Atualizar metadados |
| DELETE | `/{profile_id}/resume-documents/{document_id}` | 204 | Remover metadados |

O upload e o processamento de arquivos não estão implementados. O DELETE remove apenas o metadado; o arquivo físico, quando existir no futuro, não é apagado por cascata.

### Validação

| Método | Caminho | Status | Função |
| --- | --- | --- | --- |
| POST | `/{profile_id}/validation/{resource}/{item_id}/confirm` | 200 | Confirmar registro |
| POST | `/{profile_id}/validation/{resource}/{item_id}/reject` | 200 | Rejeitar registro |

### Erros

| Status | Situação |
| --- | --- |
| 400 | Erro de domínio genérico |
| 404 | Perfil ou registro inexistente no perfil informado |
| 409 | Conflito de unicidade (competência, idioma, documento) |
| 422 | Payload inválido ou regra de proveniência violada |
| 500 | Falha interna de persistência, sem detalhes do PostgreSQL |

Formato padrão:

```json
{ "detail": "profile not found" }
```

## 11. Exemplos

### Criar perfil

```http
POST /api/v1/profiles
Content-Type: application/json
```

```json
{
  "full_name": "Ana Souza",
  "professional_headline": "Backend Engineer",
  "email": "ana.souza@example.com",
  "city": "Sao Paulo",
  "state": "SP",
  "country": "Brasil",
  "linkedin_url": "https://www.linkedin.com/in/ana-souza"
}
```

Resposta `201` (trecho):

```json
{
  "id": "16bda8c3-15c4-4c2d-9e67-e4bfbc8ac878",
  "full_name": "Ana Souza",
  "professional_headline": "Backend Engineer",
  "educations": [],
  "experiences": [],
  "skills": [],
  "certifications": [],
  "languages": [],
  "projects": [],
  "preferences": null,
  "resume_documents": [],
  "created_at": "2026-11-25T22:31:13.000000Z",
  "updated_at": "2026-11-25T22:31:13.000000Z"
}
```

### Criar competência

```http
POST /api/v1/profiles/{profile_id}/skills
```

```json
{
  "name": "Python",
  "category": "technical",
  "proficiency_level": "advanced",
  "years_experience": 6
}
```

Resposta `201` (trecho):

```json
{
  "id": "2b0f4a6e-6f0b-4d5f-9f2e-1a2b3c4d5e6f",
  "name": "Python",
  "normalized_name": "python",
  "category": "technical",
  "proficiency_level": "advanced",
  "years_experience": 6,
  "source_type": "manual",
  "validation_status": "confirmed",
  "confidence_score": null
}
```

### Criar competência sugerida por IA

```json
{
  "name": "Rust",
  "source_type": "ai",
  "confidence_score": 0.42
}
```

Resposta: `validation_status` igual a `pending`. Enviar `validation_status: "confirmed"` com `source_type: "ai"` retorna `422`.

### Confirmar registro

```http
POST /api/v1/profiles/{profile_id}/validation/skills/{item_id}/confirm
```

```json
{
  "resource": "skills",
  "id": "2b0f4a6e-6f0b-4d5f-9f2e-1a2b3c4d5e6f",
  "validation_status": "confirmed",
  "updated_at": "2026-11-25T22:35:00.000000Z"
}
```

### Preferências

```http
PUT /api/v1/profiles/{profile_id}/preferences
```

```json
{
  "preferred_job_titles": ["Backend Engineer"],
  "preferred_locations": ["Sao Paulo"],
  "work_modes": ["remote", "hybrid"],
  "employment_types": ["full_time"],
  "minimum_salary": 8000,
  "maximum_salary": 15000,
  "salary_currency": "brl",
  "willingness_to_relocate": true,
  "preferred_seniority": "senior"
}
```

## 12. Execução e testes

Backend:

```powershell
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Documentação interativa: `http://127.0.0.1:8000/docs`.

Testes:

```powershell
cd backend
uv run pytest -v
uv run ruff check .
uv run mypy app
```

Os testes usam o banco isolado `vaganexo_test`, derivado de `DATABASE_URL`. O fixture recusa qualquer banco cujo nome não termine em `_test`, cria as tabelas no início da sessão, limita a limpeza aos dados de teste e remove apenas as tabelas do metadata no final. Nenhum dado do banco `vaganexo` é apagado.

Para apontar explicitamente para outro banco de teste:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://usuario:senha@127.0.0.1:5433/vaganexo_test"
```

## 13. Decisões e limites desta fase

- Sem autenticação: o MVP é local e individual. O escopo por perfil já está aplicado em todas as consultas, o que prepara a futura camada de autorização.
- Sem upload: apenas metadados de documentos são registrados.
- Sem IA: nenhuma sugestão é gerada; o modelo apenas suporta a proveniência e a confirmação.
- Sem exclusão de perfil via API: a integridade de exclusão já é garantida no banco e testada.
- CORS configurado por `CORS_ORIGINS`, com padrão para o frontend local em `http://127.0.0.1:3000` e `http://localhost:3000`.
