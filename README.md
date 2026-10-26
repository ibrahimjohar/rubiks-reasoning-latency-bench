# Rubik's Cube Race: Fast Decision Models vs. a Frontier LLM

**AI Engineering, Assignment 02**
**Ibrahim Johar Farooqi · 23K-0074 · BAI-7A · FAST-NUCES Karachi**

> Is a model that decides in milliseconds more useful than a frontier LLM that spends longer planning, if the slower model solves the task in fewer moves?

Four models play the same scrambled 3×3 cubes through OpenRouter. On every turn each model gets the current state and picks **one** of the 18 face turns, until the cube is solved or it has used **30 moves**. Every request is logged: the move, its latency, tokens and the reported cost. Each puzzle has an exact BFS shortest solution, so the results show both speed and the quality of each model's decisions.

---

## 🎥 Demo recording

<!-- RECORDING: replace the two lines below after adding media/demo.mp4 -->
**▶ [Watch the screen recording](media/demo.mp4)** (direct link: `media/demo.mp4` in this repository)

_The recording shows the models racing, the completed race with final ranks, and the closing results slide. My name and roll number stay on screen throughout._

---

## Results

<!-- RESULTS: paste the output of `python report.py` (results/summary.md) here -->
_Results will be added after the live benchmark run. Raw per-request logs for every run are kept in [`results/runs/`](results/runs/)._

### Answers to the five questions

<!-- ANSWERS: written from the measured results -->
1. **Which model is fastest at making decisions?** _pending results_
2. **Which model achieved the highest solve rate?** _pending results_
3. **Which model found the shortest solutions, and how close to the known optimum?** _pending results_
4. **Did the fastest model also achieve the best solution quality?** _pending results_
5. **Fast decision model, frontier LLM, or a hybrid agent for a real application? What evidence?** _pending results_

---

## Models

| Model | Category | OpenRouter ID | Interface |
|---|---|---|---|
| Jev 1.13 | System-1 decision model | `typesafe/jev-1.13` | Decisions API (`/api/alpha/decisions`) |
| GPT-6 Luna Decisions | System-1 decision model | `openai/gpt-6-luna-decisions` | Decisions API |
| Cloudflare Clef | System-1 decision model | `cloudflare/clef` | Decisions API |
| Claude Opus 5.5 | Frontier LLM | `anthropic/claude-opus-5.5` | Chat Completions (`/api/v1/chat/completions`) |

All four model IDs were checked with a live call before the benchmark (`smoke_test.py`). There are no fallback models. A model that fails is recorded as failing, never swapped for another.

## How the AI plays (state → action)

As in the Snake example from class, the game is a state/action loop:

```
state (current cube + this model's move history) ──► model ──► one move
        ▲                                                         │
        └──────── engine applies the move, checks if solved ◄─────┘
```

**One state object, identical for all four models.** The decision models receive it as the Decisions API `state` field. Opus receives the same object as JSON text in its message:

```json
{
  "cube_facelets": "UUFUUFUUFRRRRRRRRRFFDFFDFFDDDBDDBDDBLLLLLLLLLUBBUBBUBB",
  "faces": { "U": ["UUF","UUF","UUF"], "R": ["RRR","RRR","RRR"], "...": "..." },
  "format": "cube_facelets lists 54 stickers in face order U, R, F, D, L, B ...",
  "recent_moves": [],
  "moves_remaining": 30
}
```

**One question, identical for all four models:** *"Choose the single next move most likely to progress toward the solved cube."* The 18 moves are defined the same way for every model ("Turn the right face clockwise by 90 degrees", and so on):
- The **decision models** get them as the options of a `choice` question. Their reply includes the chosen move plus a confidence and a probability for each option, and all of it is logged.
- **Opus** gets the same 18 moves listed in its message and must reply with exactly `{"move": "R'"}`. A JSON schema with the 18 moves as an `enum` is requested as a structured-output constraint.

## Experiment design

| Test set | Scramble | Puzzles | Purpose |
|---|---|---|---|
| Warm-up | 3–4 turns | 3 | Verify adapters, move validation and the engine |
| **Primary** | **4–5 turns** | **10** | Main comparison with exact shortest distances |
| Extension | 15–20 turns | 5 | Probe behaviour and failure rate on complex states |

