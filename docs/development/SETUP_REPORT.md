# Relatório técnico de preparação — VagaNexo AI

## 12.1. Resumo da execução

Objetivo: preparar a infraestrutura do VagaNexo AI, com diretórios, ambientes, dependências, Docker e a validação mínima de instalação. Nenhuma funcionalidade de inteligência artificial, análise de currículos, busca de vagas ou candidaturas foi implementada.

Diretório utilizado: `C:\Users\lucas\OneDrive\Documentos\VagaNexo`.

Data e horário: 25/11/2026. A verificação das ferramentas começou nesta sessão e a bateria de validação foi executada entre 16:40:38 e 16:43:17, horário de Brasília (UTC−3).

Situação ao término: preparação concluída. O repositório Git já existia na branch `main`, sem commits. A árvore de diretórios, os arquivos de configuração, o ambiente virtual Python 3.13.17, os lockfiles e os containers Docker já estavam presentes e foram preservados. Nesta execução foram localizadas as ferramentas, executados `scripts\setup.ps1` e `scripts\dev.ps1`, e repetidos os testes de backend, frontend, PostgreSQL, pgvector, Redis e `GET /health`.

## 12.2. Ambiente identificado

Valores lidos nesta máquina, sem substituição por versões presumidas.

| Item | Versão identificada |
| --- | --- |
| Sistema operacional | Microsoft Windows NT 10.0.26300.0 |
| PowerShell | 5.1.26100.9818 |
| Git | 2.55.0.windows.5 |
| Python do projeto | 3.13.17 em `C:\Users\lucas\AppData\Local\Programs\Python\Python313\python.exe` |
| Python padrão do launcher | 3.14.7 em `C:\Python314\python.exe` (não usado pelo projeto) |
| uv | 0.13.10 (e3e7c1eac 2026-11-24, x86_64-pc-windows-msvc) |
| Node.js | v26.8.1 |
| npm | 12.2.2 |
| Docker | 29.8.1 (cliente e servidor) |
| Docker Compose | v5.5.1 |

O executável do uv está em:

`C:\Users\lucas\AppData\Local\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe`

O diretório desse executável já faz parte do PATH do usuário. O processo inicial desta sessão não enxergava o comando `uv` até o PATH ser recarregado. Nenhuma reinstalação foi necessária.

## 12.3. Estrutura criada

A árvore abaixo já estava no diretório e foi conferida. O único arquivo novo desta execução é este relatório.

Diretórios:

- `frontend/public/`
- `frontend/src/app/`
- `frontend/src/components/ui/`
- `frontend/src/features/dashboard/`
- `frontend/src/features/profile/`
- `frontend/src/features/resumes/`
- `frontend/src/features/jobs/`
- `frontend/src/features/applications/`
- `frontend/src/features/settings/`
- `frontend/src/hooks/`
- `frontend/src/lib/`
- `frontend/src/services/`
- `backend/app/api/routes/`
- `backend/app/core/`
- `backend/app/database/`
- `backend/app/models/`
- `backend/app/schemas/`
- `backend/app/parsers/`
- `backend/app/ai/`
- `backend/app/profile/`
- `backend/app/cv_engine/`
- `backend/app/matching/`
- `backend/app/connectors/`
- `backend/app/applications/`
- `backend/app/workers/`
- `backend/tests/unit/`
- `backend/tests/integration/`
- `backend/alembic/versions/`
- `backend/.venv/` (ambiente local, ignorado pelo Git)
- `infrastructure/docker/postgres/init/`
- `storage/uploads/`
- `storage/resumes/`
- `storage/generated/`
- `storage/temporary/`
- `docs/architecture/`
- `docs/development/`
- `docs/api/`
- `scripts/`

Arquivos de configuração:

- `.editorconfig`
- `.gitattributes`
- `.gitignore`
- `.env.example`
- `backend/pyproject.toml`
- `backend/.python-version` com o conteúdo `3.13`
- `backend/alembic.ini`
- `backend/alembic/env.py`
- `backend/alembic/script.py.mako`
- `backend/.env.example`
- `frontend/package.json`
- `frontend/tsconfig.json`
- `frontend/next.config.ts`
- `frontend/eslint.config.mjs`
- `frontend/components.json`
- `frontend/.env.example`
- `infrastructure/compose.yaml`
- `infrastructure/docker/postgres/init/001_pgvector.sql`

