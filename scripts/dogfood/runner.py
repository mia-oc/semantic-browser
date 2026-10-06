#!/usr/bin/env python3
"""Dogfood runner: time an oracle "model" through scenarios using a given browser layer.

Methods (--impl):
  sb   semantic_browser from whatever is on PYTHONPATH (use a v1.3.2 worktree for the baseline)
  pw   raw Playwright with a full aria snapshot per step (what a classic agent pays), oracle-chosen locators

The oracle can only act on things the model was *shown* (room text), and pays a step for `more`/scroll.
Output: JSON lines (one per run) so reports can aggregate across impls/options.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fixtures import FixtureServer  # noqa: E402
from scenarios import Scenario, Step, by_name  # noqa: E402

FAMILY = {
    "fill": {"fill"},
    "click": {"click", "open", "toggle", "select_option", "submit"},
    "open": {"open", "click"},
    "select": {"select_option", "click"},
    None: {"click", "open", "toggle", "fill", "select_option", "submit", "hover", "scroll"},
}


def _shown(a, text: str) -> bool:
    ref = getattr(a, "ref", None)
    if ref is not None and re.search(rf"(?<![\w.]){re.escape(str(ref))}(?![\w])", text):
        # new-style numbered refs: appear as "[7]" or "7 " at line start
        if re.search(rf"\[{re.escape(str(ref))}\b|^\s*{re.escape(str(ref))}[ .:\]]", text, re.M):
            return True
    return a.id in text


def choose(obs, step: Step):
    text = (obs.planner.room_text if obs.planner else "") or ""
    fam = FAMILY.get(step.op, FAMILY[None])
    shown = [a for a in obs.available_actions if a.enabled and a.op in fam and _shown(a, text)]
    if step.hover:
        for rx in step.match:
            for a in obs.available_actions:
                if a.op == "hover" and re.search(rx, a.label, re.I) and _shown(a, text):
                    return a
    for rx in step.match:
        for a in shown:
            if re.search(rx, a.label, re.I):
                return a
    if step.nth is not None and len(shown) > step.nth:
        return shown[step.nth]
    return None


async def _page_state(page) -> dict:
    try:
        title = await page.title()
    except Exception:
        title = ""
    try:
        text = await page.evaluate("document.body ? document.body.innerText : ''")
    except Exception:
        text = ""
    return {"title": title, "url": page.url, "text": text}


def _success(sc: Scenario, st: dict) -> bool:
    if sc.ok_title and re.search(sc.ok_title, st["title"] or ""):
        return True
    if sc.ok_url and re.search(sc.ok_url, st["url"] or ""):
        return True
    return bool(sc.ok_text and re.search(sc.ok_text, st["text"] or ""))


async def run_sb(sc: Scenario, base: str, args) -> dict:
    import semantic_browser
    from semantic_browser import ManagedSession
    from semantic_browser.models import ActionRequest

    rec: dict = {"impl": args.label or f"sb-{semantic_browser.__version__}", "scenario": sc.name, "steps": [],
                 "model_chars": 0, "success": False, "fail": None, "saw": sc.must_see is None}
    kwargs: dict = {"headful": args.headful}
    if args.lite != "off" or args.budget:
        from semantic_browser.config import RuntimeConfig

        cfg = RuntimeConfig()
        if args.lite != "off":
            cfg.lite = args.lite
        if args.budget:
            cfg.extraction.view_budget = args.budget
        kwargs["config"] = cfg
    t = time.perf_counter()
    session = await ManagedSession.launch(**kwargs)
    rec["launch_ms"] = int((time.perf_counter() - t) * 1000)
    rt = session.runtime
    page = rt._page

    def note(kind: str, ms: float, obs, extra: str = "", status: str = ""):
        text = (obs.planner.room_text if obs and obs.planner else "") or ""
        rec["model_chars"] += len(text)
        if sc.must_see and re.search(sc.must_see, text):
            rec["saw"] = True
        rec["steps"].append({"kind": kind, "ms": int(ms), "chars": len(text), "label": extra, "status": status})

    t_all = time.perf_counter()
    try:
        url = sc.url if sc.url.startswith("http") else base + sc.url
        t = time.perf_counter()
        res = await rt.navigate(url)
        note("navigate", (time.perf_counter() - t) * 1000, res.observation, url, res.status)
        obs = res.observation
        for step in sc.steps:
            a = choose(obs, step)
            tries = 0
            while a is None and not step.optional and tries < 3:
                tries += 1
                more = next((x for x in obs.available_actions if x.id == "more"), None)
                scroll = next((x for x in obs.available_actions if x.op == "scroll" or re.search(r"scroll", x.label, re.I)), None)
                helper = more if (more and tries == 1 and "[more]" in (obs.planner.room_text or "")) else scroll
                if helper is None:
                    break
                t = time.perf_counter()
                r = await rt.act(ActionRequest(action_id=helper.id, value="down" if helper.requires_value else None))
                note("helper:" + helper.id, (time.perf_counter() - t) * 1000, r.observation, helper.label, r.status)
                obs = r.observation
                a = choose(obs, step)
            if a is None and step.optional:
                continue
            if a is None:
                rec["fail"] = f"no_match:{step.match[0]}"
                break
            opts = {"submit": True} if step.op == "fill" and step.value and "search" in step.match[0].lower() else {}
            t = time.perf_counter()
            r = await rt.act(ActionRequest(action_id=a.id, value=step.value, options=opts))
            note(a.op, (time.perf_counter() - t) * 1000, r.observation, a.label[:40], r.status)
            obs = r.observation
            if r.status in {"failed", "invalid", "stale"}:
                rec["fail"] = f"act_{r.status}:{(r.message or '')[:80]}"
                # one retry after fresh observe, as a model would
                obs = await rt.observe(mode="summary")
                a2 = choose(obs, step)
                if a2 is None:
                    break
                r = await rt.act(ActionRequest(action_id=a2.id, value=step.value, options=opts))
                note(a2.op + ":retry", 0, r.observation, a2.label[:40], r.status)
                obs = r.observation
                if r.status in {"failed", "invalid", "stale"}:
                    break
                rec["fail"] = None
        rec["total_ms"] = int((time.perf_counter() - t_all) * 1000)
        st = await _page_state(page)
        rec["success"] = _success(sc, st) and rec["fail"] is None
        if not rec["success"] and rec["fail"] is None:
            rec["fail"] = f"wrong_outcome:title={st['title'][:40]!r}"
    except Exception as exc:
        rec["fail"] = f"exception:{type(exc).__name__}:{str(exc)[:100]}"
        rec["total_ms"] = int((time.perf_counter() - t_all) * 1000)
    finally:
        try:
            await session.close()
        except Exception:
            pass
    return rec


async def _pw_try_step(page, step: Step) -> bool:
    for frame in page.frames:
        for rx in step.match:
            pat = re.compile(rx, re.I)
            if step.op == "fill":
                cands = [frame.get_by_label(pat), frame.get_by_placeholder(pat), frame.get_by_role("textbox", name=pat)]
            else:
                cands = [frame.get_by_role("button", name=pat), frame.get_by_role("link", name=pat),
                         frame.get_by_role("combobox", name=pat), frame.get_by_role("option", name=pat),
                         frame.get_by_text(pat)]
            for loc in cands:
                try:
                    if await loc.count() == 0:
                        continue
                    tgt = loc.first
                    if step.op == "fill":
                        await tgt.fill(step.value or "", timeout=3000)
                        if "search" in step.match[0].lower():
                            await tgt.press("Enter")
                    else:
                        await tgt.click(timeout=3000)
                    return True
                except Exception:
                    continue
    return False


async def run_pw(sc: Scenario, base: str, args) -> dict:
    """Idealised classic agent: full aria snapshot per step, oracle picks locators perfectly."""
    from playwright.async_api import async_playwright

    rec = {"impl": "pw-aria", "scenario": sc.name, "steps": [], "model_chars": 0, "success": False, "fail": None,
           "saw": sc.must_see is None}
    pw = await async_playwright().start()
    t = time.perf_counter()
    browser = await pw.chromium.launch(headless=not args.headful)
    page = await (await browser.new_context()).new_page()
    rec["launch_ms"] = int((time.perf_counter() - t) * 1000)

    async def snap(kind, ms, label=""):
        try:
            s = await page.locator("body").aria_snapshot()
        except Exception:
            s = ""
        if sc.must_see and re.search(sc.must_see, s):
            rec["saw"] = True
        rec["model_chars"] += len(s)
        rec["steps"].append({"kind": kind, "ms": int(ms), "chars": len(s), "label": label, "status": "ok"})

    t_all = time.perf_counter()
    try:
        url = sc.url if sc.url.startswith("http") else base + sc.url
        t = time.perf_counter()
        await page.goto(url, wait_until="load", timeout=30000)
        await snap("navigate", (time.perf_counter() - t) * 1000, url)
        for step in sc.steps:
            t = time.perf_counter()
            done = False
            deadline = time.monotonic() + 2.5  # a competent agent retries while the page renders
            while not done and time.monotonic() < deadline:
                done = await _pw_try_step(page, step)
                if not done:
                    await asyncio.sleep(0.1)
            if not done and step.optional:
                continue
            if not done:
                rec["fail"] = f"no_match:{step.match[0]}"
                break
            await page.wait_for_timeout(150)
            await snap(step.op or "act", (time.perf_counter() - t) * 1000, step.match[0][:40])
        rec["total_ms"] = int((time.perf_counter() - t_all) * 1000)
        st = await _page_state(page)
        rec["success"] = _success(sc, st) and rec["fail"] is None
        if not rec["success"] and rec["fail"] is None:
            rec["fail"] = f"wrong_outcome:title={st['title'][:40]!r}"
    except Exception as exc:
        rec["fail"] = f"exception:{type(exc).__name__}:{str(exc)[:100]}"
        rec["total_ms"] = int((time.perf_counter() - t_all) * 1000)
    finally:
        await browser.close()
        await pw.stop()
    return rec


def summarise(recs: list[dict]) -> str:
    lines = [f"{'scenario':26} {'impl':16} {'ok':>5} {'ms(med)':>8} {'steps':>5} {'tok(med)':>8} {'saw':>4}  fail"]
    keys = sorted({(r["scenario"], r["impl"]) for r in recs})
    for sc, impl in keys:
        rs = [r for r in recs if r["scenario"] == sc and r["impl"] == impl]
        ok = sum(1 for r in rs if r["success"])
        ms = statistics.median([r.get("total_ms", 0) for r in rs])
        st = statistics.median([len(r["steps"]) for r in rs])
        tok = statistics.median([r["model_chars"] / 4 for r in rs])
        saw = sum(1 for r in rs if r["saw"])
        fail = next((r["fail"] for r in rs if r["fail"]), "")
        lines.append(f"{sc:26} {impl:16} {ok}/{len(rs):<3} {ms:8.0f} {st:5.0f} {tok:8.0f} {saw}/{len(rs)}  {fail or ''}")
    for impl in sorted({r["impl"] for r in recs}):
        rs = [r for r in recs if r["impl"] == impl]
        ok = sum(1 for r in rs if r["success"])
        lines.append(f"TOTAL {impl}: success {ok}/{len(rs)}  median_ms={statistics.median([r.get('total_ms', 0) for r in rs]):.0f}"
                     f"  median_tokens={statistics.median([r['model_chars'] / 4 for r in rs]):.0f}")
    return "\n".join(lines)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", choices=["sb", "pw"], default="sb")
    ap.add_argument("--label", default=None, help="label for this impl/option set in reports")
    ap.add_argument("--scenarios", nargs="*", default=None)
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--headful", action="store_true")
    ap.add_argument("--set", dest="which", choices=["local", "real", "all"], default="local")
    ap.add_argument("--budget", type=int, default=None, help="view budget in chars")
    ap.add_argument("--lite", choices=["off", "media", "max"], default="off")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    server = FixtureServer().start()
    recs: list[dict] = []
    try:
        for sc in by_name(args.scenarios, args.which):
            for _ in range(args.reps):
                r = await (run_sb if args.impl == "sb" else run_pw)(sc, server.base, args)
                recs.append(r)
                print(f"  {sc.name:26} {r['impl']:16} {'OK ' if r['success'] else 'FAIL'} {r.get('total_ms', 0):6}ms {r.get('fail') or ''}", flush=True)
    finally:
        server.stop()
    print()
    print(summarise(recs))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "a") as fh:
            for r in recs:
                fh.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
