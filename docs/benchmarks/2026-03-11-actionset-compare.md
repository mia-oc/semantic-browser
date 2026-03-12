# End-to-end benchmark (1 AI-driven multi-step public-site tasks)

Methods compared per task request:
- Standard browser tooling (raw DOM extraction + JS actions)
- OpenClaw browser tooling (snapshot refs + browser actions)
- Semantic Browser (observe/act with semantic action IDs)

Each method ran the exact same 1 prompts and used the same planner model route.
Planner route: `openai:gpt-5.3-codex`

Cost model: Sonnet 4.6 estimated pricing constants (input $3.00 / 1M, output $15.00 / 1M).

Metric basis (apples-to-apples across all three methods):
- `tok-in` / `tok-out`: planner LLM input/output tokens only (does not include browser payload bytes).
- `planner tool calls`: LLM-declared tool/function calls returned by planner API response payloads.
- `browser/runtime calls`: browser operations issued by each method loop (navigate/observe/act/open/close/evaluate/click/type/press).
- `total tool calls`: planner tool calls + browser/runtime calls.
- `est. cost/request`: Sonnet 4.6-normalised cost from planner tokens only.

| Method | Success rate | Failures | Median speed ms | Median tok-in | Median tok-out | Median planner tool calls | Median browser/runtime calls | Median total tool calls | Median total tool calls (success-only) | Est. cost/request (USD) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Standard browser tooling | 0.0 | 1 | 30906.0 | 39444.0 | 255.0 | 0.0 | 15.0 | 15.0 | 0.0 | 0.122157 |
| OpenClaw browser tooling | 0.0 | 1 | 12345.7 | 11511.0 | 102.0 | 0.0 | 5.0 | 5.0 | 0.0 | 0.036063 |
| Semantic Browser | 0.0 | 1 | 56972.6 | 3085.0 | 49.0 | 0.0 | 15.0 | 15.0 | 0.0 | 0.009990 |

## Per-run journals

- JSON journals directory: `docs/benchmarks/journals/2026-03-12`
- One journal file is written for every method x task run (3 files total).

## Tasks

- **wikipedia_english_current_events** (wikipedia): Open English Wikipedia, then open Current events.

Artifacts: `docs/benchmarks/2026-03-11-actionset-compare.md` and `docs/benchmarks/2026-03-11-actionset-compare.json`