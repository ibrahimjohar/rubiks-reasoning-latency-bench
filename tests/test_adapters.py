"""Adapter tests against a local fake transport. No network, no cost."""

import asyncio
import json
from dataclasses import replace

import httpx
import pytest

from backend.app.adapters import chat, decisions
from backend.app.adapters.base import RunAborted
from backend.app.cube import MOVES, SOLVED, apply_move
from backend.app.prompt import build_state, chat_body, decisions_body
from backend.app.rules import Rules

RULES = replace(Rules(), retry_backoff_seconds=0.0, timeout_seconds=1.0)
STATE = build_state(apply_move(SOLVED, "R"), [], 30)


def client_for(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def run(coro):
    return asyncio.run(coro)


def decision_reply(choice, status=200):
    body = {"model": "typesafe/jev-1.13-20260917", "provider": "TypeSafe", "id": "gen-1",
            "answers": {"next_move": {"type": "choice", "choice": choice, "confidence": 0.4,
                                      "probabilities": {m: 1 / 18 for m in MOVES}}},
            "usage": {"input_tokens": 700, "output_tokens": 0, "cost": 0.00003}}
    return lambda request: httpx.Response(status, json=body)


def chat_reply(content, finish="stop"):
    body = {"id": "gen-2", "model": "anthropic/claude-opus-5.5", "provider": "Anthropic",
            "choices": [{"finish_reason": finish,
                         "message": {"content": content, "reasoning": "thinking"}}],
            "usage": {"prompt_tokens": 300, "completion_tokens": 90, "cost": 0.003,
                      "completion_tokens_details": {"reasoning_tokens": 80}}}
    return lambda request: httpx.Response(200, json=body)


async def _decide(adapter, handler, rules=RULES):
    async with client_for(handler) as c:
        return await adapter.decide(c, "model/x", STATE, rules)


# ---------------------------------------------------------------- fairness
def test_same_state_and_question_for_every_model():
    a = decisions_body("typesafe/jev-1.13", STATE)
    b = decisions_body("cloudflare/clef", STATE)
    assert a["state"] == b["state"] and a["questions"] == b["questions"]
    assert list(a["questions"]["next_move"]["criteria"]) == MOVES
    body = chat_body("anthropic/claude-opus-5.5", STATE, reasoning_effort="low",
                     max_tokens=1024, structured=True)
    user = body["messages"][1]["content"]
    assert json.dumps(STATE, indent=2) in user
    assert a["questions"]["next_move"]["instructions"] in user
    assert body["response_format"]["json_schema"]["schema"]["properties"]["move"]["enum"] == MOVES


# ---------------------------------------------------------------- decisions
def test_decision_ok():
    res = run(_decide(decisions, decision_reply("R'")))
    assert res.outcome == "ok" and res.move == "R'"
    assert res.confidence == 0.4 and len(res.probabilities) == 18
    assert res.cost_usd == 0.00003 and res.attempts == 1


def test_decision_illegal_choice_is_malformed_not_repaired():
    res = run(_decide(decisions, decision_reply("M")))
    assert res.outcome == "malformed" and res.move is None and res.raw_move == "M"


# ---------------------------------------------------------------- chat
def test_chat_ok():
    res = run(_decide(chat, chat_reply('{"move": "R\'"}')))
    assert res.outcome == "ok" and res.move == "R'"
    assert res.reasoning_tokens == 80 and res.cost_usd == 0.003


@pytest.mark.parametrize("content", [
    '```json\n{"move": "R\'"}\n```',          # code fence
    'I think R\' is best. {"move": "R\'"}',   # prose
    '{"move": "R\'", "why": "x"}',            # extra keys
    '{"move": "M"}',                          # illegal move
    '{"move": "r\'"}',                        # wrong case
    "",                                       # empty
])
def test_chat_malformed_is_logged_not_repaired(content):
    res = run(_decide(chat, chat_reply(content)))
    assert res.outcome == "malformed" and res.move is None
    assert res.raw_content == content[:500]


def test_chat_truncated_reply_flagged():
    res = run(_decide(chat, chat_reply('{"mo', finish="length")))
    assert res.outcome == "malformed" and "max_tokens" in res.error


# ---------------------------------------------------------------- policy
def test_retry_on_503_then_success():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, text="busy")
        return decision_reply("U")(request)

    res = run(_decide(decisions, handler))
    assert res.outcome == "ok" and res.attempts == 2 and res.retries == 1


def test_no_retry_on_400():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(400, text="bad request")

    res = run(_decide(decisions, handler))
    assert res.outcome == "error" and calls["n"] == 1


def test_retries_exhausted_is_error():
    res = run(_decide(decisions, lambda r: httpx.Response(502, text="bad gateway")))
    assert res.outcome == "error" and res.attempts == RULES.max_retries + 1


def test_timeout_is_error():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    res = run(_decide(chat, handler))
    assert res.outcome == "error" and "timeout" in res.error


@pytest.mark.parametrize("status", [401, 402, 403])
def test_account_errors_abort_the_run(status):
    with pytest.raises(RunAborted):
        run(_decide(chat, lambda r: httpx.Response(status, text="no")))
