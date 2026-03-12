"""Locator resolution from action metadata."""

from __future__ import annotations

from semantic_browser.models import ActionDescriptor


async def resolve_locator(page, action: ActionDescriptor):
    recipe = action.locator_recipe
    name = (recipe.get("name") or "").strip()
    role = (recipe.get("role") or "").strip()
    tag = (recipe.get("tag") or "").strip()
    dom_id = (recipe.get("dom_id") or "").strip()
    test_id = (recipe.get("test_id") or "").strip()
    href = (recipe.get("href") or "").strip()
    if role in {"button", "link", "textbox", "checkbox", "combobox", "searchbox"} and name:
        try:
            return page.get_by_role(role, name=name).first
        except Exception:
            pass
    if tag in {"input", "textarea", "select"} and name:
        try:
            return page.get_by_label(name).first
        except Exception:
            pass
    if test_id and hasattr(page, "get_by_test_id"):
        try:
            return page.get_by_test_id(test_id).first
        except Exception:
            pass
    if dom_id:
        try:
            return page.locator(f"#{dom_id}").first
        except Exception:
            pass
    if tag == "a" and href:
        try:
            return page.locator(f'a[href="{href}"]').first
        except Exception:
            pass
    if name:
        return page.get_by_text(name).first
    return page.locator("body")
