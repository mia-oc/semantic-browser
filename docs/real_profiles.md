# Running with Real Browser Profiles

When your agent needs login persistence, SSO continuity, or trust signals that only a real Chromium profile can provide, use persistent or clone profile modes.

## When You Need a Real Profile

| Scenario | Profile mode | Why |
|----------|-------------|-----|
| Agent logs into a site and you want to reuse the session | `persistent` | Cookies, localStorage, and session tokens persist |
| SSO / OAuth flows with remember-me | `persistent` | Trust cookies and device tokens carry over |
| Testing against an authenticated profile without risk | `clone` | Original profile is never modified |
| Quick auth bootstrap from saved cookies | `ephemeral` + `storage_state_path` | Lightweight — no extensions or trust signals |
| Stateless tasks (scraping, public pages) | `ephemeral` | No profile needed |

## Persistent Mode

Launch directly against a real Chromium user data directory:

### Python

```python
session = await ManagedSession.launch(
    headful=True,
    profile_mode="persistent",
    profile_dir="/Users/you/Library/Application Support/Google/Chrome",
)
runtime = session.runtime

await runtime.navigate("https://authenticated-site.com")
obs = await runtime.observe(mode="summary")
print(obs.planner.room_text)

await session.close()
```

### CLI

```bash
semantic-browser launch --profile-mode persistent \
  --profile-dir "/Users/you/Library/Application Support/Google/Chrome"
```

### Service

```bash
curl -X POST http://127.0.0.1:8765/sessions/launch \
  -H "Content-Type: application/json" \
  -H "X-API-Token: dev-token" \
  -d '{
    "headful": true,
    "profile_mode": "persistent",
    "profile_dir": "/Users/you/Library/Application Support/Google/Chrome"
  }'
```

## Clone Mode

Copies the profile into a temp directory before launching. The original profile is untouched.

```python
session = await ManagedSession.launch(
    headful=True,
    profile_mode="clone",
    profile_dir="/Users/you/Library/Application Support/Google/Chrome",
)
```

Clone mode is ideal when you want to start from an authenticated state but don't want the agent's actions to affect the original profile (e.g. form submissions, account changes, history pollution).

## Storage State (Lightweight Alternative)

If you only need cookies and localStorage (no extensions, no trust signals):

```python
session = await ManagedSession.launch(
    headful=False,
    profile_mode="ephemeral",
    storage_state_path="state.json",
)
```

Generate a storage state file from Playwright:

```python
# Save state from an existing context
await context.storage_state(path="state.json")
```

**Limitations:** Storage state does not replicate:
- Browser extensions
- Service workers
- Trust signals (device tokens, fingerprint reputation)
- IndexedDB data

For anything beyond simple cookie auth, use a real profile.

## Finding Your Chrome Profile Path

| OS | Default path |
|----|-------------|
| macOS | `~/Library/Application Support/Google/Chrome` |
| Linux | `~/.config/google-chrome` |
| Windows | `%LOCALAPPDATA%\Google\Chrome\User Data` |

For a specific Chrome profile (e.g. "Profile 2"), append the profile name:

```
~/Library/Application Support/Google/Chrome/Profile 2
```

Check `chrome://version` in your browser to see the exact profile path.

## Safety Guarantees

| Guarantee | Details |
|-----------|---------|
| Profile directory never deleted | `close()` shuts down the browser process but never removes the profile directory |
| Clone mode is isolated | The original profile is copied, never written to |
| Attached modes don't close external Chrome | `close()` in `attached_cdp` or `attached_context` mode only disconnects |
| Force close is explicit | `force_close_browser()` must be called deliberately |

## Common Pitfalls

### Profile lock conflicts

Chrome locks the profile directory when running. If another Chrome instance is using the same profile, launch will fail or produce warnings.

**Fix:** Close all other Chrome instances using the same profile before launching. The runtime detects lock files and warns you.

### Headless detection with profiles

Some sites detect headless Chrome even with a real profile. The profile provides cookies and auth, but the browser fingerprint still looks headless.

**Fix:** Use `headful=True`. This is the default for a reason — real-world sites with auth flows almost always have bot detection.

### Stale sessions in persistent profiles

If a persistent profile contains expired session tokens, the site may redirect to a login page. The observation will show the login form, not the authenticated content.

**Fix:** Check `obs.page.url` after navigation. If it's a login redirect, the agent needs to re-authenticate or use a fresh profile.

### Large profile directories

Full Chrome profiles can be several GB. Clone mode copies the entire directory, which takes time.

**Fix:** For frequently-cloned profiles, create a minimal profile with only the needed extensions and auth state. Or use storage state if extensions aren't required.
