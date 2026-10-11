# TokenKharch ₹

**Know your token *kharch* (spend) before you hit send.**

TokenKharch is an MCP server that counts the tokens in an LLM prompt, prices it across 11 models (Claude, GPT and Gemini), finds the patterns that waste tokens, rewrites the prompt to be leaner (with rules, plus an optional local LLM via Ollama), and keeps a ledger of what you spent and saved.

You use it from any MCP client: Claude Desktop, Claude Code, claude.ai, ChatGPT, Cursor and others. You ask the assistant to analyze a prompt, and it calls TokenKharch's tools.

## Why it exists

LLM APIs bill per token, and prompts pick up waste: polite filler, role-play boilerplate, instructions copied twice, wordy phrasing. A system prompt is sent on **every** call, so 50 wasted tokens × 1M calls/month adds up to real money. TokenKharch makes that cost visible and fixes the easy parts automatically.

## Architecture

<img width="2549" height="1108" alt="mermaid-diagram-2026-10-11-213709" src="https://github.com/user-attachments/assets/f3a6077c-8d6f-4478-a1a2-d1feee7a1f2d" />


Design decisions worth knowing:

- **Thin MCP adapter.** `server.py` only declares tools. The logic lives in `tokenkharch/service.py`, so it can be tested without a client.
- **Savings are measured, not guessed.** Each optimizer rule re-tokenizes the text before and after, so "−22 tokens" is a real count.
- **Two levels of token counting.** Anthropic's `count_tokens` endpoint (exact for Claude) → tiktoken `o200k_base` (exact for GPT-4o/5, a proxy for others). tiktoken downloads its vocabulary on first use, after which it's cached and works offline.
- **Demo mode.** With no `ANTHROPIC_API_KEY`, `send_to_claude` returns a simulated reply. Every other tool works without a key.
- **Prices live in JSON** (`tokenkharch/pricing.json`) with sources and a date. You update them without touching code.
- **Hybrid optimizer with a local LLM.** `optimize_prompt_local` runs the rules first, then asks a local Ollama model (default `llama3.2:3b`) to compress the result. The prompt never leaves the machine and the rewrite costs $0. The output is re-tokenized with tiktoken and **only accepted** if it is shorter, keeps every number, quoted string, code span and `{placeholder}`, adds none of its own, and most of its words appear in the original. Otherwise the rules-only result is returned, with the reason.
- **Two optimizer modes.** `safe` only makes meaning-preserving edits (dedupe, wordy→concise, whitespace). `aggressive` also strips filler and role-play boilerplate.

## Setup (Windows PowerShell)

```powershell
cd D:\Project\MCP\TokenKharch
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # then put your real key in .env (optional, only send_to_claude uses it)
python -m pytest -q         

# Optional: local LLM rewrite (https://ollama.com)
ollama pull llama3.2:3b     # any Ollama model works; set TOKENKHARCH_OLLAMA_MODEL to change the default
python scripts/benchmark.py --local
```

## Run

```powershell
python server.py                  # stdio: for Claude Desktop, Claude Code, Cursor (the client starts it for you)
python server.py --http           # streamable HTTP at http://127.0.0.1:8000/mcp
python server.py --http --port 9000 --host 0.0.0.0
```

## Connect a client

### Claude Desktop

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

### Claude Code

```powershell
claude mcp add tokenkharch -- D:\Project\MCP\TokenKharch\.venv\Scripts\python.exe D:\Project\MCP\TokenKharch\server.py
```

### Cursor and other stdio clients

Use the same `command` + `args` as the Claude Desktop config above.

### ChatGPT (and claude.ai custom connectors)

ChatGPT only connects to **remote** MCP servers over HTTPS, so run the HTTP transport and put a tunnel in front of it:

```powershell
python server.py --http --port 8000
ngrok http 8000                   # or: cloudflared tunnel --url http://localhost:8000
```

Then in ChatGPT, turn on **Settings → Apps & Connectors → Advanced → Developer mode**, create a connector, and give it the tunnel URL with `/mcp` at the end (for example `https://abc123.ngrok-free.app/mcp`). The same URL works as a custom connector on claude.ai. Connector menus change between releases, so check the client's current docs if these labels differ.

> **Security:** the HTTP server has no authentication. Anyone who has the tunnel URL can call every tool. That includes `read_document`, which reads any file the server process can access, and `send_to_claude`, which spends your Anthropic credits if a key is set. Keep the URL private, stop the tunnel when you're done, and leave `ANTHROPIC_API_KEY` empty if you don't need live calls.

Then ask the assistant: *"Use tokenkharch to analyze and optimize this system prompt: …"*

## MCP tools

| Tool | What it does |
|---|---|
| `analyze_prompt` | Tokens, USD/INR cost, waste issues, efficiency score, cheapest models |
| `optimize_prompt` | Leaner rewrite plus measured savings per rule |
| `optimize_prompt_local` | Rules + local Ollama rewrite, with a guard that rejects unsafe rewrites |
| `compare_cost` | Token and cost difference between two prompt versions |
| `send_to_claude` | Optimize, call Claude, return the answer with billed usage, and log it |
| `read_document` | Load a local file to use as `document` context |
| `usage_report` | Ledger totals by model and day |
| `list_models` | Supported models and prices |
| `status` | Active tokenizer, live vs demo mode, default model, Ollama reachability and models |

## Benchmark

`python scripts/benchmark.py --local` on 8 sample prompts (tiktoken `o200k_base` counts):

| Optimizer | Tokens | Saved |
|---|---|---|
| Rules, safe mode | 230 → 195 | 15.2% |
| Rules, aggressive mode | 230 → 156 | 32.2% |
| Rules (safe) + `llama3.2:3b` | 230 → 112 | 51.3% (6/8 rewrites accepted) |

Eight hand-written prompts is a small sample, and savings depend heavily on how wordy the input is: already-tight prompts save close to 0%.

## Limitations and next steps

- The local-LLM guard is a heuristic. It catches dropped numbers, quotes and code, and rewrites where the model answered the prompt, but not a dropped instruction made of plain words (in the benchmark, `llama3.2:3b` dropped "do not add commentary" and the rewrite was still accepted). It can also be over-strict ("five" → "5" is rejected). Next step: an eval that runs the original and rewritten prompts through the target model and compares the answers.
- Token counts for Gemini and older Claude models are approximations (tiktoken proxy).
- Prompt caching savings (cache reads cost about 10% of input on Claude) aren't modelled yet. That would be a natural next feature.
- The HTTP transport has no auth. Adding OAuth or a bearer token would be needed before hosting it anywhere public.
