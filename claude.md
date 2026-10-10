# TokenKharch: notes for AI coding assistants

- Python 3.10+. Core logic lives in `tokenkharch/`; `server.py` (FastMCP) is a thin adapter over `tokenkharch/service.py`. Put new logic in the service/core, not in the adapter.
- Prices: edit `tokenkharch/pricing.json` only (USD per 1M tokens).
- Run tests with `python -m pytest -q`. Tests must never call the real Anthropic API (they unset `ANTHROPIC_API_KEY`).
- Usage ledger: SQLite at `data/tokenkharch.db` (override with `TOKENKHARCH_DB`).
- No web UI: the MCP server is the only interface (`python server.py` for stdio, `--http` for remote clients like ChatGPT).