Arquivos de automação:

- `scripts/setup.ps1`
- `scripts/dev.ps1`
- `scripts/check.ps1`

Arquivos de documentação:

- `README.md`
- `LICENSE` (MIT, copyright 2026 VagaNexo AI)
- `docs/architecture/overview.md`
- `docs/development/setup.md`
- `docs/api/health.md`
- `docs/development/SETUP_REPORT.md`

Arquivos de dependências e lockfiles:

- `backend/uv.lock`
- `frontend/package-lock.json`

Módulos Python com `__init__.py`: `app`, `app.api`, `app.api.routes`, `app.core`, `app.database`, `app.models`, `app.schemas`, `app.parsers`, `app.ai`, `app.profile`, `app.cv_engine`, `app.matching`, `app.connectors`, `app.applications` e `app.workers`.

## 12.4. Dependências instaladas

O comando `uv sync --python 3.13` concluiu com código 0. A resolução informou 127 pacotes e a verificação do ambiente informou 105 pacotes. As versões abaixo foram lidas do ambiente `backend\.venv`.

### Python — produção

| Biblioteca | Versão | Finalidade |
| --- | --- | --- |
| fastapi | 0.165.0 | Aplicação HTTP e endpoint de saúde |
| uvicorn | 0.54.0 | Servidor ASGI |
| sqlalchemy | 2.1.9 | ORM e engine SQLAlchemy 2 |
| pydantic | 2.14.4 | Modelos de dados |
| pydantic-settings | 2.16.3 | Configuração por ambiente |
| alembic | 1.20.1 | Migrações do banco |
| httpx | 0.28.1 | Cliente HTTP |
| psycopg | 3.3.9 | Driver PostgreSQL |
| python-multipart | 0.0.34 | Formulários e upload |
| pymupdf | 2.1 | Leitura de PDF, reservada para etapa futura |
| python-docx | 1.2.0 | Leitura de DOCX, reservada para etapa futura |
| docxtpl | 0.20.2 | Modelos DOCX, reservada para etapa futura |
| pillow | 13.0.0 | Imagens, reservada para etapa futura |
| openai | 3.59.0 | SDK compatível com APIs OpenAI |
| sentence-transformers | 6.3.0 | Biblioteca de embeddings, sem download de modelo |
| celery | 5.7.0 | Tarefas assíncronas, com extra Redis |
| redis | 8.2.0 | Cliente Redis usado pelo Celery |

### Python — desenvolvimento

| Biblioteca | Versão | Finalidade |
| --- | --- | --- |
| pytest | 9.2.0 | Testes |
| pytest-cov | 7.1.0 | Cobertura |
| ruff | 0.17.6 | Lint e formato |
| mypy | 2.4.1 | Checagem de tipos |

O arquivo `backend/uv.lock` fixa o grafo completo, inclusive dependências transitivas como o cliente do Celery. Nenhum modelo de linguagem ou de embeddings foi baixado.

### Node.js

`npm install` informou que a árvore já estava atualizada. `npm ls --depth=0` listou:

| Pacote | Versão | Finalidade |
| --- | --- | --- |
| next | 16.4.6 | App Router e build |
| react | 19.3.0 | Interface |
| react-dom | 19.3.0 | Renderização |
| typescript | 5.9.3 | Compilador |
| tailwindcss | 4.3.3 | Estilos |
| @tailwindcss/turbopack | 4.3.3 | Integração do Tailwind com o Turbopack |
| eslint | 9.39.4 | Lint |
| eslint-config-next | 16.4.6 | Regras do Next.js |
| zod | 4.6.7 | Validação |
| react-hook-form | 7.92.0 | Formulários |
| @hookform/resolvers | 7.0.9 | Integração do Zod com o React Hook Form |
| lucide-react | 1.80.0 | Ícones |
| sonner | 2.0.8 | Notificações |
| clsx | 2.1.1 | Composição de classes |
| tailwind-merge | 3.7.1 | Fusão de classes Tailwind |
| class-variance-authority | 0.7.1 | Variantes de componentes |
| shadcn | 4.23.0 | CLI e base do shadcn/ui |
| @base-ui/react | 1.9.0 | Primitivos usados pelo componente gerado |
| tw-animate-css | 1.4.0 | Animações exigidas pelo preset do shadcn |
| cn | 0.5.2 | Função `cn` importada por `src/lib/utils.ts` e pelo botão |
| @types/node | 20.19.43 | Tipos do Node.js |
| @types/react | 19.3.3 | Tipos do React |
| @types/react-dom | 19.3.0 | Tipos do React DOM |

