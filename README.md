# Rubik's cube race: fast decision models vs a frontier LLM

AI Engineering, Assignment 02
Ibrahim Johar Farooqi, 23K-0074, BAI-7A, FAST-NUCES Karachi

> Is a model that decides in milliseconds more useful than a frontier LLM that spends longer planning, if the slower model solves the task in fewer moves?

Four models play the same scrambled 3x3 cubes through OpenRouter. On every turn each model gets the current state and picks one of the 18 face turns, until the cube is solved or it has used 30 moves. Every request is logged with its move, latency, tokens and reported cost. Each puzzle has an exact BFS shortest solution, so I can measure both speed and decision quality.

## Demo recording

<!-- RECORDING: replace the line below if the video is hosted elsewhere -->
[Watch the screen recording](media/demo.mp4) (`media/demo.mp4` in this repository)

The recording shows the models racing, completed races with final status and ranks, and the closing results slide. My name and roll number stay on screen throughout.

## Results

The reported tables come from two v1 runs. The code in this repository is v2, which has the state fixes described in [What went wrong and what I changed](#what-went-wrong-and-what-i-changed). I did not run a v2 benchmark because the budget ran out.

No model solved a primary puzzle. Opus solved 2 of the 3 easier warm-up puzzles, and the three decision models solved none.

### Primary v1 (10 puzzles, 4-5 moves)

Run [`20261109T161544Z-dceb5d`](results/runs/20261109T161544Z-dceb5d.json)

| Model | Solved | Success | Avg latency / move | Avg time / puzzle | Total time | Avg moves | Gap | Optimal-move rate | Malformed | Errors | Retries | Cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Jev 1.13 | 0/10 | 0.0% | 668 ms | 20.1 s | 201.1 s | 30.0 | N/A | 43.3% | 0 | 0 | 0 | $0.0113 |
| GPT-6 Luna Decisions | 0/10 | 0.0% | 591 ms | 25.3 s | 252.6 s | 30.0 | N/A | 19.5% | 0 | 27 | 27 | $0.0141 |
| Cloudflare Clef | 0/10 | 0.0% | 1075 ms | 32.4 s | 324.3 s | 30.0 | N/A | 27.2% | 0 | 0 | 0 | $0.0489 |
| Claude Opus 5.5 | 0/10 | 0.0% | 5601 ms | 168.2 s | 1682.0 s | 30.0 | N/A | 47.3% | 3 | 0 | 0 | $2.5826 |

The random-move baseline on the same puzzles has a 0.00% solve rate (Monte Carlo, 30-move limit), and a random first move is optimal 6.1% of the time. Reported spend was $2.6570 over 1200 turns.

### Warm-up v1 (3 puzzles, 3-4 moves)

Run [`20261109T154553Z-47d5b3`](results/runs/20261109T154553Z-47d5b3.json)

| Model | Solved | Success | Avg latency / move | Avg time / puzzle | Total time | Avg moves | Gap | Optimal-move rate | Malformed | Errors | Retries | Cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Jev 1.13 | 0/3 | 0.0% | 616 ms | 18.5 s | 55.5 s | 30.0 | N/A | 50.0% | 0 | 0 | 0 | $0.0034 |
| GPT-6 Luna Decisions | 0/3 | 0.0% | 588 ms | 24.3 s | 73.0 s | 30.0 | N/A | 17.6% | 0 | 7 | 7 | $0.0043 |
| Cloudflare Clef | 0/3 | 0.0% | 1169 ms | 35.2 s | 105.6 s | 30.0 | N/A | 28.9% | 0 | 0 | 0 | $0.0145 |
| Claude Opus 5.5 | 2/3 | 66.7% | 4475 ms | 56.7 s | 170.1 s | 12.7 | +1.00 (n=2) | 50.0% | 0 | 0 | 0 | $0.2664 |

The random-move baseline is again 0.00%. Reported spend was $0.2887 over 308 turns.

### Secondary measures from primary v1

Since nothing was solved, I also looked at how far each model got and how it played. "Puzzles improved" counts the puzzles where the model reached a state closer to solved than its starting position, using exact distances. Each of those improvements was 1 move. "Immediate undos" counts applied moves that exactly reversed the previous applied move.

| Model | Median latency | p95 latency | Puzzles improved | Immediate undos |
|---|---|---|---|---|
| Jev 1.13 | 621 ms | 889 ms | 1/10 | 245/290 (84%) |
| GPT-6 Luna Decisions | 583 ms | 909 ms | 2/10 | 25/263 (10%) |
| Cloudflare Clef | 964 ms | 1879 ms | 2/10 | 54/290 (19%) |
| Claude Opus 5.5 | 2547 ms | 15576 ms | 5/10 | 176/287 (61%) |

### Answers to the five questions

1. Which model is fastest at making decisions? GPT-6 Luna Decisions, at 591 ms per move on average in primary v1. Jev 1.13 was next at 668 ms, then Cloudflare Clef at 1075 ms and Claude Opus 5.5 at 5601 ms. Opus took about 9.5 times as long per move as Luna.

2. Which model achieved the highest solve rate? In the primary run all four tied at 0 of 10. As a secondary result, Opus was the only model to solve anything in the warm-up, with 2 of 3 solved (66.7%).

3. Which model found the shortest solutions, and how close to the known optimum? The primary run has no solutions, so its gap is N/A for every model. In the warm-up, Opus solved one 3-move puzzle in 3 moves (gap 0) and another 3-move puzzle in 5 moves (gap 2), for an average gap of +1.00 over 2 solves. No other model has a gap to compare. On the secondary measures in primary v1, Opus had the highest optimal-move rate (47.3%) and improved on its start in 5 of 10 puzzles.

4. Did the fastest model also achieve the best solution quality? No. Luna was fastest and had the lowest optimal-move rate in both runs (19.5% in primary, 17.6% in warm-up), and it solved nothing. Jev's 43.3% looks close to Opus, but 84% of Jev's moves undid the previous move, and undoing a bad move counts as optimal. I would treat that rate as inflated. With zero primary solves, this answer rests on secondary measures.

5. Fast decision model, frontier LLM or a hybrid in a real application? I would use a hybrid, and my evidence for it is limited. None of the models could solve a 4-5 move cube alone, so neither type is enough on this task. The fast models cost little (Jev $0.0113 against Opus $2.5826 for the same 300 turns) and answered in under a second on average in the case of Jev and Luna, but they repeated moves without making progress. Opus was the only model that solved anything and it improved on the most puzzles, at about 8 times Jev's latency and 228 times its cost. It was also tested under a reduced setup (low effort, 1024 tokens and the history bug), so its numbers may understate it. In a real application a fast model could propose moves while a check catches stalls, such as repeated undos or no drop in distance, and hands over to the LLM or to an exact solver. On a cube the exact solver in this repository would be the better verifier, since it gives every optimal move offline at no API cost. I did not test this hybrid, so this is a recommendation drawn from the failures above.

## What went wrong and what I changed

In v1, Opus ran at reasoning effort `low` with `max_tokens` 1024. Its median reasoning in the primary run was 0 tokens per move (mean 210), and 175 of its 300 turns had no reasoning tokens. Three replies were cut off by the token limit and counted as malformed. On many turns it played probe pairs such as `R R' U U' F F'`.

I also found a state bug after the runs. The move history was sent as `recent_moves` with no explanation, and Opus read it as the scramble and undid its own moves. Its saved reasoning on one turn says: "I'm tracing back the recent moves, F', F, L, L', F', which net out to just F', so undoing that would take an F." The letters "scrambl" appear in the reasoning of 103 of its 300 primary turns. All four models saw the same state, so the bug applied to all of them.

For v2 I renamed the field to `moves_you_have_played`, and the format note now says these are the model's own moves, already applied. I also restored the face orientation in words (which edge is each face's top row and left column). It had been dropped along with the face grids that Luna refused.

