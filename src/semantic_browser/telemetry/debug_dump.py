"""Trace export helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SENSITIVE_KEYS = {"value", "password", "token", "secret", "authorization", "api_key"}


def _sanitize(value: Any, parent_key: str | None = None) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for k, v in value.items():
            key = str(k).lower()
            if key in _SENSITIVE_KEYS:
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = _sanitize(v, parent_key=key)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(v, parent_key=parent_key) for v in value]
    if isinstance(value, str) and (parent_key or "") in _SENSITIVE_KEYS:
        return "[REDACTED]"
    return value


def export_json_bundle(path: str, payload: dict[str, Any]) -> str:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sanitized = _sanitize(payload)
    out_path.write_text(json.dumps(sanitized, indent=2, default=str), encoding="utf-8")
    return str(out_path)