O shadcn/ui está configurado em `frontend/components.json` com estilo `base-nova`, RSC, TypeScript, Tailwind em `src/app/globals.css`, ícones Lucide e alias `@/*`. O único componente visual presente é o primitivo `src/components/ui/button.tsx`. A página inicial permanece o exemplo do Next.js.

### Imagens e serviços Docker

| Serviço | Imagem e tag | Identificador | Conteúdo em execução |
| --- | --- | --- | --- |
| postgres | `pgvector/pgvector:pg17` | `sha256:b513c48566e4777cd3370451400000c78eda6a08131d68f4c31d4a76f27bd8fd` | PostgreSQL 17.12 (Debian 17.12-1.pgdg12+1) |
| redis | `redis:7-alpine` | `sha256:7f7d30b7fdd09467bac58198a1f166dd69789d348d4fe859cccb20e0cf287fbe` | Redis server 7.4.12 |

Volume nomeado: `vaganexo_postgres_data`, gerenciado pelo Docker, fora da pasta sincronizada pelo OneDrive. O script `001_pgvector.sql` executa `CREATE EXTENSION IF NOT EXISTS vector` na primeira inicialização do volume.

## 12.5. Configurações realizadas

### Ambiente virtual Python

- Gerenciador: uv.
- Local: `backend/.venv`.
- Interpretador: Python 3.13.17.
- `requires-python` em `backend/pyproject.toml`: `>=3.13`.
- Grupo de desenvolvimento instalado por padrão (`tool.uv.default-groups`).
- Ruff aponta para Python 3.13, comprimento de linha 100 e os pacotes `app`, `tests` e `alembic`.
- Pytest usa `tests/`, `pythonpath = ["."]` e cobertura do pacote `app`.
- Mypy usa Python 3.13, pacote `app` e `ignore_missing_imports`.

### Frontend

- Next.js 16.4.6 com App Router, TypeScript, ESLint, diretório `src/` e alias `@/*`.
- Tailwind CSS 4, com o loader `@tailwindcss/turbopack` declarado em `frontend/next.config.ts`.
- A raiz do Turbopack está fixada no diretório `frontend`, para não herdar um lockfile de outro diretório do usuário.
- Gerenciador: npm, com `frontend/package-lock.json`.

### Backend

- `backend/app/main.py` cria a aplicação FastAPI, configura log no ciclo de vida e registra o roteador de saúde.
- `GET /health` devolve `{"status":"healthy","application":"VagaNexo AI"}`.
- A configuração lê `backend/.env` por meio do Pydantic Settings. A chave de IA fica em `SecretStr` e não é impressa pela aplicação.
- SQLAlchemy expõe `create_db_engine()` e o modelo base. Não há tabelas de negócio.
- Alembic está apontado para `backend/alembic`. `alembic/env.py` substitui a URL do `alembic.ini` pela `DATABASE_URL` do ambiente. O `alembic.ini` versionado conserva apenas o placeholder `change-me` e a porta 5432.
- Celery está instanciado com broker e backend Redis, sem tarefas de negócio.

### PostgreSQL

- Banco e usuário: `vaganexo`.
- Imagem com pgvector.
- Publicação somente em `127.0.0.1`.
- Porta do host nesta máquina: `5433`.
- A porta 5432 do host está ocupada por outro processo `postgres` (PID 6236). O arquivo local `.env` e a `DATABASE_URL` do backend usam 5433. As senhas locais coincidem. Os valores não são registrados neste relatório.
- Healthcheck: `pg_isready`.
- Reinício: `unless-stopped`.
- Estado observado: `healthy`.

### pgvector

Consulta executada dentro do container:

`SELECT extname, extversion FROM pg_extension WHERE extname = 'vector'`

Resultado: `vector|0.8.7`.

