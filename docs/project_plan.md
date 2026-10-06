# Project Plan — v1.4 "Dogfood overhaul" → v1.5 "Real-model dogfooding"

North star: an AI agent should drive a real browser **as fast and as cheaply as a CLI**,
with the page's *content and its options in one compact view*, and a path through
bot-gates (CAPTCHA) that hands the hard part to a vision model.

Status legend: `[x]` done · `[ ]` open

## Phase 0 — Repo hygiene
- [x] Reconcile local vs remote. `origin` is a stale fork (`mia-oc`, v1.2.0 era); canonical remote is
      `upstream` (`visser23/semantic-browser`). Local `main` was 0 ahead / 3 behind upstream. Fast-forwarded to v1.3.2.
- [x] Uncommitted `/health` draft was superseded by upstream's hardened version (stashed, not lost).

## Phase 1 — Review (see `docs/review_v1.3.2.md`)
- [x] End-to-end code review with measured evidence.
- [x] Docs review.

## Phase 2 — Measure (dogfood harness)
- [x] Local deterministic fixtures for classically hard patterns (`scripts/dogfood/`, 9 scenarios).
- [x] Real-site scenarios (8 live sites) incl. gated/profile sites (a logged-in Chrome profile attached over CDP, read-only: Paddy Power, Gmail).
- [x] Methods: `httpx`, raw Playwright (full aria snapshot), `sb-old` (v1.3.2 worktree), `sb-new` with option matrix (budget, lite).
- [x] Baseline numbers for v1.3.2 captured **before** fixes (and re-run for the final report).
- [x] Results: [`benchmarks/2026-10-06-dogfood-v1.4.md`](benchmarks/2026-10-06-dogfood-v1.4.md).

## Phase 3 — Fix (only keep what the benchmark proves)
- [x] F1 Fast settle (event-driven, network-aware): local suite 4.1 s -> 0.44 s median, real sites 4.5 s -> 1.4 s.
- [x] F2 Page view: content + inline numbered refs, context-disambiguated labels (27/27 local, 16/16 real).
- [x] F3 Ref-handle execution (no ordinal bug, no `body` false-success, shadow DOM + cross-origin frames); refs monotonic per session.
- [x] F4 Persistent daemon + thin stdlib CLI (`sb`), label targets, `view --expand`.
- [x] F5 Lite mode: **implemented, NOT proven** -> kept opt-in (`--lite`, default off). No speed-up measured (warm, cold, real sites).
- [x] F6 Captcha pipeline: detect -> annotated PNG (+optional PDF) -> answer by tile number/text; verified on the fixture and on Google's public reCAPTCHA demo (detection, annotation, selection, multi-round). Acceptance by real providers is not claimed.
- [x] F7 Docs rewritten around the CLI-first flow; planner contract, API reference, getting started, architecture updated.
- [x] Dogfooding fixes: tab-title privacy leak in attach mode, popup hijack in shared browsers, wrapper-element fake buttons,
      advertised-but-missing `view --expand`, captcha false positive (`type=submit` named like captcha), misleading post-submit captcha text,
      secrets masking (`cc-*`, one-time-code), private-dir ownership check for the socket fallback.

## Phase 4 — Release
- [x] All tests green (175+ passed), ruff + mypy clean.
- [x] Version bump to 1.4.0, CHANGELOG, README.
- [x] Commit, push (fork -> PR to upstream), tag. PyPI upload: see scratchpad for what the machine could actually do.

## Phase 5 — Real-model dogfooding (v1.5)
- [x] Vet the repo for OpenClaw-era harness/config; remove it (scripts, journals, docs); protocol now requires a *named* planner.
- [x] Drive the tool myself (Claude Sonnet 5.5) on live sites with a journaling wrapper (`scripts/dogfood/sbj.py`, typed text redacted).
      Round 1: 11/13 tasks, median 4 calls. [`benchmarks/2026-10-06-dogfood-real-model.md`](benchmarks/2026-10-06-dogfood-real-model.md)
- [x] Fix, test-first, what hurt: wrong prices (accessible twin), transparent radios, delegated handlers, overlay hints, `view --all`, `find`
      (snippets, `<th>` columns, behind overlays), label targets, stretched-link `covered`, blank table cells, title-only effects,
      CAPTCHA image settling, stale daemon, daemon start errors, `do` batching, `scroll N`.
- [x] Round 3 (final code): 7/7 tasks, median 1 call.
- [x] Release plumbing: `scripts/publish.sh`, `.env.example`, CI `pip-audit` fix. Version 1.5.0 (1.4.0 was never published).

## Phase 6 — Agent-facing instructions and round 4 (v1.6)
- [x] `sb guide` / `sb guide --skill` / `docs/agent_guide.md` (tests: verb coverage, size cap, safety rules, docs in sync, works with no daemon).
- [x] README: "Give it to your agent" section, accurate "How It Works" (v1.4+ engine), v1.6 notes.
- [x] Round 4 live tasks (GitHub, form, DuckDuckGo, Wikipedia ×2, catalogue, BBC, PyPI): fixed collapsed-header inputs, `find` ranking/context, gate flag.
- [x] Version 1.6.0; publish via `scripts/publish.sh --upload`.

## Follow-ups (not started; see benchmark report "Known limitations")
- Brief mode: print only changed lines after non-navigating actions.
- Fold repeated sidebar chrome after in-site navigation (Paddy Power repeats ~50 menu links before the content).
- Profile HN/Amazon latency after clicks.
- Run a *weaker* LLM (not just a frontier model) through `sbj.py` to see which verbs/messages it trips on.
- Fold promo/donation banners and the doubled rating/label text seen on Amazon/Guardian.
- Skip the grace re-settle for `check`/toggle when the element's own line changed.
- Recognise a page's inner scroll container in `[screen n/m]` (Paddy Power reports 1/1).
- Review remaining legacy-engine issues: `_extract_nav_labels` precedence, `blockers.py` modal rect key.
- Press-and-hold / slider / audio CAPTCHA verbs; hCaptcha/Turnstile verification.

## Non-negotiables
- Backwards compatible Python API (`observe/act/navigate`, `ActionRequest`, legacy `act-*` IDs).
- No hard-coded credentials. Gated-site testing is read-only (no purchases, no bets placed).
- Don't revert a change unless a benchmark shows it regressed.
