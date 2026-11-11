# RUNNING

Lightweight local run instructions.

## Prerequisites

- Python 3.10+
- Optional: Docker Desktop (sandbox experiments)

## Install

```powershell
cd d:\Projects\aiagentdemo\researcher_master
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Start app

```powershell
.\run_local.ps1
```

or

```powershell
$env:PYTHONPATH = (Get-Location).Path
.\.venv\Scripts\python.exe -m uvicorn src.app.main:app --reload --host 127.0.0.1 --port 8000
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Smoke check

```powershell
$env:SMOKE_FAST=1
.\.venv\Scripts\python.exe run_smoke_test.py
```
