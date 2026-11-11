from fastapi import FastAPI, HTTPException, BackgroundTasks
from src.logging_config import configure_logging
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles


load_dotenv()

configure_logging()

app = FastAPI(title="Researcher-Master MVP")

# Allow basic CORS for local dev and the static UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Attempt to register improved verifier agent (if available) with the orchestrator.
try:
    from src.orchestrator import orchestrator
    from src.verifier.agent import verifier_agent as _improved_verifier
    try:
        orchestrator.register_agent("verifier", _improved_verifier)
    except Exception:
        pass
except Exception:
    pass

# serve static UI — resolve path so it works from any cwd
from pathlib import Path
_static_dir = Path(__file__).resolve().parent / "static"
if not _static_dir.exists():
    _static_dir = Path("src/app/static")
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/")
async def root():
    """Redirect to unified dashboard."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html", status_code=302)


@app.get("/review")
async def review_ui():
    return {"url": "/static/review.html"}

class AskRequest(BaseModel):
    question: str
    top_k: int = 5


class AskOrLearnRequest(BaseModel):
    question: str
    top_k: int = 5
    learn_if_unknown: bool = True
    max_learn_sources: int = 3


class GenerateRequest(BaseModel):
    prompt: str
    top_k: int = 0
    use_rag: bool = False


class RunGoalRequest(BaseModel):
    goal: str
    max_steps: int = 6

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/kg")
async def get_kg():
    kg_path = os.getenv("KG_OUT_PATH", "./data/kg.json")
    if not os.path.exists(kg_path):
        raise HTTPException(status_code=404, detail="KG not found. Build it with build_kg.py")
    import json
    with open(kg_path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/kg/mapping")
async def get_kg_mapping():
    mapping_path = os.getenv("KG_MAPPING_PATH", "./data/kg_mapping.json")
    import json
    # If a mapping file exists, return it. Otherwise attempt to build mapping and persist into DB.
    if os.path.exists(mapping_path):
        with open(mapping_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # mapping file missing: try to build mapping programmatically
    try:
        from src.kg.mapper import map_kg_to_chunks
        mapping = map_kg_to_chunks()
        # attempt to persist mapping into lightweight storage (optional)
        try:
            from src.storage.db import save_mapping
            for label, entry in mapping.items():
                try:
                    save_mapping(label, entry)
                except Exception:
                    # best-effort: continue if DB persistence fails
                    pass
        except Exception:
            pass
        # also write mapping file for faster subsequent loads
        os.makedirs(os.path.dirname(mapping_path), exist_ok=True)
        with open(mapping_path, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=2)
        return mapping
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build mapping: {e}")


@app.get("/kg/mapping/{label}")
async def get_kg_mapping_for_label(label: str):
    """Return mapping for a single KG node label. Tries DB first, then mapping file, then builds mapping on-demand."""
    # try DB
    try:
        from src.storage.db import get_mapping
        entry = get_mapping(label)
        if entry:
            return entry
    except Exception:
        pass

    # try file
    mapping_path = os.getenv("KG_MAPPING_PATH", "./data/kg_mapping.json")
    if os.path.exists(mapping_path):
        try:
            import json
            with open(mapping_path, "r", encoding="utf-8") as f:
                mapping = json.load(f)
            if label in mapping:
                return mapping[label]
        except Exception:
            pass

    # fallback: build full mapping and return single label
    try:
        from src.kg.mapper import map_kg_to_chunks
        mapping = map_kg_to_chunks()
        if label in mapping:
            return mapping[label]
        raise HTTPException(status_code=404, detail="Label not found in KG mapping")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build mapping: {e}")


@app.get("/review/queue")
async def get_review_queue():
    try:
        from src.storage.db import get_review_queue
        q = get_review_queue()
        return {"queue": q}
    except Exception:
        # fallback to file-based queue
        review_path = os.getenv("REVIEW_QUEUE_PATH", "./data/review_queue.json")
        import json
        if not os.path.exists(review_path):
            return {"queue": []}
        with open(review_path, "r", encoding="utf-8") as f:
            return json.load(f)


class ReviewMark(BaseModel):
    index: int


@app.post("/review/mark")
async def mark_reviewed(mark: ReviewMark):
    try:
        from src.storage.db import get_review_queue, remove_review
        q = get_review_queue()
        found = next((x for x in q if x.get("idx") == mark.index), None)
        if not found:
            raise HTTPException(status_code=404, detail="Review item not found")
        remove_review(mark.index)
        return {"status": "removed", "item": found}
    except HTTPException:
        raise
    except Exception:
        # fallback to file path
        review_path = os.getenv("REVIEW_QUEUE_PATH", "./data/review_queue.json")
        import json
        if not os.path.exists(review_path):
            raise HTTPException(status_code=404, detail="Review queue not found")
        with open(review_path, "r", encoding="utf-8") as f:
            queue = json.load(f)
        if mark.index < 0 or mark.index >= len(queue):
            raise HTTPException(status_code=400, detail="Index out of range")
        item = queue.pop(mark.index)
        with open(review_path, "w", encoding="utf-8") as f:
            json.dump(queue, f, indent=2)
        return {"status": "removed", "item": item}


class MemoryAddRequest(BaseModel):
    payload: dict
    id: str | None = None


@app.post("/admin/memory/add")
async def admin_memory_add(req: MemoryAddRequest):
    try:
        from src.memory.memory import init_memory, add_memory
        import time
        init_memory()
        mem_id = req.id or f"mem:{int(time.time() * 1000)}"
        add_memory(mem_id, req.payload)
        return {"status": "ok", "id": mem_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/memory/list")
async def admin_memory_list(limit: int = 100):
    try:
        from src.memory.memory import init_memory, get_all_memory
        init_memory()
        return {"items": get_all_memory(limit=limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/memory/query")
async def admin_memory_query(q: str, top_k: int = 5):
    try:
        from src.memory.memory import init_memory, query_memory
        init_memory()
        return {"results": query_memory(q, top_k=top_k)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class LLMCheckRequest(BaseModel):
    prompt: str = "Respond with one short line proving local LLM is active."
    max_tokens: int = 120


@app.post("/admin/llm/check")
async def admin_llm_check(req: LLMCheckRequest):
    try:
        import time
        from src.llm.llm import get_default_llm
        start = time.time()
        llm = get_default_llm()
        out = llm.generate(req.prompt, max_tokens=req.max_tokens)
        latency_ms = int((time.time() - start) * 1000)
        text = out.get("text") if isinstance(out, dict) else str(out)
        return {
            "status": "ok",
            "backend": type(llm).__name__,
            "latency_ms": latency_ms,
            "output": (text or "").strip(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class DeepLearnRequest(BaseModel):
    topic: str
    max_queries: int = 5
    max_learn_sources: int = 30
    build_kg: bool = True


@app.post("/admin/learn/deep")
async def admin_learn_deep(req: DeepLearnRequest):
    """Deep learning cycle: generate queries, discover, ingest, persist memory, and optionally build KG."""
    if not req.topic.strip():
        raise HTTPException(status_code=400, detail="Missing topic")
    try:
        from src.llm.llm import get_default_llm
        from src.orchestrator import orchestrator
        from src.storage.db import get_discovery_queue, remove_discovery_candidate
        from src.memory.memory import init_memory, add_memory
        import time
        import uuid

        llm = get_default_llm()
        q_prompt = (
            f"Create {max(3, req.max_queries)} deep research web search queries for topic: {req.topic}. "
            "Return one query per line, no explanation."
        )
        q_out = llm.generate(q_prompt, max_tokens=300)
        q_text = q_out.get("text") if isinstance(q_out, dict) else str(q_out)
        parsed = [x.strip("-* \t") for x in (q_text or "").splitlines() if x.strip()]
        queries = [req.topic] + parsed
        # dedupe and clip
        seen = set()
        uniq_queries = []
        for q in queries:
            k = q.lower().strip()
            if not k or k in seen:
                continue
            seen.add(k)
            uniq_queries.append(q)
        queries = uniq_queries[: max(1, req.max_queries)]

        discovered = 0
        for q in queries:
            try:
                res = orchestrator.run_agent("discovery", [q])
                discovered += len(res or [])
            except Exception:
                pass

        queue = get_discovery_queue()
        accepted = 0
        ingested_resources = []
        for item in queue[: req.max_learn_sources]:
            cand = item.get("item") if isinstance(item.get("item"), dict) else item
            try:
                orchestrator.run_agent("ingest", [cand])
                accepted += 1
                ingested_resources.append(
                    {
                        "id": item.get("id") or cand.get("id"),
                        "title": cand.get("title"),
                        "url": cand.get("url"),
                        "source": cand.get("source"),
                    }
                )
                remove_discovery_candidate(item.get("id") or cand.get("id"))
            except Exception:
                pass

        kg_summary = {"built": False}
        if req.build_kg:
            try:
                from src.scripts.build_kg import main as build_kg_main
                from src.kg.mapper import map_kg_to_chunks
                import json
                build_kg_main()
                mapping = map_kg_to_chunks()
                kg_path = os.getenv("KG_OUT_PATH", "./data/kg.json")
                nodes = 0
                edges = 0
                if os.path.exists(kg_path):
                    with open(kg_path, "r", encoding="utf-8") as f:
                        kg = json.load(f)
                    nodes = len(kg.get("nodes", []))
                    edges = len(kg.get("edges", []))
                kg_summary = {"built": True, "nodes": nodes, "edges": edges, "mapped_nodes": len(mapping)}
            except Exception as e:
                kg_summary = {"built": False, "error": str(e)}

        init_memory()
        mem_id = f"deep:{uuid.uuid4()}"
        add_memory(
            mem_id,
            {
                "topic": req.topic,
                "queries": queries,
                "discovered_count": discovered,
                "accepted_count": accepted,
                "resources": ingested_resources[:20],
                "kg": kg_summary,
                "timestamp": time.time(),
            },
        )

        return {
            "status": "ok",
            "topic": req.topic,
            "llm_backend": type(llm).__name__,
            "queries": queries,
            "discovered_count": discovered,
            "accepted_count": accepted,
            "resources": ingested_resources,
            "kg": kg_summary,
            "memory_id": mem_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ask")
async def ask(req: AskRequest):
    """Answer using RAG + local or OpenAI LLM. Works without OPENAI_API_KEY (uses default LLM)."""
    from src.rag.rag import answer_question

    answer_result = answer_question(req.question, top_k=req.top_k)
    return {"question": req.question, "answer": answer_result.get("answer", ""), "sources": answer_result.get("sources", [])}


@app.post("/ask_or_learn")
async def ask_or_learn(req: AskOrLearnRequest):
    """If we have knowledge: answer. If not (no/weak sources), optionally learn from Wikipedia/crawler then answer again."""
    from src.rag.rag import answer_question

    # 1) Try to answer from current index
    result = answer_question(req.question, top_k=req.top_k)
    sources = result.get("sources", [])
    top_score = (sources[0].get("score")) if sources else 0.0
    answer = result.get("answer", "")

    # 2) If confidence is low and learn_if_unknown, trigger discovery + ingest then re-answer
    if req.learn_if_unknown and (not sources or (top_score is not None and top_score < 0.25)):
        try:
            from src.orchestrator import orchestrator
            from src.activity_log import log
            log("ask_or_learn", "Learning new knowledge for question", {"question": req.question[:100]})
            # Discovery with question as seed (Wikipedia + search)
            orchestrator.run_agent("discovery", [req.question])
            from src.storage.db import get_discovery_queue
            queue = get_discovery_queue()
            # Ingest up to max_learn_sources from queue
            for item in queue[: req.max_learn_sources]:
                cand = item.get("item") if isinstance(item.get("item"), dict) else item
                try:
                    orchestrator.run_agent("ingest", [cand])
                    from src.storage.db import remove_discovery_candidate
                    remove_discovery_candidate(item.get("id") or cand.get("id"))
                except Exception:
                    pass
            # Re-answer
            result = answer_question(req.question, top_k=req.top_k)
            answer = result.get("answer", "")
            sources = result.get("sources", [])
        except Exception as e:
            answer = (answer or "") + "\n\n(Attempted to learn more but failed: " + str(e) + ")"

    learned = req.learn_if_unknown and (not sources or (top_score or 0) < 0.25)
    return {"question": req.question, "answer": answer, "sources": sources, "learned": learned}


@app.post("/api/agent/generate")
async def api_agent_generate(req: GenerateRequest):
    """Generate a response using the default LLM. Optionally include RAG sources.

    Returns: { output: str, rag: optional(dict) }
    """
    try:
        from src.llm.llm import get_default_llm
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM module not available: {e}")

    llm = get_default_llm()
    gen = llm.generate(req.prompt, max_tokens=512)
    output = gen.get('text') if isinstance(gen, dict) else str(gen)

    result = {"output": output}
    # persist LLM output into DB (best-effort) for later inspection / KG mapping
    try:
        from src.storage import db as storage_db
        import time
        doc_id = f"llm:{abs(hash(output))}"
        meta = {"prompt": req.prompt, "timestamp": time.time(), "source": "llm"}
        try:
            storage_db.insert_chunk(doc_id, doc_id, output, meta)
        except Exception:
            # fallback: ignore persistence errors
            pass
    except Exception:
        pass
    # optionally run RAG to gather supporting sources
    if req.use_rag or (req.top_k and req.top_k > 0):
        try:
            from src.rag.rag import answer_question
            rag_res = answer_question(req.prompt, top_k=req.top_k or 5)
            result["rag"] = rag_res
        except Exception:
            # non-fatal: continue returning LLM output
            result["rag"] = {"error": "RAG not available"}

    return result


@app.post("/api/agent/run_goal")
async def api_agent_run_goal(req: RunGoalRequest):
    """Run the planner to generate and execute a plan for the provided goal.

    Returns the planner run summary.
    """
    try:
        from src.activity_log import log
        log("run_goal", "Planning and executing goal", {"goal": req.goal[:80]})
    except Exception:
        pass
    try:
        from src.agent.planner import generate_and_execute
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Planner not available: {e}")

    try:
        summary = generate_and_execute(req.goal, max_steps=req.max_steps)
        return {"status": "ok", "summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class AgentRunRequest(BaseModel):
    args: list = []
    kwargs: dict = {}


@app.post("/admin/run_pipeline")
async def admin_run_pipeline(background_tasks: BackgroundTasks):
    """Trigger the full ingest->KG->mapping pipeline in background."""
    try:
        from src.activity_log import log
        log("pipeline", "Running full pipeline (ingest → KG → mapping)", {})
    except Exception:
        pass
    try:
        from src.scripts.run_pipeline import main as run_pipeline_main
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline runner not found: {e}")

    # run in background
    background_tasks.add_task(run_pipeline_main)
    return {"status": "started"}


@app.post("/admin/rebuild_index")
async def admin_rebuild_index(background_tasks: BackgroundTasks):
    try:
        from src.scripts.rebuild_index import main as rebuild_main
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rebuild script not found: {e}")
    background_tasks.add_task(rebuild_main)
    return {"status": "rebuild_started"}


@app.post("/admin/orchestrator/start")
async def admin_orch_start():
    try:
        from src.orchestrator import orchestrator
        orchestrator.start()
        return {"status": "orchestrator_started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/orchestrator/stop")
async def admin_orch_stop():
    try:
        from src.orchestrator import orchestrator
        orchestrator.stop()
        return {"status": "orchestrator_stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/worker/start")
async def admin_worker_start(payload: dict):
    """Start a named worker to process discovery queue: {"name":"discovery_worker","interval":5} """
    name = payload.get('name', 'discovery_worker')
    interval = int(payload.get('interval', 5))
    try:
        from src.orchestrator import orchestrator
        orchestrator.start_worker(worker_name=name, poll_interval=interval)
        return {"status": "worker_started", "name": name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/worker/stop")
async def admin_worker_stop(payload: dict):
    name = payload.get('name', 'discovery_worker')
    try:
        from src.orchestrator import orchestrator
        orchestrator.stop_worker(name)
        return {"status": "worker_stop_requested", "name": name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/autonomy/start")
async def admin_autonomy_start(payload: dict):
    """Start an autonomous manager loop for a goal: {"goal": "...", "interval": 60} """
    goal = payload.get('goal')
    interval = int(payload.get('interval', 60))
    if not goal:
        raise HTTPException(status_code=400, detail="Missing 'goal' in payload")
    try:
        from src.continuous.manager import manager
        started = manager.start(goal, loop_interval=interval)
        return {"status": "started" if started else "already_running", "goal": goal}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/autonomy/stop")
async def admin_autonomy_stop():
    try:
        from src.continuous.manager import manager
        manager.stop()
        return {"status": "stop_requested"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/autonomy/status")
async def admin_autonomy_status():
    try:
        from src.continuous.manager import manager
        return manager.status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/orchestrator/run/{agent_name}")
async def admin_orch_run(agent_name: str, req: AgentRunRequest):
    try:
        from src.orchestrator import orchestrator
        # run agent synchronously and return result (may be non-JSON-serializable)
        res = orchestrator.run_agent(agent_name, *req.args, **req.kwargs)
        return {"status": "ok", "agent": agent_name, "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/status")
async def admin_status():
    try:
        from src.orchestrator import orchestrator
        from src.storage.db import get_discovery_queue, get_review_queue
        schedules = orchestrator.list_schedules()
        workers = list(getattr(orchestrator, '_workers', {}).keys())
        discovery_q = get_discovery_queue()
        review_q = get_review_queue()
        return {
            "orchestrator_running": bool(getattr(orchestrator, 'running', False)),
            "schedules": schedules,
            "worker_names": workers,
            "discovery_queue_count": len(discovery_q),
            "review_queue_count": len(review_q),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/activity")
async def admin_activity(limit: int = 80):
    """Recent agent activity (discovery, ingest, verify) for UI live view."""
    try:
        from src.activity_log import get_recent
        return {"events": get_recent(limit=limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/logs")
async def admin_logs():
    try:
        from src.storage.db import get_sandbox_runs, get_schedule_runs
        sandbox = get_sandbox_runs()
        schedules = get_schedule_runs()
        return {"sandbox_runs": sandbox, "schedule_runs": schedules}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/queues")
async def admin_queues():
    try:
        from src.storage.db import get_discovery_queue, get_review_queue
        return {"discovery_queue": get_discovery_queue(), "review_queue": get_review_queue()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ScheduleRequest(BaseModel):
    name: str
    agent: str
    interval_seconds: int
    args: list = []
    kwargs: dict = {}


@app.post("/admin/schedule/add")
async def admin_schedule_add(req: ScheduleRequest):
    try:
        from src.orchestrator import orchestrator
        orchestrator.schedule_agent(req.agent, req.interval_seconds, args=req.args, kwargs=req.kwargs)
        return {"status": "scheduled", "name": req.name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/schedule/list")
async def admin_schedule_list():
    try:
        from src.orchestrator import orchestrator
        # return persisted schedules with friendly shape when possible
        schedules = orchestrator.list_schedules()
        return {"schedules": schedules}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/schedule/runs")
async def admin_schedule_runs():
    try:
        from src.storage.db import get_schedule_runs
        runs = get_schedule_runs()
        return {"runs": runs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/schedule/remove")
async def admin_schedule_remove(req: ScheduleRequest):
    try:
        from src.orchestrator import orchestrator
        orchestrator.remove_schedule(req.name)
        return {"status": "removed", "name": req.name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class DiscoverRequest(BaseModel):
    seeds: list
    provider: str = "auto"


@app.post("/admin/discover")
async def admin_discover(req: DiscoverRequest):
    """Run discovery agent with provided seed queries and return discovered candidates."""
    try:
        from src.orchestrator import orchestrator
        res = orchestrator.run_agent("discovery", req.seeds)
        # discovery agent saved candidates; return queue snapshot
        from src.storage.db import get_discovery_queue
        queue = get_discovery_queue()
        return {"status": "ok", "found": res, "queue_count": len(queue)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/discover/queue")
async def admin_discover_queue():
    try:
        from src.storage.db import get_discovery_queue
        q = get_discovery_queue()
        return {"queue": q}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class DiscoverAccept(BaseModel):
    id: str


@app.post("/admin/discover/accept")
async def admin_discover_accept(req: DiscoverAccept):
    try:
        from src.storage.db import get_discovery_queue, remove_discovery_candidate
        q = get_discovery_queue()
        item = next((x for x in q if x["id"] == req.id), None)
        if not item:
            # try matching by id inside stored item
            item = next((x for x in q if x.get("item", {}).get("id") == req.id), None)
        if not item:
            raise HTTPException(status_code=404, detail="Candidate not found")
        # extract candidate dict robustly
        candidate = item.get("item") if isinstance(item.get("item"), dict) else item
        # unwrap nested 'item' if double-wrapped
        while isinstance(candidate, dict) and "item" in candidate and isinstance(candidate["item"], dict) and ("text" not in candidate or not candidate.get("text")):
            candidate = candidate["item"]
        # hand to ingest_agent
        from src.orchestrator import orchestrator
        orchestrator.run_agent("ingest", [candidate])
        remove_discovery_candidate(req.id)
        return {"status": "accepted", "id": req.id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/discover/reject")
async def admin_discover_reject(req: DiscoverAccept):
    try:
        from src.storage.db import remove_discovery_candidate
        remove_discovery_candidate(req.id)
        return {"status": "rejected", "id": req.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/verifier/run")
async def admin_verifier_run():
    """Run the verifier agent on items currently in the review queue."""
    try:
        from src.storage.db import get_review_queue
        from src.orchestrator import orchestrator
        q = get_review_queue()
        items = [x.get("item") for x in q]
        res = orchestrator.run_agent("verifier", items)
        return {"status": "ok", "results": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SandboxRequest(BaseModel):
    code: str
    timeout: int = 10


@app.post("/sandbox/run")
async def sandbox_run(req: SandboxRequest):
    """Run a small Python snippet in the local sandbox runner. Local-only and not secure."""
    try:
        from src.sandbox.runner import run_code
        rc, out, err = run_code(req.code, timeout=req.timeout)
        # try to return run records from DB for traceability
        try:
            from src.storage.db import get_sandbox_runs
            runs = get_sandbox_runs()
        except Exception:
            runs = []
        return {"returncode": rc, "stdout": out, "stderr": err, "recent_runs": runs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class MasteryRequest(BaseModel):
    topic: str


def _load_kg_sync():
    """Load KG from file (sync)."""
    kg_path = os.getenv("KG_OUT_PATH", "./data/kg.json")
    if not os.path.exists(kg_path):
        return {"nodes": [], "edges": []}
    import json
    with open(kg_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_kg_mapping_sync():
    """Load KG mapping from file or build via mapper (sync)."""
    mapping_path = os.getenv("KG_MAPPING_PATH", "./data/kg_mapping.json")
    if os.path.exists(mapping_path):
        import json
        with open(mapping_path, "r", encoding="utf-8") as f:
            return json.load(f)
    try:
        from src.kg.mapper import map_kg_to_chunks
        return map_kg_to_chunks()
    except Exception:
        return {}


@app.post("/synthesis/mastery")
async def synthesis_mastery(req: MasteryRequest):
    try:
        from src.synthesis.planner import generate_mastery_report
        kg = _load_kg_sync()
        mapping = _load_kg_mapping_sync()
        report = generate_mastery_report(req.topic, kg, mapping)
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/system")
async def admin_system():
    """Return quick diagnostics: LLM backend, retriever status, DB path and key env flags."""
    info = {}
    try:
        from src.llm.llm import get_default_llm
        llm = get_default_llm()
        info['llm'] = {'type': type(llm).__name__}
    except Exception as e:
        info['llm_error'] = str(e)

    try:
        from src.rag.retriever import get_default_retriever
        retr = get_default_retriever()
        retr_status = {'type': type(retr).__name__}
        try:
            # heuristic: check for an in-memory index or docs for fallback
            loaded = False
            if hasattr(retr, 'index') and getattr(retr, 'index') is not None:
                loaded = True
            elif hasattr(retr, 'docs') and getattr(retr, 'docs'):
                loaded = True
            retr_status['loaded'] = bool(loaded)
        except Exception:
            retr_status['loaded'] = False
        info['retriever'] = retr_status
    except Exception as e:
        info['retriever_error'] = str(e)

    # also check for on-disk metadata file for fallback retriever
    try:
        from src.rag import retriever as retr_mod
        meta_path = getattr(retr_mod, 'METADATA_PATH', None)
        fallback_meta = None
        if meta_path:
            fallback_meta = meta_path + '.fallback.json'
        else:
            fallback_meta = './data/metadata.pkl.fallback.json'
        import os
        if os.path.exists(fallback_meta):
            try:
                info.setdefault('retriever', {})['fallback_metadata'] = {'path': fallback_meta, 'size': os.path.getsize(fallback_meta)}
            except Exception:
                info.setdefault('retriever', {})['fallback_metadata'] = {'path': fallback_meta}
        else:
            info.setdefault('retriever', {})['fallback_metadata'] = {'path': fallback_meta, 'exists': False}
    except Exception:
        pass

    try:
        import os
        from src.storage import db as storage_db
        info['db_path'] = storage_db.DB_PATH
        info['db_exists'] = os.path.exists(storage_db.DB_PATH)
    except Exception as e:
        info['db_error'] = str(e)

    try:
        from src.memory.memory import get_all_memory, init_memory
        init_memory()
        info["memory"] = {"count": len(get_all_memory(limit=500))}
    except Exception as e:
        info["memory_error"] = str(e)

    try:
        import os
        info['env'] = {'OPENAI_API_KEY': bool(os.getenv('OPENAI_API_KEY')), 'LLM_BACKEND': os.getenv('LLM_BACKEND')}
    except Exception:
        info['env'] = {}

    return info


@app.post("/admin/retriever/build")
async def admin_retriever_build():
    """Trigger building/saving the fallback retriever index from bundled samples."""
    try:
        from src.scripts.bootstrap_index import build_and_save
        build_and_save()
        # attempt to reload the singleton retriever so it's ready in-memory
        try:
            from src.rag.retriever import get_default_retriever
            retr = get_default_retriever()
            try:
                retr.load()
            except Exception:
                pass
        except Exception:
            pass
        return {"status": "built"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Agent API: plan/generate/run_goal are defined earlier with richer behavior ---
# The plan endpoint (below) is intentionally lightweight and kept for compatibility.
@app.post("/api/agent/plan")
async def api_agent_plan(payload: dict):
    goal = payload.get('goal', '')
    from src.llm.llm import get_default_llm
    llm = get_default_llm()
    plan = llm.plan(goal)
    return {"goal": goal, "plan": plan}



class EvalAnswerRequest(BaseModel):
    answer: str
    references: list = []


@app.post("/eval/answer")
async def eval_answer(req: EvalAnswerRequest):
    try:
        from src.eval.evaluator import evaluate_answer
        res = evaluate_answer(req.answer, req.references)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class LessonRequest(BaseModel):
    topic: str
    level: str = "intro"


@app.post("/tutor/lesson")
async def tutor_lesson(req: LessonRequest):
    try:
        from src.tutor.engine import generate_lesson
        lesson = generate_lesson(req.topic, level=req.level)
        return lesson
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