I then ran two Opus-only pilots at medium effort, with `max_tokens` 8000 and a 300 s timeout. Each sent 2 probes for each of 3 primary puzzles: the starting state and the state after one exact optimal move.

| Pilot | Stage | Optimal moves | Undid its own move (mid-game) | Median reasoning tokens | Cut off | Errors | Cost |
|---|---|---|---|---|---|---|---|
| [`20261109T203729Z`](results/pilots/pilot_20261109T203729Z_medium.json) | before the wording fix | 2/6 (33%) | 2/3 (67%) | 1439 | 0 | 0 | $0.2062 |
| [`20261109T204813Z`](results/pilots/pilot_20261109T204813Z_medium.json) | after the wording fix | 2/6 (33%) | 0/3 (0%) | 1534.5 | 0 | 0 | $0.1963 |

The fix stopped the undoing on these probes, but accuracy did not improve. Opus opened with `F'` on all 3 puzzles in both pilots and missed all 3 mid-game probes each time. With 3 mid-game probes per pilot, this is a small check. The account then ran out of credit, so I did not run v2.

## Limitations

- The reported Opus numbers come from the v1 setup (low effort plus the history bug). No v2 benchmark was run.
- The primary set has 10 puzzles with 1 repeat each, and the warm-up has 3 puzzles.
- Luna's 502 refusals are counted as errors and each one uses a move: 27 of 300 primary turns and 7 of 90 warm-up turns.
- Decision models can't output illegal moves because they answer a fixed choice question, while Opus can.
- Latency includes network time.
- Costs are as reported by OpenRouter. Refused Luna turns have no reported cost.

