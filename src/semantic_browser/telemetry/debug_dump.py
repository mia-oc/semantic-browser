"""Trace export helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def export_json_bundle(path: str, payload: dict[str, Any]) -> str:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return str(out_path)
