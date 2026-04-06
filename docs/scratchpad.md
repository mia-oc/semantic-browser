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
