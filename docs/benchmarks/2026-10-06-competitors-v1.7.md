# Wide dogfood + competitor comparison (v1.7, 2026-10-06)

Driven by **Claude Sonnet 5.5 (Cursor agent)**: one command per call, seeing only what each tool printed, every call timed and journaled by
`scripts/dogfood/tj.py`. Each tool was driven by hand, like for like, on the same sites. No scripts picked locators.

Raw journal: `raw/2026-10-06/competitors-v1.7.jsonl` (every step; demo-site passwords replaced with `[typed]`).

## Tools compared

| Tool | Version | Paradigm |
|---|---|---|
| `sb` (this repo) | 1.6.0 + the 1.7.0 changes as they landed | numbered text view, `do` batching, labels instead of refs-only |
| `agent-browser` (`ab`) | 0.38.2 | `snapshot -i` then `@eN` refs, one verb per call |
| `@playwright/cli` (`pw`) | 0.1.22 | YAML accessibility snapshots, `eN` refs |
| `browse` (`bse`) | 0.6.1 | whole-page dumps (one task only) |
| `browser-use` | – | LLM-in-the-loop agent, a different paradigm; excluded |

## Method and honesty notes

- **Single run per task, one machine** (macOS arm64, headless Chromium, live sites). `docs/benchmark_protocol.md` asks for 3 runs and medians;
  the hand-driven tables do **not** meet that bar (the replay section below does: 3 runs, medians, raw data), so only the replay figures are the README's headline numbers (its hand-driven summary is labelled single-run). Read the numbers as indicative.
- The `sb` columns are **aggregates over all recorded steps for that task, including runs made before a fix landed**, so they overstate `sb`'s
  final cost (for instance `shop` shows 24 calls; the final run was 2 calls). Competitors were not re-run after `sb` fixes, but their journals
  also include my own slips (one `ab` success was corrected to a re-run, noted in the journal).
- Tokens = output chars / 4. Time = tool wall-clock including browser start for the first call of a session.
- `bse` was run on one task (its dumps are far larger than the others); it is not a fair full comparison.
- Gated or sensitive sites were read-only. No production anti-bot gate was solved (npm/Stack Overflow Cloudflare, Reddit, PyPI/Fastly,
  DuckDuckGo anomaly were left alone). CAPTCHAs were only attempted on vendors' own public demo pages (see below).

## Like-for-like results

| Task | Site | `sb` | `ab` | `pw` | notes |
|---|---|---|---|---|---|
| wiki: height of the Eiffel Tower | Wikipedia | ok, 1.6 s, 1.9k tok | ok, 1.4 s, 24k tok | partial, 4.8 s, 5.5k tok | `bse` ok but 765k tok; `pw` only found it by searching for the answer itself |
| hn: top story + points | Hacker News | ok, 1.7 s, 1.3k | ok, 2.1 s, 4.4k | ok, 2.0 s, 12k | |
| form: 6-step login/form | local fixture | ok, 3.1 s, 0.4k | ok, 1.6 s, 0.5k | ok, 3.4 s, 1.1k | `sb` 1 `do` call vs 10 calls |
| shop: login, 2 adds, cart | saucedemo | ok, 14 s (aggregate), 6.7k | **fail** | ok, 6.6 s, 3.1k | `ab`: 4 `click` attempts on Add to cart no-op'd silently |
| dyn: click Start, read text | the-internet dynamic loading | ok, 41 s (aggregate), 0.7k | **fail** | ok, 66 s, 0.9k | the site's own script hangs ~30 s; fixed in `sb` (see below) |
| dnd: drag A onto B | the-internet drag-and-drop | ok, 1.4 s, 0.2k | partial | ok, 4.0 s, 0.4k | `ab`: "no interactive elements" for the draggable |
| mdn: open search modal, search | MDN | ok, 6.4 s, 9.7k (aggregate) | ok, 3.0 s, 1.3k | ok, 5.6 s, 25.6k | |
| gov: UK visa-check wizard | GOV.UK | ok, 3.9 s, 2.5k | ok, 7.3 s, 17k | – | `ab` first attempt silently no-op'd on a stale ref (re-run) |
| todo: add 3, tick one | TodoMVC | ok, 7.8 s, 1.7k | ok, 3.1 s, 0.7k | ok, 7.1 s, 7.4k | checkboxes were unlabeled in all three until the `sb` fix |
| npm: package page | npmjs.com | fail | fail | fail | Cloudflare "Just a moment" for every tool (external) |

