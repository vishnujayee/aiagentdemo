# Researcher-Master

Local-first agentic AI prototype with retrieval, discovery, verification, and a FastAPI dashboard.

## What it does

- Answers questions with RAG: `POST /ask`
- Learns when knowledge is weak: `POST /ask_or_learn`
- Uses local LLM backends (lexical, Ollama, transformers) and optional OpenAI
- Stores knowledge in local SQLite + retriever index
- Supports discovery from Wikipedia and web search
- Runs planner/orchestrator/worker loops for autonomous cycles
- Includes UI tabs for chat, discovery, KG, review, pipeline, and system status

## Quick start (Windows PowerShell)

```powershell
cd d:\Projects\aiagentdemo\researcher_master
.\setup_and_run.ps1
```

Then open:

- `http://127.0.0.1:8000/` (main dashboard)
- `http://127.0.0.1:8000/health`

## Verify core functionality

```powershell
cd d:\Projects\aiagentdemo\researcher_master
$env:PYTHONPATH = (Get-Location).Path
.\.venv\Scripts\python.exe run_smoke_test.py
```

Fast mode (no heavy models):

```powershell
$env:SMOKE_FAST=1
.\.venv\Scripts\python.exe run_smoke_test.py
```

## Local run (after setup)

```powershell
.\run_local.ps1
```

or

```powershell
.\.venv\Scripts\python.exe -m uvicorn src.app.main:app --reload --host 127.0.0.1 --port 8000
```

## Main endpoints

- `GET /health`
- `POST /ask`
- `POST /ask_or_learn`
- `POST /api/agent/generate`
- `POST /api/agent/run_goal`
- `POST /admin/discover`
- `POST /admin/discover/accept`
- `POST /admin/run_pipeline`
- `GET /admin/system`

## Notes

- Copy `.env.example` to `.env` and adjust backend/env settings.
- For Ollama, run a local model and keep `OLLAMA_BASE_URL` reachable.
- This is a prototype; keep sandbox execution local-only.
