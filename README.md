# Semantic Browser

<p align="left">
  <img src="https://github.com/user-attachments/assets/dac79ee0-6ebb-48b3-a27d-2e339ea16961" alt="Semantic Browser mascot" width="240" align="right" />
</p>

**Version 1.5.0 (Beta)** · [PyPI](https://pypi.org/project/semantic-browser/) · [Changelog](CHANGELOG.md) · [License: MIT](LICENSE)

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

Less confusion, less hallucination, dramatically less cost: on 8 live sites the model reads a median **~2.5k tokens per step (1.3k with
`--budget 2500`) instead of ~15k for a raw accessibility snapshot**, at ~1.4 s per two-step task with 16/16 success
([benchmark report](docs/benchmarks/2026-10-06-dogfood-v1.4.md)).

## Why Semantic Browser

- **One compact view** — page content with inline `[n]` refs; shadow DOM, iframes (cross-origin too), custom div widgets and duplicate labels handled.
- **Exact-element execution** — a ref is bound to one element handle; stale refs fail loudly, never retarget (no silent `<body>` clicks).
- **Fast** — event-driven settling: ~0.3–0.5 s to a usable page; whole 3–5-step tasks in ~0.3–1 s on the local hard-pattern suite (v1.3.2: ~4 s).
- **Built-in blockers** — cookie banners, modals, and anti-bot gates are detected and signaled.
- **CAPTCHA assist** — `sb captcha` produces a numbered, annotated image (or PDF) for a vision model and clicks the tiles it names.
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
| **[Agent CLI (`sb`)](docs/agent_cli.md)** | v1.4: the verbs, how to read the view, sessions, attach to a running Chrome, security model |
| **[CAPTCHA assist](docs/captcha.md)** | Detect → annotate (PNG/PDF) → answer by tile number; what was verified and honest limits |
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
Live page → extract semantic tree → group into regions → curate actions → render room text
                                                                              ↓
                                                              LLM planner picks action ID
                                                                              ↓
                                                              runtime resolves & executes
                                                                              ↓
                                                              observe delta → repeat
```

1. **Observe** — the runtime extracts the page's semantic structure, groups it into regions, curates the top actions, and renders a text-adventure "room".
2. **Plan** — the LLM planner reads the room text and replies with one action ID.
3. **Act** — the runtime resolves the action to a DOM element, executes it, waits for the page to settle, and produces a delta observation.
4. **Repeat** — the planner sees the delta and picks the next action.

## Benchmarks

Latest dogfood run (details, protocol, raw data and caveats: [docs/benchmarks/2026-10-06-dogfood-v1.4.md](docs/benchmarks/2026-10-06-dogfood-v1.4.md)):

| Method | Local hard-pattern suite | 8 live sites | Tokens read / step (live, median) |
|--------|---:|---:|---:|
| v1.3.2 | 12/27 | 14/16 | ~0.8k |
| Raw Playwright accessibility snapshot | 21/27 | 11/16 | ~15k (max 143k) |
| **v1.4** | **27/27** | **16/16** | ~2.5k (1.3k with `--budget 2500`) |

**Real model, live sites** (me, Claude Sonnet 5.5, one command per call, journaled with `scripts/dogfood/sbj.py`;
[report](docs/benchmarks/2026-10-06-dogfood-real-model.md)): round 1 on 1.4.0 completed 11 of 13 tasks (median 4 calls; it found a wrong-price bug and several missing-control bugs);
after the fixes the final round completed 7 of 7 (median 1 call, ~0.26k tokens read; part of that is the new `do` batching). Reddit and Hacker News blocked this IP in every mode and are reported as such.

The first table is a scripted stand-in for the model; the real-model numbers above are a handful of tasks on one machine. Neither is a universal guarantee. Protocol: [`docs/benchmark_protocol.md`](docs/benchmark_protocol.md). Manifest: [`benchmarks/manifest.json`](benchmarks/manifest.json).

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

## What's New in v1.4.0

- **`sb` agent CLI + persistent daemon** — one short command per step, browser stays alive between calls (unix socket, `0700` dir).
- **New page view engine (default)** — one JS pass per frame; shadow DOM, cross-origin iframes, clickable `div`s, occlusion/overlay detection,
  numbered refs bound to exact elements (monotonic per session). Legacy engine: `extraction.engine="legacy"`.
- **Fast settle** — DOM-quiet + network-quiet instead of fixed polling: local suite 4.1 s → 0.44 s median, real sites 4.5 s → 1.4 s.
- **CAPTCHA assist** — detect, number tiles, crop PNG/PDF, `select`/`text`/`submit`; verified on Google's public reCAPTCHA demo (detection and multi-round
  flow; provider acceptance is not claimed).
- **Attach safely** — `--cdp` works in its own tab and never lists or adopts a person's other tabs.
- **Lite mode** (`--lite media|max`, off by default) — shipped *unproven*: no measurable speed-up in the benchmark.
- **Fixes found by dogfooding** — silent `<body>` clicks, duplicate-label clicks hitting the first match, stale refs after navigation, `view --expand`
  advertised but missing, password/card/OTP values masked, and more (see [CHANGELOG](CHANGELOG.md)).
- Bench harness: `scripts/dogfood/` (fixtures, oracle-model runner, `navbench`).

Honest trade-off: the v1.4 view is ~3× larger than v1.3.2's (it shows *all* options instead of the top 25) but ~6–55× smaller than a raw accessibility snapshot.

Full details: [CHANGELOG.md](CHANGELOG.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and PR expectations.

## License

MIT — see [LICENSE](LICENSE).