Medians over every task each tool attempted (from `tj --report`; includes the caveats above):

| Tool | Tasks | Success | Partial | Median calls | Median seconds | Median tokens / task |
|---|---:|---:|---:|---:|---:|---:|
| `sb` | 19 | 16 | 1 | 3 | 2.6 | 736 |
| `ab` | 10 | 6 | 1 | 9.5 | 3.0 | 1002 |
| `pw` | 9 | 7 | 1 | 8 | 4.8 | 3059 |
| `bse` | 1 | 1 | 0 | 9 | 5.0 | 764,983 |

Where `sb` was **not** faster: raw per-call latency on a warm page is similar for all three (50-150 ms). `ab` was quicker on `form` (1.6 s vs
3.1 s) and `todo` because each of its calls is tiny; `sb` wins by needing about a third of the calls, not by being faster per call. `sb` loses
on token cost for `mdn` versus `ab` (9.7k aggregate, dominated by the two pre-fix runs where the modal was invisible).

## Repeat runs (protocol-grade): `scripts/dogfood/replay.py`

The hand-driven table above is single-run and includes my false starts. To meet `docs/benchmark_protocol.md` (3 runs, medians, raw data), the shortest
working command sequence each tool needed was replayed 3 times per task, **cold start every run, rounds interleaved** (round -> task -> tool), headless Chromium,
same machine, 2026-10-06. Raw: `raw/2026-10-06/replay-v1.7.jsonl` (45 runs). Success = the expected answer appears in the output
(`330`, `points`, `2 items left`, both product names on the cart page, `Dropped!`). `sb` was 1.7.0 from the working tree; `agent-browser` 0.38.2; `@playwright/cli` 0.1.22.

| Task | `sb` | `agent-browser` | `playwright-cli` |
|---|---|---|---|
| wiki (Eiffel height) | 3/3 · 2 calls · 2.1 s · 1.8k tok | 3/3 · 2 · 1.8 s · 24.2k | 3/3 · 2 · 1.9 s · 87.5k |
| hn (front page) | 3/3 · 1 · 1.7 s · 1.3k | 3/3 · 2 · 1.9 s · 1.0k | 3/3 · 2 · 2.1 s · 12.0k |
| todo (3 adds, tick one) | 3/3 · 2 · 2.2 s · 0.4k | 3/3 · 11 · 2.1 s · 0.7k | 3/3 · 11 · 5.0 s · 3.2k |
| shop (login, 2 adds, cart) | 3/3 · 2 · 2.8 s · 0.5k | 3/3 · 10 · 2.0 s · 0.9k | 3/3 · 10 · 5.2 s · 3.5k |
| dnd (drag) | 3/3 · 2 · 2.1 s · 0.2k | 3/3 · 5 · 2.0 s · 0.1k | 3/3 · 4 · 2.9 s · 0.4k |
| **median of all 15 runs** | **2 calls · 2.1 s · 460 tok** | 5 · 2.0 s · 862 | 4 · 2.9 s · 3,486 |

Reading it honestly:

- **Calls and tokens favour `sb`; browser time does not.** `agent-browser` is as fast or faster per task (shop 2.0 s vs 2.8 s, todo 2.1 s vs 2.2 s): its calls are tiny, while `sb`'s first call
  starts a background browser daemon. `playwright-cli` is slower on multi-step tasks (5 s) and verbose on big pages (87.5k tokens for Wikipedia).
- `agent-browser` prints less than `sb` on the smallest pages (HN 1.0k vs 1.3k, drag 0.1k vs 0.2k) because it lists only interactive elements; it pays for that on
  content questions (Wikipedia 24.2k, since `read` dumps the page).
- The replay is **hindsight for all three tools**: refs and sequences come from the hand-driven runs. It measures what each tool costs when the model knows what to do. It does not
  measure how well a model finds its way, which is what the hand-driven table does (and where `agent-browser` failed the shop task: clicks reported `✓ Done` with no page change; the replay
  shows the same task passes with the right refs, so that failure was about discovering them from its output).
