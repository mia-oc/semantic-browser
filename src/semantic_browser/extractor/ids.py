"""Stable ID assignment and matching."""

from __future__ import annotations

import hashlib
from typing import Any


def fingerprint_for(node: dict[str, Any]) -> str:
    raw = "|".join(
        [
            str(node.get("role", "")),
            str(node.get("tag", "")),
            str(node.get("name", ""))[:80],
            str(node.get("type", "")),
            str(node.get("href", ""))[:120],
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def assign_node_ids(nodes: list[dict[str, Any]], previous: dict[str, str] | None = None) -> dict[str, str]:
    previous = previous or {}
    out: dict[str, str] = {}
    for idx, node in enumerate(nodes):
        fp = fingerprint_for(node)
        out[fp] = previous.get(fp, f"elm-{idx}-{fp[:6]}")
    return out
