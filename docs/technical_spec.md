# Technical Specification: Semantic Browser Runtime

## 1. Technology Stack

| Component          | Choice                    | Rationale                          |
|--------------------|---------------------------|------------------------------------|
| Language           | Python 3.11+              | Async-first, LLM ecosystem        |
| Browser automation | Playwright (async)        | Best Chromium API, modern, typed   |
| Browser            | Chromium / Chrome          | Single excellent path for v1       |
| Data contracts     | Pydantic v2               | Validation, serialisation, schemas |
| HTTP server        | FastAPI + uvicorn          | Async, OpenAPI, lightweight        |
| CLI framework      | Click                     | Mature, composable, testable       |
| Testing            | pytest + pytest-asyncio    | Standard async Python testing      |
| Packaging          | pyproject.toml + hatch     | Modern Python packaging            |
| Linting            | ruff                       | Fast, comprehensive                |
| Type checking      | mypy (strict)              | Contract safety                    |

---

## 2. Package Structure

```
semantic-browser/
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── LICENSE
├── docs/
│   ├── vision.md
│   ├── requirements.md
│   ├── technical_spec.md
│   ├── project_plan.md
│   ├── system_arch.md
│   └── scratchpad.md
├── src/
│   └── semantic_browser/
│       ├── __init__.py              # Public API re-exports
│       ├── runtime.py               # SemanticBrowserRuntime class
│       ├── session.py               # ManagedSession class
│       ├── browser_manager.py       # Browser lifecycle management
│       ├── models.py                # All Pydantic data contracts
│       ├── config.py                # RuntimeConfig, defaults
│       ├── errors.py                # Custom exception hierarchy
│       │
│       ├── extractor/
│       │   ├── __init__.py
│       │   ├── engine.py            # Extraction orchestrator
│       │   ├── page_state.py        # Raw page state capture
│       │   ├── dom_snapshot.py      # DOM tree snapshot utilities
│       │   ├── ax_snapshot.py       # Accessibility tree snapshot
│       │   ├── visibility.py        # Viewport/visibility computations
│       │   ├── labels.py            # Label/name resolution
│       │   ├── semantics.py         # Semantic role/type classification
│       │   ├── grouping.py          # Region + content group detection
│       │   ├── blockers.py          # Blocker/overlay detection
│       │   ├── classifier.py        # Page type classification
│       │   ├── ids.py               # Stable ID generation + matching
│       │   ├── diff.py              # Canonical model diff / delta
│       │   └── settle.py            # Composite page settle strategy
│       │
│       ├── executor/
│       │   ├── __init__.py
│       │   ├── resolver.py          # Locator strategy resolution
│       │   ├── actions.py           # Action execution pipeline
│       │   ├── validation.py        # Pre-execution validation
│       │   └── results.py           # Result classification
│       │
│       ├── profiles/
│       │   ├── __init__.py
│       │   ├── base.py              # Profile protocol/base class
│       │   ├── registry.py          # Profile lookup by domain
│       │   ├── generic.py           # Default generic profile
│       │   └── common_patterns.py   # Shared pattern matchers
│       │
│       ├── service/
│       │   ├── __init__.py
│       │   ├── server.py            # FastAPI app factory
│       │   ├── routes.py            # HTTP endpoint definitions
│       │   └── schemas.py           # Request/response JSON schemas
│       │
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── main.py              # Click CLI entry point
│       │   └── commands.py          # Individual CLI commands
│       │
│       └── telemetry/
│           ├── __init__.py
│           ├── trace.py             # Step-level trace recording
│           ├── replay.py            # Trace replay utilities
│           └── debug_dump.py        # Debug bundle export
│
├── tests/
│   ├── conftest.py                  # Shared fixtures
│   ├── unit/
│   │   ├── test_models.py
│   │   ├── test_config.py
│   │   ├── extractor/
│   │   │   ├── test_settle.py
│   │   │   ├── test_labels.py
│   │   │   ├── test_semantics.py
│   │   │   ├── test_grouping.py
│   │   │   ├── test_blockers.py
│   │   │   ├── test_ids.py
│   │   │   └── test_diff.py
│   │   └── executor/
│   │       ├── test_resolver.py
│   │       ├── test_validation.py
│   │       └── test_results.py
│   ├── integration/
│   │   ├── test_managed_session.py
│   │   ├── test_attached_session.py
│   │   ├── test_observe.py
│   │   ├── test_act.py
│   │   └── test_delta.py
│   ├── e2e/
│   │   ├── test_cli.py
│   │   └── test_service.py
│   └── corpus/
│       ├── runner.py
│       ├── metrics.py
│       ├── fixtures/
│       └── tasks/
└── corpus/
    ├── sites.yaml
    └── tasks/
```

