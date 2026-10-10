"""TokenKharch MCP server - exposes the token/cost tools to any MCP client (Claude Desktop, Claude Code, Cursor...).

Run:  python server.py            (stdio transport, what Claude Desktop expects)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

from tokenkharch import service, store

mcp = FastMCP("TokenKharch")


@mcp.tool
def analyze_prompt(prompt: str, document: Optional[str] = None, model: Optional[str] = None,
                   expected_output_tokens: int = 500) -> dict:
    """Count tokens and estimate cost (USD + INR) for a prompt and optional document text.
    Also returns detected token-wasting issues, a 0-100 efficiency score, and the same request priced on every model."""
    r = service.analyze_prompt(prompt, document, model, expected_output_tokens, source="mcp")
    r["model_comparison"] = r["model_comparison"][:5]  # keep tool output small for the calling model
    return r


@mcp.tool
def optimize_prompt(prompt: str, mode: str = "aggressive", model: Optional[str] = None) -> dict:
    """Rewrite a prompt to use fewer tokens. mode='safe' only shortens wordy phrases, dedupes and trims whitespace;
    'aggressive' also strips filler words and role-play boilerplate. Returns the new prompt and measured savings."""
    r = service.optimize_prompt(prompt, mode, model)
    r.pop("diff", None)
    return r


@mcp.tool
def compare_cost(original_prompt: str, optimized_prompt: str, model: Optional[str] = None,
                 expected_output_tokens: int = 500) -> dict:
    """Side-by-side token and USD cost of two prompt versions."""
    return service.compare(original_prompt, optimized_prompt, model, expected_output_tokens)


@mcp.tool
def send_to_claude(prompt: str, model: Optional[str] = None, max_tokens: int = 512,
                   document: Optional[str] = None, auto_optimize: bool = True) -> dict:
    """Optimize (optional) -> send to Claude -> return the answer with real billed usage, logged to the ledger.
    Falls back to a demo response if ANTHROPIC_API_KEY is not set."""
    return service.send(prompt, model, max_tokens, document, auto_optimize, source="mcp")


@mcp.tool
def read_document(file_path: str, max_chars: int = 50_000) -> dict:
    """Read a local text/markdown/code file so its content can be passed as `document` to the other tools."""
    path = Path(file_path).expanduser()
    if not path.is_file():
        return {"error": f"File not found: {file_path}"}
    raw = path.read_text(encoding="utf-8", errors="ignore")
    from tokenkharch.tokenizer import count_tokens
    return {"file_path": str(path.resolve()), "content": raw[:max_chars], "chars": len(raw),
            "tokens": count_tokens(raw[:max_chars]), "truncated": len(raw) > max_chars}


@mcp.tool
def usage_report() -> dict:
    """Total tokens, spend and savings recorded so far, broken down by model and day."""
    s = store.stats()
    s.pop("recent", None)
    return s


@mcp.tool
def list_models() -> list[dict]:
    """Models TokenKharch can price, with USD per 1M input/output tokens."""
    return service.models()


if __name__ == "__main__":
    mcp.run()
