# Benchmark Protocol

Use this protocol before publishing benchmark numbers in `README.md`.

## Required metadata

- Benchmark date (UTC)
- Commit SHA under test
- Runtime version
- Task pack identifier and count
- Planner: a **named real model** (and how it was driven) or an explicitly labelled scripted stand-in; never an unnamed config
- Environment details (OS, browser, headless/headful)
- Run count and aggregation method

## Tooling

`scripts/dogfood/replay.py` repeats a fixed per-tool command sequence N times (cold start, interleaved rounds, medians, pass = expected text present) so a hand-driven result can meet the 3-run rule; refs in its sequences come from a hand-driven run, so it measures tool cost, not model navigation. `scripts/dogfood/tj.py` journals hand-driven runs of any CLI (`tj TOOL TASK words...`, `tj --done TOOL TASK success|fail|partial "note"`, `tj --report`);
it records calls, wall time and output size per step. See `docs/benchmarks/2026-10-06-competitors-v1.7.md` for an example run.

`scripts/dogfood/runner.py` (scripted-oracle local/live suites) and `scripts/dogfood/navbench.py` (time and tokens to a usable page) are the older harnesses. Run live suites with the methods
**interleaved** (one round of each method, repeated), never one method after another: sequential runs let network drift look like a regression (seen on 1.7).

## Reproducibility rules

1. Run at least 3 times for each method.
2. Publish median metrics and per-run raw results.
3. Record all harness flags and fallback behaviors.
4. Record known flaky tasks and failure taxonomy.
5. Update `benchmarks/manifest.json` with the new result entry.

## Publication gate

Only update benchmark claims in `README.md` when:

- manifest entry exists and validates,
- raw report files are present,
- protocol fields are complete.
