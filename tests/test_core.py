import asyncio
import os
import tempfile

os.environ["TOKENKHARCH_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["ANTHROPIC_API_KEY"] = ""  # blank, not unset, so load_dotenv() cannot restore a real key from .env

import pytest

from tokenkharch import pricing, service, store
from tokenkharch.analyzer import analyze, efficiency_score
from tokenkharch.optimizer import optimize
from tokenkharch.tokenizer import count_tokens

VERBOSE = ("You are a very helpful assistant. Please could you just summarize this report in order to "
           "help me. Keep it short. Keep it short.")


def test_token_count_basics():
    assert count_tokens("") == 0
    assert count_tokens("hello world") >= 2


def test_cost_maths():
    c = pricing.cost(1_000_000, 1_000_000, "claude-sonnet-5-5")
    p = pricing.get_price("claude-sonnet-5-5")
    assert c["total_usd"] == pytest.approx(p.input + p.output)
    assert c["total_inr"] == pytest.approx(c["total_usd"] * pricing.usd_to_inr(), rel=1e-3)


def test_unknown_model_raises():
    with pytest.raises(ValueError):
        pricing.get_price("gpt-imaginary")


def test_compare_sorted_cheapest_first():
    rows = pricing.compare_models(1000, 500)
    costs = [r["total_usd"] for r in rows]
    assert costs == sorted(costs)


def test_analyzer_finds_waste():
    types = {i.type for i in analyze(VERBOSE)}
    assert {"filler_words", "boilerplate", "duplicate_sentences"} <= types
    assert efficiency_score(VERBOSE) < efficiency_score("Summarize this report in 3 bullets.")


def test_optimizer_reduces_tokens_and_keeps_meaning():
    r = optimize(VERBOSE)
    assert r["tokens_after"] < r["tokens_before"]
    assert r["tokens_saved"] == r["tokens_before"] - r["tokens_after"]
    assert "summarize this report" in r["optimized"].lower()
    assert r["optimized"].lower().count("keep it short") == 1
    assert "helpful assistant" not in r["optimized"].lower()


def test_safe_mode_keeps_politeness():
    r = optimize("Please summarize this in order to help.", mode="safe")
    assert "please" in r["optimized"].lower()
    assert "in order to" not in r["optimized"].lower()


def test_clean_prompt_unchanged():
    p = "Summarize the report in 5 bullets. Output Markdown."
    assert optimize(p)["optimized"] == p


def test_diff_reconstructs_both_sides():
    r = optimize(VERBOSE)
    before = "".join(d["text"] for d in r["diff"] if d["op"] != "insert")
    after = "".join(d["text"] for d in r["diff"] if d["op"] != "delete")
    assert before == VERBOSE and after == r["optimized"]


def test_send_demo_mode_logs_to_ledger():
    store.reset()
    out = service.send(VERBOSE)
    assert out["response"]["demo"] is True
    t = store.stats()["totals"]
    assert t["requests"] == 1 and t["tokens_saved"] > 0 and t["cost_usd"] == 0


def test_mcp_tools_registered_and_callable():
    from fastmcp import Client
    from server import mcp

    async def go():
        async with Client(mcp) as client:
            names = {t.name for t in await client.list_tools()}
            assert {"analyze_prompt", "optimize_prompt", "send_to_claude", "usage_report", "status", "optimize_prompt_local"} <= names
            res = await client.call_tool("optimize_prompt", {"prompt": VERBOSE})
            assert res.data["tokens_saved"] > 0
            res = await client.call_tool("analyze_prompt", {"prompt": VERBOSE})
            assert res.data["tokens"]["total_input"] > 0 and res.data["issues"]
    asyncio.run(go())


# --- local LLM (Ollama) rewrite: Ollama is mocked, tests never need a running server ---

def _fake_ollama(monkeypatch, text, error=None):
    from tokenkharch import local_llm
    monkeypatch.setattr(local_llm, "generate", lambda prompt, model, system=None: {
        "text": text, "prompt_tokens": 42, "output_tokens": 7, "latency_ms": 5, "error": error})


def test_local_rewrite_accepted_when_shorter_and_complete(monkeypatch):
    _fake_ollama(monkeypatch, "Here is the rewritten prompt: Summarize this report briefly.")
    r = service.optimize_prompt_local(VERBOSE)
    assert r["local_llm"]["accepted"] is True
    assert r["optimized"] == "Summarize this report briefly."  # preamble stripped
    assert r["tokens_after"] < r["tokens_after_rules"] < r["tokens_before"]
    assert r["local_llm"]["cost_usd"] == 0.0


def test_local_rewrite_rejected_when_it_drops_numbers(monkeypatch):
    _fake_ollama(monkeypatch, "Summarize the report.")
    r = service.optimize_prompt_local("Please summarize the report in 5 bullets under 120 words.")
    assert r["local_llm"]["accepted"] is False and "120" in r["local_llm"]["reason"]
    assert "120" in r["optimized"]  # fell back to the rules-only result


def test_local_rewrite_rejected_when_not_shorter(monkeypatch):
    _fake_ollama(monkeypatch, VERBOSE + " Also add more detail please.")
    r = service.optimize_prompt_local(VERBOSE)
    assert r["local_llm"]["accepted"] is False
    assert r["tokens_after"] == r["tokens_after_rules"]


def test_local_rewrite_falls_back_when_ollama_down(monkeypatch):
    _fake_ollama(monkeypatch, "", error="Ollama not reachable")
    r = service.optimize_prompt_local(VERBOSE)
    assert r["local_llm"]["accepted"] is False and "not reachable" in r["local_llm"]["reason"]
    assert r["tokens_saved"] > 0  # rules still saved tokens


def test_status_reports_ollama(monkeypatch):
    from tokenkharch import local_llm
    monkeypatch.setattr(local_llm, "list_models", lambda: None)
    assert service.status()["ollama"]["reachable"] is False


def test_local_rewrite_rejected_when_model_answers_instead(monkeypatch):
    _fake_ollama(monkeypatch, '{"date": "2024-01-01", "amount": 100}')
    r = service.optimize_prompt_local("Extract all dates and amounts from the invoice below and return them as JSON "
                                      "with keys date and amount. Please be thorough and careful about it.")
    assert r["local_llm"]["accepted"] is False and "added content" in r["local_llm"]["reason"]


def test_local_rewrite_rejected_when_words_are_unrelated(monkeypatch):
    _fake_ollama(monkeypatch, "Bananas grow quickly everywhere.")
    r = service.optimize_prompt_local(VERBOSE)
    assert r["local_llm"]["accepted"] is False and "not in the prompt" in r["local_llm"]["reason"]
