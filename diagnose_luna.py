"""
Diagnose why GPT-6 Luna Decisions refuses the current request (HTTP 502
"OpenAI refused to answer question").

Sends 6 single requests (round 2: splits the new state into its parts) to Luna ONLY (no retries, a few cents at most), each
changing ONE thing relative to the first smoke-test request that Luna answered.
Uses the smoke-test cube (solved + R), never a benchmark puzzle.

    python diagnose_luna.py
"""

import json
import time

import httpx

from backend.app.cube import MOVES, move_description
from backend.app.prompt import INSTRUCTIONS as NEW_INSTR, MOVE_CRITERIA as NEW_CRIT, build_state
from backend.app.rules import api_key

URL = "https://openrouter.ai/api/alpha/decisions"
MODEL = "openai/gpt-6-luna-decisions"
FACELETS = "UUFUUFUUFRRRRRRRRRFFDFFDFFDDDBDDBDDBLLLLLLLLLUBBUBBUBB"

OLD_STATE = (
    "Rubik's Cube state as 54 facelets in face order U, R, F, D, L, B "
    "(9 stickers per face, read row by row). Each letter names the face whose "
    "centre colour that sticker matches. A solved cube has every face uniform.\n"
    f"State: {FACELETS}\nMoves played so far: none"
)
OLD_INSTR = "Choose the single next move that brings this Rubik's Cube closest to solved."
FN = {"U": "Up", "R": "Right", "F": "Front", "D": "Down", "L": "Left", "B": "Back"}


def old_desc(m):
    f = FN[m[0]]
    if m.endswith("2"):
        return f"Turn the {f} face 180 degrees"
    if m.endswith("'"):
        return f"Turn the {f} face 90 degrees counter-clockwise"
    return f"Turn the {f} face 90 degrees clockwise"


OLD_CRIT = {m: old_desc(m) for m in MOVES}
NEW_STATE = build_state(FACELETS, [], 30)

# Round 3: the exact state the benchmark now sends, 6 times, to check Luna answers reliably.
FINAL = build_state(FACELETS, [], 30)
VARIANTS = {f"F{i} final state, repeat {i}": (FINAL, NEW_INSTR, NEW_CRIT) for i in range(1, 7)}

key = api_key()
if not key:
    raise SystemExit("OPENROUTER_API_KEY is missing from .env")

with httpx.Client(timeout=60, headers={"Authorization": f"Bearer {key}"}) as c:
    for name, (state, instr, crit) in VARIANTS.items():
        body = {"model": MODEL, "state": state,
                "questions": {"next_move": {"type": "choice", "instructions": instr,
                                            "criteria": crit}}}
        t0 = time.perf_counter()
        r = c.post(URL, json=body)
        ms = (time.perf_counter() - t0) * 1000
        if r.status_code == 200:
            ans = r.json()["answers"]["next_move"]
            print(f"{name:48} OK   {ans['choice']:3} conf={ans.get('confidence')}  {ms:.0f} ms")
        else:
            print(f"{name:48} FAIL HTTP {r.status_code}  {r.text[:90]}")
