# Review of v1.3.2 — end-to-end, evidence-based

> **Historical review of 1.3.2.** Its numbers are not current; for 1.7 see [v1.7 suites](benchmarks/2026-10-06-v1.7-suites.md) and [competitor comparison](benchmarks/2026-10-06-competitors-v1.7.md).

Method: read all of `src/`, ran the suite (116 pass, 77 s), then dogfooded with
`scripts/dogfood/` (deterministic local fixtures + real sites) against a v1.3.2 worktree.
Raw-Playwright reference is an *idealised* oracle (perfect locator choice, no model latency).

## Headline numbers (baseline, 9 local scenarios x 2 reps)

| Method | Success | Median wall / scenario | Notes |
|---|---|---|---|
| raw Playwright (aria oracle) | 14/18 | ~0.55 s | idealised |
| **sb v1.3.2** | **8/18** | **~4.1 s** | 1.4 s per step |

Profile of one `act`: 1 774 ms total = 2 x ~790 ms settle + 167 ms execute + ~25 ms extraction.
**97 % of the latency is defensive waiting; extraction is 25 ms.**

## Weaknesses (ranked by impact on an AI user)

### A. The AI cannot see the page's content, only a list of links
1. `room_text` has a <=350-char narration + a flat action list. No body text, prices, table rows,
   search results. Fixture `search_read_price`: price never shown (0/2 `saw`). A model can navigate but
   cannot *answer* anything. This contradicts the README's "context and text options".
2. Actions are flat and context-free: HN shows `open "a-13"`, `hide`, `hide`, `628 comments` with no
   link to the story they belong to. Fixture `shop_duplicates`: six identical "Add to basket".
3. Ranking is wrong: Wikipedia donation-banner buttons (£2.75, £15…) outrank real content because `click`
   is tiered above `open`. `_extract_nav_labels` has an operator-precedence bug
   (`a and b or c`) so any button/link anywhere counts as "nav".
4. Narration contains raw newlines/ads (`LIVE\n. \n\nFrench police…`).

### B. Slowness (the product's entire reason to exist)
5. Four serial settle loops (nav, structural, behavioural, frame) + fixed 300 ms quiet = ~790 ms per call.
6. `act` settles, then calls `observe()` which settles *again*; `observe` also retries up to 3x on empty.
7. `capture_page_info` runs a full-DOM `querySelectorAll('*')` + `getComputedStyle` on every element
   to detect modals — O(n) style recalcs on large pages.
8. No resource blocking, no animation disabling -> transitions & trackers prolong settling.

### C. Correctness: silent wrong actions
9. **Ordinal bug**: IDs encode an ordinal for duplicate fingerprints but `resolve_locator` ignores it
   (`get_by_role(...).first`). Fixture proves it: clicked *Red Kettle* when asked for *Blue Mug*, and
   reported `success`.
10. **False success fallback**: `resolve_locator` ends in `page.locator("body")` -> click "succeeds"
    on `<body>`.
11. `<a>` has role `a` (not `link`) so the ARIA chain is skipped for links; falls to `get_by_text(...).first`.
12. New tabs/popups are detected (`new_tab`) but the runtime keeps observing the old page.
13. Playwright dialogs (alert/confirm) are silently auto-dismissed; the model is never told.
14. Click timeouts are 5 s and error messages don't say *what* is covering the target.

### D. Coverage gaps (invisible to the model)
15. Shadow DOM (open roots) — invisible. Fixture `shadow_login`: 0/2.
16. Cross-origin iframes (payments, captcha, embeds) skipped by design (`contentDocument`). `iframe_payment`: 0/2.
17. Clickable `div`/`span` (cursor:pointer, onclick *property*) invisible. `custom_dropdown_date`: 0/2.
18. No scroll op is ever offered; lazy/infinite content unreachable. `lazy_feed_item35`: 0/2.
19. Visually hidden checkbox/radio inputs (custom styled controls) are dropped.
20. No overlay/occlusion awareness: a cookie wall covering the page is detected by keyword only.

### E. "Operates like a CLI" is not true today
21. CLI sessions live in an in-process dict (`_sessions`). `semantic-browser launch` exits and the session
    dies; `observe --session X` in the next process says "Unknown session". Only `portal` (REPL) and the
    HTTP service keep state.
22. `observe` prints the **full JSON model** (locator recipes etc.), not `room_text` — the token-efficient
    view is not what a shell-using agent receives.
23. Heavy Python start-up per call (pydantic + click + playwright imports) — a thin client must be stdlib only.
24. IDs like `act-8f2a2d1c-0` are token-expensive and typo-prone for small models.

### F. Anti-bot / CAPTCHA
25. `captcha_like` blocker fires on the *word* "captcha" in text. No iframe/provider detection, no
    screenshot, no way to answer. Nothing to hand to a vision model.

### G. Hygiene / docs
26. `requires-python >=3.11` but system python is 3.9 (works only in the venv) — doc says nothing.
27. Docs describe the text-adventure room but not what to do when it is insufficient; no troubleshooting,
    no "which mode when" guidance; README benchmark is on a harness not reproducible offline.
28. `origin` remote points at a stale fork (46 phantom commits "ahead").
29. Full test suite takes 77 s, mostly settle sleeps.

## Where this "wouldn't make sense" to an AI (as the consumer)
- It must reply with an opaque hash ID. Numbers/short refs are cheaper and safer.
- After acting it receives the *whole* room again, not what changed.
- It can't read; it can only click. Reading is half of browsing.
- When something silently fails (body-click, wrong duplicate), nothing tells it.
- It has no way to ask "is this text on the page?" (`find`) or "show me the picture" (`shot`).
