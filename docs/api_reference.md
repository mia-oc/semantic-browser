# API Reference

Complete reference for every public class, method, and model in Semantic Browser.

## Package Exports

```python
from semantic_browser import (
    AgentSession,      # v1.4: one-string verbs ("goto", "click 7", ...) -> text; see agent_cli.md
    ManagedSession,
    SemanticBrowserRuntime,
    RuntimeConfig,
    ActionRequest,
    Observation,
    StepResult,
    __version__,
)
```

---

## ManagedSession

The recommended entry point. Manages browser lifecycle (launch, close) and exposes the runtime.

### `ManagedSession.launch(...)`

```python
session = await ManagedSession.launch(
    headful=True,              # Show browser window (False for headless)
    profile_mode="ephemeral",  # "ephemeral" | "persistent" | "clone"
    profile_dir=None,          # Path to Chromium profile directory
    storage_state_path=None,   # Path to Playwright storage state JSON
    browser_path=None,         # Custom Chromium binary path
    config=None,               # RuntimeConfig instance
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `headful` | `bool` | `True` | `True` shows the browser window. `False` runs headless. Use `True` for sites with bot detection. |
| `profile_mode` | `str` | `"ephemeral"` | Browser profile strategy. See [Runtime Modes](runtime_modes.md). |
| `profile_dir` | `str \| None` | `None` | Path to a Chromium user data directory. Required for `persistent` and `clone` modes. |
| `storage_state_path` | `str \| None` | `None` | Path to a Playwright storage state JSON file. Lightweight cookie/localStorage bootstrap for `ephemeral` mode. |
| `browser_path` | `str \| None` | `None` | Path to a custom Chromium binary. If `None`, uses the Playwright-managed browser. |
| `config` | `RuntimeConfig \| None` | `None` | Runtime configuration overrides. |

**Returns:** `ManagedSession`

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `session.runtime` | `SemanticBrowserRuntime` | The runtime instance for this session. |

### Methods

| Method | Description |
|--------|-------------|
| `await session.new_page()` | Open a new browser tab in this session's context. |
| `await session.close()` | Close the session and browser (respects ownership mode). |

---

## AgentSession (v1.4)

Verb layer shared by the `sb` CLI and the daemon. Returns text, never raises for page problems.

```python
s = await AgentSession.launch(headful=True, profile_dir=None, cdp=None, lite="off", budget=None)
text = await s.run('type 3 "hello" --enter')      # same strings as the CLI; str or list[str]
await s.close()
```

| Member | Description |
|--------|-------------|
| `launch(*, headful, profile_dir, profile_mode, cdp, name, lite, budget)` | Start a managed browser, or attach with `cdp="http://127.0.0.1:9222"` (a dedicated tab is opened; only it is closed on exit). |
| `run(line)` | Execute one verb (see [agent_cli.md](agent_cli.md)). Output = outcome line + page view. |
| `runtime` | The underlying `SemanticBrowserRuntime` (e.g. `rerender(page=2)`). |
| `close()` | Close the session. |

---

## SemanticBrowserRuntime

The core runtime. All observation, action, and navigation methods live here.

### Construction

Normally obtained via `ManagedSession.launch().runtime`. Can also be created directly for attach scenarios:

```python
# From an existing Playwright page
runtime = SemanticBrowserRuntime.from_page(page)

# From an existing Playwright browser context
runtime = SemanticBrowserRuntime.from_context(context)

# From a CDP endpoint (remote Chrome)
runtime = await SemanticBrowserRuntime.from_cdp_endpoint(
    "ws://127.0.0.1:9222/devtools/browser/XXXXX",
    target_url_contains="example.com",  # pick tab by URL substring
    page_index=0,                        # or pick tab by index
    prefer_non_blank=True,               # skip about:blank tabs
)
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `runtime.session_id` | `str` | UUID for this runtime session. |
| `runtime.ownership_mode` | `OwnershipMode` | One of `owned_ephemeral`, `owned_persistent_profile`, `attached_context`, `attached_cdp`. |

### `observe(mode, *, expanded)`

Capture the current page state as a structured observation.

```python
obs = await runtime.observe(mode="summary", expanded=False)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mode` | `str` | `"summary"` | `"summary"`, `"full"`, `"delta"`, `"auto"`, or `"debug"` |
| `expanded` | `bool` | `False` | If `True`, show all actions (equivalent to `more`). |

**Returns:** `Observation`

The runtime automatically retries up to 3 times if the page has no visible nodes (handles late-loading SPAs).

### `act(request)`

Execute a single action on the page.

