# Getting Started

This guide gets you from zero to a working semantic automation loop.

## Prerequisites

- Python `3.11+`
- `pip`
- Internet access (for live-site runs)

## Install

```bash
pip install "semantic-browser[managed]"
semantic-browser install-browser
semantic-browser doctor
```

## First Run (Interactive)

```bash
semantic-browser portal --url https://example.com --headless
```

In the portal prompt:

```text
observe summary
actions
act <action_id>
observe delta
quit
```

## First Run (Python API)

```python
import asyncio
from semantic_browser import ManagedSession
from semantic_browser.models import ActionRequest

async def main() -> None:
    session = await ManagedSession.launch(headful=False)
    runtime = session.runtime
    await runtime.navigate("https://example.com")
    obs = await runtime.observe("summary")
    first = next((a for a in obs.available_actions if a.op == "open"), None)
    if first:
        await runtime.act(ActionRequest(action_id=first.id))
    await session.close()

asyncio.run(main())
```

## Local Service Mode

Start local service:

```bash
semantic-browser serve --host 127.0.0.1 --port 8765 --api-token dev-token
```

Example requests:

```bash
curl -X POST http://127.0.0.1:8765/sessions/launch \
  -H "Content-Type: application/json" \
  -H "X-API-Token: dev-token" \
  -d '{"headful": false}'

curl -X POST http://127.0.0.1:8765/sessions/<session_id>/observe \
  -H "Content-Type: application/json" \
  -H "X-API-Token: dev-token" \
  -d '{"mode": "summary"}'
```

## Troubleshooting

- Missing Playwright: `pip install "semantic-browser[managed]"`
- Browser launch issues: `semantic-browser install-browser`
- Weak observations on dynamic pages: retry with `observe full` or `observe debug`
