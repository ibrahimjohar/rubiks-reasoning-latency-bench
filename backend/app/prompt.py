"""The single state/action contract shared by all four models.

Fairness: every model receives the SAME state object (same fields, same
wording, same move history policy) and the SAME instruction sentence and move
definitions. Only the transport differs: the Decisions API takes the object as
`state` and the moves as `criteria`; the chat API receives the identical object
as JSON text plus the identical move list, and must answer {"move": "..."}.
"""

from __future__ import annotations

import json

from .cube import MOVES, face_grids, move_description

INSTRUCTIONS = ("Choose the single next move most likely to progress toward "
                "the solved cube.")

STATE_FORMAT_NOTE = (
    "cube_facelets lists 54 stickers in face order U (up), R (right), F (front), "
    "D (down), L (left), B (back), 9 per face, read row by row. Each letter names "
    "the face whose centre colour that sticker matches. faces shows the same data "
    "as a 3x3 grid per face: U is seen from above with F at the bottom, D from "
    "below with F at the top, and R, F, L, B are each seen from their own side "
    "with U at the top. The cube is solved when every face shows only its own letter."
)

MOVE_CRITERIA = {m: move_description(m) for m in MOVES}


def build_state(facelets: str, moves_played: list[str], moves_remaining: int) -> dict:
    """moves_played: every legal move this model has applied so far (full history).
    moves_remaining: turns left before the move limit (invalid turns also count)."""
    return {
        "cube_facelets": facelets,
        "faces": face_grids(facelets),
        "format": STATE_FORMAT_NOTE,
        "recent_moves": list(moves_played),
        "moves_remaining": moves_remaining,
    }


def decisions_body(model_id: str, state: dict) -> dict:
    return {
        "model": model_id,
        "state": state,
        "questions": {
            "next_move": {
                "type": "choice",
                "instructions": INSTRUCTIONS,
                "criteria": MOVE_CRITERIA,
            }
        },
    }


CHAT_SYSTEM = (
    "You are an agent playing a Rubik's Cube game. Each turn you receive the "
    "current state and choose exactly one action. Respond with only a JSON "
    'object of the form {"move": "<MOVE>"} where <MOVE> is one of the allowed '
    "moves. No other text."
)


def chat_user_message(state: dict) -> str:
    moves = "\n".join(f"{m}: {d}" for m, d in MOVE_CRITERIA.items())
    return (f"State:\n{json.dumps(state, indent=2)}\n\n"
            f"Question: {INSTRUCTIONS}\n\nAllowed moves:\n{moves}")


MOVE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "cube_move",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"move": {"type": "string", "enum": MOVES}},
            "required": ["move"],
            "additionalProperties": False,
        },
    },
}


def chat_body(model_id: str, state: dict, *, reasoning_effort: str,
              max_tokens: int, structured: bool) -> dict:
    body = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": CHAT_SYSTEM},
            {"role": "user", "content": chat_user_message(state)},
        ],
        "max_tokens": max_tokens,
        "reasoning": {"effort": reasoning_effort},
        "usage": {"include": True},
    }
    if structured:
        body["response_format"] = MOVE_SCHEMA
        # Only route to providers that honour the schema; never silently drop it.
        body["provider"] = {"require_parameters": True}
    return body
