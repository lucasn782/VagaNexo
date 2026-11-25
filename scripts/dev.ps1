#Requires -Version 5.1
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $PSScriptRoot

function Fail([string]$Message) {
    Write-Host "ERRO $Message" -ForegroundColor Red
    exit 1
}

function Read-EnvValue([string]$Path, [string]$Name) {
    $prefix = $Name + "="
    foreach ($line in Get-Content -Path $Path -Encoding UTF8) {
        if ($line.StartsWith($prefix)) {
            return $line.Substring($prefix.Length).Trim()
        }
    }

    return $null
}

function Test-LocalPort([string]$Port) {
    $pattern = ":" + $Port + "\s"
    $listening = netstat -ano | Select-String "LISTENING" | Select-String $pattern
    return $null -ne $listening
}

$envFile = Join-Path $RepoRoot ".env"
$composeFile = Join-Path $RepoRoot "infrastructure\compose.yaml"

if (-not (Test-Path $envFile)) {
    Fail "Arquivo .env ausente. Execute: powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1"
}

if (-not (Test-Path $composeFile)) {
    Fail "Arquivo ausente: infrastructure\compose.yaml"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail "Docker nao encontrado no PATH."
}

docker info 1>$null 2>$null
if ($LASTEXITCODE -ne 0) {
    Fail "Docker Desktop nao esta em execucao. Abra o Docker Desktop, aguarde o daemon e execute este script de novo."
}

$postgresPort = Read-EnvValue $envFile "POSTGRES_PORT"
if (-not $postgresPort) {
    $postgresPort = "5432"
}

$postgresAlreadyRunning = docker ps --filter "name=^vaganexo-postgres$" --filter "status=running" --format "{{.Names}}"
if ($LASTEXITCODE -ne 0) {
    Fail "Nao foi possivel consultar o container vaganexo-postgres."
}

if (-not $postgresAlreadyRunning -and (Test-LocalPort $postgresPort)) {
    Fail "A porta local $postgresPort ja esta em uso. Ajuste POSTGRES_PORT no .env da raiz e a mesma porta em DATABASE_URL no backend\.env, ou libere a porta. O servico Windows postgresql-x64-17 costuma ocupar a 5432."
}

Write-Host "==> Iniciando PostgreSQL e Redis" -ForegroundColor Cyan
docker compose --env-file $envFile -f $composeFile up -d
if ($LASTEXITCODE -ne 0) {
    Fail "docker compose up falhou."
}

docker compose --env-file $envFile -f $composeFile ps
if ($LASTEXITCODE -ne 0) {
    Fail "docker compose ps falhou."
}

Write-Host ""
Write-Host "Servicos publicados somente em localhost." -ForegroundColor Green
Write-Host "PostgreSQL: 127.0.0.1:$postgresPort  (banco e usuario: vaganexo)"
Write-Host "Redis:      127.0.0.1:6379"
Write-Host ""
Write-Host "Backend, em outro terminal:" -ForegroundColor Cyan
Write-Host "  cd backend"
Write-Host "  uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
Write-Host ""
Write-Host "Frontend, em outro terminal:" -ForegroundColor Cyan
Write-Host "  cd frontend"
Write-Host "  npm run dev"
Write-Host ""
Write-Host "Health check: http://127.0.0.1:8000/health"
