# ==========================================================
# Start Python MCP AI Service (local, no Docker)
# Usage (PowerShell, project root): .\deploy\start-python-local.ps1
# First run will create .venv and install requirements (heavy, be patient)
# Requires: Python 3.11 (py -3.11)
# ==========================================================
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$PySvc = Join-Path $Root 'python-mcp-service'
$Venv  = Join-Path $PySvc '.venv'

Write-Host "[1/4] Check Python 3.11 ..." -ForegroundColor Cyan
py -3.11 --version

if (-not (Test-Path $Venv)) {
    Write-Host "[2/4] Create venv .venv ..." -ForegroundColor Cyan
    py -3.11 -m venv $Venv
} else {
    Write-Host "[2/4] Reuse existing .venv" -ForegroundColor Cyan
}

$Py = Join-Path $Venv 'Scripts\python.exe'
Write-Host "[3/4] Install requirements.txt ..." -ForegroundColor Cyan
& $Py -m pip install --upgrade pip
& $Py -m pip install -r (Join-Path $PySvc 'requirements.txt')

Write-Host "[4/4] Start MCP Server (SSE :8000, Ctrl+C to stop) ..." -ForegroundColor Green
$env:MCP_TRANSPORT       = 'sse'
$env:MCP_HTTP_HOST       = '0.0.0.0'
$env:MCP_HTTP_PORT       = '8000'
$env:CALLBACK_BASE_URL   = if ($env:CALLBACK_BASE_URL) { $env:CALLBACK_BASE_URL } else { 'http://localhost:8080' }
$env:INTERNAL_API_KEY    = if ($env:INTERNAL_API_KEY) { $env:INTERNAL_API_KEY } else { 'internal-secret-key-2026' }
if (-not $env:LLM_API_KEY) { Write-Host "  WARNING: LLM_API_KEY not set, will run in offline mode (no real LLM analysis)." -ForegroundColor Yellow }

Set-Location $PySvc
& $Py -m app.server
