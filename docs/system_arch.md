# System Architecture (v1.4)

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
* Snapshot JS returns a JSON **string** (structured returns cost ~3× in Playwright serialisation).
* The thin client imports only the stdlib; the package `__init__` is lazy.

## Extension points

| Want to… | Edit |
|----------|------|
| Recognise a new widget as clickable | `classify()` in `extractor/snapshot.js` |
| Change how the page prints | `extractor/view.py` (`_Builder`) |
| Add a verb | `agent.py` (`_v_<name>`) + `verbs_help.py` + `tests/integration/test_v14_local_sites.py` |
| Add a CAPTCHA provider | `_PROVIDER_FRAMES` / selector tables in `captcha.py` |
| Tune waiting | `SettleConfig` (`quiet_ms`, `net_quiet_ms`, `grace_ms`, caps) |
