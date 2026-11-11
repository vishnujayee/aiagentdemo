"""Pluggable LLM interface with a lightweight lexical fallback.

Auto mode is local-first and conservative:
1) Ollama (if reachable)
2) OpenAI (only if key is present)
3) Lexical fallback

Transformers backend is available, but only when explicitly requested via
LLM_BACKEND=transformers to avoid surprise large downloads.
"""
from typing import Dict, Any, List
import re
import os
import logging

logger = logging.getLogger(__name__)


class BaseLLM:
    def generate(self, prompt: str, max_tokens: int = 256) -> Dict[str, Any]:
        raise NotImplementedError()

    def plan(self, goal: str) -> List[str]:
        raise NotImplementedError()


class LexicalLLM(BaseLLM):
    """Very small fallback LLM: pattern-based responses and simple plan decomposition."""

    def generate(self, prompt: str, max_tokens: int = 256) -> Dict[str, Any]:
        s = prompt.strip()
        if len(s) == 0:
            return {"text": "", "meta": {}}

        if re.search(r"summar|tl;dr|short summary", s, re.I):
            sent = s.split('.')
            return {"text": (sent[0].strip() + '.') if sent else s[:200], "meta": {}}

        if re.search(r"plan|steps|how to", s, re.I):
            steps = re.split(r",| and |;", s)
            steps = [st.strip() for st in steps if st.strip()]
            if not steps:
                return {"text": "1. Clarify the goal\n2. Gather evidence\n3. Execute and verify", "meta": {}}
            return {"text": "\n".join([f"1. {steps[0]}", "2. Gather evidence", "3. Execute and verify"]), "meta": {}}

        return {"text": s[:max_tokens], "meta": {}}

    def plan(self, goal: str) -> List[str]:
        parts = re.split(r"\.|,|and|then", goal)
        steps = [p.strip() for p in parts if p.strip()]
        if not steps:
            return [goal]
        return [f"Step {i+1}: {s}" for i, s in enumerate(steps[:10])]


_DEFAULT_LLM: BaseLLM = None


