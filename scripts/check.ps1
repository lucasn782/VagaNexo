#Requires -Version 5.1
param(
    [switch]$RequireRunning
)

$ErrorActionPreference = "Continue"
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $PSScriptRoot
$failures = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]

function Write-Ok([string]$Message) {
    Write-Host "OK   $Message" -ForegroundColor Green
}

function Add-Failure([string]$Message) {
    $script:failures.Add($Message)
    Write-Host "ERRO $Message" -ForegroundColor Red
}

function Add-Warning([string]$Message) {
    $script:warnings.Add($Message)
    Write-Host "AVISO $Message" -ForegroundColor Yellow
}

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Test-File([string]$RelativePath) {
    $path = Join-Path $RepoRoot $RelativePath
    if (-not (Test-Path $path)) {
        Add-Failure "Arquivo ausente: $RelativePath"
        return
    }

    $item = Get-Item $path
    if (-not $item.PSIsContainer -and $item.Length -eq 0 -and $RelativePath -notlike "*__init__.py" -and $RelativePath -notlike "*.gitkeep") {
        Add-Failure "Arquivo vazio: $RelativePath"
        return
    }

    Write-Ok $RelativePath
}

Refresh-Path
Write-Host "==> Python" -ForegroundColor Cyan

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Add-Failure "Python launcher (py) nao encontrado."
}
else {
    & py -3.13 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)"
    if ($LASTEXITCODE -eq 0) {
        $pyVersion = & py -3.13 -c "import sys; print(sys.version.split()[0])"
        Write-Ok "Python $pyVersion"
    }
    else {
        Add-Failure "Python 3.13 nao esta instalado."
    }
}

Write-Host "==> Ambiente virtual" -ForegroundColor Cyan
$venvPython = Join-Path $RepoRoot "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Add-Failure "Ambiente virtual ausente: backend\.venv"
}
else {
    & $venvPython -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)"
    if ($LASTEXITCODE -eq 0) {
        $venvVersion = & $venvPython -c "import sys; print(sys.version.split()[0])"
        Write-Ok "backend\.venv usa Python $venvVersion"
    }
    else {
        Add-Failure "backend\.venv nao usa Python 3.13."
    }
}

Write-Host "==> Dependencias Python" -ForegroundColor Cyan
if ((Test-Path $venvPython) -and (Test-Path (Join-Path $RepoRoot "backend\uv.lock"))) {
    & $venvPython -c @"
import importlib
import sys
modules = [
    'fastapi',
    'uvicorn',
    'sqlalchemy',
    'pydantic',
    'pydantic_settings',
    'alembic',
    'httpx',
    'psycopg',
    'multipart',
    'pymupdf',
    'docx',
    'docxtpl',
    'PIL',
    'openai',
    'sentence_transformers',
    'celery',
    'redis',
]
failed = []
for name in modules:
    try:
        importlib.import_module(name)
    except Exception as exc:
        failed.append(f'{name}: {exc}')
if failed:
    print('\n'.join(failed))
    sys.exit(1)
print('imports-ok')
"@
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "Importacoes Python"
    }
    else {
        Add-Failure "Falha ao importar dependencias Python."
    }
}
else {
    Add-Failure "uv.lock ou o ambiente virtual ainda nao foram gerados. Execute scripts\setup.ps1."
}

Write-Host "==> Dependencias Node.js" -ForegroundColor Cyan
$packageJsonPath = Join-Path $RepoRoot "frontend\package.json"
$packageLockPath = Join-Path $RepoRoot "frontend\package-lock.json"
$nodeModulesPath = Join-Path $RepoRoot "frontend\node_modules"
if (-not (Test-Path $packageJsonPath) -or -not (Test-Path $packageLockPath) -or -not (Test-Path $nodeModulesPath)) {
    Add-Failure "Dependencias Node ausentes. Execute scripts\setup.ps1."
}
else {
    $packageJson = Get-Content $packageJsonPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $installed = @{}
    foreach ($collection in @($packageJson.dependencies, $packageJson.devDependencies)) {
        if ($null -eq $collection) {
            continue
        }
        foreach ($property in $collection.PSObject.Properties) {
            $installed[$property.Name] = $true
        }
    }

    $requiredNode = @(
        "next",
        "react",
        "react-dom",
        "typescript",
        "tailwindcss",
        "zod",
        "react-hook-form",
        "@hookform/resolvers",
        "lucide-react",
        "sonner",
        "clsx",
        "tailwind-merge",
        "class-variance-authority",
        "eslint"
    )
    $missingNode = @($requiredNode | Where-Object { -not $installed.ContainsKey($_) })
    if ($missingNode.Count -gt 0) {
        Add-Failure ("Pacotes Node ausentes no package.json: " + ($missingNode -join ", "))
    }
    else {
        Write-Ok "package.json contem os pacotes exigidos"
    }

    Push-Location (Join-Path $RepoRoot "frontend")
    try {
        & npm ls --depth=0 1>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "npm ls"
        }
        else {
            Add-Failure "npm ls encontrou dependencias Node inconsistentes."
        }
    }
    finally {
        Pop-Location
    }
}

