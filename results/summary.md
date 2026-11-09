### Primary v1 (10 puzzles, run `20261109T161544Z-dceb5d`)

| Model | Avg latency / move | Avg time / puzzle | Total time | Avg moves | Total moves | Solved | Success rate | Avg optimality gap | Optimal solves | Optimal-move rate | Malformed | Errors | Retries | Cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Jev 1.13 | 668 ms | 20.1 s | 201.1 s | 30.0 | 300 | 0/10 | 0.0% | N/A | 0 | 43.3% | 0 | 0 | 0 | $0.0113 |
| GPT-6 Luna Decisions | 591 ms | 25.3 s | 252.6 s | 30.0 | 300 | 0/10 | 0.0% | N/A | 0 | 19.5% | 0 | 27 | 27 | $0.0141 |
| Cloudflare Clef | 1075 ms | 32.4 s | 324.3 s | 30.0 | 300 | 0/10 | 0.0% | N/A | 0 | 27.2% | 0 | 0 | 0 | $0.0489 |
| Claude Opus 5.5 | 5601 ms | 168.2 s | 1682.0 s | 30.0 | 300 | 0/10 | 0.0% | N/A | 0 | 47.3% | 3 | 0 | 0 | $2.5826 |

Random-move baseline (Monte Carlo, same puzzles, 30-move limit): **0.00%** solve rate.
Reported spend for this run: $2.6570 over 1200 turns.

### Warmup v1 (3 puzzles, run `20261109T154553Z-47d5b3`)

| Model | Avg latency / move | Avg time / puzzle | Total time | Avg moves | Total moves | Solved | Success rate | Avg optimality gap | Optimal solves | Optimal-move rate | Malformed | Errors | Retries | Cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Jev 1.13 | 616 ms | 18.5 s | 55.5 s | 30.0 | 90 | 0/3 | 0.0% | N/A | 0 | 50.0% | 0 | 0 | 0 | $0.0034 |
| GPT-6 Luna Decisions | 588 ms | 24.3 s | 73.0 s | 30.0 | 90 | 0/3 | 0.0% | N/A | 0 | 17.6% | 0 | 7 | 7 | $0.0043 |
| Cloudflare Clef | 1169 ms | 35.2 s | 105.6 s | 30.0 | 90 | 0/3 | 0.0% | N/A | 0 | 28.9% | 0 | 0 | 0 | $0.0145 |
| Claude Opus 5.5 | 4475 ms | 56.7 s | 170.1 s | 12.7 | 38 | 2/3 | 66.7% | +1.00 (n=2) | 1 | 50.0% | 0 | 0 | 0 | $0.2664 |

Random-move baseline (Monte Carlo, same puzzles, 30-move limit): **0.00%** solve rate.
Reported spend for this run: $0.2887 over 308 turns.
