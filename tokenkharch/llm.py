from __future__ import annotations

import os
import time

from .tokenizer import count_tokens


def has_api_key() -> bool:
    """True only for a key that looks like an Anthropic key (sk-ant-...), so a typo falls back to demo mode."""
    return os.environ.get("ANTHROPIC_API_KEY", "").strip().startswith("sk-ant-")


def call_claude(prompt: str, model: str, max_tokens: int = 512, document: str | None = None,
                force_demo: bool = False) -> dict:
    content = f"<document>\n{document}\n</document>\n\n{prompt}" if document else prompt

    if force_demo or not has_api_key() or not model.startswith("claude"):
        reason = ("non-Claude model selected" if not model.startswith("claude")
                  else "no valid ANTHROPIC_API_KEY (should start with sk-ant-)" if not has_api_key() else "demo mode on")
        text = (f"[Demo response - {reason}]\n\nTokenKharch would send {count_tokens(content)} input tokens to "
                f"{model} here. Set ANTHROPIC_API_KEY in .env and pick a Claude model to get a real answer "
                "with exact usage numbers billed by the API.")
        return {"text": text, "input_tokens": count_tokens(content), "output_tokens": count_tokens(text),
                "latency_ms": 0, "demo": True, "error": None}

    try:
        import anthropic
        client = anthropic.Anthropic()
        t0 = time.perf_counter()
        msg = client.messages.create(model=model, max_tokens=max_tokens,
                                     messages=[{"role": "user", "content": content}])
        latency = int((time.perf_counter() - t0) * 1000)
        text = "".join(b.text for b in msg.content if b.type == "text")
        return {"text": text, "input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens,
                "latency_ms": latency, "demo": False, "error": None}
    except Exception as e:  # surface a clean error instead of a stack trace in the UI
        return {"text": "", "input_tokens": 0, "output_tokens": 0, "latency_ms": 0, "demo": False,
                "error": f"{type(e).__name__}: {e}"}
