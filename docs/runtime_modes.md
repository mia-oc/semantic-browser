# Runtime Modes

Semantic Browser supports several browser lifecycle and attachment modes. This guide helps you pick the right one.

## Quick Decision Table

| I want to... | Mode | Profile | How |
|--------------|------|---------|-----|
| Run a quick stateless task | `owned_ephemeral` | `ephemeral` | `ManagedSession.launch()` |
| Run tasks with login persistence | `owned_persistent_profile` | `persistent` | `ManagedSession.launch(profile_mode="persistent", profile_dir="...")` |
| Experiment with an auth'd profile safely | `owned_persistent_profile` | `clone` | `ManagedSession.launch(profile_mode="clone", profile_dir="...")` |
| Bootstrap cookies without a full profile | `owned_ephemeral` | `ephemeral` + storage state | `ManagedSession.launch(storage_state_path="state.json")` |
| Attach to my already-running Chrome | `attached_cdp` | — | `SemanticBrowserRuntime.from_cdp_endpoint("ws://...")` |
| Attach to a Playwright page I already have | `attached_context` | — | `SemanticBrowserRuntime.from_page(page)` |
| Run a headless HTTP service for many clients | service mode | per-session | `semantic-browser serve` |

## Profile Modes

### Ephemeral (default)

```python
session = await ManagedSession.launch(profile_mode="ephemeral")
```

- Fresh browser context every run.
- No cookies, localStorage, or login state carried over.
- Best for: stateless tasks, scraping, CI pipelines.
- Fastest launch time.

### Persistent

```python
session = await ManagedSession.launch(
    profile_mode="persistent",
    profile_dir="/path/to/chrome-profile",
)
```

- Uses a real Chromium user data directory.
- Cookies, localStorage, extensions, and trust signals persist across runs.
- Best for: agent tasks requiring login, SSO, or session continuity.
- The runtime **never deletes** the profile directory.
- Warning: don't run two sessions against the same profile directory simultaneously.

### Clone

```python
session = await ManagedSession.launch(
    profile_mode="clone",
    profile_dir="/path/to/chrome-profile",
)
```

- Copies the profile into a temporary directory, then launches against the copy.
- Original profile is never modified.
- Best for: safe experimentation with authenticated profiles.
- The temporary copy is cleaned up on close.

### Storage State (ephemeral + cookies)

```python
session = await ManagedSession.launch(
    profile_mode="ephemeral",
    storage_state_path="state.json",
)
```

- Ephemeral context bootstrapped with cookies/localStorage from a Playwright storage state file.
- Lighter than a full profile, but limited: no extensions, no trust signals, no service workers.
- Best for: quick auth bootstrap when you have a saved login state.

## Ownership Modes

Ownership mode determines what `close()` does to the browser.

### `owned_ephemeral`

Created by `ManagedSession.launch()` with `profile_mode="ephemeral"`.

- `close()` shuts down the browser process.
- Everything is cleaned up.

### `owned_persistent_profile`

Created by `ManagedSession.launch()` with `profile_mode="persistent"` or `"clone"`.

- `close()` shuts down the browser process.
- Profile directory is **never deleted** (persistent) or temp copy is cleaned up (clone).

### `attached_context`

Created by `SemanticBrowserRuntime.from_page()` or `.from_context()`.

- `close()` does **not** close the browser — it's externally owned.
- Emits a warning reminding you to use `force_close_browser()` if you need destructive close.

### `attached_cdp`

Created by `SemanticBrowserRuntime.from_cdp_endpoint()`.

- `close()` does **not** close the external Chrome process.
- Disconnects the CDP connection and stops Playwright.
- Use `force_close_browser()` only if you explicitly own the Chrome process.

## Headful vs Headless

```python
session = await ManagedSession.launch(headful=True)   # shows window
session = await ManagedSession.launch(headful=False)   # headless
```

**Recommendation:** Use `headful=True` (or omit — it's the default) for sites with bot detection. Many modern sites (betting, banking, e-commerce) detect headless Chrome and serve degraded pages or block entirely.

Use `headful=False` for:
- CI/CD pipelines where no display is available.
- High-throughput stateless scraping of permissive sites.
- Development environments using `xvfb` or similar virtual displays.

## Service Mode

The HTTP service wraps all of the above into a REST API. Each client creates their own session with their own profile mode.

```bash
# Start the service
semantic-browser serve --host 127.0.0.1 --port 8765 --api-token my-token

# Clients create sessions via HTTP
curl -X POST http://127.0.0.1:8765/sessions/launch \
  -H "Content-Type: application/json" \
  -H "X-API-Token: my-token" \
  -d '{"headful": false, "profile_mode": "ephemeral"}'
```

Service configuration via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `SEMANTIC_BROWSER_API_TOKEN` | `None` | If set, all requests must include `X-API-Token` header |
| `SEMANTIC_BROWSER_CORS_ORIGINS` | `["http://localhost:*"]` | Allowed CORS origins |
| `SEMANTIC_BROWSER_SESSION_TTL_SECONDS` | `3600` | Idle session cleanup TTL |

Sessions are automatically cleaned up after the TTL expires with no activity.

## CDP Attach (Advanced)

For connecting to an already-running Chrome instance.

### Start Chrome with remote debugging

```bash
# macOS
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222

# Linux
google-chrome --remote-debugging-port=9222

# Windows
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```

### Attach

```python
runtime = await SemanticBrowserRuntime.from_cdp_endpoint(
    "ws://127.0.0.1:9222/devtools/browser/XXXXX",
)
```

### Tab selection

```python
# By URL substring
runtime = await SemanticBrowserRuntime.from_cdp_endpoint(
    endpoint, target_url_contains="example.com"
)

# By index
runtime = await SemanticBrowserRuntime.from_cdp_endpoint(
    endpoint, page_index=0
)

# Skip about:blank tabs (default)
runtime = await SemanticBrowserRuntime.from_cdp_endpoint(
    endpoint, prefer_non_blank=True
)
```

### Important CDP constraints

- The endpoint must be a **browser** websocket (`/devtools/browser/...`), not a page websocket.
- `close()` does not close the external Chrome — use `force_close_browser()` if needed.
- Profile lifecycle is entirely your responsibility.

## Migration from v1.0

If you used `user_data_dir` in v1.0:

| v1.0 | v1.1+ |
|------|-------|
| `user_data_dir="/path"` for storage state | `storage_state_path="/path/state.json"` in `ephemeral` mode |
| `user_data_dir="/path"` for real profile | `profile_mode="persistent", profile_dir="/path"` |
