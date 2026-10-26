"""Adapter for the frontier LLM (OpenRouter chat completions).

The reply must be exactly a JSON object {"move": "<one of 18 moves>"} (surrounding
whitespace allowed). Anything else (prose, code fences, extra keys, an illegal
move, a reply cut off by max_tokens) is logged as malformed and never repaired.
"""

from __future__ import annotations

import json

import httpx

from ..cube import MOVES
from ..prompt import chat_body
from ..rules import Rules
from .base import MoveResult, post_with_policy

CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"


def parse_move(content: str) -> tuple[str | None, object, str | None]:
    """Strictly parse the reply. Returns (legal move or None, raw value, error)."""
    try:
        obj = json.loads(content.strip())
    except (ValueError, AttributeError):
        return None, None, "reply is not a bare JSON object"
    if not isinstance(obj, dict) or set(obj) != {"move"}:
        return None, obj, 'reply must be exactly {"move": "<MOVE>"}'
    raw = obj["move"]
    if raw not in MOVES:
        return None, raw, f"move {raw!r} is not one of the 18 legal moves"
    return raw, raw, None


async def decide(client: httpx.AsyncClient, model_id: str, state: dict,
                 rules: Rules) -> MoveResult:
    body = chat_body(model_id, state,
                     reasoning_effort=rules.opus_reasoning_effort,
                     max_tokens=rules.opus_max_tokens,
                     structured=rules.opus_structured_output)
    response, res = await post_with_policy(client, CHAT_URL, body, rules)
    if response is None:
        return res
    try:
        data = response.json()
    except ValueError:
        res.outcome = "malformed"
        res.error = "response was not JSON"
        res.raw_content = response.text[:500]
        return res

    usage = data.get("usage") or {}
    details = usage.get("completion_tokens_details") or {}
    res.input_tokens = usage.get("prompt_tokens")
    res.output_tokens = usage.get("completion_tokens")
    res.reasoning_tokens = details.get("reasoning_tokens")
    res.cost_usd = usage.get("cost")
    res.served_model = data.get("model")
    res.provider = data.get("provider")
    res.generation_id = data.get("id")

    if data.get("error"):
        res.outcome = "error"
        res.error = f"provider error: {str(data['error'])[:300]}"
        return res

    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = message.get("content") or ""
    res.finish_reason = choice.get("finish_reason")
    res.raw_content = content[:500]
    reasoning = message.get("reasoning")
    res.reasoning = reasoning[:2000] if isinstance(reasoning, str) else None

    move, raw, err = parse_move(content)
    res.raw_move = raw
    if res.finish_reason == "length" and move is None:
        err = f"cut off by max_tokens ({rules.opus_max_tokens}); {err}"
    if move is None:
        res.outcome, res.error = "malformed", err
    else:
        res.outcome, res.move, res.error = "ok", move, None
    return res
