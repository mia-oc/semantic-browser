# Technical Spec (v1.4)

## 1. Snapshot (`extractor/snapshot.js`)

One `frame.evaluate` per frame returns `JSON.stringify({gen,title,url,ready,scroll,nodes,flow,layer,frames,stats})`.

* `flow` tokens (reading order): `['t',text] ['b',y] ['h',level] ['H'] ['r',kind,name] ['R'] ['li'] ['c'] ['e',ref,y] ['f',idx,title,src]`.
* `nodes[]`: `{ref, kind, op, name, ctx?, rect, in_viewport, covered?, disabled?, value?, options?, checked?, href?, click_proxy?, frame_id}`.
* Walk pierces **open** shadow roots; iframes are captured by separate per-frame evaluates (so cross-origin works),
  ≤8 frames, depth ≤2, 4 s each.
* Visibility: `checkVisibility()` plus `display: contents` handling; `aria-hidden`, zero-size, off-canvas culled.
* Clickable-div heuristics: `onclick` prop/attribute, `tabindex`, `cursor:pointer` whose parent is not pointer,
  custom elements with interactive roles. `body/html` are never clickable; containers wrapping real controls aren't.
* Hidden checkbox/radio: the visible `<label>` is used as `click_proxy`.
* Occlusion: `elementFromPoint` (shadow-aware) at the centre; `covered` when the hit target is unrelated. A *blocking
  layer* = fixed/sticky ancestor of ≥2 centre-row hit points covering ≥15 % of the viewport.
* Duplicate labels get `ctx` (nearest distinguishing heading/row text).

## 2. Refs (`RefTable`)

Global integers → `(frame, local_id, gen)`. Reset when the main-frame `gen` changes. Fingerprint
`frame|op|kind|name|ctx|href#ordinal` lets a re-rendered element keep its number. Executor resolves with `RESOLVE_JS`
(`window.__sb.els.get(id).deref()`), so actions use the exact element handle.

## 3. Settle (`extractor/settle.py`)

`fast_settle` = in-page MutationObserver quiet window (`quiet_ms`=80; watches childList + class/hidden/open/aria-*/style/disabled)
+ `NetTracker` (in-flight document/xhr/fetch/script/stylesheet/other; ignores image/font/media/websocket; entries older
than 4 s ignored) + a busy-indicator heuristic (`aria-busy`, progressbar, spinner/skeleton/loading classes, bare
"Loading…" text; ≤60 checks, ≤3.5 s). Caps: action 2500, navigation 5000, observe 800 ms. `settle.mode="legacy"` keeps the
v1.3 four-loop settle (used with fake pages in unit tests). **Grace**: after click/open/toggle/press/submit that changed no
non-input line, wait `grace_ms`=350 (cap 700) once more.

## 4. View (`extractor/view.py`)

Line builder with region collapsing (nav/footer/header/aside), inline `[n]` elements, headings `#`, list items `- `, table
cells ` | `, frames `⟦frame: title⟧`. Overlay mode shows only the blocking layer. Windowing by character `budget`
(default 5000, `--budget`/`extraction.view_budget`); `all_lines` keeps the entire page for `find` and diffing.

## 5. Verb layer (`agent.py`) and daemon

`AgentSession.run(str|list)` → text. Verbs map to `ActionRequest`s (`click`→`action_id`, `type`→`op=fill`,
`select`→`select_option`, `check`→`toggle`, `hover`, `press`, `scroll`, `wait`) or direct runtime calls (`goto`, `back`,
`tabs`, `shot`, `captcha`). Ref `op` overrides are limited to `{hover,press,click,scroll_into_view}`.

Daemon protocol: newline-delimited JSON over `~/.semantic-browser/run/<name>.sock` (falls back to a short
`/tmp/sb-<uid>/run` when the path would exceed the 104-byte AF_UNIX limit):
`→ {"argv":["click","7"]}` `← {"ok":true,"text":"…","ms":123}`. One lock serialises commands per session. Idle exit 900 s.

## 6. CAPTCHA (`captcha.py`)

`detect(page)` → `Challenge[]` (provider/kind/frame). `annotate` injects `#__sb_cap_marks` badges + `data-sb-tile`
attributes in the challenge frame, crops a PNG (viewport-clamped), optionally a JPEG→PDF via a 60-line writer, then removes
the badges. `select_tiles`, `type_text`, `open_checkbox`, `submit`, `refresh` act through frame locators.

## 7. Lite (`lite.py`)

CDP `Network.setBlockedURLs` (extension patterns for media/fonts; tracker host patterns for `max`) + a DOMContentLoaded
no-animation stylesheet. Per page, best-effort; lifted by `captcha`.

## 8. Compatibility

`Observation`, `ActionDescriptor` (+`ref`,`kind`,`context`,`value`), `StepResult` (+`outcome`) are additive.
`RuntimeConfig.extraction.engine="legacy"` selects the v1.3 extractor. `PlannerAction.id` is `str(ref)` under v2;
legacy `act-*` ids still resolve under `legacy`.
