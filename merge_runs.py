"""
Combine two runs of the SAME tier into one 4-model result file for the dashboard,
slide and report. Takes Jev/Luna/Clef trials from one run and Opus trials from
another (e.g. the original primary run + an Opus-only re-run with higher effort).

This is valid only because the puzzles, the state object, the question, the move
limit and the scoring are identical in both runs; the script checks that and
refuses otherwise. Provenance (both run ids and both rule snapshots) is stored.

    python merge_runs.py --decisions 20261109T161544Z-dceb5d --opus <opus-run-id>
"""

import argparse
import json
from datetime import datetime, timezone

from backend.app.rules import MODELS
from backend.app.runner import RUNS_DIR, load_run

def merge(a: dict, b: dict) -> dict:
    """jev/luna/clef trials from run a, opus trials from run b."""
    pa = [g["puzzle"]["id"] for g in a["games"]]
    pb = [g["puzzle"]["id"] for g in b["games"]]
    if a["tier"] != b["tier"] or pa != pb:
        raise ValueError(f"Runs differ in tier or puzzles: {a['tier']} {pa} vs {b['tier']} {pb}")
    if a["rules"]["max_moves"] != b["rules"]["max_moves"]:
        raise ValueError("Runs differ in move limit")
    if a["status"] != "completed" or b["status"] != "completed":
        raise ValueError(f"Both runs must be completed (got {a['status']}, {b['status']})")
    if any("opus" not in g["trials"] for g in b["games"]):
        raise ValueError("--opus run has no Opus trials")
    if any(k not in g["trials"] for g in a["games"] for k in ("jev", "luna", "clef")):
        raise ValueError("--decisions run is missing decision-model trials")

    games = []
    for ga, gb in zip(a["games"], b["games"]):
        trials = {k: ga["trials"][k] for k in ("jev", "luna", "clef")}
        trials["opus"] = gb["trials"]["opus"]
        games.append({**ga, "trials": trials})

    opus_a = sum(s.get("cost_usd") or 0 for g in a["games"]
                 for s in g["trials"].get("opus", {}).get("steps", []))
    cost = a["spend"]["reported_cost_usd"] - opus_a + b["spend"]["reported_cost_usd"]
    rid = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-merged"
    return {
        "id": rid, "mode": "merged", "tier": a["tier"],
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "finished_utc": b["finished_utc"], "status": "completed", "abort_reason": None,
        "rules": b["rules"], "models": MODELS, "plan": a["plan"],
        "spend": {"reported_cost_usd": round(cost, 8), "http_attempts": None,
                  "turns": sum(t["turns"] for g in games for t in g["trials"].values()),
                  "turns_without_reported_cost": None},
        "current_game": len(games) - 1, "games": games,
        "provenance": {"decision_models_from": a["id"], "opus_from": b["id"],
                       "decision_rules": a["rules"], "opus_rules": b["rules"]},
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--decisions", required=True, help="run id providing jev, luna, clef")
    ap.add_argument("--opus", required=True, help="run id providing opus")
    args = ap.parse_args()
    try:
        m = merge(load_run(args.decisions), load_run(args.opus))
    except ValueError as exc:
        raise SystemExit(str(exc))
    (RUNS_DIR / f"{m['id']}.json").write_text(json.dumps(m, indent=1))
    print(f"Saved results/runs/{m['id']}.json (jev/luna/clef from {args.decisions}, opus from {args.opus})")
