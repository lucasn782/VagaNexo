#Requires -Version 5.1
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $PSScriptRoot

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
    Write-Host "OK   $Message" -ForegroundColor Green
}

function Fail([string]$Message) {
    Write-Host "ERRO $Message" -ForegroundColor Red
    exit 1
}

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Resolve-Uv {
    $command = Get-Command uv -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidate = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe"
    if (Test-Path $candidate) {
        return $candidate
    }

    return $null
}

function New-DevPassword {
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $bytes = New-Object byte[] 32
    $rng.GetBytes($bytes)
    $password = ([Convert]::ToBase64String($bytes) -replace "[^a-zA-Z0-9]", "")
    return $password.Substring(0, 24)
}

function Read-EnvValue([string]$Path, [string]$Name) {
    if (-not (Test-Path $Path)) {
        return $null
    }

    $prefix = $Name + "="
    foreach ($line in Get-Content -Path $Path -Encoding UTF8) {
        if ($line.StartsWith($prefix)) {
            return $line.Substring($prefix.Length)
        }
    }

    return $null
}

function Read-DatabasePassword([string]$Path) {
    $url = Read-EnvValue $Path "DATABASE_URL"
    if (-not $url) {
        return $null
    }

    $scheme = $url.IndexOf("://")
    $at = $url.LastIndexOf("@")
    if ($scheme -lt 0 -or $at -lt 0 -or $at -le $scheme) {
        return $null
    }

    $userInfo = $url.Substring($scheme + 3, $at - ($scheme + 3))
    $colon = $userInfo.IndexOf(":")
    if ($colon -lt 0) {
        return $null
    }

    return $userInfo.Substring($colon + 1)
}

function Copy-EnvIfMissing([string]$Example, [string]$Destination, [bool]$ReplacePassword, [string]$Password) {
    if (Test-Path $Destination) {
        Write-Ok "Ja existe: $Destination"
        return
    }

    if (-not (Test-Path $Example)) {
        Fail "Arquivo de exemplo ausente: $Example"
    }

    $content = [System.IO.File]::ReadAllText($Example)
    if ($ReplacePassword) {
        $content = $content.Replace("change-me", $Password)
    }

    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($Destination, $content, $utf8)
    Write-Ok "Criado: $Destination"
}

Refresh-Path
Write-Step "Verificando ferramentas"

foreach ($tool in @("git", "node", "npm", "docker")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Fail "Ferramenta ausente: $tool"
    }
    Write-Ok $tool
}

$nodeVersion = (& node -v).Trim().TrimStart("v")
$nodeMajor = [int]($nodeVersion.Split(".")[0])
if ($nodeMajor -lt 20) {
    Fail "Node.js 20 ou superior e necessario. Versao atual: $nodeVersion"
}
Write-Ok "Node.js $nodeVersion"

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Fail "Python launcher ausente. Instale Python 3.13 com: winget install --id Python.Python.3.13 --scope user"
}

& py -3.13 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)"
if ($LASTEXITCODE -ne 0) {
    Fail "Python 3.13 ausente. Instale com: winget install --id Python.Python.3.13 --scope user"
}
Write-Ok "Python 3.13"

$uv = Resolve-Uv
if (-not $uv) {
    Fail "uv ausente. Instale com: winget install --id astral-sh.uv --scope user"
}
Write-Ok "uv"

$gitDir = Join-Path $RepoRoot ".git"
if (-not (Test-Path $gitDir)) {
    Write-Step "Inicializando repositorio Git"
    & git init $RepoRoot
    if ($LASTEXITCODE -ne 0) {
        Fail "git init falhou."
    }
    Write-Ok "Repositorio Git criado"
}

Write-Step "Preparando arquivos de ambiente"

$rootEnv = Join-Path $RepoRoot ".env"
$backendEnv = Join-Path $RepoRoot "backend\.env"
$frontendEnv = Join-Path $RepoRoot "frontend\.env.local"
$password = Read-EnvValue $rootEnv "POSTGRES_PASSWORD"
if (-not $password -or $password -eq "change-me") {
    $existingDatabasePassword = Read-DatabasePassword $backendEnv
    if ($existingDatabasePassword -and $existingDatabasePassword -ne "change-me") {
        $password = $existingDatabasePassword
    }
    else {
        $password = New-DevPassword
    }
}

Copy-EnvIfMissing (Join-Path $RepoRoot ".env.example") $rootEnv $true $password
Copy-EnvIfMissing (Join-Path $RepoRoot "backend\.env.example") $backendEnv $true $password
Copy-EnvIfMissing (Join-Path $RepoRoot "frontend\.env.example") $frontendEnv $false $password

$rootPassword = Read-EnvValue $rootEnv "POSTGRES_PASSWORD"
$databasePassword = Read-DatabasePassword $backendEnv
if ($rootPassword -and $databasePassword -and $rootPassword -ne $databasePassword) {
    Fail "POSTGRES_PASSWORD e a senha de DATABASE_URL estao diferentes. Alinhe os arquivos .env sem apagar os demais valores."
}
Write-Ok "Senha local do PostgreSQL alinhada entre a raiz e o backend"

Write-Step "Instalando dependencias Python"
$env:UV_LINK_MODE = "copy"
Push-Location (Join-Path $RepoRoot "backend")
try {
    & $uv sync --python 3.13
    if ($LASTEXITCODE -ne 0) {
        Fail "uv sync falhou."
    }
}
finally {
    Pop-Location
}
Write-Ok "uv sync"

Write-Step "Instalando dependencias Node.js"
$packageJson = Join-Path $RepoRoot "frontend\package.json"
if (-not (Test-Path $packageJson)) {
    Fail "frontend\package.json nao encontrado."
}

Push-Location (Join-Path $RepoRoot "frontend")
try {
    & npm install
    if ($LASTEXITCODE -ne 0) {
        Fail "npm install falhou."
    }
}
finally {
    Pop-Location
}
Write-Ok "npm install"

Write-Step "Ambiente preparado"
Write-Host "Proximo passo: powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1"
