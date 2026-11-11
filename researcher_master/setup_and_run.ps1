<#
  One-click setup and run: install dependencies (including DDGS),
  initialize DB, bootstrap retriever, then start the app.
  Use this to get the product running from scratch.

  Usage (PowerShell):
    .\setup_and_run.ps1
#>
param()

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Push-Location $scriptDir
$env:PYTHONPATH = $scriptDir

# Create venv if missing
if (-not (Test-Path ".venv")) {
  Write-Host "Creating virtual environment..."
  python -m venv .venv
}

Write-Host "Installing dependencies into .venv (including DDGS search client)..."
$venvPython = Join-Path $scriptDir '.venv\Scripts\python.exe'
& $venvPython -m pip install --upgrade pip -q
& $venvPython -m pip install -r requirements.txt

Write-Host "Initializing DB (chunks, KG, memory, queues)..."
& $venvPython -c "from src.storage.db import init_db; init_db(); print('DB ready')"

Write-Host "Bootstrapping retriever index (sample docs)..."
& $venvPython -m src.scripts.bootstrap_index

Write-Host ""
Write-Host "Setup complete. Starting Researcher-Master on http://127.0.0.1:8000"
Write-Host "  Dashboard:  http://127.0.0.1:8000/"
Write-Host "  Chat:       http://127.0.0.1:8000/static/chat.html"
Write-Host "  Agent activity tab shows crawling and learning in real time."
Write-Host ""
& $venvPython -m uvicorn src.app.main:app --reload --host 127.0.0.1 --port 8000
Pop-Location
