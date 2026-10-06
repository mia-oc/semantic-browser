# Requirements (v1.7)

## User-visible behaviour

| ID | Requirement | Verified by |
|----|-------------|-------------|
| R1 | `sb <verb>` works from separate shell invocations against one persistent browser | `tests/unit/test_v14_daemon_client.py`, manual daemon e2e |
| R2 | Each verb prints an outcome line + the resulting view (or an explicit failure prefix and exit 1) | `tests/integration/test_v14_local_sites.py` |
| R3 | Duplicate labels are disambiguated in the view; refs are stable across re-renders of the same element | `shop_duplicates`, `test_duplicate_buttons_*` |
| R4 | Shadow DOM, cross-origin iframes, div-based widgets, hidden checkboxes, hover menus are operable | local fixture suite |
| R5 | Blocking overlays are announced with a dismiss ref; clicks on covered elements fail with the covering element named | `cookie_overlay` |
| R6 | SPA / timer-driven rendering is waited for without fixed sleeps | `spa_settings`, `search_read_price` |
| R7 | Stale/unknown refs are rejected, never retargeted; no `<body>` fallback | `test_v14_refs_and_ops.py`, resolver tests |
| R8 | CAPTCHA grids/text are detected, annotated as PNG (+PDF), answerable by tile number/text | `test_captcha_grid_end_to_end` |
| R9 | Lite mode never breaks CAPTCHA images and is off by default | `test_lite_*` |
| R10 | Existing Python/HTTP API continues to work; `engine="legacy"` restores v1.3 room text | existing suite (116 tests) |

## KPIs (measured on 1.7, see `docs/benchmarks/2026-10-06-v1.7-suites.md` and `2026-10-06-competitors-v1.7.md`)

* Local hard-pattern suite: success rate and median wall time vs raw Playwright (1.7: 27/27 vs 21/27, 0.47 s vs 0.58 s).
* Real-site read-only scenarios: success, median wall time, tokens shown to the model per task.
* `navigate` and `act` latency (median, local fixtures).

## Edge cases explicitly handled

`display: contents`, `&nbsp;`-only text nodes, footnote links `[7]`, `body.onclick`, containers wrapping real controls,
`alert()` dialogs, `target=_blank` popups, `about:blank`/blank first paint, navigation destroying the JS context mid-snapshot.

## Out of scope (documented limits)

Closed shadow roots (cannot be read), press-and-hold/slider/audio CAPTCHAs (described, not performed), file downloads,
Windows named-pipe support for the daemon (unix sockets only).
