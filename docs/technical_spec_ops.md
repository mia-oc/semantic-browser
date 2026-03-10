# Technical Specification: Operations & Interfaces

_Continuation of `technical_spec.md`. Covers blockers, security, service
API, CLI, configuration, and error hierarchy._

---

## 7. Blocker Detection

### 7.1 Detection Heuristics

| Blocker Type       | Detection Strategy                                        |
|--------------------|-----------------------------------------------------------|
| Cookie banner      | Fixed/sticky overlay with consent-related text + buttons  |
| Login wall         | Form with password field + overlay/fullscreen positioning  |
| Modal dialog       | `role="dialog"` or `aria-modal` or z-index overlay        |
| CAPTCHA            | Known iframe sources (recaptcha, hcaptcha, turnstile)     |
| Permission prompt  | Browser-level dialog detected via Playwright events       |
| Native dialog      | `page.on("dialog")` event handling                        |
| File chooser       | `page.on("filechooser")` event                           |
| Instability        | Mutation rate exceeds threshold, settle fails repeatedly   |

### 7.2 Unreliability Heuristics

| Condition                                        | Flag                        |
|--------------------------------------------------|-----------------------------|
| > 50% visible interactables lack meaningful name | `low_semantic_quality`      |
| Region detection produces < 2 regions            | `poor_structure`            |
| Overlay churn (modals appear/disappear rapidly)  | `overlay_instability`       |
| Canvas-dominant page                             | `canvas_dominant`           |
| Repeated redirects in settle window              | `redirect_storm`            |
| > 80% of page area is ad content                 | `ad_saturated`              |
| Action coverage < 30% of visible interactables   | `low_action_coverage`       |

---

## 8. Security & Redaction

### 8.1 Auto-Redacted Fields

The following are redacted in observations by default:

| Field Type              | Observation Value      |
|-------------------------|------------------------|
| `input[type=password]`  | `"[REDACTED]"`         |
| Credit card number      | `"[REDACTED:card]"`    |
| CVV                     | `"[REDACTED:cvv]"`     |
| Visible auth tokens     | `"[REDACTED:token]"`   |
| Fields with `autocomplete=cc-*` | `"[REDACTED]"` |

### 8.2 Redaction Override

Callers can opt-in to seeing redacted values via config:

```python
config = RuntimeConfig(redaction=RedactionConfig(expose_secrets=True))
```

This is disabled by default and requires explicit opt-in.

---

## 9. Service API (Optional)

### 9.1 FastAPI Application

The service is a thin HTTP layer over the core runtime:

```
POST   /sessions/launch           → LaunchRequest → SessionInfo
POST   /sessions/attach           → AttachRequest → SessionInfo
POST   /sessions/{id}/close       → CloseResponse

POST   /sessions/{id}/observe     → ObserveRequest → Observation
POST   /sessions/{id}/inspect     → InspectRequest → InspectionResult
POST   /sessions/{id}/act         → ActionRequest → StepResult
POST   /sessions/{id}/navigate    → NavigateRequest → StepResult

GET    /sessions/{id}/diagnostics → DiagnosticsReport
POST   /sessions/{id}/export-trace → TraceExportRequest → file
```

### 9.2 Design Principle

The server is a transport adapter. All logic lives in the core library.
The server only handles serialisation, session routing, and HTTP concerns.

---

## 10. CLI Design

### 10.1 Command Tree

```
semantic-browser
├── launch          [--headful/--headless] [--profile DIR]
├── attach          --cdp WS_URL | --page-id ID
├── observe         --session ID [--mode summary|full|delta|debug]
├── inspect         --session ID --target TARGET_ID
├── act             --session ID --action ACTION_ID [--value VALUE]
├── navigate        --session ID --url URL
├── diagnostics     --session ID
├── export-trace    --session ID --out PATH
├── install-browser
├── doctor
└── version
```

### 10.2 Output Modes

All commands support `--format json|text` (default: text for terminals,
json when piped).

---

## 11. Configuration

```python
class RuntimeConfig(BaseModel):
    settle: SettleConfig = SettleConfig()
    extraction: ExtractionConfig = ExtractionConfig()
    redaction: RedactionConfig = RedactionConfig()
    telemetry: TelemetryConfig = TelemetryConfig()
    profiles: ProfileConfig = ProfileConfig()

class SettleConfig(BaseModel):
    ready_states: list[str] = ["complete", "interactive"]
    mutation_quiet_ms: int = 300
    interactable_stable_ms: int = 200
    layout_stable_ms: int = 150
    max_settle_ms: int = 15000

class ExtractionConfig(BaseModel):
    max_elements: int = 2000
    max_depth: int = 30
    include_frames: bool = True
    content_group_min_items: int = 3

class RedactionConfig(BaseModel):
    enabled: bool = True
    expose_secrets: bool = False

class TelemetryConfig(BaseModel):
    enabled: bool = True
    trace_dir: str | None = None
    max_traces: int = 100

class ProfileConfig(BaseModel):
    enabled: bool = True
    profile_dirs: list[str] = []
```

---

## 12. Error Hierarchy

```python
class SemanticBrowserError(Exception): ...
class BrowserNotReadyError(SemanticBrowserError): ...
class SessionNotFoundError(SemanticBrowserError): ...
class ActionNotFoundError(SemanticBrowserError): ...
class ActionStaleError(SemanticBrowserError): ...
class ActionExecutionError(SemanticBrowserError): ...
class SettleTimeoutError(SemanticBrowserError): ...
class ExtractionError(SemanticBrowserError): ...
class PageUnreliableError(SemanticBrowserError): ...
class AttachmentError(SemanticBrowserError): ...
```
