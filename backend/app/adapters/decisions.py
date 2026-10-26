"""Adapter for the three System-1 decision models (OpenRouter Decisions API)."""

from __future__ import annotations

import httpx

from ..cube import MOVES
from ..prompt import decisions_body
from ..rules import Rules
from .base import MoveResult, post_with_policy

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"


async def decide(client: httpx.AsyncClient, model_id: str, state: dict,
                 rules: Rules) -> MoveResult:
    response, res = await post_with_policy(client, DECISIONS_URL,
                                           decisions_body(model_id, state), rules)
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
    res.input_tokens = usage.get("input_tokens")
    res.output_tokens = usage.get("output_tokens")
    res.cost_usd = usage.get("cost")
    res.served_model = data.get("model")
    res.provider = data.get("provider")
    res.generation_id = data.get("id")

    answer = (data.get("answers") or {}).get("next_move")
    if not isinstance(answer, dict):
        res.outcome = "malformed"
        res.error = "no next_move answer in response"
        res.raw_content = str(data)[:500]
        return res
    res.raw_move = answer.get("choice")
    res.confidence = answer.get("confidence")
    res.probabilities = answer.get("probabilities")
    if res.raw_move in MOVES:
        res.outcome, res.move, res.error = "ok", res.raw_move, None
    else:
        res.outcome = "malformed"
        res.error = f"choice {res.raw_move!r} is not one of the 18 legal moves"
    return res
