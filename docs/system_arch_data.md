# System Architecture: Data Model & Lifecycle

_Continuation of `system_arch.md`. Covers data model, session lifecycle,
token economy, and technology boundaries._

---

## 6. Data Model Overview

```
Observation
├── session_id: str
├── timestamp: datetime
├── mode: str
├── page: PageInfo
│   ├── url, title, domain
│   ├── page_type, page_identity
│   ├── ready_state, modal_active
│   └── frame_count, profile_name
├── summary: PageSummary
├── blockers: list[Blocker]
│   ├── kind, severity
│   ├── description
│   └── related_action_ids
├── warnings: list[WarningNotice]
├── regions: list[RegionSummary]
│   ├── id, kind, name
│   ├── frame_id, order
│   ├── visible, in_viewport
│   ├── interactable_count
│   └── primary_action_ids
├── forms: list[FormSummary]
│   ├── id, name, frame_id
│   ├── field_ids, submit_action_ids
│   ├── validity
│   └── required_missing
├── content_groups: list[ContentGroupSummary]
│   ├── id, kind, name
│   ├── item_count
│   └── preview_items: list[ContentItemPreview]
│       ├── id, title, subtitle
│       ├── badges, key_values
│       └── open_action_id
├── available_actions: list[ActionDescriptor]
│   ├── id, op, label
│   ├── target_id, region_id
│   ├── enabled, requires_value
│   ├── destructive, navigational
│   ├── primary
│   └── confidence
├── metrics: ObservationMetrics
└── confidence: ConfidenceReport
```

---

## 7. Session Lifecycle

### Managed Mode

```
ManagedSession.launch()
    │
    ├── Playwright.start()
    ├── Browser.launch(chromium, headful=True)
    ├── Context.new(user_data_dir?)
    ├── Page.new()
    ├── SemanticBrowserRuntime.from_page(page)
    │
    ▼
  ACTIVE SESSION
    │
    ├── navigate(), observe(), act(), inspect()
    │
    ▼
ManagedSession.close()
    │
    ├── Runtime.close()
    ├── Context.close()
    ├── Browser.close()
    └── Playwright.stop()
```

### Attached Mode

```
SemanticBrowserRuntime.from_page(existing_page)
    │
    ├── Wrap page reference
    ├── No browser ownership
    │
    ▼
  ACTIVE RUNTIME
    │
    ├── navigate(), observe(), act(), inspect()
    │
    ▼
Runtime.close()
    │
    ├── Detach from page
    ├── Clean up internal state
    └── Do NOT close browser/page
```

---

## 8. Token Economy Strategy

```
First page load:
    observe(mode="full")  ──► ~2-4KB structured JSON

Routine turns:
    act(action)
        └── returns StepResult with:
            └── observation: delta  ──► ~0.2-0.8KB

Escalation triggers for full re-observation:
    ├── Page identity changed (navigation)
    ├── Confidence dropped below threshold
    ├── Blocker appeared/disappeared
    ├── Large structural change detected
    └── Caller explicitly requests full mode

Inspection (on-demand detail):
    inspect(target_id)  ──► ~0.5-1KB focused detail
```

---

## 9. Technology Boundaries

```
┌─ semantic-browser (core) ──────────────────────────┐
│  pydantic v2                                        │
│  standard library (asyncio, json, re, etc.)        │
│  No playwright dependency                          │
│  No browser dependency                             │
│  Models, config, errors, extraction logic          │
└────────────────────────────────────────────────────┘

┌─ semantic-browser[managed] ────────────────────────┐
│  playwright                                         │
│  Browser lifecycle management                       │
│  Chromium installation tooling                      │
└────────────────────────────────────────────────────┘

┌─ semantic-browser[server] ─────────────────────────┐
│  fastapi                                            │
│  uvicorn                                            │
│  HTTP/WebSocket transport layer                     │
└────────────────────────────────────────────────────┘

┌─ semantic-browser[full] ───────────────────────────┐
│  All of the above                                   │
│  CLI tooling (click)                                │
│  Development utilities                              │
└────────────────────────────────────────────────────┘
```
