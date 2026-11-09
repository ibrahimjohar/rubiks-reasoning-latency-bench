"""
Pilot: check that Opus is configured to actually plan BEFORE paying for a full run.

Sends TWO requests per puzzle with the settings you pass:
  1. the puzzle's starting state (no history),
  2. the state after one exact optimal move, with that move in the history.
Request 2 catches the failure seen in the primary run, where Opus undid its own
correct move on the next turn. Nothing is played; no run file is written. It reports, per
puzzle: reasoning tokens, whether the reply was cut off, latency, cost and
whether the chosen move is one of the exact optimal moves. Then it projects the
cost of a full Opus-only run and prints PASS/FAIL against fixed criteria.

    python pilot_opus.py --effort medium --max-tokens 8000 --puzzles 5
    python pilot_opus.py --effort high   --max-tokens 16000 --puzzles 5

Stops early once its own spend reaches --budget (default $1.50).
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import statistics
from datetime import datetime, timezone

import httpx

from backend.app import solver
from backend.app.cube import apply_move, inverse_move
from backend.app.adapters import chat
from backend.app.adapters.base import RunAborted
from backend.app.prompt import build_state
from backend.app.rules import MODEL_BY_KEY, ROOT, api_key, load_rules
from backend.app.scrambles import get_puzzles

# Pass criteria (decided before seeing any result).
MIN_OPTIMAL_SHARE = 0.6     # at least 60% of first moves are exactly optimal
MIN_MEDIAN_REASONING = 500  # Opus really thinks: median >= 500 reasoning tokens
MAX_CUTOFF = 0              # no reply cut off by max_tokens
MAX_ERRORS = 0              # no timeouts / HTTP errors
MAX_UNDO_SHARE = 0.2        # at most 20% of mid-game replies undo the previous (correct) move


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--effort", choices=["low", "medium", "high"], required=True)
    ap.add_argument("--max-tokens", type=int, required=True)
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--tier", default="primary")
    ap.add_argument("--puzzles", type=int, default=5)
    ap.add_argument("--budget", type=float, default=1.50)
    args = ap.parse_args()

    if not api_key():
        raise SystemExit("OPENROUTER_API_KEY is missing from .env")
    rules = dataclasses.replace(load_rules(), opus_reasoning_effort=args.effort,
                                opus_max_tokens=args.max_tokens,
                                timeout_seconds=args.timeout, max_retries=1)
    puzzles = get_puzzles(args.tier, args.puzzles)
    print(f"Pilot: Opus, effort={args.effort}, max_tokens={args.max_tokens}, "
          f"timeout={args.timeout}s, {len(puzzles)} {args.tier} puzzles, budget ${args.budget:.2f}")
    if input('Type "yes" to send up to %d paid requests: ' % (2 * len(puzzles))).strip().lower() != "yes":
        raise SystemExit("Cancelled. No requests were sent.")

    await asyncio.to_thread(solver.warm_up)
    rows, spent = [], 0.0
    headers = {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json",
               "X-Title": "rubiks-reasoning-latency-bench"}
    async with httpx.AsyncClient(headers=headers) as client:
        stop = False
        for p in puzzles:
            if stop:
                break
            first = solver.optimal_moves(p["state"])[0]
            probes = [("start", p["state"], []),
                      ("mid", apply_move(p["state"], first), [first])]
            for kind, facelets, history in probes:
                if spent >= args.budget:
                    break
                state = build_state(facelets, history, rules.max_moves - len(history))
                try:
                    res = await chat.decide(client, MODEL_BY_KEY["opus"]["id"], state, rules)
                except RunAborted as exc:
                    print(f"Stopped: {exc}")
                    stop = True
                    break
                spent += res.cost_usd or 0.0
                opt = solver.optimal_moves(facelets)
                good = res.move in opt if res.move else False
                undo = bool(history) and res.move == inverse_move(history[-1])
                rows.append({"puzzle": p["id"], "probe": kind, "distance": solver.distance(facelets),
                             "history": history, "outcome": res.outcome, "move": res.move,
                             "optimal": good, "undo": undo, "optimal_moves": opt,
                             "reasoning_tokens": res.reasoning_tokens,
                             "output_tokens": res.output_tokens, "finish_reason": res.finish_reason,
                             "latency_ms": res.latency_ms, "cost_usd": res.cost_usd,
                             "error": res.error})
                print(f"{p['id']:11} {kind:5} d={solver.distance(facelets)} {res.outcome:9} "
                      f"move={str(res.move):4} optimal={str(good):5} undo={str(undo):5} "
                      f"reasoning={res.reasoning_tokens} finish={res.finish_reason} "
                      f"{(res.latency_ms or 0)/1000:.1f} s ${res.cost_usd or 0:.4f}")
            if spent >= args.budget:
                print(f"Stopped: pilot budget ${args.budget:.2f} reached.")
                break

    n = len(rows)
    if not n:
        return
    opt_share = sum(r["optimal"] for r in rows) / n
    med_reason = statistics.median([r["reasoning_tokens"] or 0 for r in rows])
    mids = [r for r in rows if r["probe"] == "mid"]
    undo_share = (sum(r["undo"] for r in mids) / len(mids)) if mids else 0.0
    cutoff = sum(r["finish_reason"] == "length" for r in rows)
    errors = sum(r["outcome"] == "error" for r in rows)
    costs = [r["cost_usd"] for r in rows if r["cost_usd"]]
    per_call = statistics.mean(costs) if costs else 0.0
    lat = statistics.mean([r["latency_ms"] or 0 for r in rows])

    checks = [
        (f"move optimal on >= {MIN_OPTIMAL_SHARE:.0%} of probes", opt_share >= MIN_OPTIMAL_SHARE, f"{opt_share:.0%}"),
        (f"undoes its own correct move on <= {MAX_UNDO_SHARE:.0%} of mid-game probes",
         undo_share <= MAX_UNDO_SHARE, f"{undo_share:.0%}"),
        (f"median reasoning >= {MIN_MEDIAN_REASONING} tokens", med_reason >= MIN_MEDIAN_REASONING, f"{med_reason:.0f}"),
        ("no reply cut off by max_tokens", cutoff <= MAX_CUTOFF, str(cutoff)),
        ("no timeouts / errors", errors <= MAX_ERRORS, str(errors)),
    ]
    print(f"\nSpent ${spent:.4f} | mean ${per_call:.4f} per call | mean latency {lat/1000:.1f} s")
    for name, ok, val in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {val}")
    verdict = all(ok for _, ok, _ in checks)

    full = get_puzzles(args.tier)
    best = sum(p["shortest_distance"] for p in full)            # every move optimal
    likely = round(sum(p["shortest_distance"] for p in full) / max(opt_share, 0.25))  # detours ~ 1/accuracy
    worst = len(full) * rules.max_moves                          # never solves
    print(f"\nProjected Opus-only cost for all {len(full)} {args.tier} puzzles:")
    print(f"  best ${best * per_call:.2f} ({best} turns) | likely ${likely * per_call:.2f} "
          f"({likely} turns) | worst ${worst * per_call:.2f} ({worst} turns)")
    print(f"  wall time, likely: ~{likely * lat / 60000:.0f} min (puzzles run one after another)")
    print("\nVERDICT:", "PASS - settings are fit for a full run." if verdict
          else "FAIL - do NOT run the full benchmark with these settings.")

    out = ROOT / "results" / "pilots"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"pilot_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{args.effort}.json"
    path.write_text(json.dumps({"settings": vars(args), "rows": rows, "spent_usd": spent,
                                "checks": [{"check": c, "pass": ok, "value": v} for c, ok, v in checks],
                                "verdict": verdict}, indent=1))
    print(f"Saved to {path.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
