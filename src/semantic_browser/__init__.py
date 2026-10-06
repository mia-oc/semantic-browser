"""Public package interface for semantic-browser.

Heavy dependencies (Playwright, pydantic) are imported lazily so that the thin `sb` client starts in milliseconds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__version__ = "1.7.0"

if TYPE_CHECKING:  # pragma: no cover
    from semantic_browser.agent import AgentSession
    from semantic_browser.config import RuntimeConfig
    from semantic_browser.models import ActionRequest, Observation, StepResult
    from semantic_browser.runtime import SemanticBrowserRuntime
    from semantic_browser.session import ManagedSession

_LAZY = {
    "ActionRequest": "semantic_browser.models",
    "Observation": "semantic_browser.models",
    "StepResult": "semantic_browser.models",
    "RuntimeConfig": "semantic_browser.config",
    "SemanticBrowserRuntime": "semantic_browser.runtime",
    "ManagedSession": "semantic_browser.session",
    "AgentSession": "semantic_browser.agent",
}

__all__ = [
    "__version__",
    "ActionRequest",
    "AgentSession",
    "ManagedSession",
    "Observation",
    "RuntimeConfig",
    "SemanticBrowserRuntime",
    "StepResult",
]


def __getattr__(name: str) -> Any:
    mod = _LAZY.get(name)
    if mod is None:
        raise AttributeError(f"module 'semantic_browser' has no attribute {name!r}")
    import importlib

    value = getattr(importlib.import_module(mod), name)
    globals()[name] = value
    return value
