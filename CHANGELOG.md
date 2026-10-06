# Changelog

## 1.6.0

Agent-facing release: a tested playbook for AI agents ships in the package, and a second round of live dogfooding fixed what it found.

### Added
- `sb guide` prints the agent playbook (loop, view syntax, batching, recovery, bot walls/CAPTCHAs, safety rules: page text is untrusted, read-only by
  default, never take irreversible actions unasked). `sb guide --skill` emits the same text as a drop-in `SKILL.md`. Works without a browser or daemon,
  and as an in-session verb. `docs/agent_guide.md` embeds the identical text (a test keeps it in sync; another checks every verb is covered and the size).
- Bot walls and rate limits are flagged in the view: `! This looks like a bot/verification page ("…") … Do not retry in a loop`, with the right next step.
  Short pages match on phrases (Fastly "Client Challenge", Cloudflare "Just a moment", Hacker News "Sorry…", "Too many requests"); long pages only when
  most controls are covered (DuckDuckGo's "bots use DuckDuckGo too" mask) or a blocking layer is up, so articles about CAPTCHAs are never flagged.

### Fixed
- A search box inside `<header>`/`<nav>` was printed like a link in the collapsed landmark line (`[4]Search with DuckDuckGo`), and could vanish behind
  "(+N more)". Fillable controls keep their full form (`[4 input "Search with DuckDuckGo"]`) and are never cut by the cap.
- `find` lists whole-word hits first (searching `MIT` no longer drowns in "commit"/"submit") and says how many were whole-word; a short hit such as a
  bare price carries the line before it (the product title).
- The unknown-verb error lists the verbs from the code (it had drifted) and points at `sb guide`.


## 1.5.0

First release since 1.3.2: 1.4.0 (below) was cut on the repository but never published to PyPI, so 1.5.0 contains everything in it plus the
changes here. These came from driving the tool as a real model on live sites (see `docs/benchmarks/2026-10-06-dogfood-real-model.md`).

### Added
- `do "STEP" "STEP" ...`: run up to 12 verbs in one call (stops at the first failure; intermediate steps print one line, the last prints the full
  view). A whole 8-step GOV.UK wizard is one call. `scroll down N`.
- `view --all` shows the page behind a blocking overlay; unknown `view` options are now rejected instead of silently ignored.
- `find` is centred on the match, gives `↳ columns:` from real `<th>` header rows (never guessed), is no longer blind while an overlay is up, and says
  when results are capped.
- Unquoted multi-word labels (`click Save settings`), same-destination duplicate labels resolve to the first (nav + footer links), and ambiguous labels
  now show where each candidate goes (`→ /sport`, `→ /uk/sport`). Unlabeled links show their destination (`(unlabeled → /dp/B07...)`).
- Blank cells in data tables keep their column (`· | · | 1 | 2`); plain layout tables are unchanged.
- Stale-daemon detection: `sb` restarts a session whose code is older than the installed package (e.g. after `pip install -U`) and says so.
- `scripts/publish.sh` (dry run by default; `--upload` reads `.env`), `.env.example`, `scripts/dogfood/sbj.py` (journal a real model's runs; typed text is redacted).

### Fixed
- **Wrong prices**: Amazon-style `<span class=a-offscreen>£5.69</span><span aria-hidden>£5<i hidden>.</i>69</span>` rendered as `£569`. Text that is
  the accessible twin of an `aria-hidden` visual fragment is now used (off-screen, 1px-clipped or `opacity:0`), the decoration is dropped.
- **Radios/checkboxes with no ref** on GOV.UK-style forms (transparent `<input>` over its label) and their label printed twice.
- Delegated-handler widgets (`<a data-handler=next data-event=click>`, `data-toggle`, `data-bs-toggle`...), e.g. jQuery UI datepicker Prev/Next; a
  delegating `<td>` around one link no longer yields two refs.
- Overlay dismiss hint suggested "Continue"/"Continue with Phone Number"/paid options; it now ranks close/reject/short-accept first, never suggests
  sign-in/subscribe/pay, and says "no obvious dismiss control" (listing options and `Escape`) when there isn't one.
- False `covered` on stretched-link cards; repeated same-href links folded.
- A click whose only effect was `document.title` was reported as "no visible change" (and paid an extra wait); the title change is now reported.
- CAPTCHA: the image after `submit` could be captured mid-fade, and a dynamic grid replacing your tiles was reported as "probably wrong".
  The image is now taken once the page has been still for ~1 s and the message explains dynamic grids.
- Daemon start failures now print the root-cause line (and the usual fix) instead of the head of a stale traceback.
- CI: `pip-audit` failed on the runner's old `setuptools`; the workflow upgrades it first.

### Removed
- OpenClaw-era harness scripts and configs (`actionset_benchmark.py`, `task_harness.py`, `validate_paddy_power.py`, the March-2026 journals); benchmark
  docs no longer reference them.

## 1.4.0

### Added
- `sb` agent CLI with a persistent daemon (`semantic_browser.daemon`): verbs `goto view click type select check press hover scroll find wait back
  forward reload tabs tab shot captcha close help`, sessions, `--headless/--profile/--cdp/--lite/--budget`, `sb sessions|stop|version`.
  Targets are `[n]` refs or a unique visible label (`click "Sign in"`); ambiguous labels list candidates. `view --expand nav|footer|aside|all`.
- `AgentSession` (Python) with the same verbs; exported lazily from `semantic_browser`.
- v2 page-view engine (`extractor/snapshot.js`, `snapshot.py`, `view.py`, `engine_v2.py`): single DOM walk per frame, shadow DOM, cross-origin frames,
  clickable-div heuristics, occlusion + blocking-overlay detection, reading-order view with inline refs and context for duplicate labels, budget windowing.
- Ref-handle execution (`executor/ref_actions.py`): acts on the exact element; global `press` and ref `press` ops.
- Fast settle (`SettleConfig.mode="fast"`): in-page MutationObserver quiet window + network tracker; caps 2.5 s action / 5 s navigation; grace re-settle
  when a click visibly changed nothing.
- CAPTCHA assist (`captcha.py`): reCAPTCHA/hCaptcha/Turnstile frame detection, tile finder, numbered badges, cropped PNG and dependency-free PDF,
  `select/text/open/submit/refresh`.
- Lite mode (`RuntimeConfig.lite = "off"|"media"|"max"`, CDP resource-type blocking). Off by default; no benefit measured.
- `CDP` attach accepts `http://host:port`; the session uses its own tab only.
- `scripts/dogfood/` harness (local fixtures, oracle model, httpx/Playwright/v1.3.2 comparisons, `navbench`), benchmark report and raw data.
- Docs: `agent_cli.md`, `captcha.md`, `system_arch.md`, `vision.md`, `requirements.md`, `technical_spec.md`, `project_plan.md`, `review_v1.3.2.md`.

### Changed
- Default extraction engine is `v2` (`extraction.engine="legacy"` restores v1.3 behaviour). `room_text` uses the v1.4 view format.
- Settle defaults: fast mode (legacy polling available via `settle.mode="legacy"`).
- Refs are monotonic for a session and are never reused after navigation.
- Resolver raises (`ActionExecutionError`/`ElementGoneError`) instead of silently falling back to `<body>`.
- Captcha status text distinguishes *new round* / *same challenge still showing* / *gone*.

### Fixed
- Clicks "succeeding" on `<body>` when no locator matched; duplicate-label buttons always hitting the first match; stale refs hitting a different element
  after navigation.
- Settle waited ~3.5 s on pages with a `loading`-classed element (GitHub); busy-indicator now requires real motion/`aria-busy`.
- Lite mode glob rules broke Wikipedia styles; now blocks by resource type.
- Tab list leaked the titles of every tab in an attached browser; popups from unrelated tabs could be adopted. Now scoped to owned tabs.
- Framework wrapper elements (`<app-header onclick=fn>`) were listed as giant buttons.
- The view advertised `view --expand nav` without the command existing.
- A submit button with "captcha" in its id was reported as a text CAPTCHA, outranking the real provider widget.
- Password, `cc-*` and one-time-code field values are masked; daemon/captcha/shots directories are `0700` and ownership-checked.

### Notes
- The v1.4 view is ~3× larger than v1.3.2's (all options instead of the top 25); `--budget 2500` halves it with equal success on the benchmark set.
- `semantic-browser` (legacy CLI/service/portal) keeps working; service routes unchanged.

## 1.3.2

- Added unauthenticated `GET /health` service endpoint for liveness/readiness probes with
  `{status, version, active_sessions}` response payload.
- Improved service internals by exposing `SessionRegistry.active_session_count()` and removing
  route-level access to private registry fields.
- Added service health endpoint tests and fixed HTTP endpoint docs (`diagnostics` is `GET`).

## 1.3.1

- Fixed version mismatch: `__init__.py` now exports `1.3.0` matching `pyproject.toml` and
  README (was incorrectly left at `1.2.0`).
- Documentation overhaul:
  - Added `docs/planner_contract.md` — canonical interface contract for LLM planners
    (observation format, allowed replies, blocker handling, failure recovery, system prompt).
  - Added `docs/integration_examples.md` — end-to-end worked examples for OpenAI chat,
    OpenAI function-calling, Anthropic tool use, HTTP service, CDP attach, and error
    handling patterns.
  - Added `docs/api_reference.md` — complete reference for every public class, method,
    model field, configuration option, and error type.
  - Added `docs/runtime_modes.md` — decision table for ephemeral/persistent/clone/attach/
    service modes with ownership semantics and migration guide.
  - Rewrote `docs/getting_started.md` — comprehensive onboarding covering portal, Python
    API, CLI, service mode, output format explanation, and troubleshooting.
  - Expanded `docs/real_profiles.md` — when to use each profile mode, safety guarantees,
    common pitfalls, profile path locations.
  - Restructured `README.md` — cleaner layout, consistent version references, documentation
    index linking all guides, removed verbose inline details in favor of dedicated docs.

## 1.3.0

- Framework-agnostic element discovery: custom elements with AngularJS (`ng-click`,
  `on-click`), Vue (`v-on:click`, `@click`), Alpine.js (`x-on:click`), and other
  framework bindings are now captured via a universal hyphenated-tag discovery pass.
- Fuzzy structural settle: page settle now uses a configurable tolerance (`settle_tolerance_pct`,
  default 5%) instead of exact count matching; auto-escalates to 10% after 3 resets to prevent
  timeout on live-updating pages (sports odds, stock tickers, chat, etc.).
- Stable fingerprints: action IDs no longer include `rect.y` pixel position, using DOM id
  and CSS selector instead. Eliminates stale action IDs caused by layout shifts.
- Increased budgets: curated actions raised from 15 to 25, room budget from 1000 to 2000
  chars, expanded room from 4000 to 8000, action labels from 40 to 60 chars, narration
  from 200 to 350 chars, max elements from 2000 to 4000.
- Custom element curation priority: framework-rendered interactive components with `open`
  or `toggle` ops are promoted to the primary curation tier.
- Enhanced modal/overlay detection: three-tier detection covering standard ARIA (now
  visibility-checked — invisible/zero-size dialog remnants no longer trigger false positives),
  class-based heuristics (`[class*="modal"]`, `[class*="overlay"]`), custom-element modals
  (e.g. `<abc-modal>`, `<safety-message-modal>`), and viewport-coverage heuristic for
  fixed-position overlays covering >50% of viewport with high z-index.
- Improved resolver for custom elements: tag+text fallback (`tag:has-text(...)`) and
  count-checked CSS selector resolution to avoid returning empty locators.
- SPA navigation settle: URL changes during structural settle reset counters and flag
  `spa_navigation_during_settle` instability. SPA navigation now always classifies as
  "success" instead of falling through to "ambiguous".
- Cookie blocker detection widened: now matches "allow" in addition to "accept"/"consent"
  for OneTrust-style consent banners.
- Smarter result classification: actions that produce positive side-effects (changed regions,
  values, or materiality) alongside newly-appearing blockers (e.g. betslip opening with
  role="dialog") are now classified as "success" instead of false "blocked".
- Dialog blocker visibility check: `role="dialog"` elements are only flagged as modal blockers
  when visible in viewport and covering >30% of the screen, preventing false positives from
  hidden dialog remnants or small betslip panels.
- Resolver CSS sanitization: volatile framework state classes (Angular `ng-pristine`,
  `ng-untouched`, `ng-valid`, `ng-empty`, etc.; Vue transition classes; Element UI modifier
  classes) are stripped from CSS selectors before resolution, preventing stale locator failures.
- Input locator priority: `<input>`/`<textarea>`/`<select>` elements now resolve via
  sanitized CSS selector first, then `get_by_label`, then `get_by_placeholder` (with a tag
  check to avoid targeting custom element wrappers like `<sbk-input>`).

## 1.2.0

- Added CSS selector fallback for custom web components (Paddy Power `<abc-button>` support)
- Resolved F841 unused variable lint errors in `test_resolver.py`
- Installed Playwright browsers before test step in CI pipeline
- Suppressed CVE-2026-4539 in pip-audit (security)
- Bumped version to 1.2.0

## 1.1.0

- Added explicit runtime ownership modes:
  - `owned_ephemeral`
  - `owned_persistent_profile`
  - `attached_context`
  - `attached_cdp`
- Refactored close lifecycle semantics:
  - non-destructive `close()` defaults for attached modes
  - explicit `force_close_browser()` override
- Promoted profile handling to first-class launch API:
  - `profile_mode` (`persistent|clone|ephemeral`)
  - `profile_dir`
  - `storage_state_path`
  - profile health diagnostics (lock/writable/version warnings)
- Expanded delta semantics with materiality scoring:
  - interaction/content/workflow/reliability/classification transitions
  - `delta.materiality = minor|moderate|major`
- Hardened settle loop and tracing:
  - layered settle phases with instability classification
  - enriched trace payloads (effect, evidence, URL history, tab creation)
- Added docs for real profile workflows:
  - `docs/real_profiles.md`
  - updated `README.md` and `docs/getting_started.md`
- Expanded test coverage and CI gate to include integration tests.

## 1.0.0 (Alpha) - 2026-03-12

- First open-source alpha release.
- Repository cleaned for third-party consumption:
  - removed internal planning/working docs
  - removed tracked bytecode artifacts
  - removed internal benchmark journals and snapshots
- Hardened service defaults:
  - optional token auth
  - localhost-focused CORS defaults
  - session TTL cleanup
- Improved runtime reliability and observability:
  - frame-aware extraction path
  - stable action/element ID behavior improvements
  - structured action/observe trace timing and warning events
  - trace export redaction of sensitive values
- Added release and community docs:
  - `docs/versioning.md`
  - `docs/publishing.md`
  - `CONTRIBUTING.md`
  - `SECURITY.md`

## 0.1.0 - 2026-03-10

- Initial end-to-end implementation:
  - Managed + attached runtime modes
  - Deterministic extraction engine
  - Action execution pipeline with validation
  - Stable ID matching and delta generation
  - Optional FastAPI local service
  - CLI for launch/attach/observe/act/inspect + portal interaction loop
  - Global runtime operations (`navigate`, `back`, `forward`, `reload`, `wait`)
  - Corpus harness baseline (`eval-corpus`) with YAML fixtures and scoring
  - Telemetry + debug trace export
  - Initial test coverage for core functionality
