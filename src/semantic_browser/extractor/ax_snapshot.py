"""Accessibility tree snapshot."""

from __future__ import annotations


async def capture_ax_snapshot(page) -> dict:
    try:
        snap = await page.accessibility.snapshot()
    except Exception:
        snap = None
    return snap or {}
