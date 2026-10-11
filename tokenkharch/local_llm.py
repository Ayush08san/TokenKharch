"""Local LLM via Ollama's REST API (stdlib only, no extra dependency).

Used for the optional LLM rewrite step: free, private (the prompt never leaves the machine), and no API key.
Config: OLLAMA_HOST (default http://127.0.0.1:11434), TOKENKHARCH_OLLAMA_MODEL (default llama3.2:3b).
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

DEFAULT_MODEL = "llama3.2:3b"


def host() -> str:
    return os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")


def default_model() -> str:
    return os.environ.get("TOKENKHARCH_OLLAMA_MODEL", DEFAULT_MODEL)


def _request(path: str, payload: dict | None = None, timeout: float = 120) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(host() + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def list_models() -> list[str] | None:
    """Names of locally pulled models, or None if the Ollama server isn't reachable."""
    try:
        return [m["name"] for m in _request("/api/tags", timeout=2).get("models", [])]
    except (urllib.error.URLError, OSError, ValueError):
        return None


def generate(prompt: str, model: str, system: str | None = None) -> dict:
    """One non-streaming completion. Temperature 0 so the same prompt gives the same rewrite."""
    payload = {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0}}
    if system:
        payload["system"] = system
    try:
        t0 = time.perf_counter()
        r = _request("/api/generate", payload)
        return {"text": r.get("response", "").strip(),
                "prompt_tokens": r.get("prompt_eval_count", 0),  # counted by the local model's own tokenizer
                "output_tokens": r.get("eval_count", 0),
                "latency_ms": int((time.perf_counter() - t0) * 1000), "error": None}
    except urllib.error.HTTPError as e:  # e.g. 404 when the model hasn't been pulled
        detail = e.read().decode(errors="ignore")[:200]
        return {"text": "", "prompt_tokens": 0, "output_tokens": 0, "latency_ms": 0,
                "error": f"Ollama HTTP {e.code}: {detail} (try: ollama pull {model})"}
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {"text": "", "prompt_tokens": 0, "output_tokens": 0, "latency_ms": 0,
                "error": f"Ollama not reachable at {host()} ({type(e).__name__}). Start it with: ollama serve"}
