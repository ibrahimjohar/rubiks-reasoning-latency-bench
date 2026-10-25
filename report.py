"""Write markdown result tables from saved runs (for the README).

    python report.py                  # latest completed run of each tier
    python report.py RUN_ID [RUN_ID]  # specific runs

Output: results/summary.md and results/summary.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from backend.app import runner, stats
from backend.app.rules import MODEL_BY_KEY

OUT = Path(__file__).resolve().parent / "results"


def pick_runs(ids: list[str]) -> list[dict]:
    if ids:
        return [runner.load_run(i) for i in ids]
    latest = {}
    for r in runner.list_runs():                       # newest first
        if r["status"] == "completed" and r["mode"] == "live":
            latest.setdefault(r["tier"], r["id"])
    order = ["warmup", "primary", "extension"]
    return [runner.load_run(latest[t]) for t in order if t in latest]


def na(v, f=".1f", suffix=""):
    return "N/A" if v is None else f"{format(v, f)}{suffix}"


def tier_markdown(st: dict) -> str:
    rows = [
        f"### {st['tier'].capitalize()} tier ({st['games']} puzzles, run `{st['run_id']}`)",
        "",
        "| Model | Avg latency / move | Avg time / puzzle | Total time | Avg moves | Total moves "
        "| Solved | Success rate | Avg optimality gap | Optimal solves | Optimal-move rate "
        "| Malformed | Errors | Retries | Cost |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for m in st["models"]:
        name = MODEL_BY_KEY[m["model"]]["name"]
        gap = "N/A" if m["avg_optimality_gap"] is None else f"{m['avg_optimality_gap']:+.2f} (n={m['gap_n']})"
        rows.append(
            f"| {name} | {na(m['avg_latency_ms'], '.0f', ' ms')} | {na(m['avg_trial_time_s'], '.1f', ' s')} "
            f"| {na(m['total_time_s'], '.1f', ' s')} | {na(m['avg_moves'])} | {m['total_moves']} "
            f"| {m['solved']}/{m['trials']} | {na(m['success_rate_pct'], '.1f', '%')} | {gap} "
            f"| {m['optimal_solves']} | {na(m['optimal_move_rate_pct'], '.1f', '%')} "
            f"| {m['malformed']} | {m['errors']} | {m['retries']} | ${m['cost_usd']:.4f} |")
    base = st["random_baseline"]
    rows += ["", f"Random-move baseline (Monte Carlo, same puzzles, {st['rules']['max_moves']}-move limit): "
             f"**{na(base['success_rate_pct'], '.2f', '%')}** solve rate.",
             f"Reported spend for this run: ${st['spend']['reported_cost_usd']:.4f} "
             f"over {st['spend']['turns']} turns.", ""]
    return "\n".join(rows)


def main() -> None:
    runs = pick_runs(sys.argv[1:])
    if not runs:
        sys.exit("No completed live runs found in results/runs/.")
    all_stats = [stats.run_stats(r) for r in runs]
    md = "\n".join(tier_markdown(s) for s in all_stats)
    OUT.mkdir(exist_ok=True)
    (OUT / "summary.md").write_text(md)
    (OUT / "summary.json").write_text(json.dumps(all_stats, indent=2))
    print(md)
    print("Wrote results/summary.md and results/summary.json")


if __name__ == "__main__":
    main()
