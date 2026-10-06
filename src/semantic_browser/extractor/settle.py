"""Composite settle strategy."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, cast

from semantic_browser.config import SettleConfig
from semantic_browser.errors import SettleTimeoutError


@dataclass
class SettleReport:
    durations_ms: dict[str, int] = field(default_factory=dict)
    instability: list[str] = field(default_factory=list)


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(cast(Any, value))
    except Exception:
        return default


async def wait_for_settle(page: Any, config: SettleConfig, *, intent: str = "action") -> SettleReport:
    max_settle_ms = int(getattr(config, "max_settle_ms", 15000))
    settle_profile_fast_ms = int(getattr(config, "settle_profile_fast_ms", 1500))
    settle_profile_slow_ms = int(getattr(config, "settle_profile_slow_ms", 4000))
    nav_stable_hits = int(getattr(config, "nav_stable_hits", 2))
    structural_stable_hits = int(getattr(config, "structural_stable_hits", 2))
    behavioral_stable_hits = int(getattr(config, "behavioral_stable_hits", 2))
    frame_stable_hits = int(getattr(config, "frame_stable_hits", 2))
    interactable_stable_ms = int(getattr(config, "interactable_stable_ms", 200))
    mutation_quiet_ms = int(getattr(config, "mutation_quiet_ms", 300))
    ready_states = list(getattr(config, "ready_states", ["interactive", "complete"]))
    deadline = time.monotonic() + (max_settle_ms / 1000)
    report = SettleReport()
    # Keep simple fast-path for low-risk intents.
    if intent in {"fill", "observe"}:
        local_deadline = min(deadline, time.monotonic() + (settle_profile_fast_ms / 1000))
    else:
        local_deadline = min(deadline, time.monotonic() + (settle_profile_slow_ms / 1000))

    nav_start = time.perf_counter()
    nav_hits = 0
    while time.monotonic() < local_deadline:
        try:
            state = await page.evaluate("document.readyState")
        except Exception:
            await asyncio.sleep(0.05)
            continue
        if state in ready_states:
            nav_hits += 1
            if nav_hits >= nav_stable_hits:
                break
        else:
            nav_hits = 0
        await asyncio.sleep(0.05)
    report.durations_ms["navigation_settle"] = int((time.perf_counter() - nav_start) * 1000)

    # Capture URL for SPA transition detection during structural settle
    try:
        settle_start_url = await page.evaluate("location.href")
    except Exception:
        settle_start_url = None

    settle_tolerance_pct = float(getattr(config, "settle_tolerance_pct", 0.05))
    fuzzy_fallback_engaged = False

    def _within_tolerance(
        prev: tuple[int, int], curr: tuple[int, int], tol: float
    ) -> bool:
        if prev[0] == 0:
            return curr[0] == 0
        diff = abs(curr[0] - prev[0]) / max(prev[0], 1)
        return diff <= tol and prev[1] == curr[1]

    previous_signature: tuple[int, int] | None = None
    structural_hits = 0
    structural_start = time.perf_counter()
    resets = 0
    active_tolerance = settle_tolerance_pct
    while time.monotonic() < deadline:
        try:
            signature = await page.evaluate(
                """
                () => {
                  const sel = 'a[href],button,input,select,textarea,[role="button"]';
                  const regionSel = 'main,nav,header,footer,aside,section,article,[role="dialog"],[role="form"]';
                  const all = Array.from(document.querySelectorAll(sel));
                  const interactables = all.filter(el => {
                    const s = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return s.display !== 'none' && s.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                  }).length;
                  const regions = document.querySelectorAll(regionSel).length;
                  return [interactables, regions];
                }
                """
            )
        except Exception:
            await asyncio.sleep(0.05)
            continue
        if not isinstance(signature, (list, tuple)) or len(signature) < 2:
            sig_struct = (_as_int(signature, 0), 0)
        else:
            sig_struct = (_as_int(signature[0], 0), _as_int(signature[1], 0))
        # Detect SPA navigation mid-settle: URL change resets structural counters
        if settle_start_url is not None:
            try:
                current_url = await page.evaluate("location.href")
                if current_url != settle_start_url:
                    settle_start_url = current_url
                    previous_signature = None
                    structural_hits = 0
                    report.instability.append("spa_navigation_during_settle")
                    await asyncio.sleep(interactable_stable_ms / 1000)
                    continue
            except Exception:
                pass

        if previous_signature is None or _within_tolerance(previous_signature, sig_struct, active_tolerance):
            structural_hits += 1
        else:
            resets += 1
            structural_hits = 0
            if resets >= 3 and active_tolerance < 0.10:
                active_tolerance = 0.10
                fuzzy_fallback_engaged = True
        previous_signature = sig_struct
        if structural_hits >= structural_stable_hits:
            break
        await asyncio.sleep(interactable_stable_ms / 1000)
    report.durations_ms["structural_settle"] = int((time.perf_counter() - structural_start) * 1000)

    previous_behavioral: tuple[int, int, str] | None = None
    behavioral_hits = 0
    behavioral_start = time.perf_counter()
    while time.monotonic() < deadline:
        try:
            state = await page.evaluate(
                """
                () => {
                  const dialogs = document.querySelectorAll('[role="dialog"],[aria-modal="true"],dialog[open]').length;
                  const suggestions = document.querySelectorAll('[role="listbox"],[role="menu"],[aria-expanded="true"]').length;
                  const active = document.activeElement;
                  const activeSig = active ? `${active.tagName}:${active.getAttribute('role') || ''}:${active.id || ''}` : '';
                  return [dialogs, suggestions, activeSig];
                }
                """
            )
        except Exception:
            await asyncio.sleep(0.05)
            continue
        if not isinstance(state, (list, tuple)) or len(state) < 3:
            sig_behavioral = (0, 0, "")
        else:
            sig_behavioral = (_as_int(state[0], 0), _as_int(state[1], 0), str(state[2]))
        if previous_behavioral is None or previous_behavioral == sig_behavioral:
            behavioral_hits += 1
        else:
            behavioral_hits = 0
        previous_behavioral = sig_behavioral
        if behavioral_hits >= behavioral_stable_hits:
            break
        await asyncio.sleep(0.1)
    report.durations_ms["behavioral_settle"] = int((time.perf_counter() - behavioral_start) * 1000)

    previous_frame: tuple[int, int] | None = None
    frame_hits = 0
    frame_start = time.perf_counter()
    while time.monotonic() < deadline:
        try:
            frame_state = await page.evaluate(
                """
                () => {
                  const frames = document.querySelectorAll('iframe').length;
                  const frameInteractables = Array.from(document.querySelectorAll('iframe')).filter(f => {
                    const rect = f.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                  }).length;
                  return [frames, frameInteractables];
                }
                """
            )
        except Exception:
            await asyncio.sleep(0.05)
            continue
        if not isinstance(frame_state, (list, tuple)) or len(frame_state) < 2:
            sig_frame = (0, 0)
        else:
            sig_frame = (_as_int(frame_state[0], 0), _as_int(frame_state[1], 0))
        if previous_frame is None or previous_frame == sig_frame:
            frame_hits += 1
        else:
            frame_hits = 0
        previous_frame = sig_frame
        if frame_hits >= frame_stable_hits:
            break
        await asyncio.sleep(0.1)
    report.durations_ms["frame_settle"] = int((time.perf_counter() - frame_start) * 1000)

    if resets >= 3:
        report.instability.append("mutation_storm")
    if fuzzy_fallback_engaged:
        report.instability.append("mutation_storm_fallback")
    if previous_behavioral and previous_behavioral[0] > 0:
        report.instability.append("overlay_interference")
    if report.durations_ms["navigation_settle"] > settle_profile_slow_ms:
        report.instability.append("delayed_hydration")
    if not previous_signature or previous_signature[0] == 0:
        report.instability.append("unreachable_target")

    if time.monotonic() >= deadline:
        raise SettleTimeoutError("Page did not settle before timeout.")

    await asyncio.sleep(mutation_quiet_ms / 1000)
    return report


# ---------------------------------------------------------------------------------------------------
# Fast settle (default): one in-page DOM-quiet promise + an event-driven network tracker.
# ---------------------------------------------------------------------------------------------------

_QUIET_JS = """
([quietMs, maxMs]) => new Promise((resolve) => {
  const t0 = performance.now();
  let last = t0, n = 0;
  const watched = new Set(['class', 'hidden', 'open', 'aria-expanded', 'aria-hidden', 'style', 'disabled']);
  const mo = new MutationObserver((ms) => {
    for (const m of ms) {
      if (m.type === 'childList' && (m.addedNodes.length || m.removedNodes.length)) { last = performance.now(); n++; break; }
      if (m.type === 'attributes' && watched.has(m.attributeName)) { last = performance.now(); n++; break; }
    }
  });
  try { mo.observe(document.documentElement, { subtree: true, childList: true, attributes: true }); } catch (e) {}
  // A *busy indicator* is something that says "work in progress" AND is not just a static class name:
  // aria-busy / progressbar, or a visible element carrying a running CSS animation (spinners, skeleton pulses).
  const BUSY_SEL = '[aria-busy="true"],[role="progressbar"],[class*="spinner" i],[class*="skeleton" i],[class*="loading" i],[class*="loader" i]';
  const BUSY_TXT = /^\\s*(loading|please wait|fetching|searching|processing|just a moment)\\b[^\\n]{0,24}$/im;
  const visible = (e) => { try { return e.checkVisibility ? e.checkVisibility({ checkVisibilityCSS: true }) : e.offsetParent !== null; } catch (x) { return false; } };
  const animating = (e) => { try { return e.getAnimations({ subtree: true }).some((a) => a.playState === 'running'); } catch (x) { return false; } };
  let busyChecks = 0;
  const busy = () => {
    if (++busyChecks > 30) return false;           // bounded cost (~1.8 s)
    try {
      for (const e of document.querySelectorAll(BUSY_SEL)) {
        const r = e.getBoundingClientRect();
        if (r.width > 4 && r.height > 4 && r.bottom > 0 && r.top < innerHeight && visible(e)
            && (e.getAttribute('aria-busy') === 'true' || e.getAttribute('role') === 'progressbar' || animating(e))) return true;
      }
      const b = document.body;
      if (b && b.innerText && b.innerText.length < 4000 && BUSY_TXT.test(b.innerText)) return true;
    } catch (e) {}
    return false;
  };
  const tick = () => {
    const now = performance.now();
    if (document.readyState === 'loading' && now - t0 < maxMs) { setTimeout(tick, 20); return; }
    if (now - last >= quietMs && now - t0 < Math.min(maxMs, 2500) && busy()) { setTimeout(tick, 60); return; }
    if (now - last >= quietMs || now - t0 >= maxMs) {
      mo.disconnect();
      resolve({ waited: Math.round(now - t0), mutations: n, timedOut: now - t0 >= maxMs });
      return;
    }
    setTimeout(tick, Math.max(10, Math.min(25, quietMs / 2)));
  };
  requestAnimationFrame(() => setTimeout(tick, 0));
})
"""

_TRACKED_TYPES = {"document", "xhr", "fetch", "script", "stylesheet", "other"}


class NetTracker:
    """Counts in-flight requests that can still change the DOM (ignores images, fonts, media, sockets)."""

    def __init__(self) -> None:
        self._inflight: dict[int, float] = {}
        self._last_activity = time.monotonic()
        self._pages: list[Any] = []

    def attach(self, page: Any) -> None:
        if any(p is page for p in self._pages):
            return
        self._pages.append(page)
        try:
            page.on("request", self._on_start)
            page.on("requestfinished", self._on_end)
            page.on("requestfailed", self._on_end)
        except Exception:
            pass

    def _on_start(self, req: Any) -> None:
        try:
            if req.resource_type in _TRACKED_TYPES:
                self._inflight[id(req)] = time.monotonic()
                self._last_activity = time.monotonic()
        except Exception:
            pass

    def _on_end(self, req: Any) -> None:
        if self._inflight.pop(id(req), None) is not None:
            self._last_activity = time.monotonic()

    def inflight(self, ignore_older_than_s: float = 4.0) -> int:
        now = time.monotonic()
        return sum(1 for t in self._inflight.values() if now - t < ignore_older_than_s)

    def quiet_for_ms(self) -> int:
        if self.inflight() > 0:
            return 0
        return int((time.monotonic() - self._last_activity) * 1000)


async def fast_settle(page: Any, net: NetTracker | None, config: SettleConfig, *, intent: str = "action") -> SettleReport:
    cap_ms = {"navigation": config.navigation_cap_ms, "observe": config.observe_cap_ms}.get(intent, config.action_cap_ms)
    quiet_ms = config.quiet_ms
    report = SettleReport()
    t0 = time.monotonic()
    deadline = t0 + cap_ms / 1000
    dom_ms = 0
    net_wait_ms = 0
    while True:
        remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
        t = time.monotonic()
        try:
            res = await page.evaluate(_QUIET_JS, [quiet_ms, min(remaining_ms, cap_ms)])
            if isinstance(res, dict) and res.get("timedOut"):
                report.instability.append("dom_never_quiet")
        except Exception:
            # navigation destroyed the context: wait for the new document, then loop
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=max(200, remaining_ms))
            except Exception:
                await asyncio.sleep(0.05)
        dom_ms += int((time.monotonic() - t) * 1000)
        if net is None or net.inflight() == 0:
            break
        t = time.monotonic()
        while net.inflight() > 0 and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        net_wait_ms += int((time.monotonic() - t) * 1000)
        if time.monotonic() >= deadline:
            break
        # something finished: give the page one short quiet window to render the response
        quiet_ms = min(quiet_ms, 60)
        if net.quiet_for_ms() >= config.net_quiet_ms:
            continue
    if time.monotonic() >= deadline:
        report.instability.append("settle_cap_reached")
    report.durations_ms = {"dom_quiet": dom_ms, "network_wait": net_wait_ms, "total": int((time.monotonic() - t0) * 1000)}
    return report
