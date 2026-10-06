"""Primary runtime API."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
import warnings
from typing import Any

from semantic_browser.config import RuntimeConfig
from semantic_browser.errors import (
    ActionExecutionError,
    ActionNotFoundError,
    ActionStaleError,
    AttachmentError,
    BrowserNotReadyError,
    SettleTimeoutError,
)
from semantic_browser.executor.actions import execute_action
from semantic_browser.executor.results import build_execution, classify_status
from semantic_browser.executor.validation import resolve_action
from semantic_browser.extractor.diff import build_delta
from semantic_browser.extractor.engine import _SEE_MORE_ID, observe_page
from semantic_browser.extractor.engine_v2 import observe_page_v2
from semantic_browser.extractor.settle import NetTracker, SettleReport, fast_settle, wait_for_settle
from semantic_browser.extractor.snapshot import PageSnapshot, RefTable
from semantic_browser.extractor.view import RenderedView, ViewOptions, render_view
from semantic_browser.models import (
    ActionRequest,
    DiagnosticsReport,
    Observation,
    OwnershipMode,
    StepResult,
)
from semantic_browser.telemetry.debug_dump import export_json_bundle
from semantic_browser.telemetry.trace import TraceStore


class SemanticBrowserRuntime:
    """Deterministic semantic runtime for a live page."""

    def __init__(
        self,
        *,
        page: Any,
        config: RuntimeConfig | None = None,
        managed: bool = False,
        manager: Any | None = None,
        attached_kind: str = "page",
        ownership_mode: OwnershipMode = "owned_ephemeral",
        profile_warnings: list[str] | None = None,
    ) -> None:
        self._page = page
        self._config = config or RuntimeConfig()
        self._managed = managed
        self._manager = manager
        self._attached_kind = attached_kind
        self._ownership_mode = ownership_mode
        self._session_id = str(uuid.uuid4())
        self._current_observation: Observation | None = None
        self._id_map: dict[str, str] = {}
        self._last_expanded: bool = False
        self._trace = TraceStore(max_events=self._config.telemetry.max_events)
        self._profile_warnings = profile_warnings or []
        self._url_history: list[str] = []
        # v1.4 state
        self._refs = RefTable()
        self._net = NetTracker()
        self._snapshot: PageSnapshot | None = None
        self._view: RenderedView | None = None
        self._prev_lines: set[str] = set()
        self._popup: Any | None = None
        self._owned: list[Any] | None = None  # set when attached to a browser someone else is using
        self._dialog_notes: list[str] = []
        self._view_opts = ViewOptions(budget=self._config.extraction.view_budget)
        self._lite_sessions: dict[int, Any] = {}
        self._lite_lifted = False
        self._wire_page(page)

    # ------------------------------------------------------------------ v1.4 plumbing
    @property
    def page(self) -> Any:
        """The Playwright page currently driven (follows popups / tab switches)."""
        return self._page

    @property
    def refs(self) -> RefTable:
        return self._refs

    def _use_v2(self) -> bool:
        return self._config.extraction.engine == "v2" and hasattr(self._page, "main_frame")

    def _wire_page(self, page: Any) -> None:
        """Attach network tracking, dialog capture and popup adoption to a page (best effort)."""
        try:
            self._net.attach(page)
            page.on("dialog", lambda d: self._on_dialog(d))
            ctx = getattr(page, "context", None)
            ctx = ctx() if callable(ctx) else ctx
            if ctx is not None and not getattr(ctx, "_sb_wired", False):
                ctx.on("page", lambda p: self._on_popup(p))
                try:
                    ctx._sb_wired = True
                except Exception:
                    pass
        except Exception:
            pass

    async def _ensure_lite(self) -> None:
        if self._config.lite != "off" and not self._lite_lifted and hasattr(self._page, "context"):
            from semantic_browser import lite

            await lite.apply(self._page, self._config.lite, self._lite_sessions)

    async def allow_all_resources(self) -> None:
        """Turn lite blocking off for the rest of the session (e.g. a CAPTCHA needs its images)."""
        if self._config.lite == "off" or self._lite_lifted:
            return
        from semantic_browser import lite

        self._lite_lifted = True
        await lite.lift(self._page, self._lite_sessions)

    def _on_dialog(self, dialog: Any) -> None:
        async def _handle() -> None:
            try:
                msg = (dialog.message or "")[:120]
                self._dialog_notes.append(f'! page showed a {dialog.type} dialog: "{msg}" (auto-accepted)')
                await dialog.accept()
            except Exception:
                pass

        asyncio.ensure_future(_handle())

    def restrict_tabs_to(self, pages: list[Any]) -> None:
        """Attached to a shared browser: only ever list, switch to, or adopt tabs this session owns (or opened)."""
        self._owned = list(pages)
        self._popup = None

    def _on_popup(self, new_page: Any) -> None:
        if new_page is self._page:
            return
        if self._owned is not None:  # shared browser: ignore tabs a person (or another tool) opens
            asyncio.ensure_future(self._claim_popup(new_page))
            return
        self._take_popup(new_page)

    async def _claim_popup(self, new_page: Any) -> None:
        try:
            opener = await new_page.opener()
        except Exception:
            return
        if self._owned is not None and opener is not None and opener in self._owned:
            self._owned.append(new_page)
            self._take_popup(new_page)

    def _take_popup(self, new_page: Any) -> None:
        self._popup = new_page
        self._net.attach(new_page)
        try:
            new_page.on("dialog", lambda d: self._on_dialog(d))
        except Exception:
            pass

    async def _adopt_popup(self) -> str | None:
        pop = self._popup
        self._popup = None
        if pop is None:
            return None
        try:
            if pop.is_closed():
                return None
            try:
                await pop.wait_for_load_state("domcontentloaded", timeout=4000)
            except Exception:
                pass
            self._page = pop
            self._refs.reset()
            return f"opened in a new tab; now viewing it ({pop.url[:80]})"
        except Exception:
            return None

    def _context_pages(self) -> list[Any]:
        ctx = getattr(self._page, "context", None)
        ctx = ctx() if callable(ctx) else ctx
        try:
            pages = [p for p in (ctx.pages if ctx else []) if not p.is_closed()]
            if self._owned is not None:
                pages = [p for p in pages if p in self._owned]
            return pages
        except Exception:
            return []

    async def tab_titles(self) -> list[str]:
        out = []
        for i, p in enumerate(self._context_pages(), 1):
            try:
                t = (await p.title()) or p.url
            except Exception:
                t = p.url
            out.append(f"{'*' if p is self._page else ''}{i}:{t[:40]}")
        return out

    async def switch_tab(self, index: int) -> str:
        pages = self._context_pages()
        if not 1 <= index <= len(pages):
            raise ActionExecutionError(f"tab {index} does not exist (have {len(pages)}).")
        self._page = pages[index - 1]
        await self._page.bring_to_front()
        self._refs.reset()
        self._net.attach(self._page)
        return f"switched to tab {index}"

    async def _settle(self, intent: str) -> SettleReport | None:
        if self._config.settle.mode == "fast" and hasattr(self._page, "main_frame"):
            try:
                rep = await fast_settle(self._page, self._net, self._config.settle, intent=intent)
                self._trace.add("settle", {"intent": intent, "durations_ms": rep.durations_ms, "instability": rep.instability})
                return rep
            except Exception as exc:  # never let settle break an action
                self._trace.add("observe_warning", {"kind": "settle_error", "message": str(exc)[:120]})
                return None
        try:
            rep = await wait_for_settle(self._page, self._config.settle, intent=intent)
            self._trace.add("settle", {"intent": intent, "durations_ms": rep.durations_ms, "instability": rep.instability})
            return rep
        except SettleTimeoutError:
            self._trace.add("observe_warning", {"kind": "settle_timeout", "intent": intent})
            return None

    @classmethod
    def from_page(cls, page: Any, config: RuntimeConfig | None = None, profile_registry=None):
        del profile_registry
        if page is None:
            raise AttachmentError("Cannot attach to null page.")
        return cls(
            page=page,
            config=config,
            managed=False,
            attached_kind="page",
            ownership_mode="attached_context",
        )

    @staticmethod
    def _select_page(
        pages: list[Any],
        *,
        target_url_contains: str | None = None,
        page_index: int | None = None,
        prefer_non_blank: bool = True,
    ) -> Any | None:
        if not pages:
            return None
        if page_index is not None and 0 <= page_index < len(pages):
            return pages[page_index]
        if target_url_contains:
            needle = target_url_contains.lower()
            by_url = next((p for p in pages if needle in (getattr(p, "url", "") or "").lower()), None)
            if by_url:
                return by_url
        if prefer_non_blank:
            non_blank = next((p for p in pages if (getattr(p, "url", "") or "") not in {"", "about:blank"}), None)
            if non_blank:
                return non_blank
        return pages[0]

    @classmethod
    def from_context(cls, context: Any, config: RuntimeConfig | None = None, profile_registry=None):
        del profile_registry
        page = cls._select_page(context.pages, prefer_non_blank=True)
        if page is None:
            raise AttachmentError("Cannot attach: context has no pages.")
        return cls(
            page=page,
            config=config,
            managed=False,
            attached_kind="context",
            ownership_mode="attached_context",
        )

    @classmethod
    async def from_cdp_endpoint(
        cls,
        endpoint: str,
        config: RuntimeConfig | None = None,
        profile_registry=None,
        *,
        target_url_contains: str | None = None,
        page_index: int | None = None,
        prefer_non_blank: bool = True,
    ):
        del profile_registry
        if "/devtools/page/" in endpoint:
            raise AttachmentError(
                "CDP attach expects a browser websocket endpoint (/devtools/browser/...), "
                "not a page websocket endpoint (/devtools/page/...)."
            )
        if page_index is not None and page_index < 0:
            raise AttachmentError(f"CDP attach page_index must be >= 0 (got {page_index}).")
        try:
            from playwright.async_api import async_playwright
        except Exception as exc:
            raise AttachmentError("Playwright is required for CDP attach.") from exc
        pw = await async_playwright().start()
        try:
            browser = await pw.chromium.connect_over_cdp(endpoint)
            contexts = list(browser.contexts)
            context = contexts[0] if contexts else await browser.new_context()
            if page_index is not None:
                page_count = len(context.pages)
                if page_count == 0:
                    raise AttachmentError(
                        "CDP attach cannot select page_index when no pages are open in the target context."
                    )
                if page_index >= page_count:
                    raise AttachmentError(
                        f"CDP attach page_index {page_index} is out of range for {page_count} page(s)."
                    )
            page = cls._select_page(
                context.pages,
                target_url_contains=target_url_contains,
                page_index=page_index,
                prefer_non_blank=prefer_non_blank,
            )
            if page is None:
                page = await context.new_page()
            return cls(
                page=page,
                config=config,
                managed=False,
                manager={"pw": pw, "browser": browser, "attached_cdp": True},
                attached_kind="cdp",
                ownership_mode="attached_cdp",
            )
        except Exception as exc:
            try:
                await pw.stop()
            finally:
                pass
            raise AttachmentError(f"Failed CDP attach at {endpoint}: {exc}") from exc

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def ownership_mode(self) -> OwnershipMode:
        return self._ownership_mode

    @staticmethod
    def _is_no_visible_nodes_state(observation: Observation) -> bool:
        reasons = {r.lower() for r in observation.confidence.reasons}
        return "no visible nodes" in reasons or (
            len(observation.available_actions) == 0 and observation.confidence.overall <= 0.2
        )

    async def _observe_v2(self, mode: str, *, settle: bool, view_options: ViewOptions | None) -> Observation:
        if settle:
            await self._settle("observe")
        tabs = await self.tab_titles() if len(self._context_pages()) > 1 else None
        notes = list(self._dialog_notes)
        self._dialog_notes.clear()
        vo = view_options or self._view_opts
        observation: Observation | None = None
        id_map: dict[str, str] = {}
        t0 = time.perf_counter()
        attempt = 0
        for attempt in range(1, 4):
            observation, id_map, snap, view = await observe_page_v2(
                session_id=self._session_id, page=self._page, mode=mode, config=self._config,
                previous_observation=self._current_observation, previous_ids=self._id_map, refs=self._refs,
                view_options=vo, tabs=tabs, notes=notes,
            )
            text_chars = sum(len(t[1]) for t in snap.flow if t[0] == "t")
            blank = (snap.url or "").startswith(("about:", "chrome-error:")) or not snap.url
            if attempt < 3 and not blank and len(snap.nodes) < 2 and text_chars < 30 and mode != "delta":
                await asyncio.sleep(0.2 * attempt)  # SPA hydration / late render
                continue
            break
        assert observation is not None
        self._snapshot, self._view = snap, view
        self._id_map = id_map
        self._current_observation = observation
        if observation.page.url and (not self._url_history or self._url_history[-1] != observation.page.url):
            self._url_history.append(observation.page.url)
        self._trace.add(
            "observe",
            {"mode": mode, "engine": "v2", "actions": len(observation.available_actions), "recovery_attempts": attempt - 1,
             "observe_ms": int((time.perf_counter() - t0) * 1000), "nodes": len(snap.nodes), "js_ms": snap.stats.get("ms")},
        )
        return observation

    def rerender(self, *, page: int | None = None, expand: set[str] | None = None, all_layers: bool = False,
                 budget: int | None = None, mode: str = "view") -> RenderedView:
        """Re-render the last snapshot with different view options (no browser round trip)."""
        if self._snapshot is None:
            raise BrowserNotReadyError("No snapshot yet; call observe()/navigate() first.")
        vo = ViewOptions(
            budget=budget or (self._view_opts.budget if mode == "view" else max(self._view_opts.budget, 12000)),
            page=page, expand=expand or set(), all_layers=all_layers, mode=mode,
            line_cap=420 if mode == "view" else 2500,
        )
        self._view = render_view(self._snapshot, options=vo, tabs=None)
        return self._view

    async def observe(self, mode: str = "summary", *, expanded: bool = False, settle: bool = True,
                      view_options: ViewOptions | None = None) -> Observation:
        if self._use_v2():
            return await self._observe_v2(mode, settle=settle, view_options=view_options)
        max_attempts = 3 if mode == "summary" else 1
        observation: Observation | None = None
        id_map: dict[str, str] = {}
        settle_timed_out = False
        settle_ms = 0
        for attempt in range(1, max_attempts + 1):
            settle_start = time.perf_counter()
            try:
                settle_report = await wait_for_settle(self._page, self._config.settle, intent="observe") if settle else None
            except SettleTimeoutError:
                settle_timed_out = True
                settle_report = None
                self._trace.add(
                    "observe_warning",
                    {
                        "kind": "settle_timeout",
                        "attempt": attempt,
                        "mode": mode,
                    },
                )
            settle_ms = int((time.perf_counter() - settle_start) * 1000)
            if settle_report:
                self._trace.add(
                    "settle",
                    {
                        "intent": "observe",
                        "durations_ms": settle_report.durations_ms,
                        "instability": settle_report.instability,
                    },
                )
            observe_start = time.perf_counter()
            observation, id_map = await observe_page(
                session_id=self._session_id,
                page=self._page,
                mode=mode,
                config=self._config,
                previous_observation=self._current_observation,
                previous_ids=self._id_map,
                expanded=expanded,
            )
            observe_ms = int((time.perf_counter() - observe_start) * 1000)
            if attempt < max_attempts and self._is_no_visible_nodes_state(observation):
                await self._page.wait_for_timeout(300 + (attempt * 200))
                continue
            break

        if observation is None:
            raise BrowserNotReadyError("Observation failed: no observation payload produced.")
        if settle_timed_out and "settle timeout" not in {r.lower() for r in observation.confidence.reasons}:
            observation.confidence.reasons.append("settle timeout")

        self._id_map = id_map
        self._current_observation = observation
        if observation.page.url:
            if not self._url_history or self._url_history[-1] != observation.page.url:
                self._url_history.append(observation.page.url)
        self._trace.add(
            "observe",
            {
                "mode": mode,
                "expanded": expanded,
                "actions": len(observation.available_actions),
                "recovery_attempts": max(0, attempt - 1),
                "settle_ms": settle_ms,
                "observe_ms": observe_ms,
                "settle_timed_out": settle_timed_out,
            },
        )
        return observation

    async def inspect(self, target_id: str, mode: str = "auto") -> dict[str, Any]:
        del mode
        obs = self._current_observation or await self.observe(mode="summary")
        region = next((r for r in obs.regions if r.id == target_id), None)
        if region:
            return {"kind": "region", "region": region.model_dump()}
        form = next((f for f in obs.forms if f.id == target_id), None)
        if form:
            return {"kind": "form", "form": form.model_dump()}
        group = next((g for g in obs.content_groups if g.id == target_id), None)
        if group:
            return {"kind": "content_group", "content_group": group.model_dump()}
        action = next((a for a in obs.available_actions if a.id == target_id), None)
        if action:
            return {"kind": "action", "action": action.model_dump()}
        return {"kind": "unknown", "target_id": target_id}

    async def act(self, request: ActionRequest) -> StepResult:
        if request.action_id == _SEE_MORE_ID:
            return await self._handle_see_more(request)

        self._last_expanded = False
        obs_before = self._current_observation or await self.observe(mode="summary")
        if self._view is not None:
            self._prev_lines = set(self._view.all_lines)  # baseline for "what changed" = what the model last saw
        resolve_start = time.perf_counter()
        try:
            action = resolve_action(request, obs_before)
        except ActionStaleError as exc:
            empty_delta = build_delta(obs_before, obs_before)
            execution = build_execution(
                request.op or "unknown",
                False,
                str(exc),
                obs_before,
                obs_before,
                empty_delta,
            )
            return StepResult(
                request=request,
                status="stale",
                message=str(exc),
                execution=execution,
                observation=obs_before,
                delta=empty_delta,
            )
        except ActionNotFoundError as exc:
            empty_delta = build_delta(obs_before, obs_before)
            execution = build_execution(
                request.op or "unknown",
                False,
                str(exc),
                obs_before,
                obs_before,
                empty_delta,
            )
            return StepResult(
                request=request,
                status="invalid",
                message=str(exc),
                execution=execution,
                observation=obs_before,
                delta=empty_delta,
            )
        resolve_ms = int((time.perf_counter() - resolve_start) * 1000)
        self._trace.add("action_request", self._safe_action_payload(request))
        self._trace.add(
            "action_stage",
            {
                "stage": "resolve",
                "resolve_ms": resolve_ms,
                "action_id": action.id,
                "locator_chain": action.locator_recipe,
                "target_fingerprint": action.target_id,
                "retry_attempts": 0,
            },
        )
        execute_start = time.perf_counter()
        try:
            outcome = await execute_action(self._page, action, request, refs=self._refs if self._use_v2() else None)
            ok, message = outcome.ok, outcome.message
        except (ActionExecutionError, ActionStaleError) as exc:
            self._trace.add(
                "action_error",
                {"stage": "execute", "error_type": type(exc).__name__, "message": str(exc), "action_id": action.id},
            )
            empty_delta = build_delta(obs_before, obs_before)
            execution = build_execution(action.op, False, str(exc), obs_before, obs_before, empty_delta)
            stale = isinstance(exc, ActionStaleError)
            return StepResult(
                request=request,
                status="stale" if stale else "failed",
                message=str(exc),
                outcome=f"FAILED: {exc}",
                execution=execution,
                observation=obs_before,
                delta=empty_delta,
            )
        execute_ms = int((time.perf_counter() - execute_start) * 1000)
        settle_start = time.perf_counter()
        popup_note = await self._adopt_popup() if self._use_v2() else None
        if popup_note:
            outcome.evidence["new_tab"] = True
        navigating = action.op in {"open", "submit", "navigate"} or outcome.effect_hint == "navigation" or bool(popup_note)
        await self._settle("navigation" if navigating else "action")
        settle_ms = int((time.perf_counter() - settle_start) * 1000)
        obs_after = await self.observe(mode="delta", settle=False)
        delta = build_delta(obs_before, obs_after)
        if self._needs_grace(action, outcome, delta, popup_note):
            grace_cfg = self._config.settle.model_copy(
                update={"quiet_ms": self._config.settle.grace_ms, "action_cap_ms": self._config.settle.grace_cap_ms}
            )
            try:
                await fast_settle(self._page, self._net, grace_cfg, intent="action")
            except Exception:
                pass
            obs_after = await self.observe(mode="delta", settle=False)
            delta = build_delta(obs_before, obs_after)
        status = classify_status(ok, message, delta)
        step_outcome = self._describe_outcome(action, message, obs_before, obs_after, delta, popup_note)
        execution = build_execution(
            action.op,
            ok,
            message,
            obs_before,
            obs_after,
            delta,
            effect_hint=outcome.effect_hint,
            evidence=outcome.evidence,
        )
        result = StepResult(
            request=request,
            status=status,
            message=message,
            outcome=step_outcome,
            execution=execution,
            observation=obs_after,
            delta=delta,
        )
        self._trace.add(
            "action_result",
            {
                "status": status,
                "message": message,
                "resolve_ms": resolve_ms,
                "execute_ms": execute_ms,
                "settle_ms": settle_ms,
                "effect": execution.effect,
                "new_tab": bool(outcome.evidence.get("new_tab")),
                "evidence": outcome.evidence,
                "delta_materiality": delta.materiality,
            },
        )
        return result

    async def _handle_see_more(self, request: ActionRequest) -> StepResult:
        """Re-observe with expanded=True showing all available actions.

        If the previous observation was already expanded, return the same
        observation with a hint to choose from the existing list instead.
        """
        obs_before = self._current_observation or await self.observe(mode="summary")

        if self._use_v2() and self._view is not None:
            empty = build_delta(obs_before, obs_before)
            if not self._view.more_below:
                msg = "Nothing more below; this is the end of the page view."
            else:
                self.rerender(page=self._view.page + 1)
                if obs_before.planner:
                    obs_before.planner.room_text = self._view.text
                msg = f"Showing page {self._view.page}/{self._view.pages} of the view."
            return StepResult(
                request=request, status="success", message=msg, outcome=msg,
                execution=build_execution("see_more", True, msg, obs_before, obs_before, empty),
                observation=obs_before, delta=empty,
            )

        if self._last_expanded:
            empty_delta = build_delta(obs_before, obs_before)
            execution = build_execution("see_more", True, "already expanded", obs_before, obs_before, empty_delta)
            return StepResult(
                request=request,
                status="success",
                message="Already showing all actions. Choose from the list or try a different approach.",
                execution=execution,
                observation=obs_before,
                delta=empty_delta,
            )

        observation = await self.observe(mode="auto", expanded=True)
        self._last_expanded = True
        delta = build_delta(obs_before, observation)
        return StepResult(
            request=request,
            status="success",
            message="Expanded view: showing all available actions.",
            execution=build_execution("see_more", True, "expanded action list", obs_before, observation, delta),
            observation=observation,
            delta=delta,
        )

    def _needs_grace(self, action: Any, outcome: Any, delta: Any, popup_note: str | None) -> bool:
        """True when a click/submit changed nothing visible yet: late timers/debounced renders may still land."""
        if not self._use_v2() or self._view is None or popup_note or delta.navigated or self._config.settle.mode != "fast":
            return False
        if action.op not in {"click", "open", "toggle", "press"} and outcome.effect_hint != "content_change":
            return False
        import re

        control = re.compile(r"\[\d+ (input|select|checkbox|radio|textarea)")
        fresh = [ln for ln in self._view.all_lines if ln not in self._prev_lines and not control.search(ln)]
        return not fresh

    def _describe_outcome(self, action, message, before, after, delta, popup_note=None) -> str:
        """One line telling the model what the action did, so it need not diff two pages itself."""
        label = f"[{action.ref}] {action.label[:50]!r}" if action.ref is not None else f"{action.op} {action.label[:50]!r}"
        bits = [f"{message or action.op} {label}"]
        if popup_note:
            bits.append(popup_note)
        if delta.navigated:
            bits.append(f"-> now at {after.page.title[:60]!r} ({after.page.url[:100]})")
        if before.page.modal_active and not after.page.modal_active:
            bits.append("overlay dismissed")
        elif after.page.modal_active and not before.page.modal_active:
            bits.append("an overlay appeared and covers the page")
        if self._view is not None and not delta.navigated:
            new_lines = [ln for ln in self._view.all_lines if ln not in self._prev_lines]
            gone = len([ln for ln in self._prev_lines if ln not in set(self._view.all_lines)])
            if new_lines or gone:
                shown = "; ".join(ln[:90] for ln in new_lines[:4])
                bits.append(f"page changed (+{len(new_lines)}/-{gone} lines){': ' + shown if shown else ''}")
            elif not popup_note and action.op in {"click", "open", "toggle", "fill"} and "unchanged" not in (message or ""):
                bits.append("no visible change on the page")
        if self._view is not None:
            self._prev_lines = set(self._view.all_lines)
        return " ".join(bits)

    async def _goto(self, url: str, *, intent: str = "navigation") -> None:
        await self._ensure_lite()
        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except TypeError:
            await self._page.goto(url)
        except Exception as exc:
            if "ERR_" in str(exc) and "TIMED_OUT" not in str(exc):
                raise ActionExecutionError(f"navigation failed: {str(exc).splitlines()[0][:160]}") from exc
            # Some sites never reach DOMContentLoaded quickly (long-polling, ads): continue with what we have.
            try:
                await self._page.goto(url, wait_until="commit", timeout=20000)
            except Exception as exc2:
                raise ActionExecutionError(f"navigation failed: {str(exc2).splitlines()[0][:160]}") from exc2
        await self._settle(intent)

    async def _step_after(self, op: str, message: str, before: Observation | None, *, request: ActionRequest | None = None) -> StepResult:
        observation = await self.observe(mode="summary" if op == "navigate" else "delta", settle=False)
        base = before or observation
        delta = build_delta(before, observation)
        outcome = f"{message}" + (f" -> {observation.page.title[:60]!r} ({observation.page.url[:100]})" if op != "reload" else "")
        if self._view is not None:
            self._prev_lines = set(self._view.all_lines)
        return StepResult(
            request=request or ActionRequest(op=op),
            status="success",
            message=message,
            outcome=outcome,
            execution=build_execution(op, True, message, base, observation, delta, effect_hint="navigation"),
            observation=observation,
            delta=delta,
        )

    async def navigate(self, url: str) -> StepResult:
        if not self._page:
            raise BrowserNotReadyError("No page bound to runtime.")
        if "://" not in url and not url.startswith(("about:", "data:")):
            url = "https://" + url
        before = self._current_observation
        await self._goto(url)
        return await self._step_after("navigate", f"navigated to {url}", before, request=ActionRequest(op="navigate", value=url))

    async def back(self) -> StepResult:
        before = self._current_observation
        await self._page.go_back(wait_until="domcontentloaded")
        await self._settle("navigation")
        return await self._step_after("back", "went back", before)

    async def forward(self) -> StepResult:
        before = self._current_observation
        await self._page.go_forward(wait_until="domcontentloaded")
        await self._settle("navigation")
        return await self._step_after("forward", "went forward", before)

    async def reload(self) -> StepResult:
        before = self._current_observation
        await self._page.reload(wait_until="domcontentloaded")
        await self._settle("navigation")
        return await self._step_after("reload", "reloaded", before)

    async def current_observation(self):
        return self._current_observation

    async def diagnostics(self) -> DiagnosticsReport:
        url = self._page.url if self._page else ""
        return DiagnosticsReport(
            session_id=self._session_id,
            managed=self._managed,
            attached_kind=self._attached_kind,
            ownership_mode=self._ownership_mode,
            current_url=url,
            last_observation_at=(self._current_observation.timestamp if self._current_observation else None),
            trace_events=len(self._trace.events),
            healthy=self._page is not None,
            notes=list(self._profile_warnings),
        )

    async def export_trace(self, path: str) -> str:
        tab_creations = sum(1 for e in self._trace.events if e.get("kind") == "action_result" and e.get("payload", {}).get("new_tab"))
        dialog_events = [
            e for e in self._trace.events if e.get("kind") in {"settle", "action_result"} and "overlay" in json.dumps(e)
        ]
        payload = {
            "session_id": self._session_id,
            "ownership_mode": self._ownership_mode,
            "events": self._trace.events,
            "url_history": self._url_history,
            "tab_creation_count": tab_creations,
            "dialog_stack_events": dialog_events,
            "observation": self._current_observation.model_dump() if self._current_observation else None,
        }
        self._trace.add("trace_export", {"path": path, "bytes": len(json.dumps(payload, default=str))})
        return export_json_bundle(path, payload)

    @staticmethod
    def _safe_action_payload(request: ActionRequest) -> dict[str, Any]:
        payload = request.model_dump()
        if payload.get("value") is not None:
            payload["value"] = "[REDACTED]"
        return payload

    async def close(self) -> None:
        if self._ownership_mode in {"attached_context", "attached_cdp"}:
            warnings.warn(
                f"close() in {self._ownership_mode} does not close externally owned browser; "
                "use force_close_browser() only if you explicitly own the target browser.",
                stacklevel=2,
            )
            if self._ownership_mode == "attached_cdp" and isinstance(self._manager, dict) and "pw" in self._manager:
                await self._manager["pw"].stop()
            return
        if self._manager:
            if hasattr(self._manager, "close"):
                await self._manager.close()
            elif isinstance(self._manager, dict):
                try:
                    if self._manager.get("browser") is not None:
                        await self._manager["browser"].close()
                finally:
                    if self._manager.get("pw") is not None:
                        await self._manager["pw"].stop()

    async def force_close_browser(self) -> None:
        self._trace.add("force_close", {"ownership_mode": self._ownership_mode})
        if self._manager and hasattr(self._manager, "close"):
            await self._manager.close()
            return
        if isinstance(self._manager, dict):
            try:
                if self._manager.get("browser") is not None:
                    await self._manager["browser"].close()
            finally:
                if self._manager.get("pw") is not None:
                    await self._manager["pw"].stop()
