"""SQLite usage ledger - every analysis / LLM call is logged so spend and savings can be tracked over time."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS usage (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             TEXT    NOT NULL,
    source         TEXT    NOT NULL,   -- mcp | cli
    kind           TEXT    NOT NULL,   -- analyze | send
    model          TEXT    NOT NULL,
    input_tokens   INTEGER NOT NULL DEFAULT 0,
    output_tokens  INTEGER NOT NULL DEFAULT 0,
    tokens_saved   INTEGER NOT NULL DEFAULT 0,
    cost_usd       REAL    NOT NULL DEFAULT 0,
    saved_usd      REAL    NOT NULL DEFAULT 0,
    demo           INTEGER NOT NULL DEFAULT 0,
    preview        TEXT
);
CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage(ts);
"""


def db_path() -> Path:
    default = Path(__file__).resolve().parent.parent / "data" / "tokenkharch.db"
    return Path(os.environ.get("TOKENKHARCH_DB") or default)


@contextmanager
def connect():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def log(*, source: str, kind: str, model: str, input_tokens: int, output_tokens: int = 0,
        tokens_saved: int = 0, cost_usd: float = 0.0, saved_usd: float = 0.0,
        demo: bool = False, preview: str = "") -> int:
    with connect() as c:
        cur = c.execute(
            "INSERT INTO usage (ts, source, kind, model, input_tokens, output_tokens, tokens_saved,"
            " cost_usd, saved_usd, demo, preview) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), source, kind, model,
             input_tokens, output_tokens, tokens_saved, cost_usd, saved_usd, int(demo), preview[:120]),
        )
        row_id = cur.lastrowid
        return int(row_id) if row_id is not None else 0


def stats() -> dict:
    with connect() as c:
        totals = dict(c.execute(
            "SELECT COUNT(*) AS requests, COALESCE(SUM(input_tokens),0) AS input_tokens,"
            " COALESCE(SUM(output_tokens),0) AS output_tokens, COALESCE(SUM(tokens_saved),0) AS tokens_saved,"
            " COALESCE(SUM(cost_usd),0) AS cost_usd, COALESCE(SUM(saved_usd),0) AS saved_usd FROM usage"
        ).fetchone())
        by_model = [dict(r) for r in c.execute(
            "SELECT model, COUNT(*) AS requests, SUM(input_tokens + output_tokens) AS tokens,"
            " ROUND(SUM(cost_usd), 6) AS cost_usd FROM usage GROUP BY model ORDER BY cost_usd DESC")]
        by_day = [dict(r) for r in c.execute(
            "SELECT substr(ts,1,10) AS day, SUM(input_tokens + output_tokens) AS tokens,"
            " SUM(tokens_saved) AS saved, ROUND(SUM(cost_usd),6) AS cost_usd"
            " FROM usage GROUP BY day ORDER BY day DESC LIMIT 14")][::-1]
        recent = [dict(r) for r in c.execute("SELECT * FROM usage ORDER BY id DESC LIMIT 15")]
    return {"totals": totals, "by_model": by_model, "by_day": by_day, "recent": recent}


def reset() -> None:
    with connect() as c:
        c.execute("DELETE FROM usage")
