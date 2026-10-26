"""Run the benchmark from the terminal (same engine as the web UI).

    python run_benchmark.py --tier warmup
    python run_benchmark.py --tier primary              # 10 puzzles x 4 models
    python run_benchmark.py --tier primary --repeats 2  # play the suite twice
    python run_benchmark.py --tier extension

Before any paid call it prints the upper bounds and asks you to type "yes".
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from backend.app import runner, stats
from backend.app.rules import api_key, load_rules
from backend.app.scrambles import TIERS


def print_table(st: dict) -> None:
    head = (f"{'model':6} {'solved':>8} {'rate%':>6} {'lat ms':>8} {'trial s':>8} "
            f"{'moves':>6} {'gap':>5} {'opt%':>5} {'bad':>4} {'err':>4} {'cost $':>9}")
    print(head)
    print("-" * len(head))
    fmt = lambda v, f: "N/A" if v is None else format(v, f)
    for m in st["models"]:
        print(f"{m['model']:6} {m['solved']:>3}/{m['trials']:<4} {fmt(m['success_rate_pct'], '.1f'):>6} "
              f"{fmt(m['avg_latency_ms'], '.0f'):>8} {fmt(m['avg_trial_time_s'], '.1f'):>8} "
              f"{fmt(m['avg_moves'], '.1f'):>6} {fmt(m['avg_optimality_gap'], '.2f'):>5} "
              f"{fmt(m['optimal_move_rate_pct'], '.0f'):>5} {m['malformed']:>4} {m['errors']:>4} "
              f"{m['cost_usd']:>9.5f}")
    print(f"random baseline solve rate: {st['random_baseline']['success_rate_pct']}%")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", choices=list(TIERS), required=True)
    ap.add_argument("--puzzles", type=int, default=None,
                    help="number of puzzles from the fixed suite (default: whole tier)")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = ap.parse_args()

    if not api_key():
        sys.exit("OPENROUTER_API_KEY is missing. Copy .env.example to .env and add your key.")
    rules = load_rules()
    run = runner.Run(args.tier, args.puzzles, args.repeats, rules)
    p = run.data["plan"]
    print(f"\nTier {p['tier']}: {p['puzzles']} puzzle(s) x {p['repeats']} repeat(s) x 4 models")
    print(f"Move limit {rules.max_moves} | timeout {rules.timeout_seconds}s | "
          f"retries {rules.max_retries} | Opus effort {rules.opus_reasoning_effort}, "
          f"max_tokens {rules.opus_max_tokens}")
    print(f"Upper bound: {p['max_turns_per_model']} turns per model, "
          f"{p['max_http_calls_total']} HTTP calls in total")
    print(f"Run budget: stops before any new call once reported spend reaches "
          f"${rules.run_budget_usd:.2f}\n")
    if not args.yes and input('Type "yes" to start paid API calls: ').strip().lower() != "yes":
        sys.exit("Cancelled. No requests were sent.")

    try:
        data = asyncio.run(run.execute())
    except KeyboardInterrupt:
        run.request_abort("interrupted from keyboard")
        run.data["status"] = "aborted"
        run.save()
        sys.exit(f"\nInterrupted. Partial results saved: results/runs/{run.id}.json")

    print(f"\nRun {data['id']}: {data['status']}"
          + (f" ({data['abort_reason']})" if data["abort_reason"] else ""))
    print(f"Reported spend: ${data['spend']['reported_cost_usd']:.5f} over "
          f"{data['spend']['turns']} turns\n")
    print_table(stats.run_stats(data))
    print(f"\nSaved to results/runs/{data['id']}.json")


if __name__ == "__main__":
    main()
