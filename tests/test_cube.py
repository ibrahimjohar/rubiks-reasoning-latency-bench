import random

import pytest

from backend.app.cube import (MOVES, SOLVED, apply_move, apply_moves, face_grids,
                              inverse_move, invert_sequence, is_solved,
                              is_valid_state_string)


def test_solved_state():
    assert is_solved(SOLVED)
    assert is_valid_state_string(SOLVED)


def test_r_move_matches_hand_derived_state():
    # Solved cube + R, derived by hand and used in the live smoke test.
    assert apply_move(SOLVED, "R") == (
        "UUFUUFUUF" "RRRRRRRRR" "FFDFFDFFD" "DDBDDBDDB" "LLLLLLLLL" "UBBUBBUBB")


def test_u_and_f_moves():
    assert apply_move(SOLVED, "U") == (
        "UUUUUUUUU" "BBBRRRRRR" "RRRFFFFFF" "DDDDDDDDD" "FFFLLLLLL" "LLLBBBBBB")
    assert apply_move(SOLVED, "F") == (
        "UUUUUULLL" "URRURRURR" "FFFFFFFFF" "RRRDDDDDD" "LLDLLDLLD" "BBBBBBBBB")


@pytest.mark.parametrize("move", MOVES)
def test_move_then_inverse_is_identity(move):
    assert apply_moves(SOLVED, [move, inverse_move(move)]) == SOLVED


@pytest.mark.parametrize("face", "URFDLB")
def test_four_quarter_turns_is_identity(face):
    assert apply_moves(SOLVED, [face] * 4) == SOLVED
    assert apply_moves(SOLVED, [face + "2"] * 2) == SOLVED
    assert apply_moves(SOLVED, [face, face]) == apply_move(SOLVED, face + "2")


def test_sexy_move_has_order_six():
    s = SOLVED
    for i in range(1, 7):
        s = apply_moves(s, "R U R' U'")
        assert (s == SOLVED) == (i == 6)


def test_ru_has_order_105():
    s, n = SOLVED, 0
    while True:
        s = apply_moves(s, "R U")
        n += 1
        if s == SOLVED:
            break
    assert n == 105


def test_random_sequence_and_inverse_round_trip():
    rng = random.Random(0)
    for _ in range(200):
        seq = [rng.choice(MOVES) for _ in range(rng.randint(1, 30))]
        scrambled = apply_moves(SOLVED, seq)
        assert is_valid_state_string(scrambled)
        assert apply_moves(scrambled, invert_sequence(seq)) == SOLVED


def test_face_grids():
    g = face_grids(apply_move(SOLVED, "R"))
    assert g["U"] == ["UUF", "UUF", "UUF"]
    assert g["B"] == ["UBB", "UBB", "UBB"]


def test_illegal_move_rejected():
    with pytest.raises(KeyError):
        apply_move(SOLVED, "M")


def test_matches_magiccube_library():
    """Independent check against an established cube library (optional dependency)."""
    magiccube = pytest.importorskip("magiccube")
    colour = {"U": "W", "L": "O", "F": "G", "R": "R", "B": "B", "D": "Y"}

    def to_mc(state):
        faces = {f: state[i * 9:(i + 1) * 9] for i, f in enumerate("URFDLB")}
        return "".join(colour[c] for f in "ULFRBD" for c in faces[f])

    rng = random.Random(7)
    for _ in range(300):
        seq = [rng.choice(MOVES) for _ in range(rng.randint(1, 30))]
        ref = magiccube.Cube(3, "W" * 9 + "O" * 9 + "G" * 9 + "R" * 9 + "B" * 9 + "Y" * 9)
        ref.rotate(" ".join(seq))
        assert ref.get() == to_mc(apply_moves(SOLVED, seq))