### Redis

- Imagem `redis:7-alpine`.
- Publicação somente em `127.0.0.1:6379`.
- Healthcheck: `redis-cli ping`.
- Reinício: `unless-stopped`.
- Estado observado: `healthy`.
- Resposta do ping: `PONG`.

### Docker Compose

Arquivo: `infrastructure/compose.yaml`. Nome do projeto: `vaganexo`. `docker compose --env-file .env -f infrastructure\compose.yaml config` terminou com código 0. Nenhuma porta está publicada em `0.0.0.0`.

### Arquivos de ambiente

Versionados, com placeholders:

- `.env.example`: PostgreSQL, Redis e identificação da API de IA (`AI_PROVIDER`, `AI_BASE_URL`, `AI_MODEL`, `AI_API_KEY`).
- `backend/.env.example`: FastAPI, `DATABASE_URL`, Redis, Celery e as mesmas variáveis de IA.
- `frontend/.env.example`: `NEXT_PUBLIC_API_URL` e `NEXT_PUBLIC_APP_NAME`.

Locais e ignorados pelo Git, já existentes e não sobrescritos:

- `.env`
- `backend/.env`
- `frontend/.env.local`

`AI_API_KEY` está vazio. O provedor padrão é `openai-compatible`, a URL padrão aponta para `http://127.0.0.1:11434/v1` e o nome de modelo padrão é `llama3.1`. Nenhum servidor de modelo foi contactado.

### Git e .gitignore

O repositório já estava inicializado. `git status` mostra a branch `main` sem commits e os arquivos do projeto ainda não rastreados. Nenhum commit e nenhum push foram feitos.

