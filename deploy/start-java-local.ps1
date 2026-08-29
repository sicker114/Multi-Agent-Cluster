# ==========================================================
# Start Java Main Service (local, no Docker)
# Usage (PowerShell, project root): .\deploy\start-java-local.ps1
# Requires: MySQL8 ready + schema.sql imported, mvn package done
# ==========================================================
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Jar  = Join-Path $Root 'java-service\target\enterprise-agent-service.jar'

if (-not $env:JAVA_HOME) { $env:JAVA_HOME = 'D:\Java\jdk-17' }
Write-Host "JAVA_HOME = $env:JAVA_HOME" -ForegroundColor Cyan

if (-not (Test-Path $Jar)) {
    Write-Host "Jar not found, running mvn package ..." -ForegroundColor Yellow
    & 'D:\IntelliJ IDEA 2025.2.1\apache-maven-3.9.4\bin\mvn.cmd' -q -DskipTests -f (Join-Path $Root 'java-service\pom.xml') clean package
}

# ---- Runtime env vars (override as needed) ----
$env:MYSQL_HOST        = if ($env:MYSQL_HOST)      { $env:MYSQL_HOST }      else { 'localhost' }
$env:MYSQL_PORT        = if ($env:MYSQL_PORT)      { $env:MYSQL_PORT }      else { '3306' }
$env:MYSQL_USER        = if ($env:MYSQL_USER)      { $env:MYSQL_USER }      else { 'root' }
$env:MYSQL_PASSWORD    = if ($env:MYSQL_PASSWORD)  { $env:MYSQL_PASSWORD }  else { 'root123456' }
$env:MCP_SERVER_URL    = if ($env:MCP_SERVER_URL)  { $env:MCP_SERVER_URL }  else { 'http://localhost:8000' }
$env:INTERNAL_API_KEY  = if ($env:INTERNAL_API_KEY){ $env:INTERNAL_API_KEY }else { 'internal-secret-key-2026' }
$env:CALLBACK_BASE_URL = if ($env:CALLBACK_BASE_URL){ $env:CALLBACK_BASE_URL } else { 'http://localhost:8080' }
if (-not $env:LLM_API_KEY) { Write-Host "  WARNING: LLM_API_KEY not set, ChatClient needs it." -ForegroundColor Yellow }

Write-Host "Start Java Service (:8080, Ctrl+C to stop) ..." -ForegroundColor Green
& "$env:JAVA_HOME\bin\java.exe" -jar $Jar
