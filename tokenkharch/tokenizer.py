"""Token counting.

1. Anthropic `count_tokens` API exact for Claude models, needs an API key + network.
2. tiktoken `o200k_base` BPE exact for GPT-4o/5 family, a close proxy for others.
"""
from __future__ import annotations

import os
from functools import lru_cache

import tiktoken


@lru_cache(maxsize=1)
def _encoder() -> tiktoken.Encoding:
    # Raises if the BPE file can't be loaded (first run offline); exceptions aren't cached, so the next call retries.
    return tiktoken.get_encoding("o200k_base")


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_encoder().encode(text, disallowed_special=()))


def method() -> str:
    return "tiktoken/o200k_base"


def count_claude_exact(text: str, model: str) -> int | None:
    """Exact Claude input-token count via Anthropic's free count_tokens endpoint. None if unavailable."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key.startswith("sk-ant-") or not model.startswith("claude"):
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        res = client.messages.count_tokens(model=model, messages=[{"role": "user", "content": text}])
        return int(res.input_tokens)
    except Exception:
        return None