```python
result = await runtime.act(ActionRequest(action_id="act-XXXX-0", value="optional"))
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `request` | `ActionRequest` | The action to execute. |

**Returns:** `StepResult` (includes post-action observation and delta)

The action lifecycle: resolve action → execute on page → wait for settle → observe delta → classify status.

### `inspect(target_id, mode)`

Get detailed information about a specific element.

```python
details = await runtime.inspect("target-id")
```

**Returns:** `dict` with `kind` (`"region"`, `"form"`, `"content_group"`, `"action"`, or `"unknown"`) and the full model dump.

### `navigate(url)`

Navigate to a URL.

```python
result = await runtime.navigate("https://example.com")
```

**Returns:** `StepResult`

### `back()` / `forward()` / `reload()`

Browser history navigation.

```python
result = await runtime.back()
result = await runtime.forward()
result = await runtime.reload()
```

**Returns:** `StepResult`

### `diagnostics()`

Get runtime health information.

```python
report = await runtime.diagnostics()
```

**Returns:** `DiagnosticsReport`

### `export_trace(path)`

Export the full event trace to a JSON file.

```python
file_path = await runtime.export_trace("trace.json")
```

**Returns:** `str` (the written file path)

### `close()`

Close the runtime. Behavior depends on ownership mode:

- `owned_ephemeral` / `owned_persistent_profile`: closes browser process.
- `attached_context` / `attached_cdp`: does **not** close the external browser (emits a warning).

### `force_close_browser()`

Forcibly close the browser regardless of ownership mode. Use only when you explicitly own the external browser.

---

## Models

All models are Pydantic `BaseModel` subclasses defined in `semantic_browser.models`.

### Observation

The primary output of `observe()`. Contains everything the planner needs.

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | `str` | Session identifier |
| `timestamp` | `datetime` | When the observation was captured |
| `mode` | `ObservationMode` | The observation mode used |
| `page` | `PageInfo` | Current page metadata |
| `summary` | `PageSummary` | Headline and key points |
| `blockers` | `list[Blocker]` | Active blockers (cookie banners, modals, anti-bot) |
| `warnings` | `list[WarningNotice]` | Non-blocking warnings |
| `regions` | `list[RegionSummary]` | Semantic page regions |
| `forms` | `list[FormSummary]` | Detected forms |
| `content_groups` | `list[ContentGroupSummary]` | Grouped content (lists, cards, tables) |
| `available_actions` | `list[ActionDescriptor]` | All available actions |
| `planner` | `PlannerView \| None` | Planner-optimized view with room text |
| `metrics` | `ObservationMetrics` | Extraction performance metrics |
| `confidence` | `ConfidenceReport` | Extraction quality scores |

### PageInfo

| Field | Type | Description |
|-------|------|-------------|
| `url` | `str` | Current page URL |
| `title` | `str` | Page title |
| `domain` | `str` | Domain name |
| `page_type` | `str` | Classified page type |
| `page_identity` | `str` | Stable page identity (URL + title hash) |
| `ready_state` | `str` | Document ready state |
| `modal_active` | `bool` | Whether a modal is currently covering the page |
| `frame_count` | `int` | Number of frames on the page |
| `profile_name` | `str \| None` | Active profile name, if any |

### ActionDescriptor

Full action metadata. The `available_actions` list in `Observation` contains these.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Stable action identifier (e.g. `act-8f2a2d1c-0`) |
| `op` | `str` | Operation type: `open`, `click`, `fill`, `select_option`, `toggle`, `submit`, `back`, `forward`, `reload`, `wait`, `navigate` |
| `label` | `str` | Human-readable label for the action target |
| `target_id` | `str \| None` | Element ID this action targets |
| `region_id` | `str \| None` | Region containing this action |
| `enabled` | `bool` | Whether the action is currently executable |
| `requires_value` | `bool` | Whether the action needs a `value` argument |
| `value_schema` | `dict \| None` | Schema describing the expected value format |
| `destructive` | `bool` | Whether the action has destructive side effects |
| `navigational` | `bool` | Whether the action causes page navigation |
| `primary` | `bool` | Whether this is a primary/CTA action |
| `confidence` | `float` | Extraction confidence for this action (0.0–1.0) |
| `locator_recipe` | `dict` | Internal locator data (for the executor, not the planner) |
| `ref` | `int \| None` | v1.4: the number printed in the view (`[7]`); unique for the whole session, never reused after navigation |
| `kind` | `str \| None` | v1.4: `link`, `button`, `input`, `select`, `checkbox`, `radio`, `switch`, `combobox`, … |
| `context` | `str \| None` | v1.4: disambiguating text for duplicate labels |
| `value` | `Any \| None` | v1.4: current value of inputs/selects |

### ActionRequest

Input to `runtime.act()`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `action_id` | `str \| None` | `None` | The action ID to execute |
| `op` | `str \| None` | `None` | Operation type (alternative to action_id for global ops) |
| `target_id` | `str \| None` | `None` | Target element ID |
| `value` | `Any \| None` | `None` | Value for fill/select/navigate actions |
| `options` | `dict` | `{}` | Additional options |
| `expectation` | `str \| None` | `None` | Description of expected outcome |

### StepResult

Output of `runtime.act()`, `navigate()`, `back()`, `forward()`, `reload()`.

| Field | Type | Description |
|-------|------|-------------|
| `request` | `ActionRequest` | The original request |
| `status` | `StepStatus` | `"success"`, `"failed"`, `"blocked"`, `"stale"`, `"invalid"`, `"ambiguous"` |
| `message` | `str \| None` | Human-readable status message |
| `outcome` | `str \| None` | v1.4: one line saying what the action did and what changed (`-> now at …`, `overlay dismissed`, `page changed (+3/-1 lines): …`) |
| `execution` | `ExecutionResult` | Detailed execution outcome |
| `observation` | `Observation` | Post-action observation |
| `delta` | `ObservationDelta \| None` | What changed |

### ExecutionResult

| Field | Type | Description |
|-------|------|-------------|
| `op` | `str` | The operation that was executed |
| `ok` | `bool` | Whether execution succeeded at the DOM level |
| `started_at` | `datetime` | Execution start time |
| `ended_at` | `datetime` | Execution end time |
| `message` | `str \| None` | Execution message |
| `caused_navigation` | `bool` | Whether a page navigation occurred |
| `caused_modal_change` | `bool` | Whether a modal appeared or disappeared |
| `caused_value_change` | `bool` | Whether form values changed |
| `effect` | `StepEffect` | `"navigation"`, `"state_change"`, `"content_change"`, `"none"` |
| `evidence` | `dict` | Additional evidence (screenshots, DOM changes) |

### ObservationDelta

Describes what changed between two observations.

| Field | Type | Description |
|-------|------|-------------|
| `changed_values` | `dict` | Form field or content values that changed |
| `added_blockers` | `list[Blocker]` | Newly appeared blockers |
| `removed_blocker_kinds` | `list[str]` | Blockers that were dismissed |
| `enabled_actions` | `list[str]` | Action IDs that became available |
| `disabled_actions` | `list[str]` | Action IDs that disappeared |
| `changed_regions` | `list[str]` | Region IDs that changed |
| `page_identity_changed` | `bool` | Whether the page navigated |
| `navigated` | `bool` | Whether URL changed |
| `materiality` | `DeltaMateriality` | `"minor"`, `"moderate"`, or `"major"` |
| `notes` | `list[str]` | Human-readable change descriptions |

### PlannerView

The planner-optimized observation view. Access via `observation.planner`.

| Field | Type | Description |
|-------|------|-------------|
| `location` | `str` | Page title and domain |
| `what_you_see` | `list[str]` | Prose descriptions |
| `available_actions` | `list[PlannerAction]` | Curated action list |
| `blockers` | `list[str]` | Active blocker descriptions |
| `room_text` | `str` | Full text-adventure room description |
| `has_more_actions` | `bool` | Whether `more` would reveal additional actions |
| `total_action_count` | `int` | Total enabled actions on the page |

### PlannerAction

Simplified action for the planner (subset of `ActionDescriptor`).

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Action identifier |
| `label` | `str` | Human-readable label |
| `op` | `str` | Operation type |

### Blocker

| Field | Type | Description |
|-------|------|-------------|
| `kind` | `str` | Blocker type (e.g. `cookie_consent`, `modal_overlay`, `anti_bot`) |
| `severity` | `str` | `"low"`, `"medium"`, or `"high"` |
| `description` | `str` | Human-readable description |
| `related_action_ids` | `list[str]` | Actions that can dismiss this blocker |

### DiagnosticsReport

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | `str` | Session identifier |
| `managed` | `bool` | Whether this is a managed session |
| `attached_kind` | `str` | How the runtime was attached |
| `ownership_mode` | `OwnershipMode` | Ownership semantics |
| `current_url` | `str` | Current page URL |
| `last_observation_at` | `datetime \| None` | Last observation timestamp |
| `trace_events` | `int` | Number of trace events recorded |
| `healthy` | `bool` | Whether the runtime is healthy |
| `notes` | `list[str]` | Diagnostic notes and warnings |

### ConfidenceReport

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `overall` | `float` | `0.8` | Overall extraction confidence (0.0–1.0) |
| `extraction` | `float` | `0.8` | Element discovery quality |
| `grouping` | `float` | `0.8` | Region/form grouping quality |
| `actionability` | `float` | `0.8` | Action surface quality |
| `stability` | `float` | `0.8` | Page layout stability |
| `reasons` | `list[str]` | `[]` | Human-readable confidence notes |

---

## Configuration

### RuntimeConfig

Top-level configuration container. All fields have sensible defaults.

```python
from semantic_browser import RuntimeConfig

