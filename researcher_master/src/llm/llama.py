"""Adapter for llama.cpp / ggml Python bindings (optional).

This is a light wrapper that attempts to import `llama_cpp` (the python bindings)
if available and provides a simple generate() wrapper. It is a non-breaking optional
backend: when not installed, callers should fall back to other LLMs.
"""
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class LlamaAdapter:
    def __init__(self, model_path: str = None):
        self.model_path = model_path or os.getenv('LLAMA_MODEL_PATH')
        self.client = None
        try:
            from llama_cpp import Llama
            if not self.model_path:
                raise RuntimeError('LLAMA_MODEL_PATH not set')
            self.client = Llama(model_path=self.model_path)
        except Exception as e:
            logger.info(f"llama.cpp adapter unavailable: {e}")
            self.client = None

    def available(self) -> bool:
        return self.client is not None

    def generate(self, prompt: str, max_tokens: int = 256) -> Dict[str, Any]:
        if not self.client:
            raise RuntimeError('llama adapter not available')
        try:
            resp = self.client.create(prompt=prompt, max_tokens=max_tokens)
            text = resp.get('choices', [{}])[0].get('text', '')
            return {"text": text, "meta": {}}
        except Exception as e:
            logger.exception('llama generation failed')
            return {"text": '', "meta": {"error": str(e)}}
