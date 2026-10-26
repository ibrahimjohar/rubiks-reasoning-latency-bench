"""Fixed-seed scramble suites for the three test tiers.

Rules for every scramble:
  * no two consecutive turns of the same face (no "R R'" or "R R2"),
  * no "X Y X" sandwich where X and Y are opposite faces (e.g. "U D U"),
    because the X turns commute and would collapse into one.
For warm-up and primary puzzles the BFS distance must equal the scramble
length, so a "5-move" puzzle really needs exactly 5 moves. Extension puzzles
(15-20 turns) are too deep for exact search, so their distance is unknown.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from . import solver
from .cube import MOVES, SOLVED, apply_moves

OPPOSITE = {"U": "D", "D": "U", "R": "L", "L": "R", "F": "B", "B": "F"}

TIERS = {
    "warmup":    {"lengths": (3, 4),   "default_count": 3,  "seed": 101},
    "primary":   {"lengths": (4, 5),   "default_count": 10, "seed": 202},
    "extension": {"lengths": (15, 20), "default_count": 5,  "seed": 303},
}

SUITE_PATH = Path(__file__).resolve().parent.parent / "data" / "puzzles.json"


def _random_sequence(rng: random.Random, length: int) -> list[str]:
    seq: list[str] = []
    while len(seq) < length:
        m = rng.choice(MOVES)
        f = m[0]
        if seq and seq[-1][0] == f:
            continue
        if len(seq) >= 2 and seq[-2][0] == f and seq[-1][0] == OPPOSITE[f]:
            continue
        seq.append(m)
    return seq


def generate_tier(tier: str, count: int | None = None) -> list[dict]:
    cfg = TIERS[tier]
    count = count or cfg["default_count"]
    rng = random.Random(cfg["seed"])
    lo, hi = cfg["lengths"]
    puzzles, seen = [], set()
    while len(puzzles) < count:
        # Alternate lengths so both ends of the tier are represented.
        length = lo + (len(puzzles) % (hi - lo + 1)) if hi - lo <= 1 else rng.randint(lo, hi)
        seq = _random_sequence(rng, length)
        state = apply_moves(SOLVED, seq)
        if state in seen:
            continue
        exact = tier != "extension"
        dist = solver.distance(state) if exact else None
        if exact and dist != length:
            continue                      # reject: easier than it claims
        seen.add(state)
        puzzles.append({
            "id": f"{tier}-{len(puzzles) + 1:02d}",
            "tier": tier,
            "scramble": seq,
            "state": state,
            "shortest_distance": dist,
            "shortest_solution": solver.shortest_solution(state) if exact else None,
        })
    return puzzles


def build_suite() -> dict:
    return {
        "description": "Fixed-seed benchmark puzzles. Every model receives exactly these states.",
        "metric": "HTM (half-turn metric: X, X', X2 each count as one move)",
        "seeds": {t: c["seed"] for t, c in TIERS.items()},
        "tiers": {t: generate_tier(t) for t in TIERS},
    }


def load_suite() -> dict:
    """Load the committed suite, generating it on first use."""
    if SUITE_PATH.exists():
        return json.loads(SUITE_PATH.read_text())
    suite = build_suite()
    SUITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUITE_PATH.write_text(json.dumps(suite, indent=2))
    return suite


def get_puzzles(tier: str, count: int | None = None) -> list[dict]:
    puzzles = load_suite()["tiers"][tier]
    if count is not None:
        if count > len(puzzles):
            raise ValueError(f"Only {len(puzzles)} {tier} puzzles in the suite")
        puzzles = puzzles[:count]
    return puzzles

