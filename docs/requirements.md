# Requirements: Semantic Browser Runtime

## 1. Functional Requirements

### FR-01: Managed Browser Mode

| ID       | Requirement                                                         | Priority |
|----------|---------------------------------------------------------------------|----------|
| FR-01.1  | Launch a headful Chromium session via Playwright                    | P0       |
| FR-01.2  | Headful by default, headless as opt-in for testing                  | P0       |
| FR-01.3  | Optionally persist user profile / data dir                          | P1       |
| FR-01.4  | Provide `install-browser` CLI command for Chromium bootstrap        | P0       |
| FR-01.5  | Provide `doctor` CLI command for environment validation             | P1       |
| FR-01.6  | Clean shutdown of browser and context on session close              | P0       |
| FR-01.7  | Support `pip install semantic-browser[managed]` extras              | P0       |

### FR-02: Attached Browser Mode

| ID       | Requirement                                                         | Priority |
|----------|---------------------------------------------------------------------|----------|
| FR-02.1  | Attach to an existing Playwright `Page`                             | P0       |
| FR-02.2  | Attach to an existing Playwright `BrowserContext`                   | P0       |
| FR-02.3  | Attach to an existing Chromium instance via CDP endpoint            | P1       |
| FR-02.4  | No browser ownership — attached mode must not close caller's browser| P0       |
| FR-02.5  | Minimal interference with caller's event handlers and state         | P0       |

### FR-03: Observation

| ID       | Requirement                                                         | Priority |
|----------|---------------------------------------------------------------------|----------|
| FR-03.1  | `observe(mode="summary")` returns compact semantic observation      | P0       |
| FR-03.2  | `observe(mode="full")` returns richer observation with all actions  | P0       |
| FR-03.3  | `observe(mode="delta")` returns incremental diff from last state    | P0       |
| FR-03.4  | `observe(mode="debug")` returns engineering diagnostics             | P1       |
| FR-03.5  | Observation includes page info, regions, forms, content groups      | P0       |
| FR-03.6  | Observation includes available actions with stable IDs              | P0       |
| FR-03.7  | Observation includes blockers and warnings                          | P0       |
| FR-03.8  | Observation includes confidence report                              | P0       |

### FR-04: Inspection

| ID       | Requirement                                                         | Priority |
|----------|---------------------------------------------------------------------|----------|
| FR-04.1  | `inspect(target_id)` returns detail about a region                  | P0       |
| FR-04.2  | `inspect(target_id)` returns detail about a form and its fields     | P0       |
| FR-04.3  | `inspect(target_id)` returns detail about a content group / item    | P0       |
| FR-04.4  | `inspect(target_id)` returns detail about an action                 | P1       |

### FR-05: Action Execution

| ID       | Requirement                                                         | Priority |
|----------|---------------------------------------------------------------------|----------|
| FR-05.1  | `act()` validates action existence and target liveness              | P0       |
| FR-05.2  | `act()` resolves best locator strategy before execution             | P0       |
| FR-05.3  | `act()` executes through Playwright async API                       | P0       |
| FR-05.4  | `act()` waits for page settle after execution                       | P0       |
| FR-05.5  | `act()` re-observes and returns step result with delta              | P0       |
| FR-05.6  | Result classified: success/failed/blocked/stale/invalid/ambiguous   | P0       |
| FR-05.7  | Support ops: click, fill, clear, select_option, toggle, press_key   | P0       |
| FR-05.8  | Support ops: submit, open, expand, collapse, scroll_into_view       | P0       |
| FR-05.9  | Support ops: navigate, back, forward, reload, wait                  | P0       |
| FR-05.10 | Record whether action caused navigation/value change/modal/etc.     | P0       |

### FR-06: Semantic Extraction

| ID       | Requirement                                                         | Priority |
|----------|---------------------------------------------------------------------|----------|
| FR-06.1  | Extract page metadata (URL, title, domain, page type, ready state)  | P0       |
| FR-06.2  | Group page into meaningful regions (nav, main, footer, sidebar, etc)| P0       |
| FR-06.3  | Detect and represent forms with fields and submit actions            | P0       |
| FR-06.4  | Detect repeated structures (results, cards, rows) as content groups | P0       |
| FR-06.5  | Generate action descriptors for all reliable interactables          | P0       |
| FR-06.6  | Use HTML semantics, ARIA, labels, accessible names as primary input | P0       |
| FR-06.7  | Frame-aware extraction (do not ignore iframes)                      | P1       |
| FR-06.8  | Composite page settle strategy (not just networkidle)               | P0       |

### FR-07: Stable IDs

| ID       | Requirement                                                         | Priority |
|----------|---------------------------------------------------------------------|----------|
| FR-07.1  | Assign stable IDs to regions, forms, content groups, items, actions | P0       |
| FR-07.2  | IDs survive ordinary re-renders without flapping                    | P0       |
| FR-07.3  | Weighted fingerprint matching (role, name, label, ancestry, bounds) | P0       |
| FR-07.4  | Raw DOM IDs not treated as stable IDs                               | P0       |

### FR-08: Blocker Detection