O `.gitignore` da raiz ignora `.venv/`, `node_modules/`, `.next/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `coverage/`, `dist/`, `build/`, arquivos `.env` (com exceção de `.env.example`), temporários, e o conteúdo de `storage/uploads`, `storage/resumes`, `storage/generated` e `storage/temporary`, preservando os `.gitkeep`.

## 12.6. Testes executados

| Teste | Resultado | Observação |
| --- | --- | --- |
| Instalação Python | APROVADO | `py -3.13` e `backend\.venv` em Python 3.13.17. `uv sync --python 3.13` saiu com código 0. |
| Dependências Python | APROVADO | Importação de FastAPI, Uvicorn, SQLAlchemy, Pydantic, Pydantic Settings, Alembic, HTTPX, Psycopg, Python Multipart, PyMuPDF, python-docx, docxtpl, Pillow, OpenAI, Sentence Transformers, Celery e Redis. Saída: `imports-ok`. |
| Ruff | APROVADO | `uv run ruff check .` em `backend`: `All checks passed!` |
| Pytest | APROVADO | `uv run pytest`: 1 teste aprovado em 0,92 s. Cobertura medida do pacote `app`: 67%. O teste cobre `GET /health`. |
| TypeScript | APROVADO | `npx tsc --noEmit` em `frontend` saiu com código 0. |
| ESLint | APROVADO | `npm run lint` saiu com código 0. |
| Build Next.js | APROVADO | `npm run build`: Next.js 16.4.6 compilou e gerou as rotas estáticas `/` e `/_not-found`. |
| Docker Compose | APROVADO | `docker compose config` saiu com código 0. `scripts\dev.ps1` encontrou os dois containers em execução e saudáveis. |
| PostgreSQL | APROVADO | Container `vaganexo-postgres` healthy. Publicação `127.0.0.1:5433->5432/tcp`. `postgres --version`: PostgreSQL 17.12. |
| pgvector | APROVADO | Extensão `vector` versão 0.8.7 presente no banco `vaganexo`. |
| Redis | APROVADO | Container `vaganexo-redis` healthy em `127.0.0.1:6379`. `redis-cli ping` retornou `PONG`. Servidor 7.4.12. |
| FastAPI /health | APROVADO | Uvicorn em `127.0.0.1:8000` respondeu HTTP 200 com `{"status":"healthy","application":"VagaNexo AI"}`. O processo foi encerrado após o teste. A porta 8000 ficou livre. |

Verificações adicionais, fora da tabela obrigatória:

- `uv run mypy app`: `Success: no issues found in 22 source files`.
- `powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1 -RequireRunning`: concluído sem falhas.
- `powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1`: código 0. Os três arquivos de ambiente locais já existiam e não foram sobrescritos.
- `powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1`: código 0.

## 12.7. Problemas e soluções

### uv ausente no PATH da sessão inicial

Mensagem: `O termo 'uv' não é reconhecido como nome de cmdlet`.

Causa: o executável já estava instalado pelo winget, e o diretório já estava no PATH do usuário, mas a sessão PowerShell inicial não tinha esse diretório carregado.

Solução: o caminho do `uv.exe` foi usado diretamente e o PATH da sessão foi recarregado. `uv --version` passou a retornar 0.13.10. `scripts\setup.ps1` também localizou o uv pela função `Resolve-Uv` e concluiu com sucesso. Não houve nova instalação.

### Porta 5432 ocupada no host

Mensagem observada no ambiente: a porta 5432 está em escuta pelo processo `postgres`, PID 6236. O container do projeto está em `127.0.0.1:5433`.

Causa: outro PostgreSQL local já usa a porta pedida como padrão.

Solução já presente e mantida: `POSTGRES_PORT=5433` no `.env` da raiz e a mesma porta na `DATABASE_URL` do backend. Os scripts `dev.ps1` e o README descrevem esse ajuste. O processo da porta 5432 não foi interrompido.

### winget fora do PATH da primeira consulta

Mensagem: `O termo 'winget' não é reconhecido`.

Causa: o executável existe em `%LOCALAPPDATA%\Microsoft\WindowsApps\winget.exe`, mas não estava disponível para o primeiro comando. Como Python 3.13, uv, Node.js, npm, Git e Docker já estavam instalados, o winget não foi necessário.

Pendências não resolvidas: nenhuma falha de teste obrigatório permaneceu aberta. A ocupação da porta 5432 por outro PostgreSQL continua e é uma condição externa aceita.

## 12.8. Arquivos pendentes de configuração

- `.env`, `backend/.env` e `frontend/.env.local` já existem nesta máquina e estão fora do Git. Em outro computador, executar `scripts\setup.ps1` para copiá-los dos exemplos e gerar uma senha exclusiva de desenvolvimento.
- `AI_API_KEY` permanece vazio de propósito. Preencher somente quando o provedor escolhido exigir chave. Não colocar esse valor em arquivo versionado.
- `AI_BASE_URL` e `AI_MODEL` usam os padrões de desenvolvimento. Ajustar quando for conectar Ollama, LM Studio ou outro servidor compatível com a API da OpenAI.
- O repositório ainda não tem commit. Revisar a árvore e criar o commit manualmente quando desejado.
- Se a porta 5432 for liberada e o projeto precisar voltar a ela, alterar `POSTGRES_PORT` e a porta de `DATABASE_URL` juntos, depois recriar a publicação com `scripts\dev.ps1`.

## 12.9. Instruções de execução

Iniciar Docker, na raiz do repositório, com o Docker Desktop já em execução:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1
```

Iniciar o backend, em outro terminal:

```powershell
cd backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Iniciar o frontend, em outro terminal:

```powershell
cd frontend
npm run dev
```

Executar os testes:

```powershell
cd backend
uv run pytest
uv run ruff check .
uv run mypy app
cd ..\frontend
npm run lint
npx tsc --noEmit
npm run build
```

Verificar os serviços:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1 -RequireRunning
docker compose --env-file .env -f infrastructure\compose.yaml ps
```

O health check da API fica em `http://127.0.0.1:8000/health`. PostgreSQL local: `127.0.0.1:5433`. Redis local: `127.0.0.1:6379`.

## 12.10. Conclusão técnica

CONCLUÍDA.

A estrutura, os lockfiles, os arquivos de ambiente de exemplo, o ambiente virtual e os serviços Docker estavam íntegros. A validação executada nesta sessão aprovou Python, dependências, Ruff, Pytest, TypeScript, ESLint, build do Next.js, Docker Compose, PostgreSQL, pgvector, Redis e `GET /health`. O Mypy e os três scripts PowerShell também terminaram sem falha. A porta 5432 do host permanece com outro PostgreSQL; o banco do projeto funciona em `127.0.0.1:5433`, com a extensão `vector` 0.8.7.
