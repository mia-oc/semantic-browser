"""Ref-based action execution (v2): act on the exact live element a ref points to."""

from __future__ import annotations

from typing import Any

from semantic_browser.errors import ActionExecutionError, ElementGoneError
from semantic_browser.extractor.snapshot import RESOLVE_JS, RefEntry, RefTable
from semantic_browser.models import ActionDescriptor, ActionRequest

_DESCRIBE_COVER_JS = """(el) => {
  const r = el.getBoundingClientRect();
  const x = Math.min(Math.max(r.left + r.width / 2, 1), innerWidth - 1), y = Math.min(Math.max(r.top + r.height / 2, 1), innerHeight - 1);
  let h = document.elementFromPoint(x, y);
  if (!h) return '';
  let cur = h, best = h, g = 0;
  while (cur && g++ < 12) { const s = getComputedStyle(cur); if (s.position === 'fixed' || cur.localName === 'dialog' || cur.getAttribute('role') === 'dialog') best = cur; cur = cur.parentElement; }
  const t = (best.getAttribute('aria-label') || best.innerText || best.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 70);
  return '<' + best.localName + '>' + (t ? ' "' + t + '"' : '');
}"""

_INNER_INPUT_JS = """(el) => {
  if (el.matches('input,textarea,select') || el.isContentEditable) return el;
  const q = 'input:not([type=hidden]),textarea,[contenteditable=""],[contenteditable="true"]';
  return el.querySelector(q) || (el.shadowRoot && el.shadowRoot.querySelector(q)) || el;
}"""

_SCROLL_JS = """(dir) => {
  const vh = window.innerHeight;
  const scrollers = [document.scrollingElement || document.documentElement];
  const all = document.querySelectorAll('*');
  let best = null, bestArea = 0;
  for (const e of all) {
    const s = getComputedStyle(e);
    if (!/(auto|scroll)/.test(s.overflowY) || e.scrollHeight <= e.clientHeight + 20) continue;
    const r = e.getBoundingClientRect();
    const a = Math.max(0, Math.min(r.bottom, vh) - Math.max(r.top, 0)) * r.width;
    if (a > bestArea) { bestArea = a; best = e; }
  }
  const root = scrollers[0];
  const pageScrollable = root.scrollHeight > root.clientHeight + 20;
  const target = (pageScrollable || !best) ? root : best;
  const step = Math.round((target === root ? vh : target.clientHeight) * 0.85);
  const before = target.scrollTop;
  if (dir === 'top') target.scrollTo({ top: 0, behavior: 'instant' });
  else if (dir === 'bottom') target.scrollTo({ top: target.scrollHeight, behavior: 'instant' });
  else if (dir === 'up') target.scrollBy({ top: -step, behavior: 'instant' });
  else target.scrollBy({ top: step, behavior: 'instant' });
  return { before, after: target.scrollTop, max: target.scrollHeight - target.clientHeight, container: target === root ? 'page' : (target.id || target.localName) };
}"""


def _first_line(exc: Exception) -> str:
    return str(exc).strip().splitlines()[0][:240] if str(exc).strip() else type(exc).__name__


async def resolve_handle(refs: RefTable, ref: int, *, proxy: bool = True) -> tuple[RefEntry, Any]:
    entry = refs.entries.get(ref)
    if entry is None:
        raise ElementGoneError(f"ref {ref} is unknown (page changed). Run `view` to get fresh refs.")
    target_local = entry.click_proxy if (proxy and entry.click_proxy) else entry.local
    try:
        handle = await entry.frame.evaluate_handle(RESOLVE_JS, target_local)
        el = handle.as_element()
    except Exception as exc:
        raise ElementGoneError(f"ref {ref} ({entry.name!r}) is no longer reachable: {_first_line(exc)}") from exc
    if el is None:
        raise ElementGoneError(f"ref {ref} ({entry.name!r}) is no longer on the page. Run `view` to refresh.")
    return entry, el


async def _click(el: Any, entry: RefEntry, options: dict[str, Any]) -> str:
    force = bool(options.get("force"))
    button = "right" if options.get("button") == "right" else "left"
    try:
        await el.click(timeout=int(options.get("timeout_ms", 2500)), force=force, button=button)
        return "right-clicked" if button == "right" else "clicked"
    except Exception as exc:
        msg = str(exc)
        if "intercepts pointer events" in msg or "receives the click" in msg:
            try:
                who = await el.evaluate(_DESCRIBE_COVER_JS)
            except Exception:
                who = "another element"
            raise ActionExecutionError(
                f"blocked: [{entry.ref}] {entry.name!r} is covered by {who}. Dismiss or complete that overlay first "
                "(or pass force=true to click through)."
            ) from exc
        if "not visible" in msg or "outside of the viewport" in msg or "not stable" in msg or "Element is not attached" in msg:
            try:
                await el.evaluate("e => e.click()")
                return "clicked (script)"
            except Exception:
                pass
        raise ActionExecutionError(f"click failed on [{entry.ref}] {entry.name!r}: {_first_line(exc)}") from exc


