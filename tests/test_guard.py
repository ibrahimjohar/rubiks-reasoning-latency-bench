"""Planning guard, model subsets and run merging. Offline, no cost."""

import asyncio
import pytest

from backend.app import runner, solver, stats
from backend.app.adapters.base import MoveResult
from backend.app.rules import Rules


@pytest.fixture(autouse=True)
def scratch_runs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "RUNS_DIR", tmp_path)


def opus_like(reasoning, finish="stop", outcome="ok", error=None, smart=True):
    async def decide(client, model_id, state, rules):
        mv = solver.optimal_moves(state["cube_facelets"])[0] if smart else "U"
        return MoveResult(outcome=outcome, move=mv if outcome == "ok" else None,
                          raw_move=mv, latency_ms=10.0, wall_ms=10.0, attempts=1,
                          cost_usd=0.01, reasoning_tokens=reasoning,
                          finish_reason=finish, error=error)
    return decide


async def never_called(client, model_id, state, rules):
    raise AssertionError("decision models must not play in an opus-only run")


def run(chat, models=("opus",), guard=True, n=3):
    r = runner.Run("primary", n, 1, Rules(), {"decisions": never_called, "chat": chat},
                   label="test", models=list(models), guard=guard)
    return asyncio.run(r.execute(client=object()))


def test_guard_aborts_when_opus_does_not_reason():
    data = run(opus_like(reasoning=0, smart=False))
    assert data["status"] == "aborted"
    assert "reasoned <" in data["abort_reason"]
    assert data["spend"]["turns"] == runner.GUARD_WINDOW   # stopped right after the window


def test_guard_aborts_on_cutoffs():
    data = run(opus_like(reasoning=5000, finish="length", outcome="malformed"))
    assert data["status"] == "aborted" and "max_tokens" in data["abort_reason"]
    assert data["spend"]["turns"] == runner.GUARD_MAX_CUTOFF


def test_guard_aborts_on_timeouts():
    data = run(opus_like(reasoning=None, outcome="error", error="timeout after 60.0s"))
    assert data["status"] == "aborted" and "timeout" in data["abort_reason"]


def test_guard_passes_a_thinking_model_and_subset_plays_only_opus():
    data = run(opus_like(reasoning=3000))
    assert data["status"] == "completed"
    assert [m["key"] for m in data["models"]] == ["opus"]
    st = stats.run_stats(data)
    assert [m["model"] for m in st["models"]] == ["opus"]
    assert st["models"][0]["success_rate_pct"] == 100.0


def test_guard_off_by_default_in_runner():
    data = run(opus_like(reasoning=0, smart=False), guard=False, n=1)
    assert data["status"] == "completed"


def test_merge_combines_runs():
    from merge_runs import merge

    async def dumb(client, model_id, state, rules):
        return MoveResult(outcome="ok", move="U", raw_move="U", latency_ms=1.0,
                          wall_ms=1.0, attempts=1, cost_usd=0.001)
    full = runner.Run("primary", 2, 1, Rules(), {"decisions": dumb, "chat": dumb}, label="t")
    a = asyncio.run(full.execute(client=object()))
    b = run(opus_like(reasoning=3000), n=2)
    m = merge(a, b)
    assert [x["key"] for x in m["models"]] == ["jev", "luna", "clef", "opus"]
    for ga, gb, gm in zip(a["games"], b["games"], m["games"]):
        assert gm["trials"]["jev"] is ga["trials"]["jev"]
        assert gm["trials"]["opus"] is gb["trials"]["opus"]
    st = {x["model"]: x for x in stats.run_stats(m)["models"]}
    assert st["opus"]["success_rate_pct"] == 100.0 and st["jev"]["success_rate_pct"] == 0.0
    assert m["provenance"] == {"decision_models_from": a["id"], "opus_from": b["id"],
                               "decision_rules": a["rules"], "opus_rules": b["rules"]}


def test_merge_refuses_different_puzzles():
    from merge_runs import merge
    a = run(opus_like(reasoning=3000), n=2)
    b = run(opus_like(reasoning=3000), n=3)
    with pytest.raises(ValueError):
        merge(a, b)
