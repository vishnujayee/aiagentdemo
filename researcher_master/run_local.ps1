<#
Lightweight startup script for local development on Windows (PowerShell).
This script initializes the DB, bootstraps the retriever index, then starts FastAPI.

Usage:
  .\run_local.ps1
#>
param()

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Push-Location $scriptDir

$venvPython = Join-Path $scriptDir '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
  Write-Error "Virtual environment not found at .venv. Run .\setup_and_run.ps1 first."
}

$env:PYTHONPATH = $scriptDir

Write-Host "Initializing DB (chunks, KG, memory, queues)..."
try {
  & $venvPython -c "from src.storage.db import init_db; init_db(); print('DB ready')"
} catch {
  Write-Warning "DB init failed: $_"
}

Write-Host "Bootstrapping retriever index (sample docs)..."
try {
  & $venvPython -m src.scripts.bootstrap_index
} catch {
  Write-Warning "Bootstrap script failed: $_"
}

Write-Host "Starting uvicorn on http://127.0.0.1:8000"
& $venvPython -m uvicorn src.app.main:app --reload --host 127.0.0.1 --port 8000

Pop-Location
