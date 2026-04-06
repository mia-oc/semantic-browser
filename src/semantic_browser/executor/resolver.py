"""Locator resolution from action metadata."""

from __future__ import annotations

import re

from semantic_browser.models import ActionDescriptor

_VOLATILE_CLASS_RE = re.compile(
    r"\.(ng-(?:pristine|dirty|touched|untouched|valid|invalid|empty|not-empty|pending)"
    r"|is-(?:focused|active|dirty|touched|valid|invalid)"
    r"|v-enter|v-leave|v-enter-active|v-leave-active"
    r"|el-[\w-]+--[\w-]+)",
)


def _sanitize_css(selector: str) -> str:
    """Strip framework-injected volatile state classes from a CSS selector."""
    cleaned = _VOLATILE_CLASS_RE.sub("", selector)
    cleaned = re.sub(r"\.(?=\.|>|\s|$|\[)", "", cleaned)
    return cleaned.strip()


async def _try_locator(page, selector: str):
    """Return locator.first if it resolves to at least one element, else None."""
    try:
        loc = page.locator(selector).first
        if await loc.count() > 0:
            return loc
    except Exception:
        pass
    return None


async def resolve_locator(page, action: ActionDescriptor):
    recipe = action.locator_recipe
    name = (recipe.get("name") or "").strip()
    role = (recipe.get("role") or "").strip()
    tag = (recipe.get("tag") or "").strip()
    dom_id = (recipe.get("dom_id") or "").strip()
    test_id = (recipe.get("test_id") or "").strip()
    href = (recipe.get("href") or "").strip()
    css_selector = (recipe.get("css_selector") or "").strip()

    # For custom web components, try CSS selector then tag+text before ARIA chain.
    if recipe.get("is_custom_element"):
        if css_selector:
            loc = await _try_locator(page, css_selector)
            if loc:
                return loc
        if tag and name:
            loc = await _try_locator(page, f'{tag}:has-text("{name}")')
            if loc:
                return loc

    # Standard ARIA-based resolution chain
    if role in {"button", "link", "textbox", "checkbox", "combobox", "searchbox"} and name:
        try:
            return page.get_by_role(role, name=name).first
        except Exception:
            pass
    if tag in {"input", "textarea", "select"}:
        if css_selector:
            sanitized = _sanitize_css(css_selector)
            if sanitized:
                loc = await _try_locator(page, sanitized)
                if loc:
                    return loc
        if name:
            try:
                loc = page.get_by_label(name).first
                if await loc.count() > 0:
                    return loc
            except Exception:
                pass
            try:
                loc = page.get_by_placeholder(name).first
                if await loc.count() > 0:
                    tag_name = await loc.evaluate("el => el.tagName.toLowerCase()")
                    if tag_name in ("input", "textarea", "select"):
                        return loc
            except Exception:
                pass
    if test_id and hasattr(page, "get_by_test_id"):
        try:
            return page.get_by_test_id(test_id).first
        except Exception:
            pass
    if dom_id:
        loc = await _try_locator(page, f"#{dom_id}")
        if loc:
            return loc
    if tag == "a" and href:
        loc = await _try_locator(page, f'a[href="{href}"]')
        if loc:
            return loc
    if name:
        try:
            return page.get_by_text(name).first
        except Exception:
            pass

    if css_selector:
        sanitized = _sanitize_css(css_selector)
        if sanitized:
            loc = await _try_locator(page, sanitized)
            if loc:
                return loc
        loc = await _try_locator(page, css_selector)
        if loc:
            return loc

    return page.locator("body")
