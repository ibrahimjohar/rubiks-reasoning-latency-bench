"""FastAPI backend. The API key never leaves this process.

    uvicorn backend.app.main:app --port 8000
    open http://localhost:8000
"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import runner, stats
from .rules import MODELS, ROOT, api_key, load_rules
from .scrambles import TIERS, load_suite

app = FastAPI(title="Rubik's Cube Race")
FRONTEND = ROOT / "frontend"

_active: dict = {"run": None, "task": None}


class StartRequest(BaseModel):
    tier: str
    puzzles: int | None = Field(default=None, ge=1)
    repeats: int = Field(default=1, ge=1, le=5)
    confirm: bool = False


def _active_run() -> runner.Run | None:
    return _active["run"]


@app.get("/api/config")
def config():
    rules = load_rules()
    suite = load_suite()
    return {
        "student": {"name": rules.student_name, "roll": rules.student_roll},
        "rules": rules.snapshot(),
        "models": MODELS,
        "tiers": {t: {"lengths": TIERS[t]["lengths"], "count": len(suite["tiers"][t])}
                  for t in TIERS},
        "live_ready": bool(api_key()),
        "active_run": _active_run().id if _active_run() and _active_run().data["status"] == "running" else None,
    }


@app.get("/api/puzzles")
def puzzles():
    return load_suite()


@app.post("/api/plan")
def make_plan(req: StartRequest):
    rules = load_rules()
    n = req.puzzles or len(load_suite()["tiers"][req.tier])
    return runner.plan(req.tier, n, req.repeats, rules)


@app.post("/api/runs")
async def start_run(req: StartRequest):
    if req.tier not in TIERS:
        raise HTTPException(400, "unknown tier")
    if not req.confirm:
        raise HTTPException(400, "paid run requires confirm=true")
    if not api_key():
        raise HTTPException(409, "OPENROUTER_API_KEY is not set in .env")
    current = _active_run()
    if current and current.data["status"] == "running":
        raise HTTPException(409, f"run {current.id} is still running")
    try:
        run = runner.Run(req.tier, req.puzzles, req.repeats, load_rules())
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    _active["run"] = run
    _active["task"] = asyncio.create_task(run.execute())
    return {"id": run.id, "plan": run.data["plan"]}


@app.post("/api/runs/{run_id}/abort")
def abort_run(run_id: str):
    run = _active_run()
    if not run or run.id != run_id:
        raise HTTPException(404, "no such active run")
    run.request_abort("stopped by user")
    return {"ok": True}


@app.get("/api/runs")
def runs():
    return runner.list_runs()


def _get_run(run_id: str) -> dict:
    run = _active_run()
    if run and run.id == run_id:
        return run.data
    try:
        return runner.load_run(run_id)
    except FileNotFoundError:
        raise HTTPException(404, "run not found")


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    return _get_run(run_id)


@app.get("/api/runs/{run_id}/stats")
def get_stats(run_id: str):
    return stats.run_stats(_get_run(run_id))


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
