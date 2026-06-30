# Aegis Profit/Quality Benchmark (run 2026-06-27)

Real curation engine + real quote math over a basket of datasets. Economics use the
quote's **estimated COGS** (no provider keys in env ⇒ actual local spend = $0). Quality =
the re-verifiable guarantees (PII=0, dedup, schema-valid) re-run on each output.

| profile | rows in | rows out | dupes | PII masked | yield | quote | est COGS | margin | quality |
|---|---|---|---|---|---|---|---|---|---|
| clean-small | 200 | 200 | 0 | 0 | 100.0% | $55.00 | $6.00 | 85.6% | PASS |
| clean-mid | 2000 | 2000 | 0 | 309 | 100.0% | $55.00 | $16.20 | 67.1% | PASS |
| dup-heavy | 2025 | 1500 | 525 | 270 | 74.1% | $55.00 | $16.21 | 67.1% | PASS |
| pii-heavy | 1320 | 1200 | 120 | 3138 | 90.9% | $55.00 | $16.13 | 67.2% | PASS |
| messy-mixed | 3750 | 3000 | 750 | 4647 | 80.0% | $55.00 | $16.38 | 66.8% | PASS |
| large-ish | 8400 | 8000 | 400 | 2493 | 95.2% | $55.00 | $16.86 | 65.9% | PASS |

**Leaderboard:** 6 jobs · revenue $330.00 · est COGS $87.78 · profit $230.82 · avg margin 69.9% · quality 6/6 PASS.

**Finding:** on local-reliable data the agent is BOTH highly profitable AND fully guarantee-passing — no tradeoff, because the cleaning is deterministic and free on the DGX. The profit-vs-quality FRONTIER only appears on hard data needing paid escalation (OCR/vision/bigger model); quantifying it requires a provider key (then actual spend > 0).