## Models

| Model | Category | OpenRouter ID | Interface |
|---|---|---|---|
| Jev 1.13 | System-1 decision model | `typesafe/jev-1.13` | Decisions API (`/api/alpha/decisions`) |
| GPT-6 Luna Decisions | System-1 decision model | `openai/gpt-6-luna-decisions` | Decisions API |
| Cloudflare Clef | System-1 decision model | `cloudflare/clef` | Decisions API |
| Claude Opus 5.5 | Frontier LLM | `anthropic/claude-opus-5.5` | Chat Completions (`/api/v1/chat/completions`) |

All four model IDs were checked with a live call before the benchmark (`smoke_test.py`). There are no fallback models, and a model that fails is recorded as failing.

## How the AI plays

As in the Snake example from class, the game is a state and action loop. The model gets the current cube and its own move history and returns one move. The engine applies that move, checks whether the cube is solved, and sends the new state.

All four models get the same state object. The decision models receive it as the Decisions API `state` field, and Opus receives it as JSON text in its message. This is the v2 form:

```json
{
  "cube_facelets": "UUFUUFUUFRRRRRRRRRFFDFFDFFDDDBDDBDDBLLLLLLLLLUBBUBBUBB",
  "format": "cube_facelets lists 54 stickers in face order U, R, F, D, L, B ...",
  "moves_you_have_played": [],
  "moves_remaining": 30
}
```

All four also get the same question: "Choose the single next move most likely to progress toward the solved cube." The 18 moves are defined the same way for every model ("Turn the right face clockwise by 90 degrees", and so on). The decision models get them as the options of a `choice` question, and their reply includes the chosen move plus a confidence and a probability for each option, all logged. Opus gets the same 18 moves listed in its message and must reply with exactly `{"move": "R'"}`. A JSON schema with the 18 moves as an `enum` is requested as a structured-output constraint.

## Experiment design

| Test set | Scramble | Puzzles | Purpose | Run? |
|---|---|---|---|---|
| Warm-up | 3-4 turns | 3 | Verify adapters, move validation and the engine | yes (v1) |
| Primary | 4-5 turns | 10 | Main comparison with exact shortest distances | yes (v1) |
| Extension | 15-20 turns | 5 | Probe behaviour on complex states | no |

Scrambles are generated from fixed seeds and committed in [`backend/data/puzzles.json`](backend/data/puzzles.json). Every model plays exactly these states, and a test checks that the file matches the generator. Warm-up and primary scrambles are kept only if their exact BFS distance equals the scramble length, so a 5-move puzzle really needs 5 moves.

