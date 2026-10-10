# TokenKharch: interview demo script (5–7 minutes)

## Before the interview (5 min)

1. `.\.venv\Scripts\Activate.ps1` then `python -m pytest -q`. All tests should be green.
2. Make sure TokenKharch is connected in Claude Desktop (see README). Open a new chat and check the tools icon lists `tokenkharch`.
3. Ask Claude: *"Call tokenkharch status."* `live_llm: true` means the key is loaded, `false` means demo mode. Both are fine. Know which one you're in.
4. Reset the ledger so the usage report starts at zero: delete `data/tokenkharch.db` (it is recreated on the next call).
5. (Optional, for ChatGPT) Start `python server.py --http` and `ngrok http 8000`, and have the connector set up in ChatGPT.
6. Have VS Code open on `server.py` and `tokenkharch/service.py`.

Keep this sample prompt ready to paste:

> You are a very helpful assistant. Please could you just summarize this report in order to help me. Keep it short. Keep it short.

## The pitch (30 seconds)

> "LLM APIs charge per token, and prompts collect waste: polite filler, boilerplate, instructions repeated twice. A system prompt goes out with every call, so small waste becomes a big bill at scale. TokenKharch is an MCP server: any AI assistant, whether that's Claude or ChatGPT, can call it as a tool to see what a prompt costs across Claude, GPT and Gemini, and to rewrite it to be leaner."

## The walkthrough (in Claude Desktop)

| Step | Ask the assistant | What to say |
|---|---|---|
| 1 | "Use tokenkharch to analyze this prompt: …" | "Claude picked `analyze_prompt` on its own. Efficiency score is low: a big part of the prompt is waste." Point at the issues: duplicate sentence, boilerplate, filler. |
| 2 | "What would this cost at a million calls?" | "One call costs a fraction of a cent, which is why nobody cares. At a million calls it's real money." |
| 3 | "Now optimize it." | "`optimize_prompt` makes the rewrite much smaller. Each rule's saving is **measured** by re-tokenizing, not estimated." |
| 4 | "Optimize it again in safe mode." | "Safe mode only makes edits that keep the meaning. Aggressive also strips politeness and role-play. It's a trade-off the user controls." |
| 5 | "Which model is cheapest for this request?" | "The same request priced across 11 models. Picking the model is usually a bigger cost lever than editing the prompt." |
| 6 | "Send the optimized prompt to Claude." | "`send_to_claude` optimizes, calls Claude, and logs the *billed* token counts from the API response." (In demo mode: "Without a key it runs in demo mode, so the demo never breaks.") |
| 7 | "Show my tokenkharch usage report." | "Every call goes into SQLite: spend, tokens saved, per day and per model." |
| 8 | (Optional) Same question in ChatGPT | "Same server, different client. ChatGPT needs a remote server, so here it's the HTTP transport behind a tunnel." |
| 9 | Show `server.py` and `service.py` | "The MCP server is a thin adapter: each tool is a few lines that call the service layer." |

## Questions you'll likely get

**How do you count tokens accurately when every provider has a different tokenizer?**
Three levels. For Claude, Anthropic's `count_tokens` endpoint gives the exact number. Otherwise tiktoken `o200k_base`, which is exact for GPT-4o/5 and a close proxy for others. If tiktoken can't load its vocabulary (offline), there's a heuristic of roughly one token per short word or punctuation mark, with long words split every ~4 characters. The `status` tool and the analysis output say which method was used.

**Does the optimizer change the meaning of the prompt?**
Safe mode only does edits that keep the meaning: removing exact duplicate sentences, wordy-to-concise phrases ("in order to" → "to") and whitespace. Aggressive mode removes politeness and role-play. Modern models follow instructions without them, but that's a judgement call, so it's opt-in. To *prove* it, I'd add an eval: run both prompts on a test set and compare the outputs.

**Why rule-based instead of asking an LLM to compress the prompt?**
Rules are deterministic, free, instant and explainable: every change can be listed. An LLM rewrite costs tokens to save tokens, and it can drift in meaning. The next step would be a hybrid: rules first, then an optional cheap-model rewrite behind an eval check.

**What is MCP, and why build this as an MCP server?**
MCP (Model Context Protocol) is the standard way to give AI assistants tools. A *server* exposes tools, and a *client* (Claude Desktop, ChatGPT, Cursor) discovers and calls them. Building it once as an MCP server means it works in every client without writing a separate integration for each.

**Why does ChatGPT need a different setup from Claude Desktop?**
Claude Desktop starts the server as a local process and talks to it over stdio. ChatGPT runs in the cloud, so it can only reach a remote server over HTTPS. The same `server.py` supports both: `--http` switches to the streamable HTTP transport, and a tunnel like ngrok gives it a public URL.

**How is the efficiency score calculated?**
`100 × (1 − wasted tokens / total tokens)`, minus small penalties for unstructured or under-specified prompts. Wasted tokens are the measured tokens of the matched patterns.

**What would you change for production?**
Auth on the HTTP transport (OAuth or a bearer token) and per-user ledgers. Postgres instead of SQLite. Pricing pulled from a maintained source instead of a JSON file. Model prompt-caching discounts. Restricting `read_document` to an allow-listed folder. An eval harness for the optimizer.

**What was hard?**
(Answer honestly from your own experience.) A good one: "Making the savings numbers trustworthy. My first version guessed '2 tokens per filler word'. I changed it to re-tokenize after every rule, so the numbers are real." Another: "Keeping the diff correct. There's a test checking that the diff rebuilds both the original and optimized text exactly."

**How did you test it?**
`pytest`: 11 tests covering token counting, cost maths, analyzer detection, optimizer guarantees (clean prompts stay unchanged, safe mode keeps politeness, the diff rebuilds both sides), demo-mode logging, and the MCP tools through an in-memory FastMCP client. Tests blank the API key so they never call the real API.

## Make sure you can explain

- What a token is and why output tokens cost more than input (output is generated one token at a time; input is processed in parallel).
- The two MCP transports: stdio (local process) and streamable HTTP (remote).
- Why the service layer is separate from FastMCP (separation of concerns, testability).
- Why `pricing.json` instead of hard-coded prices.
- The SQLite schema in `store.py` and the `GROUP BY` queries behind the usage report.
