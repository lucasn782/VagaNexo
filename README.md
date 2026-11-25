# VagaNexo AI

VagaNexo AI é a base de uma plataforma para organizar carreira profissional: perfil, currículos, vagas e candidaturas. Este repositório entrega o ambiente de desenvolvimento, com frontend, API, banco de dados e fila prontos para as próximas etapas.

A leitura de currículos, o uso de modelos de linguagem, a busca de vagas e o envio de candidaturas ainda não fazem parte desta versão.

## Arquitetura tecnológica

| Camada | Tecnologias |
| --- | --- |
| Frontend | Next.js, React, TypeScript, Tailwind CSS, shadcn/ui, Zod, React Hook Form, Sonner |
| Backend | Python 3.13, FastAPI, Uvicorn, SQLAlchemy 2, Pydantic, Alembic |
| Documentos | PyMuPDF, python-docx, docxtpl, Pillow |
| IA | OpenAI Python SDK (APIs compatíveis com OpenAI) e Sentence Transformers. Nenhum modelo é baixado nesta etapa. |
| Banco | PostgreSQL 17 com pgvector |
| Filas | Redis 7 e Celery |
| Qualidade | Pytest, pytest-cov, Ruff, Mypy, ESLint, TypeScript |
| Infraestrutura | Docker Compose, uv, npm, Git |

O frontend fala com a API FastAPI. A API usará o PostgreSQL para dados relacionais e vetoriais e o Redis como broker do Celery. Provedores locais como Ollama e LM Studio entram depois, pela URL compatível com a API da OpenAI.

## Estrutura de diretórios

```text
VagaNexo/
|-- frontend/                 Next.js (App Router, src/)
|   |-- src/app/              Rotas da interface
|   |-- src/components/       Componentes visuais
|   |-- src/features/         dashboard, profile, resumes, jobs, applications, settings
|   |-- src/hooks/
|   |-- src/lib/
|   |-- src/services/
|-- backend/
|   |-- app/                  API, configuração, modelos e módulos de domínio
|   |-- tests/                Testes unitários e de integração
|   |-- alembic/              Migrações do banco
|-- infrastructure/
|   |-- compose.yaml          PostgreSQL e Redis
|   |-- docker/               Scripts de inicialização do banco
|-- storage/                  Arquivos locais de execução (não versionar documentos)
|-- docs/                     Arquitetura, desenvolvimento e API
|-- scripts/                  setup.ps1, dev.ps1, check.ps1
```

## Pré-requisitos

- Windows com PowerShell 5.1
- Git
- Node.js 20 ou superior e npm
- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- Docker Desktop em execução

Versões estáveis, sem canais nightly ou canary. O gerenciador Python do projeto é o uv. O gerenciador do frontend é o npm.

## Instalação

Na raiz do repositório:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

O script verifica as ferramentas, cria os arquivos `.env` locais quando eles ainda não existem, gera uma senha exclusiva de desenvolvimento e executa `uv sync` e `npm install`. Arquivos já presentes não são sobrescritos.

## Configuração do ambiente

Os exemplos versionados estão em `.env.example`, `backend/.env.example` e `frontend/.env.example`. A instalação copia esses arquivos para:

- `.env`
- `backend/.env`
- `frontend/.env.local`

A senha do PostgreSQL fica só nos arquivos locais. O mesmo valor precisa aparecer em `POSTGRES_PASSWORD` e na senha de `DATABASE_URL`.

Variáveis preparadas para a API de IA, lidas pelo backend:

| Variável | Função |
| --- | --- |
| `AI_PROVIDER` | Identificador do provedor. O padrão é `openai-compatible`. |
| `AI_BASE_URL` | URL base da API. Ollama: `http://127.0.0.1:11434/v1`. LM Studio: `http://127.0.0.1:1234/v1`. |
| `AI_MODEL` | Nome do modelo. |
| `AI_API_KEY` | Chave quando o servidor exigir. Deixe vazio para um servidor local sem autenticação. |

O frontend recebe apenas `NEXT_PUBLIC_API_URL` e `NEXT_PUBLIC_APP_NAME`. Chaves de IA não vão para o navegador.

Para conferir a configuração:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1
```

Use `-RequireRunning` depois de subir o Docker para exigir PostgreSQL e Redis saudáveis.

## Inicialização do Docker

Abra o Docker Desktop e aguarde o daemon. Depois:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1
```

O comando equivalente é:

```powershell
docker compose --env-file .env -f infrastructure\compose.yaml up -d
```

Os serviços escutam só em localhost. O volume `vaganexo_postgres_data` fica no Docker Desktop, fora da pasta sincronizada pelo OneDrive.

| Serviço | Endereço |
| --- | --- |
| PostgreSQL | `127.0.0.1:5432` |
| Redis | `127.0.0.1:6379` |

Banco, usuário e nome do volume local: `vaganexo`. A extensão `vector` é criada na primeira inicialização do volume.

A porta publicada no host vem de `POSTGRES_PORT`. O padrão é `5432`. Se outro PostgreSQL já escutar nessa porta, escolha uma porta livre e repita o mesmo número em `DATABASE_URL`.

## Inicialização do backend

```powershell
cd backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Para reconstruir o ambiente Python:

```powershell
cd backend
uv sync
```

## Inicialização do frontend

```powershell
cd frontend
npm run dev
```

A aplicação fica em `http://127.0.0.1:3000`.

## Endpoints disponíveis

| Método | Caminho | Descrição |
| --- | --- | --- |
| `GET` | `/health` | Retorna `{"status":"healthy","application":"VagaNexo AI"}` |
| `GET` | `/docs` | Documentação interativa gerada pelo FastAPI |
| `GET` | `/redoc` | Documentação ReDoc |
| `GET` | `/openapi.json` | Esquema OpenAPI |

A API fica em `http://127.0.0.1:8000`.

## Qualidade

Backend:

```powershell
cd backend
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy app
```

Frontend:

```powershell
cd frontend
npm run lint
npx tsc --noEmit
npm run build
```
