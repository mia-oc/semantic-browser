"""Visibility helpers."""

from __future__ import annotations


def in_viewport(node: dict) -> bool:
    return bool(node.get("in_viewport", False))
