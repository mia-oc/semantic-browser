"""Agent-facing verb layer: one short command in, one compact text view out.

    s = await AgentSession.launch(headful=True)
    print(await s.run("goto example.com"))
    print(await s.run('type 3 "hello" --enter'))

Every verb returns plain text: a one-line outcome (what the action did / why it failed) followed by the page view with
`[n]` refs. The same layer backs the `sb` CLI daemon, so a model sees identical output from Python and from a shell.
"""

from __future__ import annotations

import contextlib
import re
import shlex
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

from semantic_browser import captcha as cap
from semantic_browser.daemon import paths
from semantic_browser.errors import ActionExecutionError, BrowserNotReadyError, SemanticBrowserError
from semantic_browser.models import ActionRequest, StepResult
from semantic_browser.runtime import SemanticBrowserRuntime
from semantic_browser.verbs_help import HELP

_KEEP_SHOTS = 40


def _split(line: str | list[str]) -> list[str]:
    return list(line) if isinstance(line, list) else shlex.split(line)


def _flags(
    args: list[str], bool_flags: set[str], value_flags: set[str] | None = None, *, strict: bool = False
) -> tuple[list[str], set[str], dict[str, str]]:
    """Split flags from positionals. strict=True rejects unknown --options instead of silently treating them as text."""
    pos: list[str] = []
    flags: set[str] = set()
    vals: dict[str, str] = {}
    value_flags = value_flags or set()
    i = 0
    while i < len(args):
        a = args[i]
        if a in bool_flags:
            flags.add(a)
        elif a in value_flags and i + 1 < len(args):
            vals[a] = args[i + 1]
            i += 1
        elif strict and a.startswith("--") and len(a) > 2:
            known = ", ".join(sorted(bool_flags | value_flags))
            raise ValueError(f"unknown option {a}. Options here: {known}")
        else:
            pos.append(a)
        i += 1
    return pos, flags, vals


def _column_header(lines: list[str], is_header: list[bool], i: int) -> str:
    """The <th> row(s) above table row `i`, or "" when there is none (never guess: a wrong header is worse than none)."""
    if i >= len(is_header) or is_header[i] or " | " not in lines[i]:
        return ""
    j, gap = i - 1, 0
    while j >= 0 and not is_header[j]:
        gap = 0 if " | " in lines[j] else gap + 1
        if gap > 2 or i - j > 80:
            return ""
        j -= 1
    if j < 0:
        return ""
    top = j
    while top > 0 and is_header[top - 1] and j - top < 3:
        top -= 1
    return re.sub(r"\s{2,}", " ", re.sub(r"\[\d+[^\]]*\]", "", " / ".join(lines[top : j + 1]))).strip()


_FAIL = ("ERROR", "FAILED", "STALE", "INVALID", "BLOCKED")


def _target(words: list[str]) -> str:
    """`click 12` -> '12'; `click Save settings` (unquoted label) -> 'Save settings'."""
    first = words[0]
    return first if first.strip("[]#eE").isdigit() else " ".join(words)