- **Fixed puzzles.** Scrambles are generated from fixed seeds and committed in [`backend/data/puzzles.json`](backend/data/puzzles.json). Every model plays exactly these states, and a test checks that the file matches the generator.
- **True difficulty.** Warm-up and primary scrambles are kept only if their **exact BFS distance equals the scramble length**, so a "5-move" puzzle really needs 5 moves. No scramble has two consecutive turns of the same face, so moves like "R R'" can't cancel out.
- **Exact shortest solutions** use the half-turn metric (X, X', X2 each count as one move). A bidirectional breadth-first search builds a table of all 46,741 states within 4 moves of solved, then searches forward up to 3 moves from the puzzle. This gives the exact distance for any state up to 7 moves from solved, plus *every* optimal next move, so ties count. The solver is checked against an independent plain BFS over all 621,649 states within 5 moves.
- **Parallel race.** The four models play each puzzle at the same time. Each model is timed on its own clock, so running them together doesn't mix up their latencies.

### Rules (identical for every model)

| Rule | Value |
|---|---|
| Move limit | 30 turns per puzzle. Reaching the limit counts as **unsolved** |
| Legal moves | the 18 face turns `U U' U2 R R' R2 F F' F2 D D' D2 L L' L2 B B' B2` |
| Move history | full: every move this model has applied so far |
| Timeout | 60 s per request attempt |
| Retries | 1, only on timeout, network error or HTTP 408/429/5xx (never on a bad answer) |
| Malformed reply | logged and counted. The cube is unchanged and the turn is used up. Never repaired or reinterpreted |
| Failed request (after retry) | logged as an error. The cube is unchanged and the turn is used up |
| Opus settings | reasoning effort `low`, `max_tokens` 1024 (reasoning + answer), structured JSON output |

A note on fairness: the decision models answer through a fixed choice question, so they can never produce an illegal move. Only Opus can be penalised for malformed output. That is a real property of the two interfaces, so the malformed count is reported separately for each model.

### Metrics

| Metric | Definition |
|---|---|
| Avg latency / move | mean duration of the API request that produced each turn |
| Total solve time | wall time from a model's first request until it solves the cube or hits the limit (includes retries) |
| Total moves | turns used (every turn counts, including malformed and failed ones) |
| Success rate | solved puzzles ÷ completed puzzles |
| **Optimality gap** | moves used − exact shortest moves, **solved puzzles only**. Unsolved puzzles have no gap (N/A) and are never counted as 30 |
| Optimal-move rate | share of turns where the move was one of the exact optimal moves from that state |
| Random baseline | Monte Carlo solve rate of a player that picks uniformly random moves, on the same puzzles (no API calls). It shows what "guessing" would score |

## Cost and token guardrails

1. **Credit limit on the OpenRouter key.** This is the hard cap, and no bug in the code can get past it.
2. **Run budget (`RUN_BUDGET_USD`, default $2).** The runner adds up the cost OpenRouter reports for every request and stops before any new request once this limit is reached.
3. **Move cap.** At most 30 turns per model per puzzle, so every run has a known upper bound on calls. That bound is shown, and you must type `yes` (CLI) or confirm (UI) before any paid call.
4. **Opus token ceiling.** Opus runs at reasoning effort `low` with `max_tokens` 1024. A reply cut off by this limit is logged as malformed with the reason, not silently retried.
5. **Account errors stop the run.** A 401, 402 or 403 (bad key, no credits, model not allowed) aborts the whole run instead of being recorded as a model's mistake. A 400 is never retried.
6. **No mock data in results.** Tests use scripted offline players, but the application itself only runs live. Every saved run records its full rules snapshot and spend.

The pilot smoke test cost $0.003 for one call to each of the four models. Opus was about $0.003 per move.

## Pilot: state format

The first smoke test sent only the 54-character string. All three decision models returned nearly uniform probabilities over the 18 moves, with confidence 5–12%, and picked wrong moves. Opus picked the correct `R'`. **Before the benchmark** I added labeled 3×3 face grids and a short format description to the state. The reason was readability alone, not results on any benchmark puzzle. The final format is the same for all four models.

---

## Setup

Requires Python 3.10+.

```bash
git clone https://github.com/ibrahimjohar/rubiks-reasoning-latency-bench.git
cd rubiks-reasoning-latency-bench
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # macOS/Linux: cp .env.example .env
```

Put your OpenRouter key in `.env` (`OPENROUTER_API_KEY=...`). The key is only read by the backend. It never reaches the browser and `.env` is git-ignored.

### 1. Smoke test (one request per model, under one cent)

```bash
python smoke_test.py
```

### 2. Run the web app

```bash
uvicorn backend.app.main:app --port 8000
```

Open <http://localhost:8000>.
- **Race:** choose *New live run* → tier → **Run benchmark**. It shows the four models live: each model's cube, current move, move history, timer, latency and status (thinking / solved / move limit). *Replay saved run* re-plays any saved run at 1–16× speed.
- **Dashboard:** the five required statistics for each model, bar charts, per-puzzle results and the random baseline.
- **Results slide:** a 16:9 statistics slide for the end of the recording (has a Full screen button).

### 3. Or run from the terminal

```bash
python run_benchmark.py --tier warmup
python run_benchmark.py --tier primary
python run_benchmark.py --tier extension
python report.py          # writes results/summary.md (tables for this README)
```

### Tests (offline, no API calls)

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The 73 tests cover:
- **Engine:** move identities, (R U) has order 105, and 300 random sequences checked against the `magiccube` library.
- **Solver:** layer sizes match the known values, and distances agree with an independent plain BFS.
- **Scrambles:** the suite is deterministic and each scramble's true distance is verified.
- **Adapters:** strict parsing and malformed cases, and the retry, timeout and abort policy.
- **Runner:** the move cap, malformed counting, abort and budget guardrails, and that every model gets the same first state.
- **API:** an end-to-end run, and a check that the key is never exposed.

## Recording checklist

1. Start the app, open **Race**, choose *Replay saved run* (or *New live run*) and press Play. This is the **in-progress** stage.
2. Let the race finish. Status chips show SOLVED / MOVE LIMIT and the finishing rank. This is the **completion** stage.
3. Open **Results slide** → Full screen. This is the **statistics slide**.
4. The **name and roll-number strip** is fixed at the top of every screen and on the slide, so it is visible throughout.

## Repository structure

```
backend/app/
  cube.py          deterministic facelet engine, 18 moves built from 3D geometry
  solver.py        exact distances + all optimal moves (bidirectional BFS)
  scrambles.py     fixed-seed puzzle suite, verified true distances
  prompt.py        the shared state object, question and move definitions
  adapters/        decisions.py (Jev, Luna, Clef), chat.py (Opus), base.py (timeout/retry/abort)
  rules.py         rules, guardrails and model registry (from .env)
  runner.py        parallel race, guardrails, per-request logging, JSON results
  stats.py         metrics + random baseline
  main.py          FastAPI backend
backend/data/puzzles.json   the committed puzzle suite
frontend/          race view, dashboard, results slide (plain HTML/CSS/JS)
results/runs/      one JSON file per run with every request logged
run_benchmark.py   CLI runner      report.py   README tables      smoke_test.py   one call per model
tests/             offline test suite
media/             screen recording
```