- Illustration, not a measurement: with a model turn of ~4 s the shop task is ~11 s for `sb` (2.8 + 2x4), ~42 s for `agent-browser` (2.0 + 10x4) and ~45 s for `playwright-cli` (5.2 + 10x4).
  The turn time is an assumption; the call counts are measured.
- Five tasks, one machine, three runs: indicative. Tokens = printed characters / 4.

## Sites covered by `sb` beyond the head-to-head set

BBC, GitHub, Quotes to Scrape (login + pagination), Books to Scrape, Selenium test pages, UK GOV.UK ETA wizard, Amazon UK search results
(titles, ratings, prices readable), OpenStreetMap search, YouTube (consent wall detected as a blocking overlay with its options listed),
a Wikipedia data table (`find Tokyo` returns the row), the-internet pages (upload, iframes, dynamic loading, shadow DOM),
Stack Overflow and eBay (both returned an automated-traffic block / error page; reported, not bypassed), Hacker News, npm.

## CAPTCHAs (sanctioned demos only)

| Demo | Result |
|---|---|
| Google reCAPTCHA v2 demo | solved: 8 rounds of image grids, including multi-round "dynamic" grids (new tiles replace the clicked ones) |
| hCaptcha demo | solved after adding the canvas kind (hCaptcha draws puzzles on a canvas with no DOM tiles); two attempts were rejected first, which is how the REJECTED verdict was found |
| Cloudflare Turnstile demo | completed (the demo uses Cloudflare's published testing key) |
| captcha.com BotDetect text demo | solved: read the image, `captcha text`, `captcha submit`, page said "Correct!" |

The model does the seeing (it reads the annotated image `sb captcha` writes); the tool only locates, screenshots, clicks/drags and reports
what the page said afterwards. There is no solver service and no bypass of production gates. See `docs/captcha.md`.

## Failures found, why, and the fix

Each row had at least five hypotheses listed in `docs/scratchpad.md` before a fix was chosen.

| Symptom | Root cause | Fix |
|---|---|---|
| dyn: `goto` took 50-100 s | the page's blocking `<script>`/`<link>` hung, and `goto` waited for the full load | DOMContentLoaded grace window, then retry stalled resources individually and skip them (`_unstick`) |
| shop: six identical "Add to cart" | duplicate labels with no context | duplicate labels now render `label — context` (product name) |
| `click` on an `ab`-style stale ref silently did nothing | (competitor behaviour) | `sb` verifies the page changed and says `STALE`/no-effect |
| todo: checkboxes `(unlabeled)`, radios named by prose | label text was a bare sibling text node or sibling `<label>` | `bareLabel()` in `snapshot.js` |
| todo: footer "1 item left!" gone | collapsed footer dropped its text | numeric status notes kept; hidden text stays searchable by `find` |
| mdn: search modal invisible/ambiguous | the dialog lived in a shadow root under the `<header>` that got collapsed | `detectLayers` sees `dialog[open]:modal`/`aria-modal`, scans open shadow roots; overlays are exempt from collapsing |
| up: `click` on a file input gave `[Errno 2] ... 'None'` | no file verb | `upload N PATH...` with a credential-path guard; clear error otherwise |
| slider value invisible | not extracted | `[n slider "label"="v" lo..hi]` |
| dnd: nothing draggable listed | HTML5 DnD handlers/classes not recognised | detected and `drag FROM TO` added; `dblclick`, `click --right` added |
| password shown as `[REDACTED]` label | redaction replaced the label too | label kept, value cleared |
| ad iframes polluting views | ad frames treated as content | title-based filter |
| hCaptcha: "grid 0x0, no prompt" | puzzle drawn on a canvas | canvas kind + magenta coordinate ruler + `captcha drag/click` |
| hCaptcha "accepted" while widget said "Please try again." | verdict inferred from the challenge disappearing | read the widget's visible error text; `REJECTED` verdict |
| captcha.com: verdict said "still showing" on "Correct!" | text kind had no page-verdict logic, and the `Validate` button (`input[type=button]`) was not found | page-verdict branch (ACCEPTED/REJECTED/no verdict text); broader submit-button match |

## Not fixed / external

- npm, Stack Overflow, Reddit, PyPI and DuckDuckGo anomaly pages block all tools; `sb` reports them with a "do not retry in a loop" hint.
- eBay returned its own "Something went wrong" page to headless Chromium for search; not investigated further.
- Arkose/FunCaptcha-style gated demos were not exercised.
