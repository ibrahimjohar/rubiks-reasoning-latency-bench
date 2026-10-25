import random
from collections import Counter

from backend.app import solver
from backend.app.cube import MOVES, SOLVED, apply_move, apply_moves


def test_layer_sizes_match_known_values():
    # Number of states at exact HTM distance 0..4 (OEIS A080601).
    counts = Counter(solver._backward_table().values())
    assert [counts[d] for d in range(5)] == [1, 18, 243, 3240, 43239]


def test_trivial_distances():
    assert solver.distance(SOLVED) == 0
    for m in MOVES:
        assert solver.distance(apply_move(SOLVED, m)) == 1
        assert solver.optimal_moves(apply_move(SOLVED, m)) == [
            m if m.endswith("2") else (m[0] if m.endswith("'") else m + "'")]


def test_distance_against_plain_bfs_to_depth_5():
    # Independent plain BFS from solved to depth 5 (~620k states).
    from operator import itemgetter
    from backend.app.cube import MOVE_PERMS
    getters = [itemgetter(*MOVE_PERMS[m]) for m in MOVES]
    dist, frontier = {SOLVED: 0}, [SOLVED]
    for d in range(1, 6):
        nxt = []
        for s in frontier:
            for g in getters:
                t = "".join(g(s))
                if t not in dist:
                    dist[t] = d
                    nxt.append(t)
        frontier = nxt
    assert Counter(dist.values())[5] == 574908
    rng = random.Random(1)
    for state, d in rng.sample(list(dist.items()), 2000):
        assert solver.distance(state) == d


def test_shortest_solution_solves_and_is_minimal():
    rng = random.Random(2)
    for _ in range(50):
        seq = [rng.choice(MOVES) for _ in range(rng.randint(1, 7))]
        state = apply_moves(SOLVED, seq)
        d = solver.distance(state)
        assert d is not None and d <= len(seq)
        sol = solver.shortest_solution(state)
        assert len(sol) == d
        assert apply_moves(state, sol) == SOLVED


def test_all_optimal_moves_reduce_distance_and_ties_are_included():
    state = apply_moves(SOLVED, "U D")      # U and D commute: two optimal first moves
    assert solver.distance(state) == 2
    assert sorted(solver.optimal_moves(state)) == sorted(["U'", "D'"])


def test_far_states_report_unknown():
    rng = random.Random(3)
    unknown = 0
    for _ in range(20):
        state = apply_moves(SOLVED, [rng.choice(MOVES) for _ in range(25)])
        d = solver.distance(state)
        assert d is None or d <= solver.MAX_EXACT_DISTANCE
        unknown += d is None
    assert unknown > 0
