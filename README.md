# TokenKharch ₹

**Know your token *kharch* (spend) before you hit send.**

TokenKharch counts the tokens in an LLM prompt, prices it across 11 models (Claude, GPT and Gemini), finds the patterns that waste tokens, rewrites the prompt to be leaner, and keeps a ledger of what you spent and saved.

It ships in two ways that share one core library:

| Interface | Who uses it | Entry point |
|---|---|---|
| **Web dashboard** (FastAPI + vanilla JS) | People: paste a prompt, see cost, optimize, send | `python app.py` → http://127.0.0.1:8000 |
| **MCP server** (FastMCP) | AI assistants: Claude Desktop / Claude Code / Cursor call the tools directly | `python server.py` |

## Why it exists

LLM APIs bill per token, and prompts pick up waste: polite filler, role-play boilerplate, instructions copied twice, wordy phrasing. A system prompt is sent on **every** call, so 50 wasted tokens × 1M calls/month adds up to real money. TokenKharch makes that cost visible and fixes the easy parts automatically.

## Architecture

```
            ┌──────────────┐      ┌──────────────┐
 Browser ──▶│  app.py      │      │  server.py   │◀── MCP client (Claude Desktop…)
            │  FastAPI     │      │  FastMCP     │
            └──────┬───────┘      └──────┬───────┘
                   └──────────┬──────────┘
                     tokenkharch/service.py      ← use-case layer (one place for logic)
       ┌────────────┬─────────┼──────────┬──────────────┐
  tokenizer.py  pricing.py  analyzer.py  optimizer.py  llm.py      store.py
  tiktoken →    pricing.json regex rules  rule pipeline Anthropic   SQLite ledger
  heuristic     (editable)   + measured   + word diff   SDK + demo
  fallback                   impact                     mode
```

Design decisions worth knowing:

- **One service layer, two front-ends.** The web API and the MCP server are thin adapters, so a fix lands in both at once.
- **Savings are measured, not guessed.** Each optimizer rule re-tokenizes the text before and after, so "−22 tokens" is a real count.
- **Three levels of token counting.** Anthropic's `count_tokens` endpoint (exact for Claude) → tiktoken `o200k_base` (exact for GPT-4o/5) → an offline heuristic. The demo still works with no internet.
- **Demo mode.** With no `ANTHROPIC_API_KEY`, "send" returns a simulated reply, so a live demo can't fail on Wi-Fi or billing.
- **Prices live in JSON** (`tokenkharch/pricing.json`) with sources and a date. You update them without touching code.
- **Two optimizer modes.** `safe` only makes meaning-preserving edits (dedupe, wordy→concise, whitespace). `aggressive` also strips filler and role-play boilerplate.

## Setup (Windows PowerShell)

```powershell
cd D:\Project\MCP\TokenKharch
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # then put your real key in .env (optional)
```

## Run

```powershell
python app.py                # dashboard at http://127.0.0.1:8000  (API docs at /docs)
python -m pytest -q          # 12 tests
python server.py             # MCP server over stdio
```

### Use it from Claude Desktop

Add this to `%APPDATA%\Claude\claude_desktop_config.json`, then restart Claude Desktop:

```json
{
  "mcpServers": {
    "tokenkharch": {
      "command": "D:\\Project\\MCP\\TokenKharch\\.venv\\Scripts\\python.exe",
      "args": ["D:\\Project\\MCP\\TokenKharch\\server.py"]
    }
  }
}
```

Then ask Claude: *"Use tokenkharch to analyze and optimize this system prompt: …"*

## MCP tools

| Tool | What it does |
|---|---|
| `analyze_prompt` | Tokens, USD/INR cost, waste issues, efficiency score, cheapest models |
| `optimize_prompt` | Leaner rewrite plus measured savings per rule |
| `compare_cost` | Token and cost difference between two prompt versions |
| `send_to_claude` | Optimize, call Claude, return the answer with billed usage, and log it |
| `read_document` | Load a local file to use as `document` context |
| `usage_report` | Ledger totals by model and day |
| `list_models` | Supported models and prices |

## REST API

`GET /api/status` · `GET /api/models` · `POST /api/analyze` · `POST /api/optimize` · `POST /api/send` · `GET/DELETE /api/stats`. Interactive docs are at `/docs`.

## Limitations and next steps

- The optimizer is rule-based: predictable and free, but it can't restructure a prompt. Next step: an LLM-based rewrite (using a cheap model like Haiku), checked by comparing the answers to the original and optimized prompts on a small eval set.
- Token counts for Gemini and older Claude models are approximations (tiktoken proxy).
- Prompt caching savings (cache reads cost about 10% of input on Claude) aren't modelled yet. That would be a natural next feature.