---

## 3. Data Flow

### 3.1 Observe Flow

```
Caller
  │
  ▼
runtime.observe(mode)
  │
  ├─► settle.wait_for_settle(page)
  │     ├── check document.readyState
  │     ├── check no active navigation
  │     ├── mutation observer quiet period (300ms debounce)
  │     ├── interactable set stable check
  │     └── optional layout stability window
  │
  ├─► extractor.engine.extract(page, frames)
  │     ├── page_state.capture()         → raw page metadata
  │     ├── ax_snapshot.capture()        → accessibility tree
  │     ├── dom_snapshot.capture()       → targeted DOM fragments
  │     ├── visibility.compute()         → viewport + visibility map
  │     ├── labels.resolve()             → name/label for all elements
  │     ├── semantics.classify()         → role/type for each element
  │     ├── grouping.detect_regions()    → region segmentation
  │     ├── grouping.detect_content()    → repeated structure groups
  │     ├── blockers.detect()            → blocker/overlay detection
  │     ├── classifier.classify_page()   → page type classification
  │     └── ids.assign()                 → stable ID generation
  │
  ├─► ids.match(previous_canonical, new_extraction)
  │     └── weighted fingerprint matching
  │
  ├─► diff.compute(previous_canonical, new_canonical)
  │     └── produces ObservationDelta
  │
  ├─► canonical model updated in-memory
  │
  └─► return Observation (mode-filtered)
```

### 3.2 Act Flow

```
Caller
  │
  ▼
runtime.act(ActionRequest)
  │
  ├─► validation.validate(action_request, canonical_model)
  │     ├── action exists in canonical model?
  │     ├── target still live on page?
  │     ├── target visible (if required)?
  │     └── target enabled (if required)?
  │
  ├─► resolver.resolve_locator(action, canonical_model)
  │     ├── 1. role + accessible name
  │     ├── 2. label association
  │     ├── 3. test ID
  │     ├── 4. constrained CSS
  │     ├── 5. text within region
  │     ├── 6. DOM ancestry heuristic
  │     └── 7. positional fallback (last resort)
  │
  ├─► actions.execute(locator, operation, value)
  │     └── Playwright async call
  │
  ├─► settle.wait_for_settle(page)
  │
  ├─► runtime.observe(mode="delta")
  │     └── re-extraction + diff
  │
  ├─► results.classify(execution_outcome, observation_delta)
  │     ├── success / failed / blocked / stale / invalid / ambiguous
  │     └── caused: navigation / value_change / modal / region_update / etc
  │
  └─► return StepResult
```

### 3.3 Inspect Flow

```
Caller
  │
  ▼
runtime.inspect(target_id, mode)
  │
  ├─► resolve target from canonical model
  │
  ├─► targeted re-extraction for that element/region
  │     └── deeper form fields, item details, action metadata
  │
  └─► return InspectionResult
```

---

## 4. Extraction Engine Design

### 4.1 Input Signals

The extraction engine combines multiple signals from the live rendered page:

| Signal                   | Source                              | Use                              |
|--------------------------|-------------------------------------|----------------------------------|
| Accessibility tree       | `page.accessibility.snapshot()`     | Roles, names, states, tree       |
| DOM structure            | `page.evaluate()` JS execution      | Tags, attributes, ancestry       |
| Computed labels          | JS: `element.labels`, aria-label    | Human-readable names             |
| Bounding boxes           | `element.bounding_box()`            | Visibility, layout, grouping     |
| Form associations        | `<label for>`, fieldset, form owner | Form field grouping              |
| Visible text             | `innerText`, `textContent`          | Content, headings                |
| State flags              | Attributes + ARIA states            | checked, disabled, expanded, etc |
| Landmarks                | ARIA landmarks, HTML5 sectioning    | Region detection                 |
| Sibling patterns         | DOM structure analysis              | Repeated content detection       |
| Frame tree               | `page.frames()`                     | Multi-frame awareness            |

### 4.2 Extraction Pipeline

The extraction is a deterministic pipeline, not a single monolithic pass:

