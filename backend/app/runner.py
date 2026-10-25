"""Race runner: all four models play each puzzle at the same time.

Per turn, a model receives the shared state object and returns one move.
  * ok        -> move applied to that model's own copy of the cube
  * malformed -> logged and counted, cube unchanged, the turn is used up
  * error     -> (timeout / network / HTTP error after retries) logged, turn used up
A trial ends when the cube is solved or the model has used max_moves turns.

Guardrails enforced here:
  * hard move cap (30 turns per model per puzzle => at most 30 calls each),
  * run budget: no new request once reported spend reaches RUN_BUDGET_USD,
  * account errors (401/402/403) abort the whole run instead of being blamed
    on a model, and a user abort stops every game at its next turn,
  * no fallback models: a failing model is recorded as failing.
Each model is timed on its own clock, so running in parallel does not mix
latencies. Results are saved after every puzzle so nothing is lost on a crash.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable

import httpx

from . import solver
from .adapters import chat, decisions
from .adapters.base import MoveResult, RunAborted
from .cube import apply_move, is_solved
from .prompt import build_state
from .rules import MODELS, ROOT, Rules, api_key
from .scrambles import get_puzzles

RUNS_DIR = ROOT / "results" / "runs"

Decider = Callable[[httpx.AsyncClient, str, dict, Rules], Awaitable[MoveResult]]
DEFAULT_DECIDERS: dict[str, Decider] = {
    "decisions": decisions.decide,
    "chat": chat.decide,
}


def plan(tier: str, n_puzzles: int, repeats: int, rules: Rules) -> dict:
    """Upper bounds shown to the user before any paid call."""
    games = n_puzzles * repeats
    max_calls_per_model = games * rules.max_moves * (1 + rules.max_retries)
    return {
        "tier": tier, "puzzles": n_puzzles, "repeats": repeats, "games": games,
        "max_turns_per_model": games * rules.max_moves,
        "max_http_calls_total": max_calls_per_model * len(MODELS),
        "run_budget_usd": rules.run_budget_usd,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _step_analysis(state_before: str, move: str | None) -> dict:
    """Exact-distance bookkeeping for one turn (CPU only, no API)."""
    d = solver.distance(state_before)
    opt = solver.optimal_moves(state_before) if d is not None else None
    return {
        "distance_before": d,
        "optimal_moves": opt,
        "was_optimal": (move in opt) if (opt and move) else None,
    }


class Run:
    def __init__(self, tier: str, n_puzzles: int | None, repeats: int, rules: Rules,
                 deciders: dict[str, Decider] | None = None, label: str = "live"):
        self.rules = rules
        self.deciders = deciders or DEFAULT_DECIDERS
        puzzles = get_puzzles(tier, n_puzzles)
        self.abort_reason: str | None = None
        self._cost = 0.0
        self.data = {
            "id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6],
            "mode": label,
            "tier": tier,
            "created_utc": _now(),
            "finished_utc": None,
            "status": "running",
            "abort_reason": None,
            "rules": rules.snapshot(),
            "models": MODELS,
            "plan": plan(tier, len(puzzles), repeats, rules),
            "spend": {"reported_cost_usd": 0.0, "http_attempts": 0, "turns": 0,
                      "turns_without_reported_cost": 0},
            "current_game": 0,
            "games": [
                {"index": i, "repeat": r, "puzzle": p, "started_utc": None,
                 "trials": {m["key"]: self._new_trial(m) for m in MODELS}}
                for i, (r, p) in enumerate((r, p) for r in range(repeats) for p in puzzles)
            ],
        }

    @staticmethod
    def _new_trial(model: dict) -> dict:
        return {"model": model["key"], "status": "pending", "turns": 0,
                "applied_moves": [], "solved": False, "elapsed_ms": None,
                "final_state": None, "steps": []}

    @property
    def id(self) -> str:
        return self.data["id"]

    def request_abort(self, reason: str = "stopped by user") -> None:
        if not self.abort_reason:
            self.abort_reason = reason

    # ------------------------------------------------------------------ play
    async def _play(self, client: httpx.AsyncClient, game: dict, model: dict,
                    t_game: float) -> None:
        trial = game["trials"][model["key"]]
        decide = self.deciders[model["api"]]
        state = game["puzzle"]["state"]
        trial["status"] = "playing"
        trial["final_state"] = state
        t0 = time.perf_counter()
        while trial["turns"] < self.rules.max_moves and not is_solved(state):
            if self.abort_reason:
                trial["status"] = "aborted"
                break
            if self._cost >= self.rules.run_budget_usd:
                self.request_abort(f"run budget reached (${self._cost:.4f} of "
                                   f"${self.rules.run_budget_usd:.2f})")
                trial["status"] = "aborted"
                break
            payload = build_state(state, trial["applied_moves"],
                                  self.rules.max_moves - trial["turns"])
            t_start = round((time.perf_counter() - t_game) * 1000, 1)
            try:
                res = await decide(client, model["id"], payload, self.rules)
            except RunAborted as exc:
                self.request_abort(str(exc))
                trial["status"] = "aborted"
                break
            t_end = round((time.perf_counter() - t_game) * 1000, 1)

            spend = self.data["spend"]
            spend["http_attempts"] += res.attempts
            spend["turns"] += 1
            if res.cost_usd is None:
                spend["turns_without_reported_cost"] += 1
            else:
                self._cost += float(res.cost_usd)
                spend["reported_cost_usd"] = round(self._cost, 8)

            analysis = await asyncio.to_thread(_step_analysis, state, res.move)
            if res.outcome == "ok":
                state = apply_move(state, res.move)
                trial["applied_moves"].append(res.move)
            trial["turns"] += 1
            trial["final_state"] = state
            step = res.to_dict()
            step.update(turn=trial["turns"], t_start_ms=t_start, t_end_ms=t_end,
                        state_after=state, solved_after=is_solved(state), **analysis)
            trial["steps"].append(step)

        trial["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        if trial["status"] != "aborted":
            trial["solved"] = is_solved(state)
            trial["status"] = "solved" if trial["solved"] else "out_of_moves"

    async def execute(self, client: httpx.AsyncClient | None = None) -> dict:
        own_client = client is None
        if own_client:
            client = httpx.AsyncClient(headers={
                "Authorization": f"Bearer {api_key()}",
                "Content-Type": "application/json",
                "X-Title": "rubiks-reasoning-latency-bench",
            })
        try:
            await asyncio.to_thread(solver.warm_up)
            for game in self.data["games"]:
                if self.abort_reason:
                    break
                self.data["current_game"] = game["index"]
                game["started_utc"] = _now()
                t_game = time.perf_counter()
                await asyncio.gather(*(self._play(client, game, m, t_game) for m in MODELS))
                self.save()
        finally:
            if own_client:
                await client.aclose()
        self.data["status"] = "aborted" if self.abort_reason else "completed"
        self.data["abort_reason"] = self.abort_reason
        self.data["finished_utc"] = _now()
        self.save()
        return self.data

    def save(self) -> Path:
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        path = RUNS_DIR / f"{self.id}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1))
        tmp.replace(path)
        return path


def list_runs() -> list[dict]:
    out = []
    if RUNS_DIR.exists():
        for p in sorted(RUNS_DIR.glob("*.json"), reverse=True):
            try:
                d = json.loads(p.read_text())
            except ValueError:
                continue
            out.append({"id": d["id"], "tier": d["tier"], "mode": d.get("mode"),
                        "status": d["status"], "created_utc": d["created_utc"],
                        "games": len(d["games"]),
                        "cost_usd": d["spend"]["reported_cost_usd"]})
    return out


def load_run(run_id: str) -> dict:
    path = RUNS_DIR / f"{run_id}.json"
    if not path.resolve().parent == RUNS_DIR.resolve() or not path.exists():
        raise FileNotFoundError(run_id)
    return json.loads(path.read_text())
