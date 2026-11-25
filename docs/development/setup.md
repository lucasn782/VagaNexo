# Ambiente de desenvolvimento

Execute os comandos na raiz do repositório, no PowerShell.

## Preparar

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

O script não apaga arquivos, não remove volumes e não reinicia o computador. Se Python 3.13 ou uv estiverem ausentes, a mensagem indica o pacote winget correspondente.

## Subir PostgreSQL e Redis

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1
```

O script mostra os comandos do backend e do frontend. Cada um deles fica em um terminal separado.

O PostgreSQL do Compose escuta em `127.0.0.1` na porta definida por `POSTGRES_PORT`. O padrão é `5432`. Se essa porta já estiver ocupada, altere `POSTGRES_PORT` no `.env` da raiz e a porta de `DATABASE_URL` no `backend/.env` para o mesmo valor livre.

## Verificar

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1 -RequireRunning
```

Sem `-RequireRunning`, o script valida arquivos, dependências e a configuração do Compose. Com `-RequireRunning`, PostgreSQL, Redis e a extensão `vector` também precisam estar saudáveis.

## Recriar dependências

Backend:

```powershell
cd backend
uv sync
```

Frontend:

```powershell
cd frontend
npm ci
```

`uv.lock` e `package-lock.json` fixam as versões instaladas.
