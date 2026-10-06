# Scratchpad

## Lessons

### Headless vs Headful Browser Detection (2026-04-06)
- Paddy Power (and likely many other betting/gaming sites) detects headless browsers and redirects to a stripped-down page or blocks access entirely.
- Always use `headful=True` when validating against sites with bot detection.
- The initial v1.3 validation incorrectly attributed the redirect to geo-blocking when it was actually headless browser detection.

### Playwright `get_by_placeholder` Can Match Custom Element Wrappers (2026-04-06)
- `page.get_by_placeholder("0.00")` matched `<sbk-input placeholder="0.00">` (a custom element) instead of the actual `<input>` inside it.
- Playwright's `fill()` fails on custom elements with "Element is not an `<input>`, `<textarea>`, `<select>` or `[contenteditable]`".
- Fix: for `<input>`/`<textarea>`/`<select>` elements, prefer the sanitized CSS selector (which directly targets the real element) over ARIA-based methods that might resolve to wrapper components.
- If `get_by_placeholder` must be used, verify `tagName` matches the expected element type.

### Angular State Classes Are Volatile (2026-04-06)
- AngularJS injects state classes like `ng-pristine`, `ng-untouched`, `ng-valid`, `ng-empty` that change the moment an input is interacted with.
- CSS selectors captured during extraction include these classes but they become invalid after any interaction.
- Solution: strip these volatile classes from CSS selectors during locator resolution using a regex-based sanitizer.

### Side-Effect Blockers Cause False Classification (2026-04-06)
- Clicking an odds button to add a bet opens a betslip panel that contains `role="dialog"`.
- The dialog detection in `detect_blockers` flagged this as a new modal blocker.
- `classify_status` checked `added_blockers` before `changed_values`/`changed_regions`, so the action was classified as "blocked" even though it succeeded.
- Fix: only classify as "blocked" when there are added blockers AND no other positive effects.

### Dialog Blocker Needs Visibility + Size Check (2026-04-06)
- Many modern SPAs have `role="dialog"` elements in the DOM that are small panels, not blocking modals.
- The betslip on PP has `role="dialog"` but is a small side panel, not a page-blocking overlay.
- Fix: check that dialog elements are visible, in viewport, and cover >30% of the screen before flagging as a modal blocker.

### v1.4 dogfood lessons (2026-10-06)

- **A test can encode a bug.** `test_fallback_to_body_when_no_recipe` asserted the very behaviour that made clicks "succeed" on `<body>`.
  When a review finding contradicts an existing test, change the test and say why in its docstring.
- **URL-glob request blocking is unsafe.** `*.png?*` matched Wikipedia's `load.php?...` CSS/JS and broke the page (caught by the real-site
  benchmark, not by unit tests). Block by CDP resource type (`Fetch.enable` with `resourceType`) and allow-list captcha providers.
- **"Busy indicator" heuristics must require motion.** Matching `[class*=loading]` made GitHub wait 3.5 s forever; requiring a running CSS
  animation / `aria-busy` / `progressbar` cut it to 94 ms. Always benchmark a heuristic on real sites, not just the fixture it was written for.
- **Ref numbers must be monotonic per session.** Resetting to 1 on every document let `click 3` from a previous page hit a different
  element on the next one. Never reuse a number.
- **Do not override `HOME` in tests.** Playwright finds its browsers via `~/Library/Caches/ms-playwright`; the fixture silently skipped all 16
  integration tests. Look at the *skipped* count, not just "passed". Use `SB_HOME` for output dirs.
- **CDP attach picks an existing tab.** Attaching to a live, logged-in profile must open its own tab and close only that one.
- **AF_UNIX paths max out at ~104 bytes on macOS.** Long `$HOME`/`SB_HOME` need a short fallback dir (tested).
- **`.venv/bin/pip` pointed at Python 3.14 while tests run on 3.12.** Use `.venv/bin/python -m pip`.
- **Benchmark oracles can be wrong too.** `^Football$` failed because duplicate labels get a context suffix; check whether the product or the
  oracle is at fault before "fixing" either. Same for fixture bugs (unquoted SVG attributes lost the red fill).
- **Do not run shells with `-x`/xtrace.** It echoed an exported secret from `~/.zshenv` into the log. Debug with `echo`/`set -e` instead.
- Playwright returns big structured objects slowly; `JSON.stringify` in the page + `json.loads` was ~3x faster for the snapshot.
- Raw Playwright is *fast* (~200 ms) but hands the model 5–120 k tokens per step; the product is tokens-to-decision, not browser speed.
