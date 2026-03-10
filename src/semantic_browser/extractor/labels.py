"""Label normalization helpers."""

from __future__ import annotations


def normalized_label(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.split()).strip()
