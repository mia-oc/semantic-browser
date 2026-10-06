# Semantic Browser

<p align="left">
  <img src="https://github.com/user-attachments/assets/dac79ee0-6ebb-48b3-a27d-2e339ea16961" alt="Semantic Browser mascot" width="240" align="right" />
</p>

**Version 1.7.1 (Beta)** · [PyPI](https://pypi.org/project/semantic-browser/) · [Changelog](CHANGELOG.md) · [License: MIT](LICENSE)

Semantic Browser turns live Chromium pages into compact, numbered text views for LLM agents. The agent reads one short view
(content *and* its options), replies with one command like `click 12`, and the runtime executes it on that exact element.

```
$ sb goto https://shop.example/search?q=anvil
navigated to … -> 'Search: anvil'

@ Search: anvil — https://shop.example/search?q=anvil   [screen 1/1]
# Catalogue
[1 input:search "Search catalogue"="anvil"] [2 button]Search
- [3]Anvil Classic £49.99 In stock
- [4]Anvil Pro £89.50 Low stock

$ sb click 4
clicked [4] 'Anvil Pro' -> now at 'Anvil Pro' (https://shop.example/p/anvil-pro)
```

## Why this is a different way to browse for an AI

Most browser tools for agents give the model either a **screenshot** or a **dump of the page's internals** (an accessibility tree or the HTML), and
then ask it to pick an element id. That is like asking someone to run a web page by reading its wiring diagram. The model has to wade through
thousands of tokens it doesn't need, guess which of six identical "Add to cart" buttons is which, and take a "✓ Done" on trust even when nothing happened.

Semantic Browser prints the page **the way a person would read it out loud**: headings, text, prices and options, with each button, link and
field sitting *inside* the sentence it belongs to and numbered (`[4]Anvil Pro £89.50 Low stock`). Duplicates say what they belong to
(`Add to cart — Sauce Labs Backpack`). Menus and footers are folded away, and long pages are windowed. After every action it tells you what changed
(or that nothing did), and a stale number is refused instead of silently hitting a different button.

**Why that is faster.** All of these tools drive the same Chromium through Playwright, so the browser itself takes about the same time
(50-150 ms per step; see below). What costs real time in an agent is the *model*: every extra step is another turn of a few seconds, plus all the tokens it reads.
Semantic Browser saves exactly those:

1. **Fewer turns.** Because the model can name what it wants (`click "Add to cart — Sauce Labs Backpack"`) and chain steps (`sb do "type …" "type …" "click Cart"`),
   logging into a shop, adding two items and opening the cart takes **2 calls instead of 10**.
2. **Less to read.** The Eiffel Tower's height costs ~1.8k tokens (search the whole page with `find`) against 24k-87k for a full dump of the same page.
3. **No wasted retries.** Actions are verified and the page is told when it is gated (`! BLOCKING OVERLAY`, `! This looks like a bot/verification page`),
   and a script that never loads can't hold a page hostage (`goto` returns after a short grace window instead of waiting a minute).

Measured figures are in [Benchmarks](#benchmarks), including where it is *not* faster.

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
| **[Agent CLI (`sb`)](docs/agent_cli.md)** | v1.4: the verbs, how to read the view, sessions, attach to a running Chrome, security model |
| **[CAPTCHA assist](docs/captcha.md)** | Detect → annotate (PNG/PDF) → answer by tile number; what was verified and honest limits |
| **[Competitor comparison (1.7)](docs/benchmarks/2026-10-06-competitors-v1.7.md)** | `sb` vs `agent-browser` vs `@playwright/cli` vs `browse`, driven by hand on live sites; failures found and fixed; CAPTCHA demos. Single runs, so indicative only |
| **[Dogfood benchmark](docs/benchmarks/2026-10-06-dogfood-v1.4.md)** | v1.3.2 vs v1.4 vs raw Playwright vs httpx, hard-pattern suite, 8 live sites, gated sites, CAPTCHA demo |
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

Same five tasks, same Chromium, same machine, run **three times each, cold start every time, rounds interleaved** with `scripts/dogfood/replay.py`
(macOS arm64, headless, live sites, 2026-10-06; `sb` 1.7.0 vs `agent-browser` 0.38.2 vs `@playwright/cli` 0.1.22).
A run passes only if the right answer appears in the tool's output. Each cell is *median calls · median seconds · median tokens read*; every cell passed 3/3.

| Task | `sb` | `agent-browser` | `playwright-cli` |
|---|---|---|---|
| Eiffel Tower height (Wikipedia) | 2 · 2.1 s · **1.8k** | 2 · **1.8 s** · 24.2k | 2 · 1.9 s · 87.5k |
| Read the Hacker News front page | **1** · **1.7 s** · 1.3k | 2 · 1.9 s · **1.0k** | 2 · 2.1 s · 12.0k |
| Add 3 todos, tick one (TodoMVC) | **2** · 2.2 s · **0.4k** | 11 · **2.1 s** · 0.7k | 11 · 5.0 s · 3.2k |
| Log in, add 2 items, open cart (saucedemo) | **2** · 2.8 s · **0.5k** | 10 · **2.0 s** · 0.9k | 10 · 5.2 s · 3.5k |
| Drag one box onto another | **2** · **2.1 s** · 0.2k | 5 · 2.0 s · **0.1k** | 4 · 2.9 s · 0.4k |
| **All 15 runs: median** | **2 calls · 2.1 s · 460 tokens** | 5 calls · 2.0 s · 862 tokens | 4 calls · 2.9 s · 3,486 tokens |

What this does and doesn't say, honestly:

- **Calls are where `sb` wins** (2 vs 10 on the shop and todo tasks), and tokens on big pages (Wikipedia: 13-49x less to read). Each call is a model turn.
  *Illustration, not a measurement:* if a model turn takes ~4 s, the shop task is about 11 s with `sb` (2.8 s browser + 2 turns) against ~42 s (`agent-browser`) and ~45 s (`playwright-cli`).
- **Browser time is a tie, and `agent-browser` is sometimes ahead.** Its calls are tiny and fast (the shop task: 2.0 s vs 2.8 s, since `sb` starts a background
  browser daemon on the first call). On small pages its terse output also uses slightly fewer tokens (HN, drag-and-drop).
- The command sequences are the **shortest each tool needed**, found by driving each tool by hand first; they are replayed with the refs that run read from the tool's own output. That is hindsight for all three, so the replay
  measures per-tool cost, not how well a model finds its way. For that, see the hand-driven run next.
- Five tasks, one machine, three runs: indicative, not a guarantee.

**Hand-driven, live sites** (me, Claude Sonnet 5.5, one command per call, about 35 sites and tasks, single runs that include my false starts; full table, failures and fixes in
[the comparison report](docs/benchmarks/2026-10-06-competitors-v1.7.md)): `sb` completed 16 of 19 tasks (median 3 calls), `agent-browser` 6 of 10 (median 9.5) and
`playwright-cli` 7 of 9 (median 8). Its failures were clicks that printed `✓ Done` while the page didn't change, and a page whose script hangs for 30 s (the replay above shows `agent-browser` can do the shop task once the right refs are known; I couldn't get there by reading its output). Cloudflare-gated sites (npm, Stack Overflow) blocked every tool.

CAPTCHA demos completed (vendors' public pages only): reCAPTCHA v2, hCaptcha, Cloudflare Turnstile (testing key), captcha.com text. Earlier scripted-model results (1.4) and the real-model rounds (1.5): [dogfood-v1.4](docs/benchmarks/2026-10-06-dogfood-v1.4.md), [real-model](docs/benchmarks/2026-10-06-dogfood-real-model.md).
Protocol: [`docs/benchmark_protocol.md`](docs/benchmark_protocol.md). Manifest: [`benchmarks/manifest.json`](benchmarks/manifest.json). Reproduce: `SAUCEDEMO_PASSWORD=<the demo site's published password> python scripts/dogfood/replay.py --runs 3`.

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
