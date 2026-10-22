# Rubik's Cube Race — Fast Decision Models vs. a Frontier LLM

**AI Engineering — Assignment 02**
**Ibrahim Johar Farooqi — 23K-0074 — BAI-7A, FAST-NUCES Karachi**

> Can models that decide in milliseconds beat a frontier LLM that plans longer, if the slower model solves the cube in fewer moves?

This project benchmarks four models from OpenRouter on a shared, deterministic Rubik's Cube environment. Every model starts from the same scramble, picks one move per turn, and either solves the cube or hits the 30-move limit.

## 🎥 Demo recording

_Coming soon. The screen recording will be embedded here, with a direct link._

## Models compared

| Model | Category | OpenRouter model ID | Interface |
|---|---|---|---|
| Jev 1.13 | System-1 decision model | `typesafe/jev-1.13` | Decisions API |
| GPT-6 Luna Decisions | System-1 decision model | `openai/gpt-6-luna-decisions` | Decisions API |
| Cloudflare Clef | System-1 decision model | `cloudflare/clef` | Decisions API |
| Claude Opus 5.5 | Frontier LLM | `anthropic/claude-opus-5.5` | Chat Completions |

## Results

_Coming soon. Per-model statistics:_

| Model | Avg latency / move | Total time | Total moves | Solve rate | Optimality gap |
|---|---|---|---|---|---|
| Jev 1.13 | – | – | – | – | – |
| GPT-6 Luna Decisions | – | – | – | – | – |
| Cloudflare Clef | – | – | – | – | – |
| Claude Opus 5.5 | – | – | – | – | – |

## Answers to the experiment questions

1. **Which model is fastest at making decisions?** _TBD_
2. **Which model achieved the highest solve rate?** _TBD_
3. **Which model found the shortest solutions, and how close to optimal?** _TBD_
4. **Did the fastest model also achieve the best solution quality?** _TBD_
5. **Fast decision model, frontier LLM, or hybrid for a real application?** _TBD_

## Experiment design

- **Move set:** 18 face turns (U, D, L, R, F, B and their `'` and `2` variants), half-turn metric
- **Move limit:** 30 moves per attempt. Reaching the limit counts as unsolved.
- **Test sets:** warm-up (3–4 move scrambles), primary (4–5), extension (15–20)
- **Optimal reference:** BFS shortest solution for primary puzzles
- **Optimality gap:** model moves − exact shortest moves

## Setup

```bash
git clone https://github.com/ibrahimjohar/rubiks-reasoning-latency-bench.git
cd rubiks-reasoning-latency-bench
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # then add your OpenRouter API key
```

## Repository structure

```
backend/     FastAPI server, cube engine, model adapters
frontend/    Race UI and benchmark dashboard
results/     Raw trial logs and computed statistics
media/       Screen recording and charts
```

## API key security

The OpenRouter key is read from a backend environment variable (`OPENROUTER_API_KEY`). It is never sent to the browser, and `.env` is excluded from git.
