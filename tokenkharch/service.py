   # main logic file

from __future__ import annotations

import re

from . import llm, local_llm, pricing, store
from .analyzer import analyze, efficiency_score
from .optimizer import optimize
from .tokenizer import count_claude_exact, count_tokens, method


def analyze_prompt(prompt: str, document: str | None = None, model: str | None = None,
                   expected_output_tokens: int = 500, source: str = "mcp", exact: bool = False) -> dict:
    model = model or pricing.default_model()
    pricing.get_price(model)  
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


LOCAL_REWRITE_SYSTEM = (
    "You compress prompts for large language models. Rewrite the user's prompt to use as few words as possible "
    "while keeping every instruction, constraint, number, name, quoted text, code and output-format requirement. "
    "Do not answer the prompt. Do not add anything new. Reply with the rewritten prompt only, no preamble."
)
_PREAMBLE = re.compile(r"^(?:here(?:'s| is)[^\n]*?:|rewritten prompt:|compressed prompt:)\s*", re.IGNORECASE)
# Content an LLM rewrite must not drop: numbers, "quoted text", `code` and {placeholders}.
_MUST_KEEP = re.compile(r'\d+(?:[.,]\d+)*|"[^"\n]+"|`[^`\n]+`|\{[^{}\n]+\}')


def _clean_llm_output(text: str) -> str:
    text = _PREAMBLE.sub("", text.strip()).strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.strip("`").strip()
    if len(text) > 1 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


def _missing_must_keep(source: str, rewrite: str) -> list[str]:
    return sorted({m for m in _MUST_KEEP.findall(source) if m not in rewrite})


def _added_must_keep(source: str, rewrite: str) -> list[str]:
    """New numbers / quotes / code in the rewrite mean the model answered or invented content."""
    return sorted({m for m in _MUST_KEEP.findall(rewrite) if m not in source})


def _novel_word_share(source: str, rewrite: str) -> float:
    """Share of the rewrite's content words (4+ letters, compared by 5-letter stem) not found in the source."""
    stems = lambda t: [w[:5] for w in re.findall(r"[a-z]{4,}", t.lower())]
    src, new = set(stems(source)), stems(rewrite)
    return sum(w not in src for w in new) / len(new) if new else 0.0


def optimize_prompt_local(prompt: str, mode: str = "safe", model: str | None = None,
                          local_model: str | None = None, expected_output_tokens: int = 500) -> dict:
    """Hybrid optimizer: deterministic rules first, then a local Ollama model compresses the result further.
    The rewrite is re-tokenized with tiktoken and only accepted if it is shorter and keeps every number,
    quoted string, code span and placeholder; otherwise the rules-only result is returned."""
    model = model or pricing.default_model()
    local_model = local_model or local_llm.default_model()
    rules = optimize(prompt, mode)
    stage1 = rules["optimized"]

    # Delimiting the prompt stops small models from treating it as a request to answer.
    res = local_llm.generate(f"Rewrite this prompt:\n<prompt>\n{stage1}\n</prompt>", local_model,
                             system=LOCAL_REWRITE_SYSTEM)
    rewrite = _clean_llm_output(re.sub(r"</?prompt>", "", res["text"]))
    rewrite_tokens = count_tokens(rewrite)
    missing, added = _missing_must_keep(stage1, rewrite), _added_must_keep(stage1, rewrite)
    novel = _novel_word_share(stage1, rewrite)

    if res["error"]:
        accepted, reason = False, res["error"]
    elif not rewrite:
        accepted, reason = False, "local model returned an empty rewrite"
    elif rewrite_tokens >= rules["tokens_after"]:
        accepted, reason = False, f"rewrite was not shorter ({rewrite_tokens} vs {rules['tokens_after']} tokens)"
    elif missing:
        accepted, reason = False, "rewrite dropped required content: " + ", ".join(missing[:5])
    elif added:
        accepted, reason = False, "rewrite added content not in the prompt (model answered it?): " + ", ".join(added[:5])
    elif novel > 0.5:
        accepted, reason = False, f"{novel:.0%} of the rewrite's words are not in the prompt (model answered it?)"
    else:
        accepted, reason = True, "shorter, kept all numbers/quotes/code/placeholders, added nothing new"

    final = rewrite if accepted else stage1
    before, after = count_tokens(prompt), count_tokens(final)
    c_before = pricing.cost(before, expected_output_tokens, model)
    c_after = pricing.cost(after, expected_output_tokens, model)
    saved_usd = round(c_before["total_usd"] - c_after["total_usd"], 6)
    return {
        "model": model,
        "original": prompt,
        "optimized": final,
        "tokens_before": before,
        "tokens_after_rules": rules["tokens_after"],
        "tokens_after": after,
        "tokens_saved": before - after,
        "reduction_pct": round(100 * (before - after) / before, 1) if before else 0.0,
        "rules_applied": rules["applied"],
        "local_llm": {"model": local_model, "accepted": accepted, "reason": reason, "rewrite": rewrite,
                      "rewrite_tokens": rewrite_tokens, "local_tokenizer_prompt_tokens": res["prompt_tokens"],
                      "latency_ms": res["latency_ms"], "cost_usd": 0.0},
        "saved_usd": saved_usd,
        "saved_per_million_calls_usd": round(saved_usd * 1_000_000, 2),
    }


def send(prompt: str, model: str | None = None, max_tokens: int = 512, document: str | None = None,
         auto_optimize: bool = True, mode: str = "aggressive", source: str = "mcp",
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
    local_models = local_llm.list_models()
    return {"tokenizer": method(), "live_llm": llm.has_api_key(), "default_model": pricing.default_model(),
            "ollama": {"reachable": local_models is not None, "host": local_llm.host(),
                       "default_model": local_llm.default_model(), "models": local_models or []}}
