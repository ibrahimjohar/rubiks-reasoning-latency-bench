from backend.app import solver
from backend.app.cube import SOLVED, apply_moves
from backend.app.scrambles import TIERS, build_suite, generate_tier, load_suite


def test_generation_is_deterministic():
    assert generate_tier("primary") == generate_tier("primary")


def test_committed_suite_matches_generator():
    """The puzzles.json in the repo is exactly what the fixed seeds produce."""
    assert load_suite() == build_suite()


def test_exact_tiers_have_true_distance_equal_to_length():
    for tier in ("warmup", "primary"):
        lo, hi = TIERS[tier]["lengths"]
        for p in load_suite()["tiers"][tier]:
            assert lo <= len(p["scramble"]) <= hi
            assert p["state"] == apply_moves(SOLVED, p["scramble"])
            assert solver.distance(p["state"]) == p["shortest_distance"] == len(p["scramble"])
            assert apply_moves(p["state"], p["shortest_solution"]) == SOLVED


def test_primary_suite_size_and_uniqueness():
    suite = load_suite()["tiers"]
    assert len(suite["primary"]) >= 5            # PDF minimum
    states = [p["state"] for t in suite.values() for p in t]
    assert len(states) == len(set(states))


def test_no_redundant_consecutive_turns():
    for tier in load_suite()["tiers"].values():
        for p in tier:
            seq = p["scramble"]
            assert all(a[0] != b[0] for a, b in zip(seq, seq[1:]))


def test_extension_lengths():
    for p in load_suite()["tiers"]["extension"]:
        assert 15 <= len(p["scramble"]) <= 20
        assert p["state"] == apply_moves(SOLVED, p["scramble"])
