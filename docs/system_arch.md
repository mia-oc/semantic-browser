# System Architecture: Semantic Browser Runtime

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        EXTERNAL PLANNERS                            │
│  Claude Code  │  Codex  │  Cursor  │  Custom Agent  │  MCP Adapter │
└──────┬────────┴────┬────┴─────┬────┴───────┬────────┴──────┬───────┘
       │             │          │            │               │
       ▼             ▼          ▼            ▼               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   EXTERNAL INTERFACE LAYER                           │
│                                                                     │
│  ┌──────────────┐  ┌──────────────────┐  ┌───────────────────────┐ │
│  │  Python API   │  │  HTTP/WS Service  │  │        CLI            │ │
│  │              │  │  (FastAPI)        │  │  (Click)              │ │
│  │ observe()    │  │ POST /observe     │  │ semantic-browser      │ │
│  │ inspect()    │  │ POST /inspect     │  │   observe             │ │
│  │ act()        │  │ POST /act         │  │   act                 │ │
│  │ navigate()   │  │ POST /navigate    │  │   inspect             │ │
│  │ diagnostics()│  │ GET  /diagnostics │  │   diagnostics         │ │
│  └──────┬───────┘  └────────┬─────────┘  └──────────┬────────────┘ │
│         │                   │                        │              │
│         └───────────────────┼────────────────────────┘              │
│                             │                                       │
│                             ▼                                       │
│              ┌──────────────────────────┐                           │
│              │  SemanticBrowserRuntime   │                           │
│              │  (Core orchestrator)      │                           │
│              └─────────────┬────────────┘                           │
└────────────────────────────┼────────────────────────────────────────┘
                             │
       ┌─────────────────────┼─────────────────────┐
       │                     │                     │
       ▼                     ▼                     ▼
┌─────────────┐   ┌──────────────────┐   ┌────────────────┐
│  EXTRACTION │   │    EXECUTION     │   │   TELEMETRY    │
│    LAYER    │   │      LAYER       │   │     LAYER      │
│             │   │                  │   │                │
│ settle      │   │ validation       │   │ trace          │
│ page_state  │   │ resolver         │   │ replay         │
│ ax_snapshot │   │ actions          │   │ debug_dump     │
│ dom_snapshot│   │ results          │   │                │
│ visibility  │   │                  │   └────────────────┘
│ labels      │   └────────┬─────────┘
│ semantics   │            │
│ grouping    │            │
│ blockers    │            │
│ classifier  │            │
│ ids         │            │
│ diff        │            │
│ engine      │            │
└──────┬──────┘            │
       │                   │
       └─────────┬─────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    BROWSER EXECUTION LAYER                           │
│                                                                     │
│  ┌──────────────────────────────┐  ┌─────────────────────────────┐ │
│  │       MANAGED MODE           │  │       ATTACHED MODE          │ │
│  │                              │  │                             │ │
│  │  BrowserManager              │  │  from_page(page)            │ │
│  │  ├── Playwright launch       │  │  from_context(ctx)          │ │
│  │  ├── Chromium process        │  │  from_cdp_endpoint(ws)      │ │
│  │  ├── Context management      │  │                             │ │
│  │  ├── Page lifecycle          │  │  No browser ownership       │ │
│  │  └── Clean shutdown          │  │  No lifecycle management    │ │
│  │                              │  │  Read-only attachment       │ │
│  │  ManagedSession.launch()     │  │                             │ │
│  └──────────────────────────────┘  └─────────────────────────────┘ │
│                                                                     │
│                        Playwright Async API                         │
│                              │                                      │
│                              ▼                                      │
│                      ┌──────────────┐                               │
│                      │   Chromium    │                               │
│                      │   Browser     │                               │
│                      └──────────────┘                               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Extraction Pipeline

```
                    LIVE RENDERED PAGE
                          │
                          ▼
              ┌───────────────────────┐
              │   settle.py           │
              │   Wait for page to    │
              │   become usable       │
              │                       │
              │   readyState ─────┐   │
              │   no navigation ──┤   │
              │   mutation quiet ──┤   │
              │   interactables ──┤   │
              │   stable ─────────┘   │
              └───────────┬───────────┘
                          │ Page settled
                          ▼
         ┌────────────────┼────────────────┐
         │                │                │
         ▼                ▼                ▼
   ┌───────────┐   ┌───────────┐   ┌───────────┐
   │ AX Tree   │   │ DOM Snap  │   │ Visibility │
   │ Capture   │   │ Capture   │   │ Compute    │
   └─────┬─────┘   └─────┬─────┘   └─────┬─────┘
         │                │                │
         └────────────────┼────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │   labels.py           │
              │   Resolve names for   │
              │   all elements        │
              └───────────┬───────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │   semantics.py        │
              │   Classify roles      │
              │   and types           │
              └───────────┬───────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │   grouping.py         │
              │   Detect regions +    │
              │   content groups      │
              └───────────┬───────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │   blockers.py         │
              │   Detect overlays,    │
              │   modals, login walls │
              └───────────┬───────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │   classifier.py       │
              │   Classify page type  │
              └───────────┬───────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │   ids.py              │
              │   Generate stable IDs │
              │   + match previous    │
              └───────────┬───────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │   diff.py             │
              │   Compute delta from  │
              │   previous canonical  │
              └───────────┬───────────┘
                          │
                          ▼
                   OBSERVATION
              (mode-filtered output)
```

