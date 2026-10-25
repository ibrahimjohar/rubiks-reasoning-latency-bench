"""Benchmark rules and guardrails: the single source of truth.

Every model plays under exactly these settings. Values come from .env so they
are visible and reproducible, and each run file records a snapshot of them.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


@dataclass(frozen=True)
class Rules:
    # Game rules (identical for every model)
    max_moves: int = 30                  # PDF: 30 moves; reaching it = unsolved
    metric: str = "HTM"                  # half-turn metric, 18 legal moves
    history_policy: str = "full"         # every move this model has played so far

    # Request policy (identical for every model)
    timeout_seconds: float = 60.0        # per HTTP attempt
    max_retries: int = 1                 # only on timeout / network / HTTP 429 / 5xx
    retry_backoff_seconds: float = 2.0

    # Frontier LLM settings (Opus only; decision models have no such knobs)
    opus_reasoning_effort: str = "low"
    opus_max_tokens: int = 1024          # reasoning + answer ceiling
    opus_structured_output: bool = True  # JSON schema with the 18 moves as enum

    # Cost guardrails
    run_budget_usd: float = 2.00         # run stops before any call once reported spend reaches this

    student_name: str = "Ibrahim Johar Farooqi"
    student_roll: str = "23K-0074"

    def snapshot(self) -> dict:
        return asdict(self)


def load_rules() -> Rules:
    return Rules(
        max_moves=_int("MAX_MOVES", 30),
        timeout_seconds=_float("REQUEST_TIMEOUT_SECONDS", 60.0),
        max_retries=_int("MAX_RETRIES", 1),
        retry_backoff_seconds=_float("RETRY_BACKOFF_SECONDS", 2.0),
        opus_reasoning_effort=os.getenv("OPUS_REASONING_EFFORT", "low"),
        opus_max_tokens=_int("OPUS_MAX_TOKENS", 1024),
        opus_structured_output=os.getenv("OPUS_STRUCTURED_OUTPUT", "true").strip().lower()
        in ("1", "true", "yes"),
        run_budget_usd=_float("RUN_BUDGET_USD", 2.00),
        student_name=os.getenv("STUDENT_NAME", "Ibrahim Johar Farooqi"),
        student_roll=os.getenv("STUDENT_ROLL", "23K-0074"),
    )


def api_key() -> str:
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    return "" if key.startswith("your_") else key


# Model registry. The three decision models share one adapter and one question;
# only the model ID differs.
MODELS = [
    {"key": "jev",  "name": "Jev 1.13",                    "id": "typesafe/jev-1.13",
     "category": "System-1 decision model", "api": "decisions"},
    {"key": "luna", "name": "GPT-6 Luna Decisions",        "id": "openai/gpt-6-luna-decisions",
     "category": "System-1 decision model", "api": "decisions"},
    {"key": "clef", "name": "Cloudflare Clef",             "id": "cloudflare/clef",
     "category": "System-1 decision model", "api": "decisions"},
    {"key": "opus", "name": "Claude Opus 5.5",             "id": "anthropic/claude-opus-5.5",
     "category": "Frontier LLM", "api": "chat"},
]
MODEL_BY_KEY = {m["key"]: m for m in MODELS}
