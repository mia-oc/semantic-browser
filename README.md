# Semantic Browser Runtime

Make browser automation feel less like parsing soup and more like an old BBC Micro text adventure.

This runtime turns a live Chromium page into a compact "room" for an LLM:

```
@ BBC News (bbc.co.uk)
> Home page. Main content: "Top stories". Navigation: News, Sport, Weather.
1 open "News" [a10]
2 open "Sport" [a11]
3 fill Search BBC [a17] *value
+ 28 more [more]
```

The model replies with one action ID (`a10`) and we go again.

No giant JSON blobs. No DOM dumps. No pretending every page is stable.  
Just: what you see, what you can do, what changed.

## Why this is different (and why it now works)

Other browser tools give the LLM the same data in a different wrapper. We give it a fundamentally different view.

- **Plain-text room descriptions** - prose, not JSON.
- **Curated actions first** - top 15 useful actions, then `more` if needed.
- **Progressive disclosure** - `more` gives full action list without flooding every step.
- **Tiny action replies** - `a10`, `nav "https://..."`, `back`, `done`.
- **Narrative history** - readable previous steps, not noisy machine dump.
- **Guardrails for reality** - anti-repeat fallback, nav hardening, transient extract retry.
- **Honest failure mode** - if a site throws anti-bot gates, we say so and show evidence.

## Benchmark Results

### Baseline (validated rerun, 11 Mar 2026)

_Route: OpenAI API (`gpt-5.3-codex`). Full 25-task run against non-semantic routes, with OpenAI Responses output parsing fixed for telemetry capture._

| Method | Success rate | Median speed | Mean token-in | Mean token-out |
|---|---:|---:|---:|---:|
| Standard browser tooling | 28% (7/25) | 10,846ms | 11,895.8 | 109.8 |
| OpenClaw browser tooling | 68% (17/25) | 9,590ms | 4,889.2 | 50.5 |

Tool-usage telemetry is now captured explicitly in the harness output (per run and success-only aggregates).

### Apples-to-apples telemetry validation (12 Mar 2026, 1-task validation)

_Route: OpenAI API (`gpt-5.3-codex`). Validation rerun used one shared task (`wikipedia_english_current_events`) across all three methods after telemetry normalisation and OpenAI planner support in Semantic Browser mode._

Metric basis (same for every row):
- `planner input tokens (billable)`: tokens billed as planner input by the model provider.
- `planner output tokens (billable)`: tokens billed as planner output by the model provider.
- `browser/runtime payload bytes`: UTF-8 byte size of observation payload returned from browser/runtime and sent to planner.
- `browser/runtime payload token-estimate` (estimated): payload character count ÷ 4 (non-billable estimate).
- `total effective context load` (estimated): planner input billable tokens + payload token-estimate.
- `planner tool calls`: tool/function calls declared by planner API responses.
- `browser/runtime calls`: browser operations performed by each method loop.
- `total tool calls`: planner tool calls + browser/runtime calls.
- `indicative planner cost/request`: Sonnet 4.6-normalised estimate from planner billable tokens only.

| Method | Success rate | Planner input (billable) | Planner output (billable) | Browser payload bytes | Payload token-est (estimated) | Total effective context load (estimated) | Planner tool calls | Browser/runtime calls | Total tool calls | Indicative planner cost/request (USD) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Standard browser tooling | 0% (0/1) | 39,442 | 252 | 78,984 | 18,534 | 57,976 | 0.0 | 15.0 | 15.0 | 0.122106 |
| OpenClaw browser tooling | 0% (0/1) | 11,511 | 102 | 32,000 | 7,914 | 19,425 | 0.0 | 5.0 | 5.0 | 0.036063 |
| Semantic Browser | 100% (1/1) | 1,693 | 23 | 3,872 | 951 | 2,644 | 0.0 | 10.0 | 10.0 | 0.005424 |

Caveats:
- This is a telemetry validation run, not a quality/performance claim from one task.
- Cross-method token deltas are expected because each method sends different observation payload shapes to the same planner.

Source artefacts:
- `docs/benchmarks/2026-03-11-other-routes-25.json`
- `docs/benchmarks/2026-03-11-other-routes-25.md`
- `docs/benchmarks/journals/2026-03-11/compare-other-routes-25/`
- `docs/benchmarks/2026-03-11-actionset-compare.json` (tool-call telemetry validation)
- `docs/benchmarks/2026-03-11-actionset-compare.md` (tool-call telemetry validation)
- `docs/benchmarks/journals/2026-03-12/` (per-platform validation journals)

### Semantic Browser

| Eval | Success rate | Median token-in | Median token-out | Est. cost/task |
|---|---:|---:|---:|---:|
| 25-task full eval | 96% (24/25) | 1,004 | 17 | $0.0067 |

Yes, this is a dramatic jump.

The one remaining miss in the 25-task run is a rather tricky anti-bot challenge loop. We're working on that.
When that happens, harness now captures screenshots and sends them to the planner (LLM) to solve.

## Task harness (quality gate)

```bash
# Full 25-task eval
BENCHMARK_API=openai BENCHMARK_MODEL=gpt-5.4 python3 scripts/task_harness.py

# Quick smoke run (first 5 tasks)
HARNESS_MAX_TASKS=5 BENCHMARK_API=openai BENCHMARK_MODEL=gpt-5.4 python3 scripts/task_harness.py
```

25 tasks across: navigation, search, multi-step, content, interaction, resilience, speed.