def get_default_llm() -> BaseLLM:
    global _DEFAULT_LLM
    if _DEFAULT_LLM is not None:
        return _DEFAULT_LLM

    backend = os.getenv("LLM_BACKEND", "auto").lower()
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3")

    # 1) Ollama first in auto/local modes
    if backend in ("ollama", "local", "auto"):
        try:
            import httpx
            tags_resp = httpx.get(f"{ollama_url}/api/tags", timeout=8.0)
            if tags_resp.status_code == 200:
                class OllamaLLM(BaseLLM):
                    def generate(self, prompt: str, max_tokens: int = 256) -> Dict[str, Any]:
                        try:
                            # Newer Ollama versions may prefer /api/chat; keep backward compatibility.
                            resp = httpx.post(
                                f"{ollama_url}/api/chat",
                                json={
                                    "model": ollama_model,
                                    "messages": [{"role": "user", "content": prompt}],
                                    "stream": False,
                                    "options": {"num_predict": max_tokens},
                                },
                                timeout=240.0,
                            )
                            if resp.status_code == 404:
                                resp = httpx.post(
                                    f"{ollama_url}/api/generate",
                                    json={
                                        "model": ollama_model,
                                        "prompt": prompt,
                                        "stream": False,
                                        "options": {"num_predict": max_tokens},
                                    },
                                    timeout=240.0,
                                )
                            if resp.status_code == 404:
                                # OpenAI-compatible fallback endpoint.
                                resp = httpx.post(
                                    f"{ollama_url}/v1/chat/completions",
                                    json={
                                        "model": ollama_model,
                                        "messages": [{"role": "user", "content": prompt}],
                                        "max_tokens": max_tokens,
                                    },
                                    timeout=240.0,
                                )
                            resp.raise_for_status()
                            data = resp.json()
                            text = (
                                data.get("response")
                                or (((data.get("message") or {}).get("content")) if isinstance(data.get("message"), dict) else None)
                                or ((((data.get("choices") or [{}])[0]).get("message") or {}).get("content") if isinstance((data.get("choices") or [{}])[0], dict) else None)
                                or ""
                            )
                            return {"text": (text or "").strip(), "meta": {}}
                        except Exception as e:
                            logger.exception("Ollama generate failed")
                            return {"text": "", "meta": {"error": str(e)}}

                    def plan(self, goal: str) -> List[str]:
                        prompt = f"List 3-6 concrete steps to achieve this goal. One per line. Goal: {goal}"
                        out = self.generate(prompt, max_tokens=400)
                        text = out.get("text", "") or ""
                        lines = [
                            l.strip() for l in text.split("\n")
                            if l.strip() and (l.strip()[0].isdigit() or l.strip().startswith("-"))
                        ]
                        if not lines:
                            lines = [l.strip() for l in text.split("\n") if l.strip()][:8]
                        return lines[:10] if lines else [goal]

                _DEFAULT_LLM = OllamaLLM()
                return _DEFAULT_LLM
        except Exception as e:
            logger.debug(f"Ollama not available: {e}")

    # 2) OpenAI only if available and allowed by backend
    if backend in ("openai", "remote", "auto", "local"):
        try:
            import openai
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                class OpenAILLM(BaseLLM):
                    def __init__(self, openai_mod, key: str):
                        self.openai = openai_mod
                        self.api_key = key

                    def generate(self, prompt: str, max_tokens: int = 256) -> Dict[str, Any]:
                        try:
                            self.openai.api_key = self.api_key
                            resp = self.openai.Completion.create(
                                engine="text-davinci-003",
                                prompt=prompt,
                                max_tokens=max_tokens,
                            )
                            text = resp.choices[0].text.strip()
                            return {"text": text, "meta": {}}
                        except Exception as e:
                            logger.exception("OpenAI call failed")
                            return {"text": "", "meta": {"error": str(e)}}

                    def plan(self, goal: str) -> List[str]:
                        out = self.generate(f"Provide a short 3-step plan to achieve the goal: {goal}", max_tokens=200)
                        return [l.strip() for l in out.get("text", "").split("\n") if l.strip()][:10]

                _DEFAULT_LLM = OpenAILLM(openai, api_key)
                return _DEFAULT_LLM
        except Exception:
            pass

    # 3) Transformers only when explicitly requested.
    if backend == "transformers":
        try:
            from transformers import pipeline
            model_name = os.getenv("TRANSFORMERS_MODEL", "distilgpt2")
            pipe = pipeline("text-generation", model=model_name)

            class TransformerLLM(BaseLLM):
                def __init__(self, p):
                    self.pipe = p

                def generate(self, prompt: str, max_tokens: int = 256) -> Dict[str, Any]:
                    try:
                        params = {"do_sample": False}
                        try:
                            out = self.pipe(prompt, max_new_tokens=max_tokens, **params)
                        except TypeError:
                            out = self.pipe(prompt, max_length=max_tokens, **params)
                        text = ""
                        if isinstance(out, list) and out:
                            text = out[0].get("generated_text") or out[0].get("text") or ""
                        elif isinstance(out, dict):
                            text = out.get("generated_text") or out.get("text") or ""
                        return {"text": text, "meta": {}}
                    except Exception as e:
                        logger.exception("Transformer generation failed")
                        return {"text": "", "meta": {"error": str(e)}}

                def plan(self, goal: str) -> List[str]:
                    out = self.generate(f"Create a short plan to achieve: {goal}\n1.", max_tokens=150)
                    return [l.strip() for l in out.get("text", "").split("\n") if l.strip()][:10]

            _DEFAULT_LLM = TransformerLLM(pipe)
            return _DEFAULT_LLM
        except Exception:
            pass

    _DEFAULT_LLM = LexicalLLM()
    return _DEFAULT_LLM
