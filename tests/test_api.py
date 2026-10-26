"""End-to-end API test with scripted offline players. No network, no cost."""

import time

import pytest
from fastapi.testclient import TestClient

from backend.app import main, runner, solver
from backend.app.adapters.base import MoveResult


async def perfect(client, model_id, state, rules):
    move = solver.optimal_moves(state["cube_facelets"])[0]
    return MoveResult(outcome="ok", move=move, raw_move=move, latency_ms=1.0,
                      wall_ms=1.0, attempts=1, cost_usd=0.0)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(main, "api_key", lambda: "test-key")
    monkeypatch.setattr(runner, "DEFAULT_DECIDERS", {"decisions": perfect, "chat": perfect})
    main._active.update(run=None, task=None)
    with TestClient(main.app) as c:
        yield c


def test_config_never_exposes_key(client):
    cfg = client.get("/api/config").json()
    assert "test-key" not in str(cfg)
    assert cfg["student"] == {"name": "Ibrahim Johar Farooqi", "roll": "23K-0074"}
    assert [m["key"] for m in cfg["models"]] == ["jev", "luna", "clef", "opus"]


def test_run_requires_confirmation(client):
    r = client.post("/api/runs", json={"tier": "warmup"})
    assert r.status_code == 400


def test_live_run_end_to_end(client):
    start = client.post("/api/runs", json={"tier": "warmup", "puzzles": 2, "confirm": True}).json()
    run_id = start["id"]
    for _ in range(200):
        data = client.get(f"/api/runs/{run_id}").json()
        if data["status"] != "running":
            break
        time.sleep(0.05)
    assert data["status"] == "completed"
    st = client.get(f"/api/runs/{run_id}/stats").json()
    assert all(m["success_rate_pct"] == 100.0 for m in st["models"])
    assert all(m["avg_optimality_gap"] == 0 for m in st["models"])
    assert any(r["id"] == run_id for r in client.get("/api/runs").json())


def test_unknown_run_is_404(client):
    assert client.get("/api/runs/does-not-exist").status_code == 404
    assert client.get("/api/runs/..%2F..%2Fetc").status_code == 404
