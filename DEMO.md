# TokenKharch: interview demo script (5–7 minutes)

## Before the interview (5 min)

1. `.\.venv\Scripts\Activate.ps1` then `python -m pytest -q`. All tests should be green.
2. `python app.py`, open http://127.0.0.1:8000, click **Reset ledger**.
3. Check the top-right pills: **Live Claude API** (key loaded) or **Demo mode**. Both are fine. Know which one you're in.
4. Keep a second tab open on `/docs` (Swagger) and have VS Code open on `tokenkharch/service.py`.

## The pitch (30 seconds)

> "LLM APIs charge per token, and prompts collect waste: polite filler, boilerplate, instructions repeated twice. A system prompt goes out with every call, so small waste becomes a big bill at scale. TokenKharch shows the cost of a prompt before you send it, across Claude, GPT and Gemini, and rewrites it to be leaner. It runs as a web dashboard and as an MCP server, so an AI assistant can call it as a tool."

## The walkthrough

| Step | Click | What to say |
|---|---|---|
| 1 | **Verbose ask** sample | "Here's a realistic prompt. ~120 tokens. Efficiency score is about 50: half of it is waste." Point at the issues: duplicate sentence (high), boilerplate, filler. |
| 2 | Point at **Cost per 1M calls** | "One call costs a fraction of a cent, which is why nobody cares. At a million calls it's thousands of dollars." |
| 3 | **Optimize** | "The rewrite is about 58% smaller. The diff shows exactly what changed. Each rule's saving is **measured** by re-tokenizing, not estimated." |
| 4 | Switch Optimizer to **Safe**, Optimize again | "Safe mode only makes edits that keep the meaning. Aggressive also strips politeness and role-play. It's a trade-off the user controls." |
| 5 | **Same request on every model** | "The same request priced across 11 models. Picking the model is usually a bigger cost lever than editing the prompt." |
| 6 | **Optimize & send to Claude** | "It optimizes, calls Claude, and logs the *billed* token counts from the API response." (In demo mode: "Without a key it runs in demo mode, so the app never breaks during a demo.") |
| 7 | Scroll to **Usage ledger** | "Every call goes into SQLite: spend, tokens saved, per day and per model." |
| 8 | (Optional) Claude Desktop | "Same logic exposed as MCP tools. Here Claude calls `analyze_prompt` itself." |
| 9 | Show `service.py` | "Both front-ends call this one service layer. The web API and MCP server are thin adapters." |

## Questions you'll likely get

**How do you count tokens accurately when every provider has a different tokenizer?**
Three levels. For Claude, Anthropic's `count_tokens` endpoint gives the exact number. Otherwise tiktoken `o200k_base`, which is exact for GPT-4o/5 and a close proxy for others. If tiktoken can't load its vocabulary (offline), there's a heuristic of roughly one token per short word or punctuation mark, with long words split every ~4 characters. The UI always shows which method was used.

**Does the optimizer change the meaning of the prompt?**
Safe mode only does edits that keep the meaning: removing exact duplicate sentences, wordy-to-concise phrases ("in order to" → "to") and whitespace. Aggressive mode removes politeness and role-play. Modern models follow instructions without them, but that's a judgement call, so it's opt-in. To *prove* it, I'd add an eval: run both prompts on a test set and compare the outputs.

**Why rule-based instead of asking an LLM to compress the prompt?**
Rules are deterministic, free, instant and explainable: every change shows in the diff. An LLM rewrite costs tokens to save tokens, and it can drift in meaning. The next step would be a hybrid: rules first, then an optional cheap-model rewrite behind an eval check.

**Why both a web app and an MCP server?**
MCP (Model Context Protocol) is the standard way to give AI assistants tools. The MCP server lets Claude check costs from inside a conversation, and the dashboard is for humans. A shared service layer means no duplicated logic.

**How is the efficiency score calculated?**
`100 × (1 − wasted tokens / total tokens)`, minus small penalties for unstructured or under-specified prompts. Wasted tokens are the measured tokens of the matched patterns.

**What would you change for production?**
Auth and per-user ledgers. Postgres instead of SQLite. Pricing pulled from a maintained source instead of a JSON file. Model prompt-caching discounts. Rate limiting. An eval harness for the optimizer. Tracing real API usage through a proxy, so costs are logged from actual traffic and not only from this UI.

**What was hard?**
(Answer honestly from your own experience.) A good one: "Making the savings numbers trustworthy. My first version guessed '2 tokens per filler word'. I changed it to re-tokenize after every rule, so the numbers are real." Another: "Keeping the diff correct. There's a test checking that the diff rebuilds both the original and optimized text exactly."

**How did you test it?**
`pytest`: 12 tests covering token counting, cost maths, analyzer detection, optimizer guarantees (clean prompts stay unchanged, safe mode keeps politeness, the diff rebuilds both sides), the HTTP API including validation errors, and the MCP tools through an in-memory FastMCP client.

## Make sure you can explain

- What a token is and why output tokens cost more than input (output is generated one token at a time; input is processed in parallel).
- What MCP is: a protocol where a *server* exposes tools/resources and a *client* (Claude Desktop) discovers and calls them over stdio or HTTP.
- Why the service layer is separate from FastAPI/FastMCP (separation of concerns, testability).
- Why `pricing.json` instead of hard-coded prices.
- The SQLite schema in `store.py` and the `GROUP BY` queries behind the ledger.
