"""The single state/action contract shared by all four models.

Fairness: every model receives the SAME state object (same fields, same
wording, same move history policy) and the SAME instruction sentence and move
definitions. Only the transport differs: the Decisions API takes the object as
`state` and the moves as `criteria`; the chat API receives the identical object
as JSON text plus the identical move list, and must answer {"move": "..."}.
"""

from __future__ import annotations

import json

from .cube import MOVES, move_description

INSTRUCTIONS = ("Choose the single next move most likely to progress toward "
                "the solved cube.")

STATE_FORMAT_NOTE = (
    "cube_facelets lists 54 stickers in face order U (up), R (right), F (front), "
    "D (down), L (left), B (back), 9 per face. Each face is read row by row, "
    "top-left to bottom-right, as seen looking straight at that face: on U the top "
    "row is the edge next to B and the left column is next to L; on D the top row "
    "is next to F and the left column is next to L; on R, F, L and B the top row is "
    "next to U. The centre sticker is the 5th of each face. Each letter names "
    "the face whose centre colour that sticker matches. The cube is solved when "
    "every face shows only its own letter. moves_you_have_played lists, in order, "
    "the moves you have already applied in this game, starting from the scrambled "
    "cube you were first given; cube_facelets already includes their effect. They "
    "are your own moves, not the scramble. moves_remaining is how many moves you "
    "have left before the move limit."
)

MOVE_CRITERIA = {m: move_description(m) for m in MOVES}


def build_state(facelets: str, moves_played: list[str], moves_remaining: int) -> dict:
    """moves_played: every legal move this model has applied so far (full history).
    moves_remaining: turns left before the move limit (invalid turns also count)."""
    return {
        "cube_facelets": facelets,
        "format": STATE_FORMAT_NOTE,
        "moves_you_have_played": list(moves_played),
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
