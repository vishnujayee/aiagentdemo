# HOW_TO_RUN

## 1. First-time setup

```powershell
cd d:\Projects\aiagentdemo\researcher_master
.\setup_and_run.ps1
```

This creates `.venv`, installs dependencies, initializes DB/index, and starts API/UI.

## 2. Local LLM (Ollama) setup

Install Ollama (Windows):

```powershell
winget install --id Ollama.Ollama -e --accept-package-agreements --accept-source-agreements
```

Pull a free strong local model:

```powershell
& 'C:\Users\jayee\AppData\Local\Programs\Ollama\ollama.exe' pull qwen2.5:3b
```

Verify Ollama server + model:

```powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 11434
& 'C:\Users\jayee\AppData\Local\Programs\Ollama\ollama.exe' list
```

Expected model: `qwen2.5:3b`.

## 3. Environment config

Create `.env` (or update it) with:

```env
LLM_BACKEND=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:3b
VECTOR_BACKEND=auto
USE_DUCKDUCKGO=1
CRAWL_MAX_RESULTS=100
DEFAULT_CRAWL_DELAY=0.0
```

## 4. Start app manually (after setup)

```powershell
cd d:\Projects\aiagentdemo\researcher_master
.\run_local.ps1
```

## 5. Verify core stack

Run smoke test:

```powershell
cd d:\Projects\aiagentdemo\researcher_master
$env:PYTHONPATH = (Get-Location).Path
.\.venv\Scripts\python.exe run_smoke_test.py
```

## 6. Verify from UI (recommended)

Open:

- `http://127.0.0.1:8000/`

In **System** tab:

1. Click `LLM check`.
2. Confirm backend is `OllamaLLM` .
3. Enter topic and click `Deep Learn + Build KG`.

In other tabs:

1. **Discover & Crawl**: verify real web sources are queued.
2. **Knowledge Graph**: load KG / open D3 view.
3. **System -> Memory**: add/query memory entries.
4. **Chat & Ask**: ask topic questions and verify returned sources.

## 7. API checks (optional)

```powershell
# LLM health
curl -Method Post -Uri http://127.0.0.1:8000/admin/llm/check -ContentType application/json -Body '{"prompt":"Reply: local ok"}'

# Deep learning cycle
curl -Method Post -Uri http://127.0.0.1:8000/admin/learn/deep -ContentType application/json -Body '{"topic":"reinforcement learning","max_queries":5,"max_learn_sources":30,"build_kg":true}'
```

## 8. Typical operational flow

1. Run `Deep Learn + Build KG` for a domain/topic.
2. Review `Discover` queue (accept/reject as needed).
3. Rebuild/refresh pipeline if required.
4. Ask complex questions in `Chat & Ask`.
5. Inspect memory, KG, and activity logs for traceability.
