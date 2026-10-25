"""
Smoke test: send ONE request to each of the four benchmark models.

Checks that the API key works, that every model ID is live, and records
latency, tokens and real cost per call before the full benchmark is built.

Cube used: solved cube + the single move R. The optimal reply is R'.

Usage:
    pip install httpx python-dotenv
    python smoke_test.py                 # all four models (4 requests)
    python smoke_test.py --models opus   # just one model
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY", "")
TIMEOUT = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"

MODELS = {
    "jev":   {"id": "typesafe/jev-1.13",            "api": "decisions"},
    "luna":  {"id": "openai/gpt-6-luna-decisions",  "api": "decisions"},
    "clef":  {"id": "cloudflare/clef",              "api": "decisions"},
    "opus":  {"id": "anthropic/claude-opus-5.5",    "api": "chat"},
}

# Opus settings under test: low reasoning effort, 1024-token ceiling.
OPUS_REASONING_EFFORT = "low"
OPUS_MAX_TOKENS = 1024

# Facelet order U R F D L B (9 each). Solved cube with R applied.
STATE = (
    "UUFUUFUUF"   # U
    "RRRRRRRRR"   # R
    "FFDFFDFFD"   # F
    "DDBDDBDDB"   # D
    "LLLLLLLLL"   # L
    "UBBUBBUBB"   # B
)
OPTIMAL_MOVE = "R'"

MOVES = [f + s for f in "URFDLB" for s in ("", "'", "2")]

FACE_NAMES = {"U": "Up", "R": "Right", "F": "Front", "D": "Down", "L": "Left", "B": "Back"}


def move_description(move: str) -> str:
    face = FACE_NAMES[move[0]]
    if move.endswith("2"):
        return f"Turn the {face} face 180 degrees"
    if move.endswith("'"):
        return f"Turn the {face} face 90 degrees counter-clockwise"
    return f"Turn the {face} face 90 degrees clockwise"


STATE_TEXT = (
    "Rubik's Cube state as 54 facelets in face order U, R, F, D, L, B "
    "(9 stickers per face, read row by row). Each letter names the face whose "
    "centre colour that sticker matches. A solved cube has every face uniform.\n"
    f"State: {STATE}\n"
    "Moves played so far: none"
)

INSTRUCTIONS = (
    "Choose the single next move that brings this Rubik's Cube closest to solved."
)


def call_decisions(client: httpx.Client, model_id: str) -> dict:
    body = {
        "model": model_id,
        "state": STATE_TEXT,
        "questions": {
            "next_move": {
                "type": "choice",
                "instructions": INSTRUCTIONS,
                "criteria": {m: move_description(m) for m in MOVES},
            }
        },
    }
    t0 = time.perf_counter()
    r = client.post(DECISIONS_URL, json=body)
    latency_ms = (time.perf_counter() - t0) * 1000
    result = {"http_status": r.status_code, "latency_ms": round(latency_ms, 1)}
    try:
        data = r.json()
    except ValueError:
        result["error"] = r.text[:300]
        return result
    result["raw"] = data
    if r.status_code != 200:
        result["error"] = json.dumps(data)[:300]
        return result
    answer = (data.get("answers") or {}).get("next_move") or {}
    usage = data.get("usage") or {}
    result.update(
        move=answer.get("choice"),
        confidence=answer.get("confidence"),
        served_model=data.get("model"),
        provider=data.get("provider"),
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        cost_usd=usage.get("cost"),
    )
    return result


def call_chat(client: httpx.Client, model_id: str) -> dict:
    system = (
        "You are playing a Rubik's Cube benchmark. Each turn you choose exactly one move. "
        f"Allowed moves: {' '.join(MOVES)}. "
        'Reply with only JSON in the form {"move": "<MOVE>"} and nothing else.'
    )
    body = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": STATE_TEXT + "\n" + INSTRUCTIONS},
        ],
        "max_tokens": OPUS_MAX_TOKENS,
        "reasoning": {"effort": OPUS_REASONING_EFFORT},
        "usage": {"include": True},
    }
    t0 = time.perf_counter()
    r = client.post(CHAT_URL, json=body)
    latency_ms = (time.perf_counter() - t0) * 1000
    result = {"http_status": r.status_code, "latency_ms": round(latency_ms, 1)}
    try:
        data = r.json()
    except ValueError:
        result["error"] = r.text[:300]
        return result
    result["raw"] = data
    if r.status_code != 200:
        result["error"] = json.dumps(data)[:300]
        return result
    choice = (data.get("choices") or [{}])[0]
    content = ((choice.get("message") or {}).get("content") or "").strip()
    usage = data.get("usage") or {}
    move = None
    try:
        start, end = content.index("{"), content.rindex("}") + 1
        move = json.loads(content[start:end]).get("move")
    except (ValueError, AttributeError):
        pass
    details = usage.get("completion_tokens_details") or {}
    result.update(
        move=move,
        raw_content=content[:200],
        finish_reason=choice.get("finish_reason"),
        served_model=data.get("model"),
        provider=data.get("provider"),
        input_tokens=usage.get("prompt_tokens"),
        output_tokens=usage.get("completion_tokens"),
        reasoning_tokens=details.get("reasoning_tokens"),
        cost_usd=usage.get("cost"),
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", default="jev,luna,clef,opus",
                        help="comma-separated subset of: jev,luna,clef,opus")
    args = parser.parse_args()
    keys = [k.strip() for k in args.models.split(",") if k.strip()]
    unknown = [k for k in keys if k not in MODELS]
    if unknown:
        sys.exit(f"Unknown model key(s): {unknown}. Use: {', '.join(MODELS)}")
    if not API_KEY or API_KEY.startswith("your_"):
        sys.exit("OPENROUTER_API_KEY is missing. Copy .env.example to .env and add your key.")

    print(f"Sending {len(keys)} request(s). Cube = solved + R, optimal reply = {OPTIMAL_MOVE}\n")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "X-Title": "rubiks-reasoning-latency-bench",
    }
    results = {}
    with httpx.Client(headers=headers, timeout=TIMEOUT) as client:
        for key in keys:
            spec = MODELS[key]
            print(f"-> {key:5} {spec['id']} ...", end=" ", flush=True)
            try:
                fn = call_decisions if spec["api"] == "decisions" else call_chat
                res = fn(client, spec["id"])
            except httpx.TimeoutException:
                res = {"error": f"timeout after {TIMEOUT}s"}
            except httpx.HTTPError as exc:
                res = {"error": f"network error: {exc}"}
            res["model_id"] = spec["id"]
            res["api"] = spec["api"]
            res["valid_move"] = res.get("move") in MOVES
            res["optimal"] = res.get("move") == OPTIMAL_MOVE
            results[key] = res
            if res.get("http_status") == 402:
                print("402: out of credits. Stopping; no further requests sent.")
                break
            if "error" in res:
                print(f"ERROR {res.get('http_status', '')}: {res['error'][:150]}")
            else:
                print(f"OK  move={res.get('move')}  {res['latency_ms']} ms  "
                      f"cost=${res.get('cost_usd')}")

    print("\nSummary")
    print(f"{'model':6} {'status':7} {'move':5} {'optimal':8} {'latency':>10} "
          f"{'in_tok':>7} {'out_tok':>8} {'cost_usd':>12}")
    total = 0.0
    for key, r in results.items():
        cost = r.get("cost_usd")
        total += cost or 0
        print(f"{key:6} {str(r.get('http_status', 'ERR')):7} {str(r.get('move')):5} "
              f"{str(r['optimal']):8} {str(r.get('latency_ms', '-')):>10} "
              f"{str(r.get('input_tokens', '-')):>7} {str(r.get('output_tokens', '-')):>8} "
              f"{str(cost):>12}")
    print(f"\nTotal reported cost: ${total:.6f}")
    if "opus" in results and results["opus"].get("cost_usd"):
        c = results["opus"]["cost_usd"]
        print(f"Opus per move: ${c:.5f} -> worst case 150 Opus moves ~ ${c * 150:.2f}")
        if results["opus"].get("finish_reason") == "length":
            print("WARNING: Opus hit max_tokens (finish_reason=length); raise OPUS_MAX_TOKENS.")

    out_dir = Path("results")
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = out_dir / f"smoke_test_{stamp}.json"
    out.write_text(json.dumps({
        "timestamp_utc": stamp,
        "state": STATE,
        "optimal_move": OPTIMAL_MOVE,
        "opus_settings": {"reasoning_effort": OPUS_REASONING_EFFORT,
                          "max_tokens": OPUS_MAX_TOKENS},
        "results": results,
    }, indent=2))
    print(f"Full responses saved to {out}")


if __name__ == "__main__":
    main()