If challenge/captcha is detected, harness captures a screenshot and includes it in the LLM call.

---

## What This Is (Simple Version)

You open a real webpage.

Instead of dumping giant blobs into the model, you run a clean loop:

1. "What can I see?"
2. "What can I do?"
3. "Do this action."
4. "What changed?"

Rinse and repeat.

---

## Install

### 1) Core package (attach mode support)

```bash
pip install semantic-browser
```

### 2) Managed browser mode (recommended for first use)

```bash
pip install "semantic-browser[managed]"
```

### 3) Local service mode

```bash
pip install "semantic-browser[server]"
```

### 4) Everything (dev + tests + server + managed)

```bash
pip install "semantic-browser[full]"
```

---

## Dependencies (Clear and Explicit)

- Python: `>=3.11`
- Browser engine (v1): Chromium/Chrome only
- Automation library: Playwright async API
- Core deps:
  - `pydantic`
  - `click`
  - `PyYAML`
- Optional deps:
  - `playwright` for managed mode
  - `fastapi`, `uvicorn` for service mode

Install Chromium for managed mode:

```bash
semantic-browser install-browser
```

Check your environment:

```bash
semantic-browser doctor
```

---

## Fastest First Run (Copy/Paste)

```bash
pip install "semantic-browser[managed]"
semantic-browser install-browser
semantic-browser portal --url https://example.com --headless
```

In portal mode, try:

- `observe summary`
- `actions`
- `act <action_id>`
- `back`
- `forward`
- `reload`
- `trace my-trace.json`
- `quit`

---

## Python Library Usage

```python
import asyncio
from semantic_browser import ManagedSession
from semantic_browser.models import ActionRequest

async def demo():
    session = await ManagedSession.launch(headful=False)
    runtime = session.runtime

    await runtime.navigate("https://example.com")
    obs = await runtime.observe(mode="summary")
    print("actions:", len(obs.available_actions))

    first_open = next((a for a in obs.available_actions if a.op == "open"), None)
    if first_open:
        step = await runtime.act(ActionRequest(action_id=first_open.id))
        print("step:", step.status, step.observation.page.url)

    await runtime.export_trace("trace.json")
    await session.close()

asyncio.run(demo())
```

### CDP attach tips (important)

When attaching to an already-running Chrome, use the **browser-level** websocket:

- ✅ `ws://.../devtools/browser/<id>`
- ❌ `ws://.../devtools/page/<id>`

If you pass a page websocket, runtime now raises a clear `AttachmentError`
explaining that a browser websocket is required.

You can also hint which tab to bind:

```python
runtime = await SemanticBrowserRuntime.from_cdp_endpoint(
    endpoint,
    target_url_contains="x.com",
    prefer_non_blank=True,
)
```

If you do not provide a hint, the runtime now prefers non-blank pages over
`about:blank`.

If you use `page_index`, it must be zero-based and valid for the target context.
Invalid indices now raise `AttachmentError` instead of silently falling back.

Observation recovery: summary observations now auto-retry up to 2 extra times
when extraction returns a transient "No visible nodes" state:
- retry 1: short backoff
- retry 2: page reload + settle backoff

This reduces flaky low-confidence results on dynamic SPAs (for example Teams).

Top-first token behaviour (summary mode):
- `observe(mode="summary")` now focuses on a top-of-page slice (viewport + buffer)
- `observe(mode="full")` returns broader full-page context
- summary key points include a `top-scope summary: X/Y interactables included` hint

Auto routing mode:
- `observe(mode="auto")` computes a lightweight ARIA quality score and chooses route automatically:
  - good ARIA => compact top-scope route (`aria_compact`)
  - weak/noisy ARIA => broader route (`semantic_full`)
- route and quality are exposed in `observation.metrics` and summary key points.

Planner control-panel view (BBC Micro loop style):
- each observation now includes `observation.planner`:
  - `location`: concise room/location line
  - `what_you_see`: short capped bullet list
  - `available_actions`: capped action list (`id`, `label`, `op`)
  - `blockers`: active blocker hints
- use this as the LLM-facing payload for low token-in turns; keep full observation internal for diagnostics/recovery.

This keeps default observations leaner while allowing deterministic escalation to full context.

---

## CLI Commands

```bash
semantic-browser version
semantic-browser doctor
semantic-browser install-browser

semantic-browser portal --url https://example.com
semantic-browser serve --host 127.0.0.1 --port 8765
semantic-browser eval-corpus --config corpus/sites.yaml --out corpus-report.json

semantic-browser launch --headless
semantic-browser observe --session <id> --mode summary
semantic-browser navigate --session <id> --url https://example.com
semantic-browser act --session <id> --action <action_id>
semantic-browser inspect --session <id> --target <target_id>
semantic-browser back --session <id>
semantic-browser forward --session <id>
semantic-browser reload --session <id>
semantic-browser wait --session <id> --ms 500
semantic-browser export-trace --session <id> --out trace.json
```

---

## Docs

- `docs/vision.md` - product intent and non-negotiables
- `docs/requirements.md` - behavior requirements and KPIs
- `docs/technical_spec.md` - architecture and design
- `docs/project_plan.md` - implementation checklist and status
- `docs/system_arch.md` - architecture diagrams
- `docs/getting_started.md` - copy/paste onboarding guide
- `docs/dependencies.md` - explicit dependency matrix

If you just cloned the repo, start with `docs/project_plan.md`.
