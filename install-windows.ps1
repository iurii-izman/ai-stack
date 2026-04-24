$ErrorActionPreference = "Stop"

function New-HexSecret {
    param([int]$Bytes = 24)

    $buffer = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($buffer)
    $rng.Dispose()
    return ([System.BitConverter]::ToString($buffer) -replace "-", "").ToLowerInvariant()
}

Write-Host "Preparing AI Stack workspace..." -ForegroundColor Cyan

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI not found. Install Docker Desktop first."
}

docker compose version | Out-Null

if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Write-Host "Ollama detected." -ForegroundColor Green
} else {
    Write-Host "Ollama not found. Install it separately if you want the optional local model fallback." -ForegroundColor Yellow
}

New-Item -ItemType Directory -Force -Path ".\backups", ".\config", ".\data" | Out-Null

if (-not (Test-Path ".env")) {
    $litellmKey = "sk-$(New-HexSecret 16)"
    $webuiSecret = New-HexSecret 32
    $postgresPassword = New-HexSecret 24

    @"
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
OPENROUTER_API_KEY=
LITELLM_KEY=$litellmKey
WEBUI_SECRET_KEY=$webuiSecret
POSTGRES_USER=postgres
POSTGRES_DB=postgres
POSTGRES_PASSWORD=$postgresPassword
DATABASE_HOST=postgres
DATABASE_PORT=5432
DATABASE_NAME=postgres
DATABASE_USER=postgres
DATABASE_USERNAME=postgres
DATABASE_PASSWORD=$postgresPassword
DATABASE_SCHEMA=public
DATABASE_URL=postgresql://postgres:$postgresPassword@postgres:5432/postgres
WEBUI_ADMIN_EMAIL=
WEBUI_ADMIN_PASSWORD=
WEBUI_ADMIN_NAME=Admin
"@ | Set-Content -Path ".env" -NoNewline

    Write-Host "Created .env with generated local secrets." -ForegroundColor Green
} else {
    Write-Host ".env already exists; leaving it unchanged." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Add any cloud API keys you want to use to .env"
Write-Host "2. Start the core stack: .\stack.ps1 start core"
Write-Host "3. Start Open WebUI when needed: .\stack.ps1 start ui"
Write-Host "4. Run doctor: .\stack.ps1 doctor"
Write-Host "5. Run smoke checks: .\stack.ps1 smoke"
Write-Host ""
Write-Host "Optional local Ollama model: ollama pull qwen2.5-coder:1.5b"
