# Planner Contract

This document defines the exact interface between Semantic Browser and an LLM planner. If you are building an agent that drives a browser via Semantic Browser, this is your primary reference.

## Core Loop

Every interaction follows one cycle:

```
observe → planner decides → act → observe delta → repeat
```

The runtime produces an **observation** (a structured text "room"). The planner reads it, picks **one action ID**, and the runtime executes it deterministically. The planner then receives a **delta observation** showing what changed. This repeats until the task is complete.

## What the Planner Receives

Each observation contains a `planner` field of type `PlannerView`. The most important field is `room_text` — a compact, plain-text description of the current page state. This is what you feed into the LLM context.

### Room Text Format

```
@ Page Title (domain.com)
> Prose description of visible content. Main content: "Top Stories". Navigation: News, Sport.
! Cookie consent banner detected -> dismiss [act-a1b2c3d4-0]
1 open "News" [act-8f2a2d1c-0]
2 open "Sport" [act-c3e119fa-0]
3 fill Search BBC [act-0b9411de-0] *value
4 click "Accept All" [act-a1b2c3d4-0]
+ 28 more [more]
```

**Line-by-line breakdown:**

| Prefix | Meaning |
|--------|---------|
| `@` | Current page location (title + domain) |
| `>` | Narrative description of visible content |
| `!` | Blocker (e.g. cookie banner, modal) with optional dismiss hint |
| `N` | Numbered action — `index op "label" [action_id]` |
| `*value` | This action requires a value argument (e.g. text to type) |
| `+` | Hidden actions available via `more` |

### PlannerView Fields

| Field | Type | Purpose |
|-------|------|---------|
| `location` | `str` | Page title and domain |
| `what_you_see` | `list[str]` | Prose descriptions of visible content |
| `available_actions` | `list[PlannerAction]` | Curated actions (id, label, op) |
| `blockers` | `list[str]` | Active blockers (cookie banners, modals, anti-bot) |
| `room_text` | `str` | The full text-adventure room description |
| `has_more_actions` | `bool` | Whether hidden actions exist beyond the curated set |
| `total_action_count` | `int` | Total enabled actions on the page |

## What the Planner Should Reply With

The planner's output must be **one of these**:

| Reply | When to use | How to execute |
|-------|-------------|----------------|
| An action ID (e.g. `act-8f2a2d1c-0`) | To interact with an element | `runtime.act(ActionRequest(action_id="act-8f2a2d1c-0"))` |
| An action ID + value | For fill/select actions marked `*value` | `runtime.act(ActionRequest(action_id="act-0b9411de-0", value="search term"))` |
| `more` | When the target action isn't in the curated list | `runtime.act(ActionRequest(action_id="more"))` |
| `back` | To go back in browser history | `runtime.back()` |
| `fwd` | To go forward in browser history | `runtime.forward()` |
| `reload` | To reload the current page | `runtime.reload()` |
| `nav` + URL | To navigate to a specific URL | `runtime.navigate("https://...")` |
| `done` | Task is complete | Exit the loop |

**The planner should never output free-form browser commands, HTML selectors, or JavaScript. Only action IDs.**

## When to Use `more`

The room shows the top 25 curated actions. If the planner's target is not visible:

1. Reply with `more` to expand the full action list.
2. The next observation will show ALL enabled actions.
3. If the target is still not found after `more`, try `nav` to a direct URL, or `back` to try a different path.

`more` is idempotent — calling it twice returns the same expanded list with a hint to choose from it.

## When to Use `inspect`

Use `inspect` to get detailed information about a specific element, region, form, or content group before acting:

```python
details = await runtime.inspect("target-id")
```

This is useful when the room description doesn't provide enough detail to make a confident decision — for example, to see all fields in a form or all items in a content group.

## Handling Blockers

Blockers appear as `!` lines in the room text. Common blockers:

| Blocker | Meaning | What to do |
|---------|---------|------------|
| Cookie consent | Cookie/consent banner detected | Use the dismiss action ID shown in the `->` hint |
| Modal overlay | A dialog/modal is covering the page | Dismiss it or interact with it |
| Anti-bot challenge | CAPTCHA or bot detection | Capture evidence, try alternative path, or signal human intervention |
| Page unreliable | Extraction confidence is very low | Retry `observe`, or `reload`, or `nav` to a simpler page |

Always resolve blockers before attempting other actions. The dismiss hint (`-> dismiss [action_id]`) tells you exactly which action to use.

## Handling Failures

After `act()`, check `StepResult.status`:

| Status | Meaning | Recovery |
|--------|---------|----------|
| `success` | Action executed and page changed as expected | Continue with next step |
| `failed` | Action execution threw an error | Retry once, then try alternative action |
| `blocked` | A new blocker appeared (modal, overlay) | Dismiss the blocker first |
| `stale` | The action target no longer exists on the page | Re-observe and pick a fresh action |
| `invalid` | The action ID doesn't exist | Re-observe; the page likely changed |
| `ambiguous` | Outcome unclear | Re-observe to check current state |

## Stopping Conditions

The planner should stop the loop when:

1. **Task complete** — the goal state has been reached (confirmed via observation).
2. **Stuck** — the same observation repeats 3+ times with no progress.
3. **Hard blocker** — anti-bot/CAPTCHA with no automated path and no alternative route.
4. **Max steps** — a configurable safety limit (recommended: 20-30 steps for most tasks).

## Observation Modes

| Mode | Use case | Token cost |
|------|----------|------------|
| `summary` | Default. Top-scope elements, compact. | Lowest |
| `full` | All elements, all regions. | Higher |
| `delta` | Only what changed since last observation. | Very low |
| `auto` | Runtime picks `summary` or `full` based on page quality. | Varies |
| `debug` | Full extraction with diagnostics. | Highest |

For most agent loops, use `summary` for the initial observation and `delta` comes automatically after each `act()`.

## Recommended System Prompt

Here is a reference system prompt for an LLM planner using Semantic Browser:

```
You are a browser automation agent. You receive a text description of the current
web page (a "room") and must reply with exactly ONE action to take.

Rules:
- Reply with a single action ID from the available actions list, nothing else.
- If an action requires a value (marked *value), reply: action_id|value
- If your target is not in the curated list, reply: more
- If the task is complete, reply: done
- If stuck, reply: back (to try a different path)
- Always dismiss blockers (cookie banners, modals) before other actions.
- Never output HTML, CSS selectors, or JavaScript.
- Never guess action IDs — only use IDs from the current observation.

Your goal: {task_description}
```

## Delta Observation

After every `act()`, the runtime automatically produces a delta observation. The delta tells the planner:

- `changed_values` — form fields or content that changed
- `added_blockers` / `removed_blocker_kinds` — new or dismissed blockers
- `enabled_actions` / `disabled_actions` — actions that appeared or disappeared
- `changed_regions` — page regions that changed
- `page_identity_changed` — whether the page navigated
- `materiality` — `minor`, `moderate`, or `major` change

Use `materiality` to gauge whether the action had meaningful effect. A `minor` delta after clicking something important suggests the click may not have worked.

## Confidence Reporting

Every observation includes a `confidence` report:

```python
obs.confidence.overall      # 0.0–1.0, overall extraction confidence
obs.confidence.extraction   # quality of element discovery
obs.confidence.grouping     # quality of region/form grouping
obs.confidence.actionability # quality of action surface
obs.confidence.stability    # page layout stability
obs.confidence.reasons      # list of human-readable confidence notes
```

If `overall < 0.5`, the planner should be cautious — consider retrying `observe` or navigating to a simpler page.
