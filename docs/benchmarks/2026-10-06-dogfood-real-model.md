# Dogfood with a real model — round 1 → 3 (2026-10-06)

> **Historical report (measured on 1.4.0 - 1.5.0).** Current figures, re-run on 1.7: [v1.7 suites](2026-10-06-v1.7-suites.md) and [competitor comparison](2026-10-06-competitors-v1.7.md).

The earlier report ([2026-10-06-dogfood-v1.4.md](2026-10-06-dogfood-v1.4.md)) used a **scripted oracle** as the model. This one is the real thing: the
tool was driven by **Claude Sonnet 5.5 (Cursor agent)**, one command per call, seeing only what `sb` printed, on live sites, with every call timed and
journaled by `scripts/dogfood/sbj.py`. Typed text is redacted from the committed journals.

## Method

- Driver: me, as the model. No scripts choosing locators; verdicts are my own and are recorded with a note (`sbj.py --done`).
- Metric per task: **calls** (one `sb` invocation; a `do` batch is one call), tool time, tokens read (output chars / 4), and my verdict.
- Browser: headless Chromium (own tab), except sites that needed the logged-in `mia` Chrome (attached over CDP, own tab only) and Reddit (headful tried).
- Safety: gated sites (Paddy Power, Gmail) were read-only: no bets, no messages, Gmail counts only. No production anti-bot gate was solved; Google's
  public reCAPTCHA demo is the only CAPTCHA attempted.
- Machine: macOS arm64, Python 3.12, Playwright 1.58, single run per task (these are live sites; there is no repetition, so read the numbers as
  indicative, not statistical).
- Raw journals: `raw/2026-10-06/real-model-r1.jsonl` (v1.4.0 as first built), `-r2.jsonl` (mid-way), `-r3.jsonl` (final code = 1.5.0).

## Results

| Round | Code | Tasks | Completed | Median calls | Median tokens read | Notes |
|---|---|---:|---:|---:|---:|---|
| 1 | 1.4.0 | 13 | 11 (1 partial, 1 blocked) | 4 | ~2.7k | found the bugs below |
| 2 | mid-fix | 10 + CAPTCHA | 6 + 1 partial | 5 | ~3.0k | Reddit ×3 and Hacker News blocked/rate-limited; CAPTCHA 3 rounds accepted |
| 3 | 1.5.0 | 7 | 7 | 1 | ~0.26k | uses `do` batching; includes one slip of mine (below) |

Round 3 is not "the same tasks, faster": several tasks differ and `do` collapses many steps into one call. What it does show is that the flows that
failed or were awkward in round 1 now complete, in one or two calls.

## What I hit, and what changed

| # | Found while dogfooding | Severity | Fix (tests added first) |
|---|---|---|---|
| 1 | Amazon price `£5.69` shown as `£569` (the visual decimal is `opacity:0`; the real text is an `opacity:0` sibling) | **wrong data** | accessible-twin rule in `snapshot.js` (off-screen, 1px, or `opacity:0` twin of an `aria-hidden` fragment) |
| 2 | GOV.UK radios/checkboxes had no `[n]` (transparent input over label) so a form wizard could not continue | **blocker** | transparent radios/checkboxes are controls; repeated label printed once |
| 3 | jQuery UI datepicker Prev/Next were plain text (`<a data-handler data-event=click>`, no href) | **blocker** | framework handler attributes recognised on href-less anchors; delegating `<td>` wrapper not a 2nd control |
| 4 | Guardian: dismiss hint pointed at a dead control, then at "Continue" (a donation flow) | misleading | ranking: close/reject > short accept; never sign-in/subscribe/pay; honest "no obvious dismiss control" |
| 5 | `view --all` advertised but silently ignored; `find` blind behind an overlay | misleading | wired; unknown options now an error; `find` uses the whole page |
| 6 | `find` on a table row showed the wrong "header" (the `World` total row) once first attempted | wrong data | only real `<th>` rows count; no header → none shown |
| 7 | Three "Sport" links → "ambiguous" with no way to tell them apart | friction | candidates show their destination; same destination resolves |
| 8 | False `covered` on stretched-link cards; link repeated | noise | same-href hit is not covered; repeats folded |
| 9 | Blank table cells dropped (columns shifted) — then Hacker News spacer cells got noise | wrong/noise | placeholders only in tables that have `<th>` |
| 10 | Click whose only effect was the page title was "no visible change" | misleading | title change reported; no grace wait |
| 11 | CAPTCHA: image after `submit` was mid-fade; "probably wrong" for dynamic grids | misleading | wait for ~1 s of stillness; explanatory message |
| 12 | Stale background daemon ran old code after edits/upgrade (twice) | friction | `sb` detects and restarts; says so |
| 13 | Daemon start failure printed a traceback head | friction | root-cause line + fix hint |

## Round-3 tasks (final code)

| Task | Calls | Tool ms | Result |
|---|---:|---:|---|
| Amazon: find the first cable's price | 1 | 6,043 | `£5.69 (£2.85/count) RRP: £7.99`, decimals right |
| GOV.UK visa checker, 8 steps | 1 | 5,431 | "ETA or Standard Visitor visa" (Japan, tourism) |
| Guardian: consent → Sport (hint followed literally) | 3 | 6,728 | overlay cleared with the suggested control |
| jQuery UI datepicker → 25 Dec 2026 | 2 | 7,043 | input value `12/25/2026` (header row confirmed Friday column) |
| Wikipedia GDP table row + columns | 1 | 4,306 | row with `Country/Territory \| IMF \| World Bank \| UN` |
| Paddy Power EPL fixtures (read-only, logged-in profile) | 1 | 5,142 | fixtures and odds found |

Honest notes on round 3: the `f2` journal entry contains a slip of mine (I typed a ref number from a previous session; refs are per-session, and the
hint said otherwise). The clean run is `f2b`. Tool time is dominated by real page loads, not by `sb`.

## Round 4 (v1.6 candidate, run by hand, not through `sbj.py`)

Seven fresh tasks driven from the new agent guide only, one command per call unless `do` is noted. Single run each, one machine.

| Task | Result |
|---|---|
| GitHub repo page → licence | found; `find MIT` buried it under "commit" (fixed: whole-word first) |
| httpbin pizza form, 5 steps in one `do`, submit | all values reached the server correctly (size, toppings, name, comments) |
| DuckDuckGo search | search box printed like a link (fixed); then DDG served a human-check mask: now flagged as a bot page |
| Wikipedia infobox fact; Wikipedia search | found via `find`; search went straight to the article |
| books.toscrape category prices | `find £` returned bare prices (fixed: carries the title) |
| BBC News front page | inline cookie banner with reject control visible; headlines read |
| PyPI project page | Fastly "Client Challenge" (external); now flagged with the right next step, `sb captcha` detects it, not attempted |

## Not solved / blocked (reported, not hidden)

- **Reddit** served its human-verification gate in headless, headful *and* the logged-in `mia` Chrome from this IP. It is an IP-level decision; the tool
  reports the gate plainly (and `sb captcha` can describe it) but I did not attempt to defeat a production anti-bot gate.
- **Hacker News** returned "Sorry" (rate limit) after repeated runs from one IP. Not a tool fault.
- **CAPTCHA demo**: three rounds accepted, then Google escalated (4×4 "stairs"); I stopped. Provider acceptance is not claimed as a success metric.
- Page-load speed is bounded by the page: `sb` median ~0.3 s warm vs 36 ms for raw `httpx` (which does not run JS) — see the v1.4 report.
