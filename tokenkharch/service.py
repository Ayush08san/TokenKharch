"""Use-case layer. Both the MCP server and the web API call these functions, so logic lives in exactly one place."""
from __future__ import annotations

from . import llm, pricing, store
from .analyzer import analyze, efficiency_score
from .optimizer import optimize
from .tokenizer import count_claude_exact, count_tokens, method


def analyze_prompt(prompt: str, document: str | None = None, model: str | None = None,
                   expected_output_tokens: int = 500, source: str = "web", exact: bool = False) -> dict:
    model = model or pricing.default_model()
    pricing.get_price(model)  # validate early
    prompt_tokens = count_tokens(prompt)
    doc_tokens = count_tokens(document) if document else 0
    total_input = prompt_tokens + doc_tokens

    exact_count = count_claude_exact(prompt + ("\n" + document if document else ""), model) if exact else None
    if exact_count is not None:
        total_input = exact_count

    issues = analyze(prompt)
    warnings = []
    if total_input > 50_000:
        warnings.append("Input exceeds 50k tokens - consider chunking or retrieval instead of pasting the whole document.")
    if document and doc_tokens > 10 * max(prompt_tokens, 1):
        warnings.append("Document dominates the input - tell the model exactly what to extract from it.")

    c = pricing.cost(total_input, expected_output_tokens, model)
    return {
        "model": model,
        "tokenizer": "anthropic count_tokens (exact)" if exact_count is not None else method(),
        "tokens": {"prompt": prompt_tokens, "document": doc_tokens, "total_input": total_input,
                   "expected_output": expected_output_tokens},
        "cost": c,
        "efficiency_score": efficiency_score(prompt, issues),
        "issues": [i.to_dict() for i in issues],
        "warnings": warnings,
        "model_comparison": pricing.compare_models(total_input, expected_output_tokens),
    }


def optimize_prompt(prompt: str, mode: str = "aggressive", model: str | None = None,
                    expected_output_tokens: int = 500) -> dict:
    model = model or pricing.default_model()
    result = optimize(prompt, mode)
    before = pricing.cost(result["tokens_before"], expected_output_tokens, model)
    after = pricing.cost(result["tokens_after"], expected_output_tokens, model)
    result["cost_before"], result["cost_after"] = before, after
    result["saved_usd"] = round(before["total_usd"] - after["total_usd"], 6)
    # what this saving means at scale - the number interviewers remember
    result["saved_per_million_calls_usd"] = round(result["saved_usd"] * 1_000_000, 2)
    return result


def send(prompt: str, model: str | None = None, max_tokens: int = 512, document: str | None = None,
         auto_optimize: bool = True, mode: str = "aggressive", source: str = "web",
         force_demo: bool = False) -> dict:
    model = model or pricing.default_model()
    opt = optimize_prompt(prompt, mode, model, max_tokens) if auto_optimize else None
    final_prompt = opt["optimized"] if opt else prompt

    res = llm.call_claude(final_prompt, model, max_tokens, document, force_demo)
    actual = pricing.cost(res["input_tokens"], res["output_tokens"], model)
    saved_tokens = opt["tokens_saved"] if opt else 0
    saved_usd = round(saved_tokens / pricing.PER_MILLION * pricing.get_price(model).input, 8)

    if not res["error"]:
        store.log(source=source, kind="send", model=model, input_tokens=res["input_tokens"],
                  output_tokens=res["output_tokens"], tokens_saved=saved_tokens,
                  cost_usd=0.0 if res["demo"] else actual["total_usd"], saved_usd=saved_usd,
                  demo=res["demo"], preview=final_prompt)
    return {"model": model, "prompt_sent": final_prompt, "optimization": opt, "response": res,
            "actual_cost": actual, "saved_usd": saved_usd}


def compare(original: str, optimized: str, model: str | None = None, expected_output_tokens: int = 500) -> dict:
    model = model or pricing.default_model()
    a, b = count_tokens(original), count_tokens(optimized)
    ca, cb = pricing.cost(a, expected_output_tokens, model), pricing.cost(b, expected_output_tokens, model)
    return {"model": model, "original_tokens": a, "optimized_tokens": b, "tokens_saved": a - b,
            "original_cost_usd": ca["total_usd"], "optimized_cost_usd": cb["total_usd"],
            "saved_usd": round(ca["total_usd"] - cb["total_usd"], 6)}


def models() -> list[dict]:
    return [{"name": m.name, "provider": m.provider, "input": m.input, "output": m.output}
            for m in pricing.models().values()]


def status() -> dict:
    return {"tokenizer": method(), "live_llm": llm.has_api_key(), "default_model": pricing.default_model()}
