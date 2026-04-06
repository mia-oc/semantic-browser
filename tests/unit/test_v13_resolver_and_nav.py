"""Tests for v1.3 resolver improvements and SPA navigation classification."""

from __future__ import annotations

import pytest

from semantic_browser.executor.resolver import resolve_locator
from semantic_browser.executor.results import classify_status
from semantic_browser.models import ActionDescriptor, ObservationDelta

# ---------------------------------------------------------------------------
# SPA navigation classification
# ---------------------------------------------------------------------------


def test_spa_nav_classify_success():
    """SPA navigation (URL changed) should always classify as success."""
    delta = ObservationDelta(navigated=True)
    assert classify_status(True, "clicked", delta) == "success"


def test_spa_nav_classify_success_even_minor_materiality():
    """Even with minor materiality, navigated=True yields success."""
    delta = ObservationDelta(navigated=True, materiality="minor")
    assert classify_status(True, "clicked", delta) == "success"


def test_non_nav_ambiguous_still_works():
    """Non-navigating click with no delta signals still returns ambiguous."""
    delta = ObservationDelta()
    assert classify_status(True, "clicked", delta) == "ambiguous"


def test_navigated_takes_priority_over_blockers():
    """If navigated is True and there are blockers, navigation wins (success before blocked check)."""
    from semantic_browser.models import Blocker

    delta = ObservationDelta(
        navigated=True,
        added_blockers=[Blocker(kind="modal", severity="medium", description="Modal")],
    )
    assert classify_status(True, "clicked", delta) == "success"


def test_blocker_with_positive_effect_is_success():
    """Blocker added as side-effect of a successful action (e.g. betslip opening) = success."""
    from semantic_browser.models import Blocker

    delta = ObservationDelta(
        added_blockers=[Blocker(kind="modal", severity="medium", description="Betslip")],
        changed_regions=["betslip-panel"],
        materiality="moderate",
    )
    assert classify_status(True, "clicked", delta) == "success"


def test_blocker_with_no_other_changes_is_blocked():
    """Blocker appearing with no other positive effects = blocked."""
    from semantic_browser.models import Blocker

    delta = ObservationDelta(
        added_blockers=[Blocker(kind="modal", severity="medium", description="Age gate")],
    )
    assert classify_status(True, "clicked", delta) == "blocked"


# ---------------------------------------------------------------------------
# Resolver: custom element tag+text fallback
# ---------------------------------------------------------------------------


class _CountingLocator:
    def __init__(self, *, count_val=1):
        self._count_val = count_val

    @property
    def first(self):
        return self

    async def count(self):
        return self._count_val


class _CountCheckPage:
    """Page where locator results can be configured to match or not."""

    def __init__(self, *, locator_counts=None):
        self.calls: list[tuple[str, tuple, dict]] = []
        self._locator_counts = locator_counts or {}

    def get_by_role(self, role, name=None):
        self.calls.append(("get_by_role", (role,), {"name": name}))
        return _CountingLocator()

    def get_by_label(self, name):
        self.calls.append(("get_by_label", (name,), {}))
        return _CountingLocator()

    def get_by_placeholder(self, name):
        self.calls.append(("get_by_placeholder", (name,), {}))
        return _CountingLocator()

    def get_by_text(self, name):
        self.calls.append(("get_by_text", (name,), {}))
        return _CountingLocator()

    def locator(self, sel):
        self.calls.append(("locator", (sel,), {}))
        count = self._locator_counts.get(sel, 1)
        return _CountingLocator(count_val=count)


@pytest.mark.asyncio
async def test_custom_element_css_selector_with_count_check():
    """Custom element with matching CSS selector resolves immediately."""
    page = _CountCheckPage()
    action = ActionDescriptor(
        id="a1", op="click", label="3/1", confidence=0.75,
        locator_recipe={
            "tag": "btn-odds", "name": "3/1",
            "css_selector": "btn-odds.odds", "is_custom_element": True,
        },
    )
    await resolve_locator(page, action)
    assert page.calls[0][0] == "locator"
    assert page.calls[0][1] == ("btn-odds.odds",)
    assert len(page.calls) == 1


@pytest.mark.asyncio
async def test_custom_element_css_fails_falls_to_tag_text():
    """If CSS selector returns 0 matches, fall through to tag:has-text()."""
    page = _CountCheckPage(locator_counts={"btn-odds.odds": 0, 'btn-odds:has-text("3/1")': 1})
    action = ActionDescriptor(
        id="a2", op="click", label="3/1", confidence=0.75,
        locator_recipe={
            "tag": "btn-odds", "name": "3/1",
            "css_selector": "btn-odds.odds", "is_custom_element": True,
        },
    )
    await resolve_locator(page, action)
    assert any(
        c[0] == "locator" and 'btn-odds:has-text("3/1")' in c[1][0] for c in page.calls
    )


@pytest.mark.asyncio
async def test_custom_element_all_fail_falls_to_body():
    """If CSS and tag+text both miss, resolver eventually falls to body."""
    page = _CountCheckPage(locator_counts={
        "btn-odds.stale": 0,
        'btn-odds:has-text("")': 0,
    })
    action = ActionDescriptor(
        id="a3", op="click", label="", confidence=0.5,
        locator_recipe={
            "tag": "btn-odds", "name": "",
            "css_selector": "btn-odds.stale", "is_custom_element": True,
        },
    )
    await resolve_locator(page, action)
    assert any(c[0] == "locator" and c[1] == ("body",) for c in page.calls)


@pytest.mark.asyncio
async def test_standard_element_still_uses_aria():
    """Standard HTML buttons must still resolve via ARIA (regression)."""
    page = _CountCheckPage()
    action = ActionDescriptor(
        id="a4", op="click", label="Submit", confidence=0.9,
        locator_recipe={"role": "button", "name": "Submit", "tag": "button"},
    )
    await resolve_locator(page, action)
    assert page.calls[0][0] == "get_by_role"


@pytest.mark.asyncio
async def test_css_fallback_checks_count():
    """CSS fallback at end of chain should check count before returning."""
    page = _CountCheckPage(locator_counts={"div.ghost": 0})

    class _FailPage(_CountCheckPage):
        def get_by_role(self, role, name=None):
            self.calls.append(("get_by_role", (role,), {"name": name}))
            raise ValueError("nope")

        def get_by_label(self, name):
            self.calls.append(("get_by_label", (name,), {}))
            raise ValueError("nope")

        def get_by_placeholder(self, name):
            self.calls.append(("get_by_placeholder", (name,), {}))
            raise ValueError("nope")

        def get_by_text(self, name):
            self.calls.append(("get_by_text", (name,), {}))
            raise ValueError("nope")

    page = _FailPage(locator_counts={"div.ghost": 0})
    action = ActionDescriptor(
        id="a5", op="click", label="Mystery", confidence=0.5,
        locator_recipe={"role": "", "name": "Mystery", "tag": "div", "css_selector": "div.ghost"},
    )
    await resolve_locator(page, action)
    assert page.calls[-1][1] == ("body",)