Shortest solutions use the half-turn metric (X, X' and X2 each count as one move). A bidirectional BFS builds a table of all 46,741 states within 4 moves of solved, then searches forward up to 3 moves from the puzzle. This gives the exact distance for any state up to 7 moves from solved and every optimal next move, so ties count. The solver is checked against an independent plain BFS over all 621,649 states within 5 moves.

The four models play each puzzle at the same time. Each is timed on its own clock.

### Rules (identical for every model)

| Rule | Value |
|---|---|
| Move limit | 30 turns per puzzle. Reaching the limit counts as unsolved |
| Legal moves | the 18 face turns `U U' U2 R R' R2 F F' F2 D D' D2 L L' L2 B B' B2` |
| Move history | full: every move this model has applied so far |
| Timeout | 60 s per request attempt |
| Retries | 1, only on timeout, network error or HTTP 408/429/5xx (never on a bad answer) |
| Malformed reply | logged and counted. The cube is unchanged and the turn is used up. Never repaired or reinterpreted |
| Failed request (after retry) | logged as an error. The cube is unchanged and the turn is used up |
| Opus settings | reasoning effort `low`, `max_tokens` 1024 (reasoning and answer), structured JSON output |

### Metrics

| Metric | Definition |
|---|---|
| Avg latency / move | mean duration of the API request that produced each turn |
| Total solve time | wall time from a model's first request until it solves the cube or hits the limit (includes retries) |
| Total moves | turns used (every turn counts, including malformed and failed ones) |
| Success rate | solved puzzles divided by completed puzzles |
| Optimality gap | moves used minus exact shortest moves, solved puzzles only. Unsolved puzzles have no gap (N/A) and are never counted as 30 |
| Optimal-move rate | share of turns where the move was one of the exact optimal moves from that state |
| Random baseline | Monte Carlo solve rate of a player that picks uniformly random moves on the same puzzles (no API calls) |

## Cost and token guardrails

1. The OpenRouter key has a credit limit, which is the hard cap.
2. The runner adds up the cost OpenRouter reports and stops before any new request once `RUN_BUDGET_USD` is reached (default $2, set to $3 for the primary run).
3. Each model gets at most 30 turns per puzzle, so every run has a known upper bound on calls. You must type `yes` (CLI) or confirm (UI) before any paid call.
4. Opus runs at reasoning effort `low` with `max_tokens` 1024. A reply cut off by this limit is logged as malformed with the reason and is not retried.
5. A 401, 402 or 403 aborts the whole run instead of being recorded as a model's mistake. A 400 is never retried.
6. Tests use scripted offline players, and the application itself only runs live. Every saved run records its full rules snapshot and spend.

Reported spend was $0.2887 for the warm-up and $2.6570 for the primary run, $2.9457 in total. Opus accounted for $2.8491 of that. The two saved pilots cost another $0.4025.

## Pilot: state format

The first smoke test sent a plain-text description of the 54-character string. All three decision models returned nearly uniform probabilities over the 18 moves (confidence 5-12%) and picked wrong moves, while Opus picked the correct `R'`. I then tried a structured state that also contained labelled 3x3 face grids. GPT-6 Luna Decisions refused every request containing the grids (HTTP 502 "OpenAI refused to answer question"), and a single-sample probe on the smoke-test cube, which is not a benchmark puzzle, isolated the cause. Without the grids it answered. I removed the grids for all four models so the state stayed identical across models, before any benchmark puzzle was played.

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

Replaying saved runs and running the tests need no API calls. A live run needs an OpenRouter key in `.env` (`OPENROUTER_API_KEY=...`). The key is only read by the backend and `.env` is git-ignored.

### Run the web app

```bash
uvicorn backend.app.main:app --port 8000
```

Open <http://localhost:8000>.

- Race: "Replay saved run" replays any saved run at 1-16x speed. "New live run" starts a paid run after a confirmation step.
- Dashboard: statistics for each model, bar charts, per-puzzle results and the random baseline.
- Results slide: a 16:9 statistics slide with a Full screen button.

### Run from the terminal

```bash
python smoke_test.py                  # one request per model (paid)
python run_benchmark.py --tier primary   # also warmup or extension (paid)
python report.py 20261109T161544Z-dceb5d 20261109T154553Z-47d5b3   # offline, writes results/summary.md
```

### Tests (offline, no API calls)

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The 82 tests cover the engine (checked against the `magiccube` library on 300 random sequences), the solver, the scrambles, the adapters and their retry policy, the runner guardrails, the Opus planning guard, report labels and the API.

## Repository structure

```
backend/app/
  cube.py          deterministic facelet engine, 18 moves built from 3D geometry
  solver.py        exact distances and all optimal moves (bidirectional BFS)
  scrambles.py     fixed-seed puzzle suite, verified true distances
  prompt.py        the shared state object, question and move definitions
  adapters/        decisions.py (Jev, Luna, Clef), chat.py (Opus), base.py (timeout/retry/abort)
  rules.py         rules, guardrails and model registry (from .env)
  runner.py        parallel race, guardrails, per-request logging, JSON results
  stats.py         metrics and random baseline
  main.py          FastAPI backend
backend/data/puzzles.json   the committed puzzle suite
frontend/          race view, dashboard, results slide (plain HTML/CSS/JS)
results/runs/      one JSON file per run with every request logged
results/pilots/    Opus-only medium-effort probes
run_benchmark.py   CLI runner
report.py          README tables
smoke_test.py      one call per model
pilot_opus.py      Opus-only probe script
merge_runs.py      run merge tool (not used for the reported results)
tests/             offline test suite
media/             screen recording
```
