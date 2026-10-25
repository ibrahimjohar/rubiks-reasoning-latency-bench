"""Benchmark statistics computed from saved run files.

Definitions (also documented in the README):
  avg latency / move  mean duration of the API request that produced each turn
                      (final attempt; retries are reported separately)
  total solve time    wall time of a trial from first request to solved / move
                      limit, including retries and backoff
  total moves         turns used (every turn counts, including malformed and
                      failed requests, because each one consumes a move)
  success rate        solved trials / completed trials
  optimality gap      turns used - exact shortest distance, solved trials only;
                      unsolved trials have no gap (reported as N/A, never 30)
  optimal-move rate   share of turns whose move was one of the exact optimal
                      moves from that state (ties counted), where the distance
                      was exactly computable
Trials stopped by an abort are excluded and counted separately.
"""

from __future__ import annotations

import random
import statistics
from functools import lru_cache
from operator import itemgetter

from . import solver
from .cube import MOVES, MOVE_PERMS, is_solved
from .rules import MODELS

_GET = [itemgetter(*MOVE_PERMS[m]) for m in MOVES]


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.fmean(xs), 3) if xs else None


def _median(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 3) if xs else None


@lru_cache(maxsize=256)
def random_solve_probability(state: str, max_moves: int, sims: int = 3000,
                             seed: int = 12345) -> float:
    """Monte Carlo: chance that uniformly random legal moves solve the cube
    within max_moves turns. A zero-cost control for 'is the model guessing?'."""
    rng = random.Random(seed)
    solved = 0
    for _ in range(sims):
        s = state
        for _ in range(max_moves):
            s = "".join(rng.choice(_GET)(s))
            if is_solved(s):
                solved += 1
                break
    return solved / sims


def _completed_trials(run: dict, key: str):
    for game in run["games"]:
        t = game["trials"][key]
        if t["status"] in ("solved", "out_of_moves"):
            yield game, t


def model_stats(run: dict, key: str) -> dict:
    trials = list(_completed_trials(run, key))
    aborted = sum(1 for g in run["games"] if g["trials"][key]["status"] == "aborted")
    steps = [s for _, t in trials for s in t["steps"]]
    solved = [(g, t) for g, t in trials if t["solved"]]
    gaps = [t["turns"] - g["puzzle"]["shortest_distance"] for g, t in solved
            if g["puzzle"]["shortest_distance"] is not None]
    judged = [s for s in steps if s.get("optimal_moves")]
    costs = [s["cost_usd"] for s in steps if s.get("cost_usd") is not None]
    confid = [s["confidence"] for s in steps if s.get("confidence") is not None]
    return {
        "model": key,
        "trials": len(trials),
        "aborted_trials": aborted,
        "solved": len(solved),
        "success_rate_pct": round(100 * len(solved) / len(trials), 1) if trials else None,
        "avg_latency_ms": _mean([s.get("latency_ms") for s in steps]),
        "median_latency_ms": _median([s.get("latency_ms") for s in steps]),
        "avg_trial_time_s": _mean([t["elapsed_ms"] / 1000 for _, t in trials]),
        "total_time_s": round(sum(t["elapsed_ms"] for _, t in trials) / 1000, 2) if trials else None,
        "avg_moves": _mean([t["turns"] for _, t in trials]),
        "total_moves": sum(t["turns"] for _, t in trials),
        "avg_moves_solved": _mean([t["turns"] for _, t in solved]),
        "avg_optimality_gap": _mean(gaps),
        "gap_n": len(gaps),
        "optimal_solves": sum(1 for g in gaps if g == 0),
        "optimal_move_rate_pct": (round(100 * sum(bool(s["was_optimal"]) for s in judged) / len(judged), 1)
                                  if judged else None),
        "malformed": sum(1 for s in steps if s["outcome"] == "malformed"),
        "errors": sum(1 for s in steps if s["outcome"] == "error"),
        "retries": sum(s.get("retries", 0) for s in steps),
        "avg_confidence": _mean(confid),
        "cost_usd": round(sum(costs), 6),
        "cost_per_move_usd": round(sum(costs) / len(costs), 6) if costs else None,
        "input_tokens": sum(s.get("input_tokens") or 0 for s in steps),
        "output_tokens": sum(s.get("output_tokens") or 0 for s in steps),
        "reasoning_tokens": sum(s.get("reasoning_tokens") or 0 for s in steps),
    }


def random_baseline(run: dict) -> dict:
    """Reference row: a policy that picks one of the 18 moves uniformly at random."""
    max_moves = run["rules"]["max_moves"]
    probs, opt_share = [], []
    for game in run["games"]:
        p = game["puzzle"]
        probs.append(random_solve_probability(p["state"], max_moves))
        if p["shortest_distance"]:
            opt_share.append(len(solver.optimal_moves(p["state"])) / len(MOVES))
    return {
        "model": "random",
        "success_rate_pct": round(100 * statistics.fmean(probs), 2) if probs else None,
        "optimal_move_rate_pct_first_turn": round(100 * statistics.fmean(opt_share), 1) if opt_share else None,
    }


def run_stats(run: dict) -> dict:
    return {
        "run_id": run["id"],
        "tier": run["tier"],
        "status": run["status"],
        "games": len(run["games"]),
        "rules": run["rules"],
        "spend": run["spend"],
        "models": [model_stats(run, m["key"]) for m in MODELS],
        "random_baseline": random_baseline(run),
    }
