# Scratchpad: Semantic Browser Runtime

## Session Log

### 2026-03-10 — Project Inception

- Repository initialised (MIT licence, clean slate)
- Full planning documentation created:
  - `vision.md` — north-star goal and non-negotiables
  - `requirements.md` — functional/non-functional requirements, KPIs, edge cases
  - `technical_spec.md` — stack, data flows, extraction design, API contracts
  - `project_plan.md` — 9-phase roadmap with granular task tick-boxes
  - `system_arch.md` — architecture diagrams, module dependencies, data model
- Ready for Phase 1: Package Scaffolding

## Open Questions

1. **CDP attach reliability** — How well does Playwright's CDP connect work
   with externally managed Chrome instances in practice? May need fallback
   or clear documentation on requirements.

2. **Accessibility tree depth** — Playwright's `page.accessibility.snapshot()`
   returns a flat-ish tree. Need to evaluate whether it provides enough
   structure for good region detection, or whether supplementary DOM queries
   are needed from the start.

3. **Settle strategy tuning** — The mutation quiet period and interactable
   stability thresholds will need empirical tuning. Start conservative
   (longer waits), tighten based on corpus evaluation.

4. **Content group detection** — Repeated structure detection is the hardest
   extraction problem. May need to evaluate multiple heuristics (sibling
   tag patterns, class name patterns, bounding box grids) before settling
   on the right approach.

5. **Frame handling** — Many modern sites use iframes for ads, embeds, and
   third-party widgets. Need to decide how aggressive to be about iframe
   content extraction vs. treating them as opaque blocks.

### 2026-03-10 — End-to-End Build + Dogfood

- Implemented full package scaffold under `src/semantic_browser`
- Added deterministic extraction pipeline:
  - settle strategy (`extractor/settle.py`)
  - semantic extraction (`extractor/semantics.py`)
  - grouping, blockers, classifier, stable IDs, delta
- Added action pipeline:
  - request validation
  - locator resolution
  - action execution
  - result classification
- Added managed session + attached runtime creation paths
- Added optional FastAPI service routes and schemas
- Added CLI command set for version/doctor/install-browser/launch/attach/observe/
  navigate/act/inspect/diagnostics/export-trace
- Added telemetry trace store and JSON debug bundle export
- Added unit test baseline (8 tests passing)
- Dogfooded runtime as LLM user:
  - launched managed browser (headless)
  - navigated to `https://example.com`
  - observed actions
  - executed first surfaced action (`Learn more`)
  - observed delta with page identity change to IANA page
  - exported trace bundle to `dogfood-trace.json`

### 2026-03-10 — Service + Corpus Hardening

- Added `.gitignore` with Python/build/runtime artifact exclusions
- Added service session registry (`service/state.py`) and attach route
  (`POST /sessions/attach`)
- Added service operation routes for `back`, `forward`, `reload`
- Added CORS middleware to FastAPI app factory
- Added corpus harness baseline:
  - fixture loader (`corpus/fixtures.py`)
  - site scoring and aggregate metrics (`corpus/metrics.py`)
  - site task execution (`corpus/tasks.py`)
  - runner entrypoint (`corpus/runner.py`)
  - starter config (`corpus/sites.yaml`)
- Added CLI commands:
  - `serve`
  - `eval-corpus`
  - non-portal navigation helpers (`back`, `forward`, `reload`, `wait`)
- Added security redaction baseline (`extractor/redaction.py`)
- Expanded tests to 17 passing:
  - service e2e route test
  - validation/results tests
  - redaction tests
  - corpus metrics tests

### 2026-03-10 — Coverage Completion + Corpus Re-run

- Removed tracked `__pycache__` artifacts from repo paths and enforced ignore
- Added integration coverage for:
  - example and google observations
  - google fill/submit workflow
  - stale and disabled action edge cases
  - ID persistence across re-observation
  - delta/full ratio checks on representative pages
  - grouping and inspect details on live sites
  - cookie banner and semantically poor page heuristics (fixture pages)
- Added skipped CDP feasibility integration test scaffold (requires external CDP browser)
- Added additional extractor/unit coverage (browser manager, resolver, grouping, blockers)
- Improved runtime action robustness:
  - `runtime.act()` now returns structured `invalid`/`stale`/`failed` results instead of raising
  - locator resolution uses `.first` and includes `combobox`/`searchbox` roles
  - wait/back/forward/reload now classify as success outcomes