1. **Capture** — snapshot the page state (AX tree + targeted DOM)
2. **Classify** — determine element roles, types, and semantic weight
3. **Label** — resolve the best human-readable name for each element
4. **Group** — segment into regions, detect repeated structures
5. **Filter** — remove noise (hidden, decorative, aria-hidden)
6. **Detect blockers** — identify overlays, modals, login walls
7. **Generate actions** — create action descriptors for interactables
8. **Assign IDs** — generate stable fingerprint-based IDs
9. **Match** — match against previous canonical model
10. **Diff** — compute delta from previous state

### 4.3 Settle Strategy

The composite settle strategy uses multiple heuristics rather than
relying on a single Playwright wait condition:

```python
class SettleStrategy:
    ready_states: list[str] = ["complete", "interactive"]
    navigation_timeout_ms: int = 10000
    mutation_quiet_ms: int = 300
    interactable_stable_ms: int = 200
    layout_stable_ms: int = 150
    max_settle_ms: int = 15000
```

Logic:
1. Wait for `document.readyState` to reach acceptable state
2. Confirm no pending navigation
3. Inject MutationObserver, wait for quiet period
4. Check interactable element count stability over debounce window
5. Optionally check layout stability (bounding box changes)
6. Hard timeout as safety net

---

## 5. Stable ID System

### 5.1 Fingerprint Components

Each element's stable ID is derived from a weighted fingerprint:

| Component             | Weight | Example                            |
|-----------------------|--------|------------------------------------|
| Frame chain           | 0.10   | `main > iframe#content`            |
| Role                  | 0.20   | `button`, `textbox`, `navigation`  |
| Accessible name       | 0.25   | `"Search"`, `"Submit Order"`       |
| Label text            | 0.15   | `"Email address"`                  |
| Tag + type            | 0.05   | `input[type=email]`                |
| Ancestry signature    | 0.10   | `form > fieldset > div >`          |
| Nearby heading        | 0.10   | heading text within region         |
| Ordinal position      | 0.05   | 3rd button in region               |

### 5.2 Matching Algorithm

On re-observation:
1. Compute fingerprints for all new elements
2. For each previous canonical element, score against all new candidates
3. Accept best match above threshold (0.70)
4. Unmatched previous elements → removed
5. Unmatched new elements → assigned new IDs

### 5.3 ID Format

IDs are short, human-scannable, and prefixed by type:

```
rgn-main-content
frm-search
fld-search-query
act-submit-search
grp-search-results
itm-result-0
```

---

## 6. Action Execution System

### 6.1 Locator Resolution Priority

| Priority | Strategy              | Example                                    |
|----------|-----------------------|--------------------------------------------|
| 1        | Role + accessible name| `page.get_by_role("button", name="Search")`|
| 2        | Label association     | `page.get_by_label("Email")`               |
| 3        | Test ID               | `page.get_by_test_id("submit-btn")`        |
| 4        | Constrained CSS       | `form.search >> button[type=submit]`       |
| 5        | Text within region    | `page.get_by_text("Sign in").first`        |
| 6        | DOM ancestry          | Computed CSS path within region             |
| 7        | Positional fallback   | Bounding box click (last resort only)      |

### 6.2 Operation → Playwright Mapping

| Operation        | Playwright Method                              |
|------------------|------------------------------------------------|
| click            | `locator.click()`                              |
| fill             | `locator.fill(value)`                          |
| clear            | `locator.clear()`                              |
| select_option    | `locator.select_option(value)`                 |
| toggle           | `locator.check()` / `locator.uncheck()`        |
| press_key        | `locator.press(key)`                           |
| submit           | `locator.press("Enter")` or form submit        |
| open             | `locator.click()` (navigational)               |
| expand           | `locator.click()` (disclosure)                 |
| collapse         | `locator.click()` (disclosure)                 |
| scroll_into_view | `locator.scroll_into_view_if_needed()`         |
| navigate         | `page.goto(url)`                               |
| back             | `page.go_back()`                               |
| forward          | `page.go_forward()`                            |
| reload           | `page.reload()`                                |
| wait             | `page.wait_for_timeout(ms)`                    |

### 6.3 Result Classification

| Status    | Meaning                                                 |
|-----------|---------------------------------------------------------|
| success   | Action executed, page responded as expected             |
| failed    | Execution threw an error or timed out                   |
| blocked   | A blocker prevented execution (modal, CAPTCHA, etc.)    |
| stale     | Target no longer exists on page                         |
| invalid   | Request was malformed or action not found               |
| ambiguous | Multiple possible targets, none clearly correct         |

---

_Continued in [technical_spec_ops.md](technical_spec_ops.md) — sections 7-12
covering blocker detection, security, service API, CLI, configuration,
and error hierarchy._
