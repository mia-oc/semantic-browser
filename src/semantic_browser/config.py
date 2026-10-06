"""Runtime configuration models."""

from __future__ import annotations

from pydantic import BaseModel, Field

ProfileMode = str


class SettleConfig(BaseModel):
    mode: str = "fast"  # "fast" (event-driven, ~100-250 ms) | "legacy" (four serial polling loops, ~800 ms)
    quiet_ms: int = 80  # DOM must be mutation-free this long
    net_quiet_ms: int = 100  # no in-flight document/xhr/fetch/script for this long
    action_cap_ms: int = 2500
    navigation_cap_ms: int = 5000
    # a navigation returns once the response is committed and DOMContentLoaded fired, or this long after commit
    # (blocking scripts that never arrive must not hold the agent hostage; what has rendered is shown)
    dcl_grace_ms: int = 5000
    observe_cap_ms: int = 800
    # when an action visibly changed nothing, wait this long for late (timer/debounce driven) rendering
    grace_ms: int = 350
    grace_cap_ms: int = 700
    ready_states: list[str] = Field(default_factory=lambda: ["interactive", "complete"])
    mutation_quiet_ms: int = 300
    interactable_stable_ms: int = 200
    layout_stable_ms: int = 150
    max_settle_ms: int = 15000
    nav_stable_hits: int = 2
    structural_stable_hits: int = 2
    behavioral_stable_hits: int = 2
    frame_stable_hits: int = 2
    settle_profile_fast_ms: int = 1500
    settle_profile_slow_ms: int = 4000
    settle_tolerance_pct: float = 0.05


class ExtractionConfig(BaseModel):
    engine: str = "v2"  # "v2" single-pass snapshot (shadow DOM, frames, refs, page text) | "legacy"
    view_budget: int = 5000  # characters of page view returned per call (~1.2k tokens)
    include_frames: bool = True
    max_elements: int = 4000
    content_group_min_items: int = 3
    low_name_threshold: float = 0.5
    low_action_coverage_threshold: float = 0.3
    summary_top_scope_enabled: bool = True
    summary_top_scope_multiplier: float = 1.6


class RedactionConfig(BaseModel):
    enabled: bool = True
    expose_secrets: bool = False


class TelemetryConfig(BaseModel):
    enabled: bool = True
    trace_dir: str | None = None
    max_events: int = 1000


class RuntimeConfig(BaseModel):
    settle: SettleConfig = Field(default_factory=SettleConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    redaction: RedactionConfig = Field(default_factory=RedactionConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    #: "off" | "media" (skip images/fonts/video + disable animations) | "max" (media + well-known trackers).
    #: Speeds up heavy pages for agents that never look at pixels; the `captcha` verb lifts it automatically.
    lite: str = "off"


class LaunchConfig(BaseModel):
    headful: bool = True
    profile_mode: str = "ephemeral"
    profile_dir: str | None = None
    storage_state_path: str | None = None
