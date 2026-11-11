"""Smoke test: verify LLM, RAG, tutor, verifier, sandbox, synthesis and system work.

Run from repo root (or with PYTHONPATH set):
  python run_smoke_test.py

Optional: set SMOKE_FAST=1 to use lexical LLM + BM25-only retriever (no transformers load).
Expect: all [OK] or clear [FAIL] messages. If all OK, the product is ready to run.
"""
import os
import sys

# Ensure we can import src
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Fast smoke: avoid loading Ollama/transformers/sentence-transformers
if os.getenv("SMOKE_FAST"):
    os.environ["LLM_BACKEND"] = "lexical"
    os.environ["VECTOR_BACKEND"] = "bm25"


def ok(name: str):
    print(f"  [OK] {name}")


def fail(name: str, err: str):
    print(f"  [FAIL] {name}: {err}")


def main():
    print("Researcher-Master smoke test\n")

    # 1) DB
    try:
        from src.storage.db import init_db
        init_db()
        ok("DB init")
    except Exception as e:
        fail("DB init", str(e))
        return

    # 2) LLM (lexical / Ollama / transformers)
    try:
        from src.llm.llm import get_default_llm
        llm = get_default_llm()
        out = llm.generate("Say hello in one word.", max_tokens=20)
        text = (out or {}).get("text", "") or str(out)
        plan = llm.plan("Learn Python")
        ok(f"LLM ({type(llm).__name__}): generate + plan")
    except Exception as e:
        fail("LLM", str(e))

    # 3) Retriever (needs bootstrap or empty index)
    try:
        from src.rag.retriever import get_default_retriever
        r = get_default_retriever()
        hits = r.search("reinforcement learning", top_k=2)
        ok(f"Retriever ({type(r).__name__}): search returned {len(hits)} hits")
    except Exception as e:
        fail("Retriever", str(e))

    # 4) RAG
    try:
        from src.rag.rag import answer_question
        res = answer_question("What is reinforcement learning?", top_k=2)
        ans = res.get("answer", "")
        ok(f"RAG: answer_question (len={len(ans)})")
    except Exception as e:
        fail("RAG", str(e))

    # 5) Tutor
    try:
        from src.tutor.engine import generate_lesson
        lesson = generate_lesson("Physics", level="intro")
        assert "objectives" in lesson and "exercises" in lesson
        ok("Tutor: generate_lesson")
    except Exception as e:
        fail("Tutor", str(e))

    # 6) Verifier
    try:
        from src.orchestrator import orchestrator
        res = orchestrator.run_agent("verifier", [{"text": "Water boils at 100 degrees Celsius."}])
        assert isinstance(res, list)
        ok(f"Verifier: run_agent (checked {len(res)} item(s))")
    except Exception as e:
        fail("Verifier", str(e))

    # 7) Sandbox
    try:
        from src.sandbox.runner import run_code
        rc, stdout, stderr = run_code("print(2+2)", timeout=5)
        ok(f"Sandbox: run_code (returncode={rc}, stdout={stdout.strip() or '(empty)'})")
    except Exception as e:
        fail("Sandbox", str(e))

    # 8) Synthesis / mastery
    try:
        from src.synthesis.planner import generate_mastery_report
        report = generate_mastery_report("Math", kg={"nodes": [], "edges": []}, mapping={})
        assert "topic" in report and "learning_plan" in report
        ok("Synthesis: generate_mastery_report")
    except Exception as e:
        fail("Synthesis", str(e))

    # 9) Eval
    try:
        from src.eval.evaluator import evaluate_answer
        res = evaluate_answer("The sky is blue.", references=["sky", "blue"])
        assert "coverage" in res
        ok("Eval: evaluate_answer")
    except Exception as e:
        fail("Eval", str(e))

    print("\nSmoke test done. If all [OK], run: .\\setup_and_run.ps1  then open http://127.0.0.1:8000/")


if __name__ == "__main__":
    main()
