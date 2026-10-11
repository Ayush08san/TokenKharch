# Model Pricing tables
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PRICING_FILE = Path(__file__).with_name("pricing.json")
PER_MILLION = 1_000_000


@dataclass(frozen=True)
class ModelPrice:
    name: str
    provider: str
    input: float          # USD per 1M input tokens
    output: float         # USD per 1M output tokens
    cache_read: float | None = None

#loading Json file. Needs TTL cache for live updates
@lru_cache(maxsize=1)
def _load() -> dict:
    return json.loads(PRICING_FILE.read_text(encoding="utf-8"))

@lru_cache(maxsize=None)
def models() -> dict[str, ModelPrice]:
    return {
        name: ModelPrice(name=name, provider=p["provider"], input=p["input"],
                         output=p["output"], cache_read=p.get("cache_read"))
        for name, p in _load()["models"].items()
    }


def default_model() -> str:
    return _load()["default_model"]


def usd_to_inr() -> float:
    return float(_load().get("usd_to_inr", 88.0))


def get_price(model: str) -> ModelPrice:
    table = models()
    if model not in table:
        raise ValueError(f"Unknown model '{model}'. Known: {', '.join(table)}")
    return table[model]


def cost(input_tokens: int, output_tokens: int, model: str) -> dict:
    """Return a cost breakdown"""
    p = get_price(model)
    input_usd = input_tokens / PER_MILLION * p.input
    output_usd = output_tokens / PER_MILLION * p.output
    total = input_usd + output_usd
    return {
        "model": model,
        "input_usd": round(input_usd, 6),
        "output_usd": round(output_usd, 6),
        "total_usd": round(total, 6),
        "total_inr": round(total * usd_to_inr(), 4),
    }


def compare_models(input_tokens: int, output_tokens: int) -> list[dict]:
    """Cost of the same request across every known model"""
    rows = []
    for name, p in models().items():
        c = cost(input_tokens, output_tokens, name)
        rows.append({**c, "provider": p.provider})
    return sorted(rows, key=lambda r: r["total_usd"])
