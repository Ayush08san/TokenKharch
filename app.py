"""TokenKharch web dashboard (FastAPI). Run:  python app.py   then open http://127.0.0.1:8000"""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from tokenkharch import __version__, service, store

STATIC = Path(__file__).with_name("static")
app = FastAPI(title="TokenKharch", version=__version__,
              description="Token counting, cost estimation and prompt optimization for LLM apps.")


class AnalyzeIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=400_000)
    document: Optional[str] = None
    model: Optional[str] = None
    expected_output_tokens: int = Field(500, ge=1, le=200_000)
    exact: bool = False


class OptimizeIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=400_000)
    mode: Literal["safe", "aggressive"] = "aggressive"
    model: Optional[str] = None
    expected_output_tokens: int = Field(500, ge=1, le=200_000)


class SendIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=400_000)
    model: Optional[str] = None
    max_tokens: int = Field(512, ge=1, le=8192)
    document: Optional[str] = None
    auto_optimize: bool = True
    mode: Literal["safe", "aggressive"] = "aggressive"
    demo: bool = False


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/status")
def status():
    return {**service.status(), "version": __version__}


@app.get("/api/models")
def models():
    return service.models()


@app.post("/api/analyze")
def analyze(body: AnalyzeIn):
    return _guard(service.analyze_prompt, body.prompt, body.document, body.model,
                  body.expected_output_tokens, "web", body.exact)


@app.post("/api/optimize")
def optimize(body: OptimizeIn):
    return _guard(service.optimize_prompt, body.prompt, body.mode, body.model, body.expected_output_tokens)


@app.post("/api/send")
def send(body: SendIn):
    return _guard(service.send, body.prompt, body.model, body.max_tokens, body.document,
                  body.auto_optimize, body.mode, "web", body.demo)


@app.get("/api/stats")
def stats():
    return store.stats()


@app.delete("/api/stats")
def reset_stats():
    store.reset()
    return {"ok": True}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)