config = RuntimeConfig(
    settle=SettleConfig(max_settle_ms=20000),
    extraction=ExtractionConfig(max_elements=6000),
    redaction=RedactionConfig(enabled=True),
    telemetry=TelemetryConfig(enabled=True),
    lite="off",   # v1.4: "off" | "media" | "max" — skip images/fonts/video (+ trackers); experimental, see benchmarks
)
```

### SettleConfig

Controls how long the runtime waits for pages to stabilize before extraction.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `mode` | `str` | `"fast"` | `"fast"` (event-driven: DOM quiet + in-flight requests, ~100–250 ms) or `"legacy"` (v1.3 polling loops) |
| `quiet_ms` | `int` | `80` | v1.4: DOM must be mutation-free this long |
| `net_quiet_ms` | `int` | `100` | v1.4: no in-flight document/xhr/fetch/script for this long |
| `action_cap_ms` / `navigation_cap_ms` / `observe_cap_ms` | `int` | `2500` / `5000` / `800` | v1.4: hard caps per settle |
| `grace_ms` / `grace_cap_ms` | `int` | `350` / `700` | v1.4: extra wait when a click/submit visibly changed nothing (timer-driven renders) |
| `mutation_quiet_ms` | `int` | `300` | (legacy) ms of DOM quiet before considering settled |
| `interactable_stable_ms` | `int` | `200` | ms of stable interactable count |
| `layout_stable_ms` | `int` | `150` | ms of stable layout |
| `max_settle_ms` | `int` | `15000` | Maximum settle wait |
| `settle_tolerance_pct` | `float` | `0.05` | Fuzzy tolerance for element count changes (5%) |

### ExtractionConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `engine` | `str` | `"v2"` | v1.4 single-pass page view (shadow DOM, cross-origin frames, numbered refs). `"legacy"` restores the v1.3 extractor and room text |
| `view_budget` | `int` | `5000` | v1.4: characters of page view per observation (`~1250` tokens). 2500 halves cost with equal success on the benchmark set |
| `include_frames` | `bool` | `True` | Extract from iframes |
| `max_elements` | `int` | `4000` | Maximum elements to process |
| `content_group_min_items` | `int` | `3` | Minimum items to form a content group |

### RedactionConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | `bool` | `True` | Enable value redaction in traces |
| `expose_secrets` | `bool` | `False` | If `True`, secrets are not redacted (dev only) |

### TelemetryConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | `bool` | `True` | Enable trace collection |
| `trace_dir` | `str \| None` | `None` | Directory for trace files |
| `max_events` | `int` | `1000` | Maximum trace events to keep in memory |

---

## Errors

All errors inherit from `SemanticBrowserError`.

| Exception | When |
|-----------|------|
| `BrowserNotReadyError` | Page or browser objects are unavailable |
| `SessionNotFoundError` | Session ID not found (service mode) |
| `ActionNotFoundError` | Action ID doesn't match any known action |
| `ActionStaleError` | Action target no longer exists on the page |
| `ElementGoneError` | v1.4 (subclass of `ActionStaleError`): the exact element a ref pointed at was removed/re-rendered |
| `ActionExecutionError` | Action failed during DOM execution (v1.4: also raised instead of silently targeting `<body>`) |
| `SettleTimeoutError` | Page failed to stabilize within `max_settle_ms` |
| `ExtractionError` | Extraction pipeline failed |
| `PageUnreliableError` | Page quality too low for deterministic operation |
| `AttachmentError` | Could not attach to browser/page/CDP endpoint |

---

## Type Aliases

| Alias | Values |
|-------|--------|
| `ObservationMode` | `"summary"`, `"full"`, `"delta"`, `"debug"`, `"auto"` |
| `StepStatus` | `"success"`, `"failed"`, `"blocked"`, `"stale"`, `"invalid"`, `"ambiguous"` |
| `OwnershipMode` | `"owned_ephemeral"`, `"owned_persistent_profile"`, `"attached_context"`, `"attached_cdp"` |
| `DeltaMateriality` | `"minor"`, `"moderate"`, `"major"` |
| `StepEffect` | `"navigation"`, `"state_change"`, `"content_change"`, `"none"` |
