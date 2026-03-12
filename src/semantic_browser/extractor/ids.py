"""Stable ID assignment and matching."""

from __future__ import annotations

import hashlib
from typing import Any


def fingerprint_for(node: dict[str, Any]) -> str:
    raw = "|".join(
        [
            str(node.get("frame_id", "main")),
            str(node.get("role", "")),
            str(node.get("tag", "")),
            str(node.get("name", ""))[:80],
            str(node.get("type", "")),
            str(node.get("href", ""))[:120],
            str((node.get("rect") or {}).get("y", "")),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def assign_node_ids(nodes: list[dict[str, Any]], previous: dict[str, str] | None = None) -> dict[str, str]:
    previous = previous or {}
    out: dict[str, str] = {}
    seen: dict[str, int] = {}
    for node in nodes:
        fp = fingerprint_for(node)
        ordinal = seen.get(fp, 0)
        seen[fp] = ordinal + 1
        key = f"{fp}#{ordinal}"
        out[key] = previous.get(key, f"elm-{fp[:8]}-{ordinal}")
    return out
