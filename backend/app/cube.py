"""Deterministic 3x3 Rubik's Cube engine (facelet model).

State: a 54-character string, faces in order U R F D L B, 9 stickers per face,
row by row. Each letter names the face whose centre colour the sticker matches
(the standard Kociemba facelet convention), so the solved state is
"UUUUUUUUURRRRRRRRRFFFFFFFFFDDDDDDDDDLLLLLLLLLBBBBBBBBB".

Face layouts (as seen looking straight at the face):
  U: back row first, left->right (F is at the bottom of the grid)
  R, F, L, B: top row first, left->right as seen from that side
  D: front row first, left->right (F is at the top of the grid)

Moves are built from 3D geometry rather than hand-typed tables: each sticker
gets a cubie position and an outward normal, and a face turn rotates every
sticker in that layer by 90 degrees clockwise as seen looking at the face.
Moves use the half-turn metric (X, X', X2 each count as one move).
"""

from __future__ import annotations

from functools import lru_cache

FACES = "URFDLB"
SOLVED = "".join(f * 9 for f in FACES)
MOVES = [f + s for f in FACES for s in ("", "'", "2")]

FACE_NAMES = {"U": "upper", "R": "right", "F": "front",
              "D": "down", "L": "left", "B": "back"}

# Outward normal of each face: x = right, y = up, z = front.
NORMALS = {
    "U": (0, 1, 0), "D": (0, -1, 0),
    "R": (1, 0, 0), "L": (-1, 0, 0),
    "F": (0, 0, 1), "B": (0, 0, -1),
}


def _sticker_position(face: str, row: int, col: int) -> tuple[int, int, int]:
    """Cubie coordinate of the sticker at (row, col) of a face."""
    if face == "U":
        return (col - 1, 1, row - 1)
    if face == "D":
        return (col - 1, -1, 1 - row)
    if face == "F":
        return (col - 1, 1 - row, 1)
    if face == "B":
        return (1 - col, 1 - row, -1)
    if face == "R":
        return (1, 1 - row, 1 - col)
    if face == "L":
        return (-1, 1 - row, col - 1)
    raise ValueError(face)


# Sticker key = (cubie position, outward normal) -> facelet index 0..53
_STICKERS: list[tuple[tuple[int, int, int], tuple[int, int, int]]] = []
for _f in FACES:
    for _r in range(3):
        for _c in range(3):
            _STICKERS.append((_sticker_position(_f, _r, _c), NORMALS[_f]))
_INDEX = {key: i for i, key in enumerate(_STICKERS)}
assert len(_INDEX) == 54


def _rotate_cw(v, n):
    """Rotate vector v by 90 degrees clockwise when looking along -n at the face
    (i.e. -90 degrees about the outward normal n, right-hand rule)."""
    cross = (n[1] * v[2] - n[2] * v[1],
             n[2] * v[0] - n[0] * v[2],
             n[0] * v[1] - n[1] * v[0])
    dot = n[0] * v[0] + n[1] * v[1] + n[2] * v[2]
    return (-cross[0] + n[0] * dot, -cross[1] + n[1] * dot, -cross[2] + n[2] * dot)


def _quarter_turn_perm(face: str) -> tuple[int, ...]:
    """perm[i] = index of the sticker that moves INTO position i."""
    n = NORMALS[face]
    perm = list(range(54))
    for src, (pos, normal) in enumerate(_STICKERS):
        if sum(p * q for p, q in zip(pos, n)) != 1:   # not in this face's layer
            continue
        dst = _INDEX[(_rotate_cw(pos, n), _rotate_cw(normal, n))]
        perm[dst] = src
    return tuple(perm)


def _compose(p: tuple[int, ...], q: tuple[int, ...]) -> tuple[int, ...]:
    """Permutation for 'apply p, then q'."""
    return tuple(p[q[i]] for i in range(54))


def _build_move_perms() -> dict[str, tuple[int, ...]]:
    perms = {}
    for f in FACES:
        q = _quarter_turn_perm(f)
        q2 = _compose(q, q)
        q3 = _compose(q2, q)
        perms[f] = q
        perms[f + "2"] = q2
        perms[f + "'"] = q3
    return perms


MOVE_PERMS = _build_move_perms()


def apply_move(state: str, move: str) -> str:
    perm = MOVE_PERMS[move]          # KeyError for an illegal move, by design
    return "".join(state[i] for i in perm)


def apply_moves(state: str, moves) -> str:
    if isinstance(moves, str):
        moves = moves.split()
    for m in moves:
        state = apply_move(state, m)
    return state


def is_solved(state: str) -> bool:
    return all(len(set(state[i:i + 9])) == 1 for i in range(0, 54, 9))


def inverse_move(move: str) -> str:
    if move.endswith("2"):
        return move
    if move.endswith("'"):
        return move[0]
    return move + "'"


def invert_sequence(moves: list[str]) -> list[str]:
    return [inverse_move(m) for m in reversed(moves)]


def is_valid_state_string(state: str) -> bool:
    return (isinstance(state, str) and len(state) == 54
            and all(state.count(f) == 9 for f in FACES)
            and all(state[i * 9 + 4] == f for i, f in enumerate(FACES)))


def face_grids(state: str) -> dict[str, list[str]]:
    """Labeled 3x3 grid per face, e.g. {"U": ["UUF", "UUF", "UUF"], ...}."""
    return {f: [state[i * 9 + r * 3: i * 9 + r * 3 + 3] for r in range(3)]
            for i, f in enumerate(FACES)}


@lru_cache(maxsize=None)
def move_description(move: str) -> str:
    face = FACE_NAMES[move[0]]
    if move.endswith("2"):
        return f"Turn the {face} face by 180 degrees"
    if move.endswith("'"):
        return f"Turn the {face} face counterclockwise by 90 degrees"
    return f"Turn the {face} face clockwise by 90 degrees"