Write-Host "==> Docker, PostgreSQL e Redis" -ForegroundColor Cyan
$composeFile = Join-Path $RepoRoot "infrastructure\compose.yaml"
$envFile = Join-Path $RepoRoot ".env"
if (-not (Test-Path $composeFile)) {
    Add-Failure "infrastructure\compose.yaml ausente."
}
else {
    $composeText = Get-Content $composeFile -Raw -Encoding UTF8
    $expectedSnippets = @(
        "pgvector/pgvector:pg17",
        "redis:7-alpine",
        "127.0.0.1:",
        "vaganexo_postgres_data",
        "unless-stopped"
    )
    foreach ($snippet in $expectedSnippets) {
        if ($composeText -notlike "*$snippet*") {
            Add-Failure "compose.yaml nao contem: $snippet"
        }
    }
    if ($composeText -like "*0.0.0.0:*") {
        Add-Failure "compose.yaml publica alguma porta em 0.0.0.0."
    }
    else {
        Write-Ok "compose.yaml restringe as portas a localhost"
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Add-Failure "Docker nao encontrado no PATH."
}
elseif (-not (Test-Path $envFile)) {
    Add-Failure "Arquivo .env ausente. Ele e necessario para validar o Compose."
}
else {
    docker compose --env-file $envFile -f $composeFile config 1>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "docker compose config"
    }
    else {
        Add-Failure "docker compose config falhou."
    }

    docker info 1>$null 2>$null
    $daemonUp = $LASTEXITCODE -eq 0
    if (-not $daemonUp) {
        $message = "Docker Desktop nao esta em execucao. A configuracao foi lida, mas os servicos nao foram testados."
        if ($RequireRunning) {
            Add-Failure $message
        }
        else {
            Add-Warning $message
        }
    }
    elseif ($RequireRunning) {
        foreach ($container in @("vaganexo-postgres", "vaganexo-redis")) {
            $status = docker inspect --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}" $container 2>$null
            if ($LASTEXITCODE -ne 0) {
                Add-Failure "Container ausente: $container. Execute scripts\dev.ps1."
            }
            elseif ($status -ne "healthy") {
                Add-Failure "Container $container esta com health '$status'."
            }
            else {
                Write-Ok "$container healthy"
            }
        }

        $dbUser = "vaganexo"
        $dbName = "vaganexo"
        foreach ($line in Get-Content $envFile -Encoding UTF8) {
            if ($line.StartsWith("POSTGRES_USER=")) {
                $dbUser = $line.Substring(14)
            }
            if ($line.StartsWith("POSTGRES_DB=")) {
                $dbName = $line.Substring(12)
            }
        }

        $extension = docker exec vaganexo-postgres psql -U $dbUser -d $dbName -tAc "SELECT extname FROM pg_extension WHERE extname = 'vector';" 2>$null
        if ($LASTEXITCODE -eq 0 -and $extension.Trim() -eq "vector") {
            Write-Ok "Extensao pgvector instalada em $dbName"
        }
        else {
            Add-Failure "Nao foi possivel confirmar a extensao pgvector."
        }

        $ping = docker exec vaganexo-redis redis-cli ping 2>$null
        if ($LASTEXITCODE -eq 0 -and $ping.Trim() -eq "PONG") {
            Write-Ok "Redis respondeu PONG"
        }
        else {
            Add-Failure "Redis nao respondeu PONG."
        }
    }
    else {
        Add-Warning "Servicos nao foram consultados. Use -RequireRunning depois de scripts\dev.ps1."
    }
}

Write-Host "==> Integridade dos arquivos" -ForegroundColor Cyan
$requiredFiles = @(
    ".gitignore",
    ".editorconfig",
    ".env.example",
    "README.md",
    "LICENSE",
    "backend\pyproject.toml",
    "backend\uv.lock",
    "backend\alembic.ini",
    "backend\.python-version",
    "backend\.env.example",
    "backend\app\main.py",
    "frontend\package.json",
    "frontend\package-lock.json",
    "frontend\tsconfig.json",
    "frontend\.env.example",
    "frontend\components.json",
    "infrastructure\compose.yaml",
    "infrastructure\docker\postgres\init\001_pgvector.sql",
    "scripts\setup.ps1",
    "scripts\dev.ps1",
    "scripts\check.ps1"
)
foreach ($relativePath in $requiredFiles) {
    Test-File $relativePath
}

Write-Host ""
if ($warnings.Count -gt 0) {
    Write-Host ("Avisos: " + $warnings.Count) -ForegroundColor Yellow
}
if ($failures.Count -gt 0) {
    Write-Host ("Falhas: " + $failures.Count) -ForegroundColor Red
    exit 1
}

Write-Host "Verificacao concluida sem falhas." -ForegroundColor Green
exit 0
