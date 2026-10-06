# Semantic Browser

<p align="left">
  <img src="https://github.com/user-attachments/assets/dac79ee0-6ebb-48b3-a27d-2e339ea16961" alt="Semantic Browser mascot" width="240" align="right" />
</p>

**Version 1.7.2 (Beta)** · [PyPI](https://pypi.org/project/semantic-browser/) · [Changelog](CHANGELOG.md) · [License: MIT](LICENSE)

## What is it? (in plain English)

When an AI uses a website, it has two bad options today. It can **look at a screenshot** and squint, or it can be handed the page's **raw
machinery**: tens of thousands of lines of hidden structure, most of it irrelevant. Both are slow and expensive, and the AI still has to guess which of
six identical "Add to cart" buttons is the one it wants.

Semantic Browser gives the AI **what you see when you read the page**: the words, the prices, the options, in order, with a small number next to
everything it can click or type into. The AI says `click 4` and it happens, and the tool tells it what changed. Think of the difference between being
handed a recipe and being handed the oven's wiring diagram.

```
$ sb goto https://shop.example/search?q=anvil
@ Search: anvil   [screen 1/1]
# Catalogue
[1 input:search "Search catalogue"="anvil"] [2 button]Search
- [3]Anvil Classic £49.99 In stock
- [4]Anvil Pro £89.50 Low stock

$ sb click 4
clicked [4] 'Anvil Pro' -> now at 'Anvil Pro' (https://shop.example/p/anvil-pro)
```

**How that is different from other AI browser tools**

- **It reads the page like a person, not like a computer.** Buttons and links sit *inside* the sentence they belong to (`[4]Anvil Pro £89.50`),
  duplicates say what they belong to (`Add to cart — Sauce Labs Backpack`), and menus and footers are folded away.
- **It checks its own work.** Many tools answer "✓ Done" whether or not anything happened. Here every action reports what changed (or that nothing
  did), a number that has gone out of date is refused rather than quietly hitting a different button, and a page that is blocking robots says so
  instead of being retried forever.
- **It speaks the AI's language.** The AI can name what it wants (`click "Sign in"`), search a whole page for a word (`find "price"`), or chain steps
  in one go (`sb do "type …" "click …"`).

**Why it is faster, and what that does not mean.** All of these tools drive the same Chrome-based browser, so the browser itself takes about the same
time for each step. In an AI agent the slow, costly part is not the browser: it is every extra *turn* the AI takes (a few seconds each) and every page
it has to read (you pay for each word). Semantic Browser cuts both: logging into a shop, adding two items and opening the cart is **2 calls instead
of 10**, and finding the Eiffel Tower's height costs **1.8k tokens instead of 24k-87k**. It is *not* a faster browser: on raw browser time it is level
with, and sometimes behind, its rivals (see [Benchmarks](#benchmarks), which says where).

For developers: it turns live Chromium pages into compact, numbered text views for LLM agents. The agent reads one short view (content *and* its
options), replies with one command like `click 12`, and the runtime executes it on that exact element handle.

## Give it to your agent (30 seconds)

```bash
pip install "semantic-browser[managed]" && semantic-browser install-browser
sb guide            # the playbook an agent should read: loop, view syntax, recovery, bot walls, safety (~1.5k tokens)
```

* **Any LLM agent:** paste the output of `sb guide` into its system prompt, or tell it: *"To use the web, run `sb guide`, then drive `sb`."*
* **Claude / Cursor skills:** `mkdir -p ~/.claude/skills/semantic-browser && sb guide --skill > ~/.claude/skills/semantic-browser/SKILL.md`
* **Rules files (`AGENTS.md`, `.cursorrules`):** add the same one-liner.
* The guide is tested against the code (every verb covered, size-capped) and also lives at [docs/agent_guide.md](docs/agent_guide.md).

What the agent gets: one outcome line plus a numbered page per command, batching with `sb do`, whole-page `find`, honest failure
messages, bot-wall and CAPTCHA signalling, and rules that treat page text as untrusted input and default to read-only.

## Why Semantic Browser

- **One compact view** — page content with inline `[n]` refs; shadow DOM, iframes (cross-origin too), custom div widgets and duplicate labels handled.
- **Exact-element execution** — a ref is bound to one element handle; stale refs fail loudly, never retarget (no silent `<body>` clicks).
- **Fewer model turns** — chained steps and label targets cut a 10-step task to 2 calls (measured vs `agent-browser` and `@playwright/cli`: [Benchmarks](#benchmarks)); the browser time per step is the same as theirs.
- **Built-in blockers** — cookie banners and modals are detected with a ranked dismiss hint; bot walls and rate limits are flagged (`! This looks like a bot/verification page`) so an agent stops instead of hammering.
- **CAPTCHA assist** — `sb captcha` produces a numbered (or, for canvas puzzles, ruler-annotated) image or PDF for a vision model, performs the clicks/drags it names, and reports ACCEPTED/REJECTED from the page's own message. Exercised on vendors' public demos only.
- **Real controls** — sliders show their value, file inputs take `upload`, and `drag`, `dblclick`, `click --right` exist; hung third-party scripts no longer stall `goto`.
- **Four interfaces** — `sb` agent CLI (persistent daemon), Python API, legacy `semantic-browser` CLI, and HTTP service.

## Install

```bash
pip install "semantic-browser[managed]"
semantic-browser install-browser
```

For service mode: `pip install "semantic-browser[server]"`

## Quickstart

### Agent CLI (`sb`, new in 1.4; `do` batches in 1.5)

```bash
sb goto news.ycombinator.com   # first call starts a background Chromium (headful); later calls reuse it
sb click 12                    # act on the [12] you see in the view (or: sb click "comments")
sb find "price"                # search the whole page (table rows come with their column headers)
sb do "type 3 boots --enter" "click Football" view   # several steps, ONE call (stops at the first failure)
sb captcha --pdf               # annotated image of a CAPTCHA for a vision model
sb drag 12 15                  # drag-and-drop; also: upload N FILE, dblclick N, click N --right
sb stop
```

Full verb list, view syntax, sessions, `--cdp` attach and security model: **[docs/agent_cli.md](docs/agent_cli.md)**.

### Interactive portal

```bash
semantic-browser portal --url https://example.com --headless
```

### Python

```python
import asyncio
from semantic_browser import ManagedSession
from semantic_browser.models import ActionRequest

async def main() -> None:
    session = await ManagedSession.launch(headful=False)
    runtime = session.runtime

    await runtime.navigate("https://example.com")
    obs = await runtime.observe(mode="summary")
    print(obs.planner.room_text)

    first_link = next((a for a in obs.available_actions if a.op == "open"), None)
    if first_link:
        result = await runtime.act(ActionRequest(action_id=first_link.id))
        print(result.status, result.observation.page.url)

    await session.close()

asyncio.run(main())
```

### LLM Agent Loop (Minimal)

```python
async def agent_loop(url: str, task: str) -> None:
    session = await ManagedSession.launch(headful=False)
    runtime = session.runtime
    await runtime.navigate(url)
    obs = await runtime.observe(mode="summary")

    for step in range(25):
        action_id = call_your_llm(obs.planner.room_text, task)  # returns one action ID
        if action_id == "done":
            break
        result = await runtime.act(ActionRequest(action_id=action_id))
        obs = result.observation

    await session.close()
```

Full worked examples for OpenAI, Anthropic, and more: **[Integration Examples](docs/integration_examples.md)**

## Documentation

| Document | What it covers |
|----------|---------------|
| **[Agent guide (`sb guide`)](docs/agent_guide.md)** | The playbook to give an AI: how to drive `sb` well, recover, handle bot walls, stay safe |
| **[Agent CLI (`sb`)](docs/agent_cli.md)** | The verbs, how to read the view, sessions, attach to a running Chrome, security model |
| **[CAPTCHA assist](docs/captcha.md)** | Detect → annotate (PNG/PDF) → answer by tile number; what was verified and honest limits |
| **[Competitor comparison (1.7)](docs/benchmarks/2026-10-06-competitors-v1.7.md)** | `sb` vs `agent-browser` vs `@playwright/cli` vs `browse`, driven by hand on live sites; failures found and fixed; CAPTCHA demos. Single runs, so indicative only |
| **[v1.7 suites](docs/benchmarks/2026-10-06-v1.7-suites.md)** | Local hard patterns, 8 live sites and navigation timing vs raw Playwright and httpx, re-run on 1.7 |
| **[Dogfood benchmark (1.4, history)](docs/benchmarks/2026-10-06-dogfood-v1.4.md)** | The original v1.3.2 vs v1.4 report, kept for history |
| **[System architecture](docs/system_arch.md)** | Data flow, invariants, extension points |
| **[Getting Started](docs/getting_started.md)** | Install, first run, interactive portal, Python/CLI/service quickstarts |
| **[Planner Contract](docs/planner_contract.md)** | The exact interface between Semantic Browser and an LLM planner — what the planner receives, what it should reply, how to handle blockers, failures, and stopping |
| **[Integration Examples](docs/integration_examples.md)** | End-to-end examples: OpenAI chat, OpenAI function-calling, Anthropic tool use, HTTP service, CDP attach, error handling patterns |
| **[API Reference](docs/api_reference.md)** | Every public class, method, model, and field — `ManagedSession`, `SemanticBrowserRuntime`, `Observation`, `StepResult`, `ActionDescriptor`, configuration, errors |
| **[Runtime Modes](docs/runtime_modes.md)** | Decision table for ephemeral/persistent/clone/attach/service modes, headful vs headless, ownership semantics |
| **[Real Profiles](docs/real_profiles.md)** | Using real Chromium profiles for login persistence, SSO, clone mode, safety guarantees, common pitfalls |
| **[Benchmark Protocol](docs/benchmark_protocol.md)** | How benchmark numbers are produced and validated |
| **[Versioning](docs/versioning.md)** | Version numbering scheme |
| **[Publishing](docs/publishing.md)** | PyPI publish checklist |
| **[Changelog](CHANGELOG.md)** | Full release history |

## How It Works

```
Chromium page ──one JS walk per frame──▶ semantic nodes + reading-order flow ──▶ text view with inline [n] refs
      ▲                                                                                   │
      │                          agent reads the view, replies with one verb              ▼
      └── runtime executes on the exact element handle, settles, reports the outcome ◀── `click 12`
```

1. **Observe** — one DOM pass per frame (shadow DOM, same- and cross-origin iframes) builds nodes and a reading-order flow; occlusion and overlay detection mark what is really clickable.
2. **Render** — the view keeps content and controls together, collapses navigation, windows long pages and ranks overlay dismiss controls.
3. **Act** — a ref is bound to one element handle for the whole session, so a stale ref fails loudly instead of clicking something else. The runtime waits for the page to settle and prints one outcome line (`-> now at …`, `page changed (+3/-1 lines)`, `no visible change`).
4. **Repeat** — or batch known steps with `sb do`. Architecture: [docs/system_arch.md](docs/system_arch.md). The older planner/`observe`/`act` API (room text, action IDs) is still available for Python and service use: [Planner Contract](docs/planner_contract.md).

## Benchmarks

Every figure below was measured on **1.7.x** (macOS arm64, headless Chromium, live sites, 2026-10-06). Three views of the same question:
"what does it cost an agent to get a task done?"

### 1. Against the other agent browsers: same five tasks, three runs each

`sb` 1.7.1 vs `agent-browser` 0.38.2 vs `@playwright/cli` 0.1.22, cold start every run, rounds interleaved (`scripts/dogfood/replay.py`). A run passes
only if the right answer appears in the output; all 45 runs passed. Cells are *median calls · seconds · tokens read*.

| Task | `sb` | `agent-browser` | `playwright-cli` |
|---|---|---|---|
| Eiffel Tower height (Wikipedia) | 2 · 2.1 s · **1.8k** | 2 · **1.8 s** · 24.2k | 2 · 1.9 s · 87.5k |
| Read the Hacker News front page | **1** · **1.7 s** · 1.3k | 2 · 1.9 s · **1.0k** | 2 · 2.1 s · 12.0k |
| Add 3 todos, tick one (TodoMVC) | **2** · 2.2 s · **0.4k** | 11 · **2.1 s** · 0.7k | 11 · 5.0 s · 3.2k |
| Log in, add 2 items, open cart (saucedemo) | **2** · 2.8 s · **0.5k** | 10 · **2.0 s** · 0.9k | 10 · 5.2 s · 3.5k |
| Drag one box onto another | **2** · **2.1 s** · 0.2k | 5 · 2.0 s · **0.1k** | 4 · 2.9 s · 0.4k |
| **Median of all 15 runs** | **2 calls · 2.1 s · 460 tokens** | 5 calls · 2.0 s · 862 tokens | 4 calls · 2.9 s · 3,486 tokens |

- **`sb` wins on calls** (2 vs 10 on the shop and todo tasks) **and on tokens for big pages** (Wikipedia: 13-49x less to read). Every call is a model turn.
  *Illustration, not a measurement:* if a model turn takes ~4 s, the shop task is about 11 s with `sb` against ~42 s and ~45 s.
- **Browser time is a tie, and `agent-browser` is sometimes ahead** (shop: 2.0 s vs 2.8 s; `sb` starts a background browser on the first call). On very small pages its terse
  output also uses slightly fewer tokens.
- The sequences are the shortest each tool needed, found by driving each by hand first, then replayed. That is hindsight for all three: it measures what each tool costs, not how well a model finds its way.

### 2. Against raw Playwright snapshots: scripted suites on 1.7

A scripted stand-in for the model (no LLM) that may only act on what the tool showed it; "raw Playwright" is the idealised classic agent (a full accessibility snapshot per step, perfect locators, no settle wait).
Full tables: [v1.7 suites report](docs/benchmarks/2026-10-06-v1.7-suites.md).

| Suite | raw Playwright | `sb` 1.7 |
|---|---|---|
| 9 hard patterns (cookie overlay, shadow DOM, iframe payment, lazy feed, duplicate buttons…) x 3 | 21/27 · 0.58 s · 137 tok | **27/27** · 0.47 s · 150 tok |
| 8 live sites (Wikipedia, HN, GOV.UK, GitHub, BBC, DuckDuckGo, NHS, Amazon) x 3 interleaved rounds | 17/24 · **1.37 s** · 12.6k tok (max 161k) | **24/24** · 1.93 s · **2.5k** tok (max 3.9k) |
| Time to a usable page, 8 URLs (warm / cold cache) | **218 / 292 ms** · 5.5-7.0k tok | 339 / 434 ms · **1.3k** tok |

`sb` completes more tasks and reads about 5x fewer tokens, but it is **slower per step (about 0.5 s on the live suite)** because it waits for the page to
finish reacting before reading it; raw Playwright reads immediately, which is quicker and sometimes wrong. For reference, plain `httpx` fetches the same pages in
35 ms but returns 38.8k tokens of HTML with no JavaScript run. `--lite media` showed no reliable gain, so it stays opt-in.

### 3. Hand-driven on live sites (me, Claude Sonnet 5.5)

About 35 sites and tasks, one command per call, single runs that include my false starts ([report](docs/benchmarks/2026-10-06-competitors-v1.7.md)):
`sb` completed 16 of 19 tasks (median 3 calls), `agent-browser` 6 of 10 (median 9.5) and `playwright-cli` 7 of 9 (median 8). `agent-browser`'s failures were clicks that printed
`✓ Done` while the page didn't change, and a page whose script hangs for 30 s (the replay above shows it can do the shop task once the right refs are known; I couldn't get there by reading its output).
Cloudflare-gated sites (npm, Stack Overflow) blocked every tool. CAPTCHA demos completed (vendors' public pages only): reCAPTCHA v2, hCaptcha, Cloudflare Turnstile (testing key), captcha.com text.

Caveats: one machine, a few runs per task, live websites that change. Protocol: [`docs/benchmark_protocol.md`](docs/benchmark_protocol.md). Manifest: [`benchmarks/manifest.json`](benchmarks/manifest.json).
Reproduce: `python scripts/dogfood/runner.py --impl sb|pw --set local|real`, `python scripts/dogfood/navbench.py`, and `SAUCEDEMO_PASSWORD=<the demo site's published password> python scripts/dogfood/replay.py --runs 3`.
Older-version results (1.3.2/1.4/1.5) are kept as history: [dogfood v1.4](docs/benchmarks/2026-10-06-dogfood-v1.4.md), [real-model rounds](docs/benchmarks/2026-10-06-dogfood-real-model.md).

## CLI Reference

```bash
semantic-browser version                # Show version
semantic-browser doctor                 # Verify installation
semantic-browser install-browser        # Download Chromium
semantic-browser launch --headless      # Start a session
semantic-browser attach --cdp <ws-url>  # Attach to running Chrome
semantic-browser portal --url <url>     # Interactive exploration REPL
semantic-browser observe --session <id> --mode summary
semantic-browser act --session <id> --action <action_id>
semantic-browser inspect --session <id> --target <target_id>
semantic-browser navigate --session <id> --url <url>
semantic-browser back --session <id>
semantic-browser forward --session <id>
semantic-browser reload --session <id>
semantic-browser diagnostics --session <id>
semantic-browser export-trace --session <id> --out trace.json
semantic-browser serve --host 127.0.0.1 --port 8765 --api-token <token>
```

## What's New in v1.7.0

A long hand-driven sweep of ~35 sites/tasks against `agent-browser`, `@playwright/cli` and `browse`, journaled with `scripts/dogfood/tj.py`
([report](docs/benchmarks/2026-10-06-competitors-v1.7.md); single runs, so no numbers are claimed here). Everything below came from a failure seen live:

- **New verbs** — `upload N PATH` (credential-looking paths refused), `drag FROM TO`, `dblclick N`, `click N --right`; sliders print `value min..max`.
- **Faster on hung pages** — `goto` no longer waits out a stalled blocking script (50-100 s became a few seconds).
- **Better labels and layers** — checkboxes/radios named from adjacent text or a sibling `<label>`; shadow-DOM modals (MDN search) detected; footer status text ("1 item left") kept; ad iframes filtered; password fields keep their label.
- **CAPTCHA** — canvas puzzles (hCaptcha) via a coordinate ruler plus `captcha click/drag`; text CAPTCHAs; REJECTED/ACCEPTED taken from the page's own message rather than guessed. Completed on the reCAPTCHA, hCaptcha, Cloudflare Turnstile (testing key) and captcha.com demos. Production anti-bot gates are not attempted.
- Cleaner outcome lines (no synthetic `waited wait 'Wait'`), and `covered` flips no longer reported as page changes.

## What's New in v1.6.0

- **`sb guide`** — the agent playbook ships inside the package (`sb guide`, `sb guide --skill` for a drop-in SKILL.md). Tested for verb coverage and size.
- **Bot walls are named** — Fastly/Cloudflare/DuckDuckGo-style gates and rate limits get a `! This looks like a bot/verification page` line with the right next step,
  also on long pages when the controls are covered. Found live: PyPI "Client Challenge", DuckDuckGo "bots use DuckDuckGo too".
- **Search boxes in headers stay search boxes** — collapsed header/nav lines used to print an `<input>` like a link (`[4]Search with DuckDuckGo`); fillable controls now keep
  their full form and are never cut by the "(+N more)" cap.
- **Better `find`** — whole-word hits first (`MIT` no longer drowns in "commit"), and a short hit (a bare price) carries its card title.
- Unknown-verb errors list the verbs from the code and point at `sb guide`.

## What's New in v1.5.0

Everything here came from driving `sb` as a real model (Claude Sonnet 5.5) on live sites, then fixing what hurt
([report](docs/benchmarks/2026-10-06-dogfood-real-model.md)):

- **`sb do "step" "step" …`** — a whole GOV.UK visa wizard (8 steps) is one call; median task went from 4 calls to 1.
- **Correct text on hard markup** — Amazon prices no longer lose their decimal (`£569` → `£5.69`); transparent radios/checkboxes
  (GOV.UK) have refs; delegated-handler widgets (jQuery UI datepicker Prev/Next) are controls.
- **Honest overlays** — the dismiss hint ranks close/reject/short-accept, never "Continue", sign-in or pay-to-reject; `view --all` shows the page behind.
- **Better `find`** — centred snippets, real `<th>` column headers, works behind an overlay. Labels you type (`click Save settings`) resolve, and
  ambiguous ones show where each candidate goes.
- **CAPTCHA** — the image is captured once the page is still (dynamic reCAPTCHA grids replace tiles after Verify).
- Stale background sessions restart themselves after an upgrade. Release tooling: `scripts/publish.sh`.

Full list: [CHANGELOG.md](CHANGELOG.md). Note: 1.4.0 was never published to PyPI; 1.5.0 includes it.

## Earlier releases

1.4.0 introduced the `sb` agent CLI, the one-pass view engine, fast settling, CAPTCHA assist and safe `--cdp` attach (never published on its own; 1.5.0 was the first release to include it). Full history: [CHANGELOG.md](CHANGELOG.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and PR expectations.

## License

MIT — see [LICENSE](LICENSE).
