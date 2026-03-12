# Benchmark Protocol

Use this protocol before publishing benchmark numbers in `README.md`.

## Required metadata

- Benchmark date (UTC)
- Commit SHA under test
- Runtime version
- Task pack identifier and count
- Planner/model identifier
- Environment details (OS, browser, headless/headful)
- Run count and aggregation method

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