async def _fill(el: Any, entry: RefEntry, request: ActionRequest, action: ActionDescriptor) -> tuple[str, dict[str, Any]]:
    value = "" if request.value is None else str(request.value)
    options = request.options or {}
    inner = await el.evaluate_handle(_INNER_INPUT_JS)
    target = inner.as_element() or el
    try:
        if str(options.get("clear_strategy", "clear")).lower() == "append":
            current = await target.input_value()
            await target.fill(current + value, timeout=3000)
        elif options.get("type_slowly"):
            await target.fill("", timeout=3000)
            await target.type(value, timeout=5000)
        else:
            await target.fill(value, timeout=3000)
    except Exception as exc:
        try:  # last resort: focus + keyboard
            await target.click(timeout=1500)
            await target.type(value, timeout=4000)
        except Exception:
            raise ActionExecutionError(f"fill failed on [{entry.ref}] {entry.name!r}: {_first_line(exc)}") from exc
    submit = options.get("submit")
    if submit is None:
        t = (action.locator_recipe or {}).get("type", "")
        submit = (t == "search" or "search" in (action.label or "").lower()) and bool(value)
    if submit:
        await target.press("Enter")
        return "filled and submitted", {"submitted": True}
    return "filled", {"submitted": False}


async def _drag(refs: RefTable, el: Any, entry: RefEntry, request: ActionRequest) -> tuple[str, str, dict[str, Any]]:
    """Mouse-driven drag from `el` to the element whose ref is request.value (works for HTML5 drag-and-drop and pointer-based sliders)."""
    raw = str(request.value or "").strip("[]#eE")
    if not raw.isdigit():
        raise ActionExecutionError("usage: drag FROM TO  (two [n] refs from the view)")
    dest_entry, dest = await resolve_handle(refs, int(raw), proxy=False)
    page = entry.frame.page
    for h in (el, dest):
        try:
            await h.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass
    a, b = await el.bounding_box(), await dest.bounding_box()
    if not a or not b:
        raise ActionExecutionError(f"drag failed: [{entry.ref}] or [{dest_entry.ref}] has no visible box. Scroll it into view first.")
    ax, ay = a["x"] + a["width"] / 2, a["y"] + a["height"] / 2
    bx, by = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
    try:
        await page.mouse.move(ax, ay)
        await page.mouse.down()
        await page.mouse.move(ax + (2 if bx >= ax else -2), ay + (2 if by >= ay else -2), steps=2)  # starts the drag gesture
        await page.mouse.move(bx, by, steps=12)
        await page.mouse.up()
    except Exception as exc:
        raise ActionExecutionError(f"drag failed: {_first_line(exc)}") from exc
    return f"dragged [{entry.ref}] onto [{dest_entry.ref}]", "state_change", {}


async def execute_ref_action(page: Any, refs: RefTable, action: ActionDescriptor, request: ActionRequest) -> tuple[str, str, dict[str, Any]]:
    """Returns (message, effect_hint, evidence)."""
    ref = action.ref
    assert ref is not None
    op = action.op
    options = request.options or {}
    entry, el = await resolve_handle(refs, ref, proxy=op in {"toggle", "click", "open"})
    try:
        if op in {"click", "open"}:
            msg = await _click(el, entry, options)
            return msg, "navigation" if op == "open" else "state_change", {}
        if op == "fill":
            msg, ev = await _fill(el, entry, request, action)
            return msg, "content_change" if ev.get("submitted") else "state_change", ev
        if op == "select_option":
            tag = await el.evaluate("e => e.localName")
            if tag != "select":
                msg = await _click(el, entry, options)
                return msg + " (custom dropdown: view for options)", "state_change", {}
            val = str(request.value)
            try:
                await el.select_option(label=val, timeout=3000)
            except Exception:
                await el.select_option(value=val, timeout=3000)
            return "option selected", "state_change", {}
        if op == "toggle":
            before = None
            try:
                before = await el.is_checked()
            except Exception:
                pass
            msg = await _click(el, entry, options)
            after = None
            try:
                after = await (await resolve_handle(refs, ref, proxy=False))[1].is_checked()
            except Exception:
                pass
            if before is not None and after is not None and before == after and entry.kind == "checkbox":
                return f"{msg} but state unchanged (still {'checked' if after else 'unchecked'})", "none", {}
            return f"{'checked' if after else 'unchecked'}" if after is not None else msg, "state_change", {"checked": after}
        if op == "hover":
            await el.hover(timeout=3000)
            return "hovered", "state_change", {}
        if op == "upload":
            files = [str(v) for v in request.value] if isinstance(request.value, (list, tuple)) else ([str(request.value)] if request.value else [])
            if entry.kind != "file":
                raise ActionExecutionError(f"[{ref}] {entry.name!r} is not a file input; `upload` only works on `file` controls in the view.")
            if not files:
                raise ActionExecutionError(f"[{ref}] {entry.name!r} is a file chooser: use `upload {ref} /path/to/file` (several paths allowed).")
            await el.set_input_files(files, timeout=5000)
            return (f"{len(files)} files attached" if len(files) > 1 else "file attached"), "state_change", {}
        if op == "dblclick":
            await el.dblclick(timeout=int(options.get("timeout_ms", 2500)), force=bool(options.get("force")))
            return "double-clicked", "state_change", {}
        if op == "drag":
            return await _drag(refs, el, entry, request)
        if op == "scroll_into_view":
            await el.scroll_into_view_if_needed(timeout=3000)
            return "scrolled", "none", {}
        if op == "press":
            key = str(request.value or "Enter")
            await el.focus()
            await el.press(key, timeout=3000)
            return f"pressed {key}", "content_change" if key.lower() == "enter" else "state_change", {}
    except ActionExecutionError:
        raise
    except Exception as exc:
        raise ActionExecutionError(f"{op} failed on [{ref}] {entry.name!r}: {_first_line(exc)}") from exc
    raise ActionExecutionError(f"Unsupported ref op: {op}")


async def scroll_page(page: Any, direction: str) -> dict[str, Any]:
    d = (direction or "down").lower()
    if d not in {"down", "up", "top", "bottom"}:
        d = "down"
    return await page.evaluate(_SCROLL_JS, d)
