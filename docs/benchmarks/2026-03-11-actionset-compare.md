# End-to-end benchmark (1 AI-driven multi-step public-site tasks)

Methods compared per task request:
- Standard browser tooling (raw DOM extraction + JS actions)
- OpenClaw browser tooling (snapshot refs + browser actions)
- Semantic Browser (observe/act with semantic action IDs)

Each method ran the exact same 1 prompts and used the same planner model route.
Planner route: `openai:gpt-5.3-codex`

Cost model: Sonnet 4.6 estimated pricing constants (input $3.00 / 1M, output $15.00 / 1M).

Metric basis (apples-to-apples across all three methods):
- `planner input tokens (billable)`: tokens billed as planner input by the LLM provider.
- `planner output tokens (billable)`: tokens billed as planner output by the LLM provider.
- `browser/runtime payload bytes`: UTF-8 byte size of observation payload returned from browser/runtime and sent to planner.
- `browser/runtime payload token-estimate` (estimated): payload character count ÷ 4 (non-billable estimate).
- `total effective context load` (estimated): planner input tokens + payload token-estimate.
- `planner tool calls`: LLM-declared tool/function calls returned by planner API response payloads.
- `browser/runtime calls`: browser operations issued by each method loop (navigate/observe/act/open/close/evaluate/click/type/press).
- `total tool calls`: planner tool calls + browser/runtime calls.
- `indicative planner cost/request`: Sonnet 4.6-normalised cost from planner billable tokens only.

| Method | Success rate | Failures | Median speed ms | Planner in (billable) | Planner out (billable) | Browser payload bytes | Payload token-est (estimated) | Total effective context load (estimated) | Median planner tool calls | Median browser/runtime calls | Median total tool calls | Median total tool calls (success-only) | Indicative planner cost/request (USD) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Standard browser tooling | 0.0 | 1 | 65814.7 | 39442.0 | 252.0 | 78984.0 | 18534.0 | 57976.0 | 0.0 | 15.0 | 15.0 | 0.0 | 0.122106 |
| OpenClaw browser tooling | 0.0 | 1 | 13540.1 | 11511.0 | 102.0 | 32000.0 | 7914.0 | 19425.0 | 0.0 | 5.0 | 5.0 | 0.0 | 0.036063 |
| Semantic Browser | 1.0 | 0 | 19403.9 | 1693.0 | 23.0 | 3872.0 | 951.0 | 2644.0 | 0.0 | 10.0 | 10.0 | 10.0 | 0.005424 |

## Per-run journals

- JSON journals directory: `docs/benchmarks/journals/2026-03-12`
- One journal file is written for every method x task run (3 files total).

## Tasks

- **wikipedia_english_current_events** (wikipedia): Open English Wikipedia, then open Current events.

Artifacts: `docs/benchmarks/2026-03-11-actionset-compare.md` and `docs/benchmarks/2026-03-11-actionset-compare.json`