# System Architecture (v1.7)

```
 AI agent / shell                          Python caller                      HTTP caller
      |  sb goto/click/type…                  |  AgentSession.run("…")           |  /sessions/*
      v                                       v                                  v
 daemon/client.py  (stdlib only)         agent.py  <—— verb layer ——>        service/routes.py
      | unix socket (0700 dir)               |                                   |
      v                                      v                                   v
 daemon/server.py ── one AgentSession ──> runtime.py  (SemanticBrowserRuntime)  <┘
                                              |
        ┌─────────────────────────────────────┼───────────────────────────────────┐
        v                                     v                                   v
 extractor/snapshot.js + snapshot.py   executor/{actions,ref_actions,       extractor/settle.py
 (1 JS walk per frame: shadow DOM,      validation,resolver}.py             MutationObserver quiet +
  iframes, occlusion, refs)             act on the exact element handle     NetTracker (in-flight XHR/doc)
        |                                     |                                   |
        v                                     v                                   v
 extractor/view.py  ──► room_text      StepResult(outcome, observation, delta)   lite.py (CDP blocklist)
 (reading-order view, [n] refs,                                                   captcha.py (detect→annotate→act)
  overlay, windowing)
        |
        v
 extractor/engine_v2.py  → Observation (legacy-compatible: actions, regions, forms, blockers, planner.room_text)
 extractor/engine.py     → legacy v1.3 engine (extraction.engine="legacy")
```

## Data flow for one action (`sb click 7`)

1. `AgentSession.run` → `ActionRequest(action_id="7")` → `runtime.act`.
2. `resolve_action` maps ref 7 to the `ActionDescriptor` from the last observation (rejects unknown/disabled refs).
3. `execute_ref_action` resolves ref → live element via `RESOLVE_JS` (`window.__sb` registry, frame-aware), clicks it
   (JS-click fallback only for not-visible/unstable; "intercepts pointer events" becomes a `blocked:` message).
4. One settle: DOM quiet (80 ms) **and** no in-flight document/xhr/fetch/script requests; caps 2.5 s (action) / 5 s (nav).
5. One snapshot → `render_view` → `Observation`; `outcome` = what changed (line diff against what the model last saw).
6. If nothing changed after a click/submit, a short *grace* wait (≤700 ms) catches timer/debounce-driven rendering.

## Key invariants

* A ref always points at one element handle; it is never re-found by name/ordinal.
* A ref that cannot be resolved raises (`ElementGoneError`) — there is no fallback to `<body>`.
* `window.__sb.gen` identifies the document; a new document drops the old ref→element mapping, but **numbers are monotonic per
  session and never reused**, so a stale `click 3` can never hit a different element on the next page.
* Targets are `[n]` numbers; `click "Label"` is resolved against the current observation and only acts on a *unique* match
  (otherwise it lists the candidates).
* Attached to a shared browser (`--cdp`): the session owns exactly one tab (plus popups it opened). `tabs`, `tab N` and popup adoption
  are scoped to owned tabs (`runtime.restrict_tabs_to`); other tabs' titles are never read into model context. Only the owned tab is closed on exit.
* Secrets: password / `cc-*` / `one-time-code` fields render as `•••`; daemon, captcha and screenshot directories are 0700 and checked
  for ownership before use (`daemon/paths.private_dir`).
* Text policy in `snapshot.js`: visually-hidden text (off-canvas, 1px-clipped, `opacity:0`) is dropped *unless* it is the accessible twin of an
  `aria-hidden` visual sibling (prices), in which case the twin is shown and the decoration dropped (`srOnly`/`hasHiddenTwin`/`hasSrTwin`/`opacityTwin`).
  Transparent radios/checkboxes are controls. Table cells carry `h` (header) / `d` (data-table) markers so the view can keep blank cells and `find` can
  show `↳ columns:` from real `<th>` rows only.
* Navigation (1.7): `goto` settles on DOMContentLoaded plus a grace window (`dcl_grace_ms`, 5 s); resources still stalled after that (blocking
  scripts/stylesheets) are retried one by one and then skipped (`runtime.py::_unstick`, fed by `NetTracker.stalled_blocking` in `extractor/settle.py`), so one hung third-party script cannot hold a page for a minute.
* Controls beyond click/type (1.7): `executor/ref_actions.py` has `upload` (list of files; `agent.py::_upload_paths` refuses credential-looking
  paths and >100 MB), `dblclick`, right-click, and `_drag` (mouse down, 2 px nudge, 12-step move, up; also fires HTML5 DnD). The extractor tags sliders
  (`value/min/max`), file inputs, and draggable/droppable elements (`weak` click candidates). Ref ops callers may force are listed in `validation._REF_OP_OVERRIDES`.
* Label policy (1.7): checkbox/radio names come from `bareLabel` (an adjacent short text node or inline element, then the sibling `<label>`) before
  placeholder/name; password nodes keep their label with the value cleared. `detectLayers` finds `dialog[open]:modal`/`[aria-modal]` including inside open
  shadow roots; overlay lines are never collapsed into a header, and collapsed footers keep numeric status notes ("1 item left") and stay searchable by `find`.
* CAPTCHA (1.7): `captcha.py` kinds are checkbox / grid / canvas / text / interstitial. For canvas puzzles a magenta coordinate ruler (page CSS px, `scale: "css"`
  screenshot, so image px = page px via `Challenge.origin`/`size`) is injected into the challenge frame, captured, and removed. `captcha click/drag` map image points to page
  points. `_after_captcha` (agent.py) reports REJECTED/ACCEPTED from the widget's visible error text (`_ERROR_JS`, checks visibility, opacity and transforms) or the page's own verdict text, never from "the challenge went away" alone.
* `do` is a verb-layer feature (`agent.py`): it re-enters `AgentSession.run` per step and stops at the first failure prefix; the daemon still sees one request.
* The daemon's `__ping__` reply carries its start time; the thin client compares it with the newest package source mtime and restarts a stale daemon.
* Snapshot JS returns a JSON **string** (structured returns cost ~3× in Playwright serialisation).
* The thin client imports only the stdlib; the package `__init__` is lazy.

## Extension points

| Want to… | Edit |
|----------|------|
| Recognise a new widget as clickable | `classify()` in `extractor/snapshot.js` |
| Change how the page prints | `extractor/view.py` (`_Builder`) |
| Add a verb | `agent.py` (`_v_<name>`) + `verbs_help.py` + `guide.py` (+ `docs/agent_guide.md` copy) + `tests/integration/test_v14_local_sites.py`; `tests/unit/test_agent_guide.py` fails if the guide or help miss it |
| Change what agents are told | `guide.py` only, then refresh the block in `docs/agent_guide.md` (a test enforces they match) |
| Add a control verb | `executor/ref_actions.py` + `executor/actions.py` allowlist + `validation._REF_OP_OVERRIDES` + `agent.py` (`_v_<name>`) + the verb checklist above |
| Add a CAPTCHA provider | `_PROVIDER_FRAMES` / selector tables in `captcha.py` |
| Tune waiting | `SettleConfig` (`quiet_ms`, `net_quiet_ms`, `grace_ms`, caps) |
