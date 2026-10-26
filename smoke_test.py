"""Smoke test: ONE request per model through the real benchmark adapters.

Uses exactly the payloads the benchmark sends (same state object, same
question, Opus structured output) on the state "solved + R", whose only
optimal reply is R'. Costs well under one cent.

    python smoke_test.py                 # all four models
    python smoke_test.py --models opus   # a subset
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone

import httpx

from backend.app.adapters import chat, decisions
from backend.app.adapters.base import RunAborted
from backend.app.cube import SOLVED, apply_move
from backend.app.prompt import build_state
from backend.app.rules import MODEL_BY_KEY, ROOT, api_key, load_rules

STATE = apply_move(SOLVED, "R")
OPTIMAL = "R'"


async def main(keys: list[str]) -> None:
    rules = load_rules()
    payload = build_state(STATE, [], rules.max_moves)
    print(f"Opus: effort={rules.opus_reasoning_effort}, max_tokens={rules.opus_max_tokens}, "
          f"structured_output={rules.opus_structured_output}\n")
    results = {}
    headers = {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json",
               "X-Title": "rubiks-reasoning-latency-bench"}
    async with httpx.AsyncClient(headers=headers) as client:
        for key in keys:
            m = MODEL_BY_KEY[key]
            adapter = decisions if m["api"] == "decisions" else chat
            try:
                res = await adapter.decide(client, m["id"], payload, rules)
            except RunAborted as exc:
                print(f"{key}: ABORTED - {exc}")
                break
            results[key] = res.to_dict()
            print(f"{key:5} {res.outcome:9} move={str(res.move):4} optimal={res.move == OPTIMAL!s:5} "
                  f"{res.latency_ms} ms  cost=${res.cost_usd}  "
                  + (f"error={res.error}" if res.error else ""))
            if res.outcome != "ok" and res.raw_content:
                print(f"      raw reply: {res.raw_content[:200]!r}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "results" / f"smoke_test_{stamp}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"timestamp_utc": stamp, "state": STATE, "optimal_move": OPTIMAL,
                               "rules": rules.snapshot(), "results": results}, indent=2))
    total = sum(r["cost_usd"] or 0 for r in results.values())
    print(f"\nTotal reported cost: ${total:.6f}\nSaved to {out.relative_to(ROOT)}")
    opus = results.get("opus")
    if opus and opus["outcome"] == "error" and rules.opus_structured_output:
        print("\nOpus failed with structured output on. If the error mentions response_format "
              "or no available provider, set OPUS_STRUCTURED_OUTPUT=false in .env and retry.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="jev,luna,clef,opus")
    args = ap.parse_args()
    keys = [k.strip() for k in args.models.split(",") if k.strip()]
    if bad := [k for k in keys if k not in MODEL_BY_KEY]:
        sys.exit(f"Unknown model key(s): {bad}. Use: {', '.join(MODEL_BY_KEY)}")
    if not api_key():
        sys.exit("OPENROUTER_API_KEY is missing. Copy .env.example to .env and add your key.")
    asyncio.run(main(keys))
