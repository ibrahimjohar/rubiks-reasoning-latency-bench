"""Exact shortest-path distances (half-turn metric) via bidirectional BFS.

A table of every state within BACKWARD_DEPTH moves of solved is built once.
For a query state we expand forward up to FORWARD_DEPTH moves and look for the
first layer that meets the table, which gives the exact distance for any state
up to BACKWARD_DEPTH + FORWARD_DEPTH moves away. Beyond that, distance is
reported as None ("further than MAX_EXACT_DISTANCE").

Because every move is self-inverse up to direction, the set of states within
k moves of solved is the same as the set of states from which solved is
reachable in k moves, so the backward table can be built from solved.
"""

from __future__ import annotations

from functools import lru_cache
from operator import itemgetter

from .cube import MOVES, MOVE_PERMS, SOLVED, is_solved

BACKWARD_DEPTH = 4
FORWARD_DEPTH = 3
MAX_EXACT_DISTANCE = BACKWARD_DEPTH + FORWARD_DEPTH   # 7

_GETTERS = {m: itemgetter(*MOVE_PERMS[m]) for m in MOVES}


def _neighbours(state: str):
    for m in MOVES:
        yield m, "".join(_GETTERS[m](state))


@lru_cache(maxsize=1)
def _backward_table() -> dict[str, int]:
    dist = {SOLVED: 0}
    frontier = [SOLVED]
    for d in range(1, BACKWARD_DEPTH + 1):
        nxt = []
        for s in frontier:
            for _, t in _neighbours(s):
                if t not in dist:
                    dist[t] = d
                    nxt.append(t)
        frontier = nxt
    return dist


def warm_up() -> int:
    """Build the table eagerly; returns its size."""
    return len(_backward_table())


@lru_cache(maxsize=200_000)
def distance(state: str) -> int | None:
    """Exact HTM distance to solved, or None if > MAX_EXACT_DISTANCE."""
    if is_solved(state):
        return 0
    table = _backward_table()
    if state in table:
        return table[state]
    # Forward layers from the query state; meet the backward table.
    seen = {state}
    frontier = [state]
    for f in range(1, FORWARD_DEPTH + 1):
        best = None
        nxt = []
        for s in frontier:
            for _, t in _neighbours(s):
                if t in seen:
                    continue
                seen.add(t)
                nxt.append(t)
                d = table.get(t)
                if d is not None and (best is None or d < best):
                    best = d
        if best is not None:
            # States in layer f that hit the table: total = f + best. Because
            # the table covers all states within BACKWARD_DEPTH and the query
            # is not in it (distance > BACKWARD_DEPTH), the first meeting layer
            # with its minimum gives the exact distance.
            return f + best
        frontier = nxt
    return None


def optimal_moves(state: str) -> list[str]:
    """Every move that reduces the exact distance by one (ties included).
    Empty if the state is solved or its distance is unknown."""
    d = distance(state)
    if not d:
        return []
    out = []
    for m, t in _neighbours(state):
        if distance(t) == d - 1:
            out.append(m)
    return out


def shortest_solution(state: str) -> list[str] | None:
    """One shortest move sequence, or None if beyond MAX_EXACT_DISTANCE."""
    d = distance(state)
    if d is None:
        return None
    path = []
    while d:
        m = optimal_moves(state)[0]
        state = "".join(_GETTERS[m](state))
        path.append(m)
        d -= 1
    return path
