"""Shared HTTP handling and the result record every adapter returns."""

from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx

from ..rules import Rules

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
# Account-level failures: stop the whole run instead of charging the model.
ABORT_STATUS = {401: "invalid API key", 402: "out of credits / key credit limit reached",
                403: "key not allowed to use this model"}


class RunAborted(Exception):
    """Raised for account-level problems (bad key, no credits, budget hit)."""


@dataclass
class MoveResult:
    outcome: str                      # "ok" | "malformed" | "error"
    move: str | None = None           # validated legal move (only when outcome == "ok")
    raw_move: Any = None              # what the model actually returned, unmodified
    latency_ms: float | None = None   # duration of the final HTTP attempt
    wall_ms: float = 0.0              # all attempts + backoff, as experienced by the agent
    attempts: int = 0
    http_status: int | None = None
    error: str | None = None
    confidence: float | None = None
    probabilities: dict | None = None
    finish_reason: str | None = None
    raw_content: str | None = None
    reasoning: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    cost_usd: float | None = None
    served_model: str | None = None
    provider: str | None = None
    generation_id: str | None = None
    attempt_log: list = field(default_factory=list)

    @property
    def retries(self) -> int:
        return max(0, self.attempts - 1)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["retries"] = self.retries
        return d


async def post_with_policy(client: httpx.AsyncClient, url: str, body: dict,
                           rules: Rules) -> tuple[httpx.Response | None, MoveResult]:
    """POST under the shared timeout/retry policy.

    Returns (response, partial result). response is None if every attempt
    failed at the transport level. Raises RunAborted on 401/402/403.
    """
    res = MoveResult(outcome="error")
    started = time.perf_counter()
    response = None
    for attempt in range(rules.max_retries + 1):
        res.attempts = attempt + 1
        t0 = time.perf_counter()
        try:
            response = await client.post(url, json=body, timeout=rules.timeout_seconds)
            res.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
            res.http_status = response.status_code
            res.attempt_log.append({"status": response.status_code, "ms": res.latency_ms})
        except httpx.TimeoutException:
            res.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
            res.http_status = None
            res.error = f"timeout after {rules.timeout_seconds}s"
            res.attempt_log.append({"status": "timeout", "ms": res.latency_ms})
            response = None
        except httpx.HTTPError as exc:
            res.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
            res.http_status = None
            res.error = f"network error: {type(exc).__name__}"
            res.attempt_log.append({"status": "network", "ms": res.latency_ms})
            response = None

        if response is not None:
            if response.status_code in ABORT_STATUS:
                raise RunAborted(f"HTTP {response.status_code}: "
                                 f"{ABORT_STATUS[response.status_code]} - {response.text[:200]}")
            if response.status_code == 200:
                break
            res.error = f"HTTP {response.status_code}: {response.text[:300]}"
            if response.status_code not in RETRYABLE_STATUS:
                break
        if attempt < rules.max_retries:
            await asyncio.sleep(rules.retry_backoff_seconds)
    res.wall_ms = round((time.perf_counter() - started) * 1000, 1)
    if response is not None and response.status_code != 200:
        return None, res
    return response, res