def _snippet(line: str, needle: str, width: int = 240) -> str:
    """Trim a long line to ~width chars centred on the match, so what you searched for is always visible."""
    if len(line) <= width:
        return line
    pos = line.lower().find(needle) if needle else 0
    start = max(0, min(pos - width // 2, len(line) - width)) if pos > 0 else 0
    end = min(len(line), start + width)
    return ("…" if start else "") + line[start:end] + ("…" if end < len(line) else "")


_MARKS_JS = r"""(items) => {
  const old = document.getElementById('__sb_marks'); if (old) old.remove();
  const layer = document.createElement('div'); layer.id = '__sb_marks';
  layer.style.cssText = 'position:fixed;left:0;top:0;width:0;height:0;z-index:2147483647;pointer-events:none';
  const reg = window.__sb; let n = 0;
  for (const [local, ref] of items) {
    const w = reg && reg.els.get(local); const el = w && w.deref();
    if (!el || !el.isConnected) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4 || r.bottom < 0 || r.right < 0 || r.top > innerHeight || r.left > innerWidth) continue;
    const box = document.createElement('div');
    box.style.cssText = 'position:fixed;left:' + r.left + 'px;top:' + r.top + 'px;width:' + r.width + 'px;height:' + r.height + 'px;outline:1.5px solid #e00;box-sizing:border-box';
    const tag = document.createElement('div'); tag.textContent = String(ref);
    tag.style.cssText = 'position:fixed;left:' + Math.max(0, r.left - 1) + 'px;top:' + Math.max(0, r.top - 13) + 'px;font:bold 11px/13px Arial,sans-serif;color:#fff;background:#e00;padding:0 3px;border-radius:2px';
    layer.appendChild(box); layer.appendChild(tag); n++;
  }
  document.documentElement.appendChild(layer); return n;
}"""


async def resolve_cdp_endpoint(endpoint: str) -> str:
    """Accept `http://host:port` (as printed by `chrome --remote-debugging-port`) as well as a full `ws://…/devtools/browser/…` URL."""
    if not endpoint.startswith(("http://", "https://")):
        return endpoint
    import asyncio
    import json
    import urllib.request

    url = endpoint.rstrip("/") + "/json/version"

    def _fetch() -> str:
        # only loopback / explicit endpoints the user typed; no redirects followed to other hosts
        with urllib.request.urlopen(url, timeout=5) as r:  # noqa: S310
            return str(json.loads(r.read())["webSocketDebuggerUrl"])

    try:
        return await asyncio.get_running_loop().run_in_executor(None, _fetch)
    except Exception as exc:
        raise ActionExecutionError(f"could not read the CDP endpoint at {url}: {exc}") from exc


class AgentSession:
    def __init__(self, runtime: SemanticBrowserRuntime, session: Any | None = None, name: str = "default") -> None:
        self.runtime = runtime
        self._session = session
        self.name = name
        self._challenge: cap.Challenge | None = None
        self._shots = 0
        self._shots_dir = paths.home() / "shots"
        self._own_tab: Any | None = None  # set when attached over CDP

    # ------------------------------------------------------------------ lifecycle
    @classmethod
    async def launch(
        cls,
        *,
        headful: bool = True,
        profile_dir: str | None = None,
        profile_mode: str | None = None,
        cdp: str | None = None,
        name: str = "default",
        lite: str = "off",
        budget: int | None = None,
    ) -> AgentSession:
        from semantic_browser.config import RuntimeConfig

        config = RuntimeConfig()
        config.lite = lite if lite in {"off", "media", "max"} else "off"
        if budget:
            config.extraction.view_budget = max(600, int(budget))
        if cdp:
            runtime = await SemanticBrowserRuntime.from_cdp_endpoint(await resolve_cdp_endpoint(cdp), config=config)
            # never hijack a tab somebody else is using: work in a tab of our own and close only that one on exit
            ctx = runtime.page.context
            ctx = ctx() if callable(ctx) else ctx
            own = await ctx.new_page()
            runtime._page = own
            runtime._refs.reset()
            runtime._wire_page(own)
            runtime.restrict_tabs_to([own])  # tab list/switch/popup adoption never touch the person's own tabs
            sess = cls(runtime, None, name)
            sess._own_tab = own
            return sess
        from semantic_browser.session import ManagedSession

        mode = profile_mode or ("persistent" if profile_dir else "ephemeral")
        session = await ManagedSession.launch(headful=headful, profile_mode=mode, profile_dir=profile_dir, config=config)
        return cls(session.runtime, session, name)

    async def close(self) -> str:
        try:
            if self._session is not None:
                await self._session.close()
            else:
                if self._own_tab is not None:  # only the tab we created; never one a person is using
                    with contextlib.suppress(Exception):
                        await self._own_tab.close()
                await self.runtime.close()
        except Exception as exc:  # closing must never raise to the caller
            return f"closed (with warning: {exc})"
        return "closed"

    # ------------------------------------------------------------------ output helpers
    def _text(self, res: StepResult) -> str:
        head = res.outcome or res.message or ""
        if res.status in {"failed", "stale", "invalid", "blocked"} and not head.startswith("FAILED"):
            head = f"{res.status.upper()}: {res.message or head}"
        view = res.observation.planner.room_text if res.observation.planner else ""
        return f"{head}\n\n{view}".strip()

    def _current_view(self) -> str:
        obs = self.runtime._current_observation
        return obs.planner.room_text if obs and obs.planner else ""

    async def _fresh_view(self, head: str = "") -> str:
        obs = await self.runtime.observe(mode="summary")
        view = obs.planner.room_text if obs.planner else ""
        return f"{head}\n\n{view}".strip() if head else view

    # ------------------------------------------------------------------ dispatch
    async def run(self, line: str | list[str]) -> str:
        t0 = time.perf_counter()
        try:
            argv = _split(line)
        except ValueError as exc:
            return f"ERROR: could not parse command ({exc}). Quote text with double quotes."
        if not argv:
            return HELP
        verb, args = argv[0].lower(), argv[1:]
        handler = getattr(self, f"_v_{verb.replace('-', '_')}", None)
        if handler is None:
            return f"ERROR: unknown verb {verb!r}. Verbs: goto view click type select check press hover scroll find wait do back forward reload tabs tab shot captcha close help"
        try:
            out = await handler(args)
        except (ActionExecutionError, BrowserNotReadyError, SemanticBrowserError, RuntimeError, ValueError) as exc:
            out = f"ERROR: {exc}\n\n{self._current_view()}".strip()
        except Exception as exc:  # last-resort guard so a verb can never kill the daemon
            out = f"ERROR: {type(exc).__name__}: {str(exc).splitlines()[0][:200] if str(exc) else ''}\n\n{self._current_view()}".strip()
        self.runtime._trace.add("verb", {"verb": verb, "ms": int((time.perf_counter() - t0) * 1000)})
        return out

    # ------------------------------------------------------------------ verbs
    async def _v_help(self, args: list[str]) -> str:
        return HELP

    async def _v_close(self, args: list[str]) -> str:
        return await self.close()

    async def _v_goto(self, args: list[str]) -> str:
        if not args:
            raise ValueError("usage: goto URL")
        return self._text(await self.runtime.navigate(args[0]))

    async def _v_view(self, args: list[str]) -> str:
        pos, flags, vals = _flags(args, {"--full", "--fresh", "--all"}, {"--page", "--expand"}, strict=True)
        if "--all" in flags:  # show the page behind a blocking overlay too
            self.runtime.rerender(all_layers=True)
            return self._cached_text()
        if "--expand" in vals:  # the view itself suggests `view --expand nav` for collapsed navigation/footers
            self.runtime.rerender(expand={vals["--expand"].lower()})
            return self._cached_text()
        if "--page" in vals:
            self.runtime.rerender(page=int(vals["--page"]))
            return self._cached_text()
        if "--full" in flags:
            self.runtime.rerender(mode="full")
            return self._cached_text()
        return await self._fresh_view()

    def _cached_text(self) -> str:
        v = self.runtime._view
        return v.text if v is not None else self._current_view()

    def _resolve_label(self, text: str) -> str:
        """`click "Football"`: accept a label when exactly one element in the current view has it; else list the choices.

        Numbers stay the primary, unambiguous way to target something; this is a convenience for models that
        (reasonably) write the visible text instead of the [n].
        """
        obs = self.runtime._current_observation
        acts = [a for a in (obs.available_actions if obs else []) if getattr(a, "ref", None) is not None]
        want = " ".join(text.lower().split())

        def label_of(a: Any) -> str:
            return " ".join((a.label or "").lower().split())

        base = self.runtime.page.url

        def dest(a: Any) -> str:
            href = str((a.locator_recipe or {}).get("href") or "").strip()
            return "" if not href or href.lower().startswith("javascript") else urljoin(base, href)

        def show(a: Any) -> str:
            d = urlsplit(dest(a))
            raw = str((a.locator_recipe or {}).get("href") or "")
            if d.netloc:
                where = f" → {d.path or '/'}{'?' + d.query if d.query else ''}{'#' + d.fragment if d.fragment else ''}"
            else:
                where = f" → {raw}" if raw else ""
            return f"[{a.ref}] {a.label}" + (f" ({a.context})" if getattr(a, "context", None) else "") + where

        hits = [a for a in acts if label_of(a) == want] or [a for a in acts if want and want in label_of(a)]
        if len(hits) == 1:
            return str(hits[0].ref)
        dests = {dest(a) for a in hits}
        if len(dests) == 1 and next(iter(dests)):  # nav + footer + hero links to the same page: not ambiguous
            return str(hits[0].ref)
        if not hits:
            raise ValueError(f"no element labelled {text!r} in the current view. Use a [n] number, or `find {text}`.")
        raise ValueError(
            f"{len(hits)} elements match {text!r}: " + "; ".join(show(a) for a in hits[:6]) + ". Use the [n] number you want."
        )

    async def _ref_act(self, ref: str, op: str | None, value: Any = None, options: dict[str, Any] | None = None) -> str:
        if not str(ref).strip("[]#eE").isdigit():
            ref = self._resolve_label(str(ref))
        res = await self.runtime.act(ActionRequest(action_id=str(ref), op=op, value=value, options=options or {}))
        return self._text(res)

    async def _v_click(self, args: list[str]) -> str:
        pos, flags, _ = _flags(args, {"--force"})
        if not pos:
            raise ValueError("usage: click N [--force]")
        return await self._ref_act(_target(pos), None, options={"force": "--force" in flags})

    async def _v_type(self, args: list[str]) -> str:
        pos, flags, _ = _flags(args, {"--enter", "--append"})
        if len(pos) < 2:
            raise ValueError('usage: type N "text" [--enter] [--append]')
        opts: dict[str, Any] = {"submit": "--enter" in flags}
        if "--append" in flags:
            opts["clear_strategy"] = "append"
        return await self._ref_act(pos[0], "fill", " ".join(pos[1:]), opts)

    async def _v_select(self, args: list[str]) -> str:
        if len(args) < 2:
            raise ValueError('usage: select N "option label"')
        return await self._ref_act(args[0], "select_option", " ".join(args[1:]))

    async def _v_check(self, args: list[str]) -> str:
        if not args:
            raise ValueError("usage: check N")
        return await self._ref_act(_target(args), "toggle")

    async def _v_hover(self, args: list[str]) -> str:
        if not args:
            raise ValueError("usage: hover N")
        return await self._ref_act(_target(args), "hover")

    async def _v_press(self, args: list[str]) -> str:
        if not args:
            raise ValueError("usage: press KEY [N]")
        if len(args) > 1:
            return await self._ref_act(args[1], "press", args[0])
        return self._text(await self.runtime.act(ActionRequest(op="press", value=args[0])))

    async def _v_scroll(self, args: list[str]) -> str:
        direction = args[0] if args else "down"
        count = 1
        if len(args) > 1:
            if not args[1].isdigit() or not 1 <= int(args[1]) <= 20:
                raise ValueError("usage: scroll [up|down|top|bottom] [COUNT 1-20]")
            count = int(args[1])
        res = await self.runtime.act(ActionRequest(op="scroll", value=direction))
        for _ in range(count - 1):  # each step is a screenful; only the last view is returned
            res = await self.runtime.act(ActionRequest(op="scroll", value=direction))
        return self._text(res)

    async def _v_do(self, args: list[str]) -> str:
        """`do "type 3 boots" "click 5" view` - several verbs in ONE call (one model turn instead of many).

        Steps run in order and stop at the first failure. Intermediate steps print a one-line outcome; the last step
        prints its full result/view so the agent sees where it ended up.
        """
        if not args:
            raise ValueError('usage: do "VERB ..." "VERB ..."   (each step is one quoted command; max 12)')
        if len(args) > 12:
            raise ValueError("do: at most 12 steps per call")
        trail: list[str] = []
        for i, step in enumerate(args, 1):
            first = _split(step)[:1]
            if first and first[0].lower() in {"do", "close"}:
                raise ValueError(f"do: step {i} ({first[0]}) is not allowed inside a sequence")
            out = await self.run(step)
            failed = out.lstrip().startswith(_FAIL)
            if i == len(args) or failed:
                head = "\n".join(trail)
                tail = f"{head}\n" if head else ""
                if failed:
                    return f"{tail}{i}. {step}\nstopped at step {i} of {len(args)}:\n{out}"
                return f"{tail}{i}. {step}\n\n{out}" if trail else out
            trail.append(f"{i}. {step} -> {(out.splitlines() or [''])[0][:160]}")
        return "\n".join(trail)

    async def _v_find(self, args: list[str]) -> str:
        if not args:
            raise ValueError("usage: find TEXT")
        needle = " ".join(args).lower()
        await self.runtime.observe(mode="delta", settle=False)  # always search the live page, never a stale snapshot
        # search the full-page rendering, not just the visible window
        full = self.runtime.rerender(mode="full")
        lines = full.all_lines
        idx = [i for i, ln in enumerate(lines) if needle in ln.lower()]
        self.runtime.rerender()  # restore the normal window for later `view --page`
        label = " ".join(args)
        if not idx:
            return f"no match for {label!r} on this page (try `scroll down` if it loads lazily)."
        shown: list[str] = []
        for i in idx[:15]:
            text = _snippet(lines[i], needle)
            cols = _column_header(lines, full.header_rows, i)
            if cols:
                text += f"\n    ↳ columns: {_snippet(cols, '', 160)}"
            shown.append(text)
        more = f"\n... {len(idx) - 15} more (be more specific: `find \"longer text\"`)" if len(idx) > 15 else ""
        return f"{len(idx)} line(s) match {label!r}:\n" + "\n".join(shown) + more

    async def _v_wait(self, args: list[str]) -> str:
        if args and args[0] == "text":
            if len(args) < 2:
                raise ValueError('usage: wait text "TEXT" [MS]')
            needle = args[1].lower()
            timeout = int(args[2]) if len(args) > 2 else 8000
            t0 = time.monotonic()
            while (time.monotonic() - t0) * 1000 < timeout:
                await self.runtime.observe(mode="delta", settle=False)
                view = self.runtime._view
                if view is not None and any(needle in ln.lower() for ln in view.all_lines):
                    return await self._fresh_view(f"found {args[1]!r} after {int((time.monotonic() - t0) * 1000)}ms")
                await self.runtime._page.wait_for_timeout(250)
            return await self._fresh_view(f"TIMEOUT: {args[1]!r} did not appear within {timeout}ms")
        ms = int(args[0]) if args else 500
        return self._text(await self.runtime.act(ActionRequest(op="wait", value=ms)))

    async def _v_back(self, args: list[str]) -> str:
        return self._text(await self.runtime.back())

    async def _v_forward(self, args: list[str]) -> str:
        return self._text(await self.runtime.forward())

    async def _v_reload(self, args: list[str]) -> str:
        return self._text(await self.runtime.reload())

    async def _v_tabs(self, args: list[str]) -> str:
        titles = await self.runtime.tab_titles()
        return "\n".join(titles) if titles else "1 tab"

    async def _v_tab(self, args: list[str]) -> str:
        if not args or not args[0].isdigit():
            raise ValueError("usage: tab N   (N from `tabs`, 1-based)")
        msg = await self.runtime.switch_tab(int(args[0]))
        return await self._fresh_view(msg)

    async def _v_shot(self, args: list[str]) -> str:
        pos, flags, _ = _flags(args, {"--marks", "--full"})
        page = self.runtime.page
        paths.private_dir(self._shots_dir)
        self._prune(self._shots_dir)
        self._shots += 1
        path = Path(pos[0]).expanduser() if pos else self._shots_dir / f"{self.name}-{int(time.time())}-{self._shots}.png"
        marked = 0
        if "--marks" in flags:
            await self.runtime.observe(mode="delta", settle=False)
            snap = self.runtime._snapshot
            items = [[n["local_ref"], n["ref"]] for n in (snap.nodes if snap else []) if n.get("ref") is not None and n.get("frame_id", "main") == "main"]
            marked = await page.main_frame.evaluate(_MARKS_JS, items)
        try:
            await page.screenshot(path=str(path), full_page="--full" in flags)
        finally:
            if "--marks" in flags:
                try:
                    await page.main_frame.evaluate("() => { const m = document.getElementById('__sb_marks'); if (m) m.remove(); }")
                except Exception:
                    pass
        extra = f" with {marked} [n] boxes (elements inside iframes are not boxed)" if "--marks" in flags else ""
        return f"screenshot: {path}{extra}"

    @staticmethod
    def _prune(directory: Path) -> None:
        try:
            files = sorted(directory.glob("*.png"), key=lambda p: p.stat().st_mtime)
            for old in files[:-_KEEP_SHOTS]:
                old.unlink(missing_ok=True)
        except OSError:
            pass

    # ------------------------------------------------------------------ captcha
    async def _v_captcha(self, args: list[str]) -> str:
        page = self.runtime.page
        sub = args[0].lower() if args and not args[0].startswith("--") else "show"
        rest = args[1:] if sub != "show" else args
        # captcha pages often block images in lite mode: make sure nothing of ours stands in the way
        await self.runtime.allow_all_resources()
        if sub == "show":
            _, flags, _ = _flags(rest, {"--pdf"})
            challenges = await cap.detect(page)
            if not challenges:
                self._challenge = None
                return "No CAPTCHA detected on this page.\n\n" + self._current_view()
            first = challenges[0]
            await cap.annotate(page, first, pdf="--pdf" in flags)
            self._challenge = first
            extra = ""
            if len(challenges) > 1:
                extra = "\n(also present: " + ", ".join(f"{c.provider}/{c.kind}" for c in challenges[1:]) + ")"
            return first.describe() + extra
        current: cap.Challenge | None = self._challenge
        if current is None or sub == "open":
            challenges = await cap.detect(page)
            current = challenges[0] if challenges else None
            if sub == "open" and challenges:
                current = next((c for c in challenges if c.kind == "checkbox"), current)
            self._challenge = current
        if current is None:
            return "No CAPTCHA detected on this page."
        ch: cap.Challenge = current
        if sub == "open":
            msg = await cap.open_checkbox(page, ch)
            await self._settle_challenge(900)
            return await self._after_captcha(msg, ch)
        if sub == "select":
            nums = [int(x) for x in rest if x.strip(",").isdigit() or x.strip(",").lstrip("-").isdigit()] or [
                int(x) for chunk in rest for x in chunk.replace(",", " ").split() if x.isdigit()
            ]
            if not nums:
                raise ValueError("usage: captcha select 1 5 9")
            msg = await cap.select_tiles(ch, nums)
            return msg + "\nNext: `captcha submit` (or `captcha select ...` again to fix the selection; clicking a selected tile unselects it)."
        if sub == "text":
            if not rest:
                raise ValueError("usage: captcha text ANSWER")
            msg = await cap.type_text(page, ch, " ".join(rest))
            return msg + "\nNext: `captcha submit`."
        if sub == "submit":
            msg = await cap.submit(page, ch)
            await self._settle_challenge(1600)  # dynamic grids swap the picked tiles for new images ~1-2s after Verify
            return await self._after_captcha(msg, ch)
        if sub == "refresh":
            msg = await cap.refresh(ch)
            await self._settle_challenge(900)
            return await self._after_captcha(msg, ch)
        raise ValueError("usage: captcha [--pdf] | open | select N.. | text ANSWER | submit | refresh")

    async def _settle_challenge(self, min_ms: int, max_ms: int = 6000, still_frames: int = 3) -> None:
        """Wait at least `min_ms`, then until the viewport has been identical for `still_frames` consecutive frames.

        The picture we hand to the model must be the one a human would see, not a half-faded transition: dynamic
        grids fetch replacement images ~1-2s after Verify and then fade them in, so one identical pair is not enough.
        """
        page = self.runtime._page
        await page.wait_for_timeout(min_ms)
        waited, prev, same = min_ms, None, 0
        while waited < max_ms:
            try:
                frame = await page.screenshot(type="jpeg", quality=40)
            except Exception:
                return
            same = same + 1 if frame == prev else 0
            if same >= still_frames - 1:
                return
            prev = frame
            await page.wait_for_timeout(300)
            waited += 300

    async def _after_captcha(self, did: str, before: cap.Challenge | None = None) -> str:
        page = self.runtime.page
        challenges = await cap.detect(page)
        grid = next((c for c in challenges if c.kind in {"grid", "text"}), None)
        if grid is not None:
            await cap.annotate(page, grid)
            self._challenge = grid
            if before is None or before.kind in {"checkbox", "interstitial"}:
                verdict = "A challenge appeared:"
            elif (before.prompt, before.kind) != (grid.prompt, grid.kind):
                verdict = "The provider accepted that step and served a NEW challenge (another round). Solve this one:"
            else:
                verdict = (
                    "The same challenge is still showing. Either the answer was wrong/incomplete, or this is a dynamic grid "
                    "(\"click verify once there are none left\") that replaced the tiles you picked with new images: look at "
                    "the NEW image, select any tiles that still match, then submit again. `captcha refresh` gives a different "
                    "challenge. The page (error text, if any) is below."
                )
                return f"{did}.\n{verdict}\n" + grid.describe() + "\n\n--- page now ---\n" + await self._fresh_view()
            return f"{did}.\n{verdict}\n" + grid.describe()
        self._challenge = None
        await cap.clear_marks(page)
        remaining = [c for c in challenges if c.kind == "checkbox"]
        tail = "a checkbox widget is still present (it may now be ticked); run `view` to continue." if remaining else "no challenge is showing any more — likely solved."
        return f"{did}. {tail}\n\n" + await self._fresh_view()
