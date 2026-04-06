from __future__ import annotations

import pytest

from semantic_browser.executor.resolver import resolve_locator
from semantic_browser.models import ActionDescriptor


class _DummyLocator:
    @property
    def first(self):
        return self

    async def count(self):
        return 1


class _ZeroLocator:
    """Locator that reports zero matches."""

    @property
    def first(self):
        return self

    async def count(self):
        return 0


class _Page:
    def __init__(self):
        self.calls: list[tuple[str, tuple, dict]] = []

    def get_by_role(self, role, name=None):
        self.calls.append(("get_by_role", (role,), {"name": name}))
        return _DummyLocator()

    def get_by_label(self, name):
        self.calls.append(("get_by_label", (name,), {}))
        return _DummyLocator()

    def get_by_placeholder(self, name):
        self.calls.append(("get_by_placeholder", (name,), {}))
        return _DummyLocator()

    def get_by_text(self, name):
        self.calls.append(("get_by_text", (name,), {}))
        return _DummyLocator()

    def locator(self, sel):
        self.calls.append(("locator", (sel,), {}))
        return _DummyLocator()


@pytest.mark.asyncio
async def test_resolver_prefers_role_then_name():
    page = _Page()
    action = ActionDescriptor(
        id="a1",
        op="click",
        label="Submit",
        confidence=0.9,
        locator_recipe={"role": "button", "name": "Submit", "tag": "button"},
    )
    await resolve_locator(page, action)
    assert page.calls[0][0] == "get_by_role"


@pytest.mark.asyncio
async def test_custom_element_uses_css_selector_first():
    """Custom web components should resolve via CSS selector, not ARIA."""
    page = _Page()
    action = ActionDescriptor(
        id="a2",
        op="click",
        label="7/10",
        confidence=0.75,
        locator_recipe={
            "role": "",
            "name": "7/10",
            "tag": "abc-button",
            "css_selector": "abc-button.btn-odds",
            "is_custom_element": True,
        },
    )
    _loc = await resolve_locator(page, action)
    assert page.calls[0][0] == "locator"
    assert page.calls[0][1] == ("abc-button.btn-odds",)
    assert len(page.calls) == 1  # No ARIA fallback attempted


class _FailingPage(_Page):
    """Page that raises on all ARIA methods but supports locator()."""

    def get_by_role(self, role, name=None):
        self.calls.append(("get_by_role", (role,), {"name": name}))
        raise ValueError("not found")

    def get_by_label(self, name):
        self.calls.append(("get_by_label", (name,), {}))
        raise ValueError("not found")

    def get_by_placeholder(self, name):
        self.calls.append(("get_by_placeholder", (name,), {}))
        raise ValueError("not found")

    def get_by_text(self, name):
        self.calls.append(("get_by_text", (name,), {}))
        raise ValueError("not found")


@pytest.mark.asyncio
async def test_css_selector_fallback_when_aria_fails():
    """Standard elements with css_selector should fall back to it if all ARIA methods fail."""
    page = _FailingPage()
    action = ActionDescriptor(
        id="a3",
        op="click",
        label="Mystery Button",
        confidence=0.7,
        locator_recipe={
            "role": "",
            "name": "Mystery Button",
            "tag": "div",
            "css_selector": "div.special-button",
        },
    )
    _loc = await resolve_locator(page, action)
    # ARIA methods are tried and fail, then css_selector fallback is used
    assert any(call[0] == "locator" and call[1] == ("div.special-button",) for call in page.calls)


@pytest.mark.asyncio
async def test_standard_html_button_still_uses_aria():
    """Standard HTML buttons must still resolve via ARIA (regression test)."""
    page = _Page()
    action = ActionDescriptor(
        id="a4",
        op="click",
        label="Submit",
        confidence=0.9,
        locator_recipe={
            "role": "button",
            "name": "Submit",
            "tag": "button",
            "css_selector": "button.submit-btn",
        },
    )
    await resolve_locator(page, action)
    # Should prefer ARIA over CSS selector for standard elements
    assert page.calls[0][0] == "get_by_role"


@pytest.mark.asyncio
async def test_fallback_to_body_when_no_recipe():
    page = _Page()
    action = ActionDescriptor(
        id="a5",
        op="click",
        label="",
        confidence=0.5,
        locator_recipe={},
    )
    _loc = await resolve_locator(page, action)
    assert page.calls[-1][0] == "locator"
    assert page.calls[-1][1] == ("body",)


@pytest.mark.asyncio
async def test_dom_id_resolution():
    page = _Page()
    action = ActionDescriptor(
        id="a6",
        op="click",
        label="Click Me",
        confidence=0.8,
        locator_recipe={"dom_id": "my-button", "tag": "button", "name": "Click Me"},
    )
    # role is empty, so get_by_role is skipped; get_by_text tried then dom_id via locator
    await resolve_locator(page, action)
    assert any(call[0] == "locator" and call[1] == ("#my-button",) for call in page.calls)


@pytest.mark.asyncio
async def test_input_prefers_sanitized_css_over_label():
    """Input elements should try sanitized CSS selector first, before label/placeholder."""

    page = _Page()
    action = ActionDescriptor(
        id="a7",
        op="fill",
        label="0.00",
        confidence=0.7,
        locator_recipe={
            "name": "0.00",
            "tag": "input",
            "type": "text",
            "css_selector": "input.ng-pristine.ng-untouched",
        },
    )
    await resolve_locator(page, action)
    assert page.calls[0][0] == "locator"
    assert "ng-pristine" not in page.calls[0][1][0]


@pytest.mark.asyncio
async def test_input_falls_to_placeholder_when_css_and_label_fail():
    """When sanitized CSS returns 0 and label fails, placeholder is tried."""

    class _NoMatchPage(_Page):
        def get_by_label(self, name):
            self.calls.append(("get_by_label", (name,), {}))
            return _ZeroLocator()

        def locator(self, sel):
            self.calls.append(("locator", (sel,), {}))
            return _ZeroLocator()

    page = _NoMatchPage()
    action = ActionDescriptor(
        id="a7b",
        op="fill",
        label="0.00",
        confidence=0.7,
        locator_recipe={
            "name": "0.00",
            "tag": "input",
            "type": "text",
            "css_selector": "input.ng-pristine.ng-untouched",
        },
    )
    await resolve_locator(page, action)
    assert any(call[0] == "get_by_placeholder" for call in page.calls)


@pytest.mark.asyncio
async def test_input_sanitizes_volatile_css_classes():
    """Input resolution should strip Angular/Vue volatile state classes from CSS selector."""
    from semantic_browser.executor.resolver import _sanitize_css

    raw = "div.input-text-wrapper > input.input-text.ng-pristine.ng-untouched.ng-valid.ng-empty"
    sanitized = _sanitize_css(raw)
    assert "ng-pristine" not in sanitized
    assert "ng-untouched" not in sanitized
    assert "ng-valid" not in sanitized
    assert "ng-empty" not in sanitized
    assert "input-text-wrapper" in sanitized
    assert "input-text" in sanitized
