"""Playwright action execution."""

from __future__ import annotations

from semantic_browser.errors import ActionExecutionError
from semantic_browser.models import ActionDescriptor, ActionRequest


async def execute_action(page, action: ActionDescriptor, request: ActionRequest) -> tuple[bool, str]:
    try:
        if action.op == "navigate":
            if request.value is None:
                raise ActionExecutionError("navigate requires request.value URL")
            try:
                await page.goto(str(request.value), wait_until="domcontentloaded", timeout=15000)
            except Exception:
                await page.goto(str(request.value), timeout=15000)
            return True, "navigated"
        if action.op == "back":
            await page.go_back()
            return True, "went back"
        if action.op == "forward":
            await page.go_forward()
            return True, "went forward"
        if action.op == "reload":
            await page.reload()
            return True, "reloaded"
        if action.op == "click" or action.op == "open":
            locator = await _locator(page, action)
            await locator.click(timeout=5000)
            return True, "clicked"
        if action.op == "fill":
            locator = await _locator(page, action)
            value = "" if request.value is None else str(request.value)
            await locator.fill(value, timeout=5000)
            recipe = action.locator_recipe or {}
            input_type = recipe.get("type", "")
            label_lower = (action.label or "").lower()
            is_search = input_type == "search" or "search" in label_lower
            if is_search and value:
                await locator.press("Enter")
                return True, "filled and submitted"
            return True, "filled"
        if action.op == "clear":
            locator = await _locator(page, action)
            await locator.fill("", timeout=5000)
            return True, "cleared"
        if action.op == "select_option":
            locator = await _locator(page, action)
            await locator.select_option(str(request.value), timeout=5000)
            return True, "option selected"
        if action.op == "toggle":
            locator = await _locator(page, action)
            await locator.click(timeout=5000)
            return True, "toggled"
        if action.op == "press_key":
            await page.keyboard.press(str(request.value or "Enter"))
            return True, "key pressed"
        if action.op == "submit":
            locator = await _locator(page, action)
            await locator.press("Enter")
            return True, "submitted"
        if action.op == "scroll_into_view":
            locator = await _locator(page, action)
            await locator.scroll_into_view_if_needed(timeout=5000)
            return True, "scrolled"
        if action.op == "wait":
            ms = int(request.options.get("ms", request.value or 500))
            await page.wait_for_timeout(ms)
            return True, "waited"
    except Exception as exc:
        raise ActionExecutionError(str(exc)) from exc
    raise ActionExecutionError(f"Unsupported action op: {action.op}")


async def _locator(page, action):
    from semantic_browser.executor.resolver import resolve_locator

    return await resolve_locator(page, action)
