# Semantic Browser
<p align="left">
  <img src="https://github.com/user-attachments/assets/dac79ee0-6ebb-48b3-a27d-2e339ea16961" alt="Semantic Browser mascot" width="240" align="right" />
</p>
Semantic Browser turns live Chromium pages into compact semantic "rooms" for LLM planners.

**Release:** [`v1.0` (Alpha)](https://github.com/visser23/semantic-browser/releases/tag/v1.0)  
**Package version:** `1.0.0`  
**Latest release tag format:** see `docs/versioning.md`

Make browser automation feel less like parsing soup and more like an old BBC Micro text adventure.

- Live page -> structured room state
- DOM distilled into meaningful objects, not soup
- Built for agentic browser automation
- Token-efficient, deterministic, inspectable

```
@ BBC News (bbc.co.uk)
> Home page. Main content: "Top stories". Navigation: News, Sport, Weather.
1 open "News" [act-8f2a2d1c-0]
2 open "Sport" [act-c3e119fa-0]
3 fill Search BBC [act-0b9411de-0] *value
+ 28 more [more]
```

The planner replies with one action ID and the runtime executes deterministically.

## Why Semantic Browser

- Semantic room output instead of DOM/JSON soup.
- Curated action surface for token-efficient planning.
- Deterministic action execution loop (`observe` -> `act` -> `observe delta`).
- Built-in blocker signaling and confidence reporting.
- Python API, CLI, and local service interfaces.

## Install

```bash
pip install semantic-browser
```

Managed mode (recommended first run):

```bash
pip install "semantic-browser[managed]"
semantic-browser install-browser
```

Service mode:

```bash
pip install "semantic-browser[server]"
```

## Quickstart

```bash
semantic-browser portal --url https://example.com --headless
```

Inside portal:

- `observe summary`
- `actions`
- `act <action_id>`
- `back` / `forward` / `reload`
- `trace run-trace.json`
- `quit`

More examples: `docs/getting_started.md`

## Python Usage

```python
import asyncio
from semantic_browser import ManagedSession
from semantic_browser.models import ActionRequest

async def demo() -> None:
    session = await ManagedSession.launch(headful=False)
    runtime = session.runtime
    await runtime.navigate("https://example.com")
    obs = await runtime.observe(mode="summary")
    first_open = next((a for a in obs.available_actions if a.op == "open"), None)
    if first_open:
        result = await runtime.act(ActionRequest(action_id=first_open.id))
        print(result.status, result.observation.page.url)
    await session.close()

asyncio.run(demo())
```

## CLI Reference

```bash
semantic-browser version
semantic-browser doctor
semantic-browser install-browser
semantic-browser launch --headless
semantic-browser attach --cdp ws://127.0.0.1:9222/devtools/browser/<id>
semantic-browser observe --session <id> --mode summary
semantic-browser act --session <id> --action <action_id>
semantic-browser inspect --session <id> --target <target_id>
semantic-browser navigate --session <id> --url https://example.com
semantic-browser export-trace --session <id> --out trace.json
semantic-browser serve --host 127.0.0.1 --port 8765 --api-token dev-token
```

## Service Security Defaults

- Localhost-focused CORS defaults.
- Optional token auth via `SEMANTIC_BROWSER_API_TOKEN` / `X-API-Token`.
- Idle session TTL cleanup.

## Benchmarks

Benchmark numbers are reference harness runs, not universal guarantees.

- Protocol: `docs/benchmark_protocol.md`
- Manifest: `benchmarks/manifest.json`

## Open Source Docs

- `docs/getting_started.md`
- `docs/versioning.md`
- `docs/publishing.md`
- `CHANGELOG.md`
- `LICENSE`
- `CONTRIBUTING.md`
- `SECURITY.md`
