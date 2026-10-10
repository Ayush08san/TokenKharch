"""Token counting.

Strategy (most accurate first):
1. Anthropic `count_tokens` API - exact for Claude models, needs an API key + network.
2. tiktoken `o200k_base` BPE - exact for GPT-4o/5 family, a close proxy for others.
3. Heuristic fallback - works fully offline, so the demo never breaks.
"""
from __future__ import annotations

import math
import os
import re
from functools import lru_cache

_WORD_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


@lru_cache(maxsize=1)
def _encoder():
    try:
        import tiktoken
        return tiktoken.get_encoding("o200k_base")
    except Exception:  # not installed, or BPE file can't be downloaded (offline)
        return None


def heuristic_count(text: str) -> int:
    """~1 token per short word / punctuation mark, long words split every ~4 chars."""
    if not text:
        return 0
    return sum(max(1, math.ceil(len(piece) / 4)) for piece in _WORD_RE.findall(text))


def count_tokens(text: str) -> int:
    if not text:
        return 0
    enc = _encoder()
    if enc is not None:
        return len(enc.encode(text, disallowed_special=()))
    return heuristic_count(text)


def method() -> str:
    return "tiktoken/o200k_base" if _encoder() is not None else "heuristic (offline)"


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
