"""Runner and stats tests with scripted offline players. No network, no cost."""

import asyncio
from dataclasses import replace

import pytest

from backend.app import runner, solver, stats
from backend.app.adapters.base import MoveResult, RunAborted
from backend.app.rules import Rules


@pytest.fixture(autouse=True)
def scratch_runs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "RUNS_DIR", tmp_path)


RULES = Rules()


def make_run(dec, chat, tier="primary", n=2, rules=RULES):
    r = runner.Run(tier, n, 1, rules, {"decisions": dec, "chat": chat}, label="test")
    return r, asyncio.run(r.execute(client=object()))


def ok(move, cost=0.001):
    return MoveResult(outcome="ok", move=move, raw_move=move, latency_ms=10.0,
                      wall_ms=10.0, attempts=1, cost_usd=cost)


async def perfect(client, model_id, state, rules):
    return ok(solver.optimal_moves(state["cube_facelets"])[0])


async def always_u(client, model_id, state, rules):
    return ok("U")


async def always_malformed(client, model_id, state, rules):
    return MoveResult(outcome="malformed", raw_move="nonsense", latency_ms=5.0,
                      wall_ms=5.0, attempts=1, error="bad")


def test_perfect_player_solves_with_zero_gap_and_cap_holds():
    r, data = make_run(always_u, perfect)
    assert data["status"] == "completed"
    st = {m["model"]: m for m in stats.run_stats(data)["models"]}
    assert st["opus"]["success_rate_pct"] == 100.0
    assert st["opus"]["avg_optimality_gap"] == 0
    assert st["opus"]["optimal_move_rate_pct"] == 100.0
    assert st["jev"]["success_rate_pct"] == 0.0
    assert st["jev"]["avg_optimality_gap"] is None        # unsolved: N/A, never 30
    for g in data["games"]:
        assert g["trials"]["jev"]["turns"] == RULES.max_moves
        assert g["trials"]["opus"]["turns"] == g["puzzle"]["shortest_distance"]


def test_every_model_gets_the_same_first_state():
    seen = {}

    async def spy(client, model_id, state, rules):
        seen.setdefault(model_id, state)
        return ok("U")

    make_run(spy, spy, n=1)
    first = list(seen.values())
    assert len(first) == 4 and all(s == first[0] for s in first)


def test_malformed_turns_count_and_leave_cube_unchanged():
    r, data = make_run(always_malformed, always_malformed, n=1)
    t = data["games"][0]["trials"]["opus"]
    assert t["turns"] == RULES.max_moves and t["applied_moves"] == []
    assert t["final_state"] == data["games"][0]["puzzle"]["state"]
    st = {m["model"]: m for m in stats.run_stats(data)["models"]}
    assert st["opus"]["malformed"] == RULES.max_moves


def test_account_error_aborts_whole_run_and_trials_excluded():
    async def broke(client, model_id, state, rules):
        raise RunAborted("HTTP 402: out of credits")

    r, data = make_run(always_u, broke, n=3)
    assert data["status"] == "aborted" and "402" in data["abort_reason"]
    st = {m["model"]: m for m in stats.run_stats(data)["models"]}
    assert st["opus"]["trials"] == 0 and st["opus"]["aborted_trials"] >= 1
    assert all(g["trials"]["jev"]["status"] == "pending" for g in data["games"][1:])


def test_run_budget_stops_new_requests():
    rules = replace(RULES, run_budget_usd=0.01)
    calls = {"n": 0}

    async def pricey(client, model_id, state, rules):
        calls["n"] += 1
        return ok("U", cost=0.004)

    r, data = make_run(pricey, pricey, n=2, rules=rules)
    assert data["status"] == "aborted" and "budget" in data["abort_reason"]
    # At most one in-flight call per model can complete after the limit.
    assert data["spend"]["reported_cost_usd"] < 0.01 + 4 * 0.004
    assert calls["n"] < 10


def test_random_baseline_is_low_for_primary():
    r, data = make_run(always_u, perfect, n=2)
    base = stats.random_baseline(data)
    assert 0 <= base["success_rate_pct"] < 5
