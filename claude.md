# TokenKharch: notes for AI coding assistants

- Python 3.10+. Core logic lives in `tokenkharch/`; `app.py` (FastAPI) and `server.py` (FastMCP) are thin adapters over `tokenkharch/service.py`. Put new logic in the service/core, not in the adapters.
- Prices: edit `tokenkharch/pricing.json` only (USD per 1M tokens).
- Run tests with `python -m pytest -q`. Tests must never call the real Anthropic API (they unset `ANTHROPIC_API_KEY`).
- Usage ledger: SQLite at `data/tokenkharch.db` (override with `TOKENKHARCH_DB`).
- Frontend: `static/` holds plain HTML/CSS/JS with no build step.
