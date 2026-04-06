from __future__ import annotations

import pytest

from semantic_browser.config import SettleConfig
from semantic_browser.extractor.settle import wait_for_settle


class _Page:
    def __init__(self, *, url="https://example.com", structural_counts=None):
        self.url = url
        self.context = type("Ctx", (), {"pages": [object()]})()
        self._structural_counts = structural_counts or [10, 4]
        self._structural_call = 0

    async def evaluate(self, script: str):
        if script == "document.readyState":
            return "complete"
        if script == "location.href":
            return self.url
        if "regionSel" in script:
            if callable(self._structural_counts):
                self._structural_call += 1
                return self._structural_counts(self._structural_call)
            return self._structural_counts
        if "activeSig" in script:
            return [0, 0, "INPUT:textbox:q"]
        if "querySelectorAll('iframe')" in script:
            return [1, 1]
        return 0

    async def wait_for_timeout(self, _ms: int):
        return None


@pytest.mark.asyncio
async def test_wait_for_settle_returns_layer_durations():
    report = await wait_for_settle(_Page(), SettleConfig(max_settle_ms=1000), intent="observe")
    assert "navigation_settle" in report.durations_ms
    assert "structural_settle" in report.durations_ms
    assert "behavioral_settle" in report.durations_ms
    assert "frame_settle" in report.durations_ms


@pytest.mark.asyncio
async def test_fuzzy_settle_within_tolerance():
    """Structural settle completes when counts fluctuate within 5% tolerance."""
    call_count = 0

    def oscillating_counts(_n):
        nonlocal call_count
        call_count += 1
        base = 100
        offset = 2 if call_count % 2 == 0 else 0
        return [base + offset, 4]

    page = _Page(structural_counts=oscillating_counts)
    report = await wait_for_settle(
        page, SettleConfig(max_settle_ms=3000, settle_tolerance_pct=0.05), intent="observe"
    )
    assert "structural_settle" in report.durations_ms
    assert "mutation_storm" not in report.instability


@pytest.mark.asyncio
async def test_fuzzy_settle_auto_fallback():
    """After 3+ resets, fuzzy mode engages at 10% tolerance."""
    call_count = 0

    def wildly_varying(_n):
        nonlocal call_count
        call_count += 1
        counts = [50, 80, 50, 80, 50, 80, 90, 91, 90, 91]
        idx = min(call_count - 1, len(counts) - 1)
        return [counts[idx], 4]

    page = _Page(structural_counts=wildly_varying)
    report = await wait_for_settle(
        page, SettleConfig(max_settle_ms=5000, settle_tolerance_pct=0.0), intent="action"
    )
    assert "mutation_storm" in report.instability
    assert "mutation_storm_fallback" in report.instability