- Re-ran corpus on expanded 11-site fixture list:
  - `site_count`: 11
  - `pass_rate`: 0.8182
  - `avg_score`: 0.9091
  - misses were mostly page-type classifier mismatches (python docs + mozilla home)
- Test suite now: 48 passed, 1 skipped

### 2026-03-10 — External Docs + Cursor LLM Proof

- Rewrote `README.md` for first-time users with plain-language intro and
  copy/paste setup instructions.
- Added `docs/getting_started.md` with zero-guesswork install/run guide.
- Added `docs/dependencies.md` with explicit dependency matrix and mode mapping.
- Ran fresh LLM-style proof loop from inside Cursor via Python runtime calls:
  - navigate -> observe -> choose action -> act -> delta -> back/forward/reload
  - exported proof trace: `llm-cursor-proof-trace.json`
- Proof metrics from run:
  - initial actions: 6
  - post-action page transition: `example.com` -> IANA page
  - delta bytes: 208 vs full bytes: 14349

## Lessons

- Trace export must serialize datetimes using `default=str`; otherwise JSON export
  fails on observation timestamps.
- A fake/mocked page in tests must handle all evaluate script paths used by
  extraction helpers, or runtime tests become brittle.
- Incremental deltas are immediately useful: in dogfood run, first action changed
  page identity and expanded surfaced action count from 1 to 28 without resending
  unnecessary state in the planner loop.
- Op-only action requests (`ActionRequest(op=...)`) are essential for global
  runtime controls (`wait`, `back`, `forward`, `reload`, `navigate`) and make
  the porthole usable without always selecting a concrete element action ID.
- Single-command CLI invocations cannot share in-memory session state, so a
  persistent interactive loop (`semantic-browser portal`) is required for
  realistic local porthole testing.

### 2026-03-11 — Text Adventure Evolution

Baseline benchmark showed 0.40 success rate — identical to standard and OpenClaw
browser tooling.  Root cause: planner received the same `{url, title, text, candidates}`
JSON shape regardless of method, erasing our semantic extraction advantage.

Changes implemented (Phases A-I):

1. **Text-first room description** — `PlannerView.room_text` now holds a plain-text
   room description (LOCATION / YOU SEE / ACTIONS / BLOCKERS) instead of JSON.
   Planner input drops from ~20k tokens of JSON to ~500-2000 tokens of narrated text.

2. **Action curation** — Actions ranked by blocker-dismissal > input fields > primary >
   viewport-visible, hard capped at 15 in the room description. No more 100-candidate
   phone book.

3. **Progressive disclosure** — `act-see-more` escape hatch always available.  LLM
   can request expanded view when the curated set doesn't contain what it needs (e.g.
   deep content pages, filter controls, pagination).

4. **Content narration** — `what_you_see` now derived from visible headings (h1-h3),
   nav labels, content group previews, form names — not meta-stats like "4 regions".

5. **Fast-path extraction** — When ARIA quality >= 0.7, skip DOM stats, heavy grouping,
   and page classifier.  Target 200-500ms extraction vs prior 1-3s.

6. **One-token action responses** — Benchmark planner prompt expects a bare action ID
   (e.g. `act-3-ab12cd`), not JSON.  Eliminates fuzzy matching failure mode.

7. **Narrative history** — Step history as prose ("Step 1: Clicked 'News'. Navigated
   to BBC News.") not stringified JSON dicts.

8. **Task harness** — 25 tasks across 5 categories (navigation, search, multi-step,
   content, interaction, resilience, speed) on real public sites.
   `scripts/task_harness.py` runnable via OpenClaw.

## Lessons

- Sending the same data shape as competitors means the planner makes the same
  decisions.  Format differentiation IS competitive differentiation.
- LLMs parse prose faster and cheaper than JSON.  Every `{` and `"` is wasted tokens.
- Action curation with an escape hatch (see_more) is strictly better than dumping
  everything — it guides the common case while preserving autonomy.
- Narration beats statistics: "BBC News homepage with headlines" >> "article page with
  45 actions, 4 regions".

## Notes

- The spec explicitly prioritises **honest failure** over fake confidence.
  This should be reflected in code reviews: if a heuristic is flaky,
  prefer returning low confidence rather than guessing.

- The project is deliberately **Chromium-only** for v1. This is a feature,
  not a limitation. One good path > three partial ones.

- The `[managed]` vs `[core]` package split means extraction logic must
  not import Playwright directly — it should receive page state as data,
  not hold references to Playwright objects. This needs careful interface
  design in Phase 1.