| ID       | Requirement                                                         | Priority |
|----------|---------------------------------------------------------------------|----------|
| FR-08.1  | Detect cookie banners and consent prompts                           | P0       |
| FR-08.2  | Detect modals and overlays                                          | P0       |
| FR-08.3  | Detect login walls                                                  | P0       |
| FR-08.4  | Detect CAPTCHA-like challenges                                      | P0       |
| FR-08.5  | Detect page instability / mutation storms                           | P1       |
| FR-08.6  | Surface structured unreliability when page is semantically unfit    | P0       |

### FR-09: Interfaces

| ID       | Requirement                                                         | Priority |
|----------|---------------------------------------------------------------------|----------|
| FR-09.1  | Python async library API as primary interface                       | P0       |
| FR-09.2  | Optional local HTTP service with JSON contracts                     | P1       |
| FR-09.3  | CLI for launch, attach, observe, act, inspect, diagnostics, trace   | P1       |
| FR-09.4  | CLI supports JSON output mode                                       | P1       |

### FR-10: Telemetry & Debugging

| ID       | Requirement                                                         | Priority |
|----------|---------------------------------------------------------------------|----------|
| FR-10.1  | Trace every step: request, action, timing, observations, diffs      | P0       |
| FR-10.2  | Export debug bundle (JSON, DOM evidence, locators, optional screenshot)| P1    |
| FR-10.3  | `diagnostics()` method returns runtime health info                  | P1       |

### FR-11: Security & Privacy

| ID       | Requirement                                                         | Priority |
|----------|---------------------------------------------------------------------|----------|
| FR-11.1  | All semantic inspection is local — no data leaves the machine       | P0       |
| FR-11.2  | Redact passwords, payment details, CVV, secrets, tokens by default  | P0       |
| FR-11.3  | Expose field identity and type, not raw secret values               | P0       |

### FR-12: Site Profiles (Optional)

| ID       | Requirement                                                         | Priority |
|----------|---------------------------------------------------------------------|----------|
| FR-12.1  | Optional profile system for known domains                           | P2       |
| FR-12.2  | Profiles improve naming, grouping, noise suppression                | P2       |
| FR-12.3  | Profiles must not replace the generic extractor                     | P2       |

### FR-13: Evaluation Harness

| ID       | Requirement                                                         | Priority |
|----------|---------------------------------------------------------------------|----------|
| FR-13.1  | Corpus runner evaluating coverage, actions, IDs, blockers, grouping | P2       |
| FR-13.2  | Corpus config defines site, URL, tasks, expected outputs, thresholds| P2       |
| FR-13.3  | Metrics reporting for extraction quality                            | P2       |

---

## 2. Non-Functional Requirements

| ID       | Requirement                                                         | Priority |
|----------|---------------------------------------------------------------------|----------|
| NFR-01   | Python 3.11+ async-first codebase                                   | P0       |
| NFR-02   | Pydantic v2 for all public data contracts                           | P0       |
| NFR-03   | Playwright async API only (no sync)                                 | P0       |
| NFR-04   | Chromium/Chrome only for v1 (no Firefox, no WebKit, no Selenium)    | P0       |
| NFR-05   | No local LLM required for MVP operation                             | P0       |
| NFR-06   | Summary observation < 4KB for a typical page                        | P0       |
| NFR-07   | Delta observation < 1KB for typical incremental changes             | P0       |
| NFR-08   | Observation latency < 2s on a settled page                          | P0       |
| NFR-09   | Action round-trip < 3s (execute + settle + re-observe)              | P0       |
| NFR-10   | Package installable via standard pip with extras                    | P0       |
| NFR-11   | MIT licence                                                         | P0       |
| NFR-12   | Test coverage > 80% for core extraction and action modules          | P0       |

---

## 3. KPIs

| KPI                                  | Target             | Measurement                               |
|--------------------------------------|--------------------|-------------------------------------------|
| Semantic coverage on top-50 sites    | > 85% elements     | Corpus runner + manual review             |
| Action execution success rate        | > 90% on P0 ops    | Corpus task runner                        |
| Stable ID persistence across renders | > 95% match rate   | Re-observe same page, compare IDs         |
| Delta size vs full observation       | < 25% of full      | Byte comparison on typical page turns     |
| Blocker detection rate               | > 90% on known     | Corpus with labelled blockers             |
| Summary observation token count      | < 1000 tokens      | Tokeniser measurement on typical pages    |
| Setup time (managed mode)            | < 5 minutes        | Install + install-browser + first observe |

---

## 4. Edge Cases

| Case                                        | Expected Behaviour                                   |
|---------------------------------------------|------------------------------------------------------|
| Page is canvas-dominant (e.g. Google Maps)   | Return low-confidence observation + unreliable flag  |
| Page has 500+ interactables                  | Region-based grouping; paginated action surface      |
| Page is entirely behind a login wall         | Blocker reported, no fake actions surfaced            |
| Page uses heavy SPA routing                  | Page identity change detected on navigation          |
| Page has nested iframes                      | Frame-aware extraction, frame IDs in observations    |
| Page is ad-saturated junk                    | Unreliability surfaced, confidence low               |
| Action target removed between observe & act  | `stale` result returned, re-observation triggered    |
| Network error during action                  | `failed` result with diagnostic message              |
| Page has mutation storm / never settles      | Settle timeout, unreliability flag, partial obs      |
| Password field on page                       | Value redacted, field type exposed                   |