---

## 3. Action Execution Flow

```
        ActionRequest
             │
             ▼
    ┌────────────────┐
    │  validation.py  │
    │                │
    │  Action exists? ├──No──► InvalidResult
    │  Target live?  ├──No──► StaleResult
    │  Visible?      ├──No──► BlockedResult
    │  Enabled?      ├──No──► BlockedResult
    └───────┬────────┘
            │ Valid
            ▼
    ┌────────────────┐
    │  resolver.py    │
    │                │
    │  1. role+name  │
    │  2. label      │
    │  3. test-id    │
    │  4. CSS        │──► LocatorRecipe
    │  5. text       │
    │  6. ancestry   │
    │  7. positional │
    └───────┬────────┘
            │ Resolved
            ▼
    ┌────────────────┐
    │  actions.py     │
    │                │
    │  op → Playwright│──► Execute
    │  method mapping │
    └───────┬────────┘
            │ Executed
            ▼
    ┌────────────────┐
    │  settle.py      │
    │  Wait for page  │
    │  to re-settle   │
    └───────┬────────┘
            │ Settled
            ▼
    ┌────────────────┐
    │  Re-observe     │
    │  (delta mode)   │
    └───────┬────────┘
            │
            ▼
    ┌────────────────┐
    │  results.py     │
    │                │
    │  Classify:      │
    │  success        │
    │  failed         │
    │  blocked        │──► StepResult
    │  stale          │
    │  invalid        │
    │  ambiguous      │
    │                │
    │  Side effects:  │
    │  navigation     │
    │  value_change   │
    │  modal_change   │
    └────────────────┘
```

---

## 4. Stable ID Matching

```
    Previous Canonical          New Extraction
    ┌──────────────┐            ┌──────────────┐
    │ Element A    │            │ Element X    │
    │  fp: [...]   │            │  fp: [...]   │
    │ Element B    │◄──match───►│ Element Y    │
    │  fp: [...]   │            │  fp: [...]   │
    │ Element C    │            │ Element Z    │
    │  fp: [...]   │            │  fp: [...]   │
    └──────────────┘            │ Element W    │ ← new
                                │  fp: [...]   │
                                └──────────────┘

    Fingerprint = weighted hash of:
    ┌─────────────────────┬────────┐
    │ Frame chain         │  0.10  │
    │ Role                │  0.20  │
    │ Accessible name     │  0.25  │
    │ Label text          │  0.15  │
    │ Tag + type          │  0.05  │
    │ Ancestry signature  │  0.10  │
    │ Nearby heading      │  0.10  │
    │ Ordinal position    │  0.05  │
    └─────────────────────┴────────┘

    Match threshold: 0.70
    Above → same ID preserved
    Below → new ID assigned
```

---

## 5. Module Dependency Graph

```
                    __init__.py
                        │
            ┌───────────┼───────────┐
            │           │           │
            ▼           ▼           ▼
        runtime.py   session.py  browser_manager.py
            │           │           │
            │           └─────┬─────┘
            │                 │
            ▼                 ▼
    ┌───────────────────────────────┐
    │         config.py             │
    │         models.py             │
    │         errors.py             │
    └───────────────────────────────┘
            │
    ┌───────┴────────────────────┐
    │                            │
    ▼                            ▼
  extractor/                executor/
  ├── engine.py             ├── validation.py
  │   ├── settle.py         ├── resolver.py
  │   ├── page_state.py     ├── actions.py
  │   ├── ax_snapshot.py    └── results.py
  │   ├── dom_snapshot.py
  │   ├── visibility.py     profiles/
  │   ├── labels.py         ├── base.py
  │   ├── semantics.py      ├── registry.py
  │   ├── grouping.py       ├── generic.py
  │   ├── blockers.py       └── common_patterns.py
  │   ├── classifier.py
  │   ├── ids.py            telemetry/
  │   └── diff.py           ├── trace.py
  │                         ├── replay.py
  │                         └── debug_dump.py
  │
  service/                  cli/
  ├── server.py             ├── main.py
  ├── routes.py             └── commands.py
  └── schemas.py
```

---

_Continued in [system_arch_data.md](system_arch_data.md) — sections 6-9
covering data model, session lifecycle, token economy, and technology
boundaries._
