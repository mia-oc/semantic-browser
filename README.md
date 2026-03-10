# semantic-browser

`semantic-browser` is a deterministic semantic runtime over a live Chromium browser.

It is built for LLM planners (Codex, Cursor, Claude Code, MCP tools) that need compact,
reliable browser context and executable actions instead of raw DOM.

## Install

Core (attached mode support):

```bash
pip install semantic-browser
```

Managed mode (includes Playwright runtime support):

```bash
pip install semantic-browser[managed]
```

Server mode:

```bash
pip install semantic-browser[server]
```

Everything:

```bash
pip install semantic-browser[full]
```

## Quick start

```python
from semantic_browser import ManagedSession

session = await ManagedSession.launch(headful=True)
runtime = session.runtime

await runtime.navigate("https://example.com")
observation = await runtime.observe(mode="summary")
print(observation.model_dump_json(indent=2))

await session.close()
```

## CLI

```bash
semantic-browser version
semantic-browser doctor
semantic-browser install-browser
```

## Core API

- `observe(mode="summary"|"full"|"delta"|"debug")`
- `inspect(target_id)`
- `act(ActionRequest)`
- `navigate(url)`
- `diagnostics()`
- `export_trace(path)`

## Status

v0.1.0 provides a full end-to-end baseline implementation suitable for local
experimentation and iterative hardening.
