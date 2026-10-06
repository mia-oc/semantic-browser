#!/usr/bin/env python3
"""Navigation-only benchmark: how long until an agent has something *usable* from a URL?

  httpx     plain GET (no JS, no render)                       -> the 'as fast as curl' reference
  pw-load   Playwright goto(load) + aria snapshot              -> what a classic agent pays before it can think
  pw-dcl    Playwright goto(domcontentloaded) + aria snapshot
  sb[...]   AgentSession.goto (settle + snapshot + view)       -> options: --lite off|media|max, --budget N

Read-only. Prints a table and appends JSON lines when --out is given.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

URLS = [
    "https://example.com/",
    "https://en.wikipedia.org/wiki/Alan_Turing",
    "https://news.ycombinator.com/",
    "https://www.bbc.co.uk/news",
    "https://github.com/microsoft/playwright",
    "https://www.gov.uk/",
    "https://www.nhs.uk/",
    "https://duckduckgo.com/",
]


async def bench_httpx(reps: int) -> list[dict]:
    import httpx

    out = []
    async with httpx.AsyncClient(follow_redirects=True, timeout=20, headers={"User-Agent": "Mozilla/5.0"}) as c:
        for url in URLS:
            for _ in range(reps):
                t = time.perf_counter()
                try:
                    r = await c.get(url)
                    out.append({"impl": "httpx", "url": url, "ms": (time.perf_counter() - t) * 1000, "chars": len(r.text), "ok": r.status_code < 400})
                except Exception as exc:
                    out.append({"impl": "httpx", "url": url, "ms": (time.perf_counter() - t) * 1000, "chars": 0, "ok": False, "err": str(exc)[:60]})
    return out


COLD = False


async def _clear_cache(page) -> None:
    if COLD:
        try:
            cdp = await page.context.new_cdp_session(page)
            await cdp.send("Network.clearBrowserCache")
            await cdp.detach()
        except Exception:
            pass


async def bench_pw(reps: int, wait_until: str, headful: bool) -> list[dict]:
    from playwright.async_api import async_playwright

    out = []
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=not headful)
    page = await (await browser.new_context()).new_page()
    try:
        for url in URLS:
            for _ in range(reps):
                await page.goto("about:blank")
                await _clear_cache(page)
                t = time.perf_counter()
                try:
                    await page.goto(url, wait_until=wait_until, timeout=30000)
                    snap = await page.locator("body").aria_snapshot()
                    out.append({"impl": f"pw-{wait_until[:4]}", "url": url, "ms": (time.perf_counter() - t) * 1000, "chars": len(snap), "ok": True})
                except Exception as exc:
                    out.append({"impl": f"pw-{wait_until[:4]}", "url": url, "ms": (time.perf_counter() - t) * 1000, "chars": 0, "ok": False, "err": str(exc)[:60]})
    finally:
        await browser.close()
        await pw.stop()
    return out


async def bench_sb(reps: int, lite: str, budget: int | None, headful: bool) -> list[dict]:
    from semantic_browser.agent import AgentSession

    label = "sb" + (f"-lite-{lite}" if lite != "off" else "") + (f"-b{budget}" if budget else "")
    out = []
    s = await AgentSession.launch(headful=headful, lite=lite, budget=budget)
    try:
        for url in URLS:
            for _ in range(reps):
                await s.runtime.page.goto("about:blank")
                await _clear_cache(s.runtime.page)
                t = time.perf_counter()
                try:
                    view = await s.run(f"goto {url}")
                    out.append({"impl": label, "url": url, "ms": (time.perf_counter() - t) * 1000, "chars": len(view), "ok": not view.startswith("ERROR")})
                except Exception as exc:
                    out.append({"impl": label, "url": url, "ms": (time.perf_counter() - t) * 1000, "chars": 0, "ok": False, "err": str(exc)[:60]})
    finally:
        await s.close()
    return out


def table(rows: list[dict]) -> str:
    impls = sorted({r["impl"] for r in rows})
    lines = [f"{'url':44}" + "".join(f"{i:>16}" for i in impls)]
    for url in URLS:
        cells = []
        for i in impls:
            rs = [r for r in rows if r["impl"] == i and r["url"] == url]
            ok = [r for r in rs if r["ok"]]
            if not rs:
                cells.append(f"{'-':>16}")
            elif not ok:
                cells.append(f"{'FAIL':>16}")
            else:
                cells.append(f"{statistics.median(r['ms'] for r in ok):6.0f}ms {statistics.median(r['chars'] for r in ok) / 4:6.0f}t")
        lines.append(f"{url[8:52]:44}" + "".join(c.rjust(16) for c in cells))
    lines.append("-" * (44 + 16 * len(impls)))
    tot = []
    for i in impls:
        ok = [r for r in rows if r["impl"] == i and r["ok"]]
        tot.append(f"{statistics.median(r['ms'] for r in ok):6.0f}ms {statistics.median(r['chars'] for r in ok) / 4:6.0f}t" if ok else "FAIL")
    lines.append(f"{'MEDIAN (all urls)':44}" + "".join(t.rjust(16) for t in tot))
    return "\n".join(lines) + "\n(ms = wall time to a usable result; t = tokens (chars/4) the agent must read)"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--headful", action="store_true")
    ap.add_argument("--impls", nargs="+", default=["httpx", "pw-load", "pw-dcl", "sb", "sb-lite-media", "sb-lite-max"])
    ap.add_argument("--out", default=None)
    ap.add_argument("--cold", action="store_true", help="clear the HTTP cache before every load")
    a = ap.parse_args()
    global COLD
    COLD = a.cold
    rows: list[dict] = []
    for impl in a.impls:
        print(f"... {impl}", flush=True)
        if impl == "httpx":
            rows += await bench_httpx(a.reps)
        elif impl == "pw-load":
            rows += await bench_pw(a.reps, "load", a.headful)
        elif impl == "pw-dcl":
            rows += await bench_pw(a.reps, "domcontentloaded", a.headful)
        elif impl == "sb":
            rows += await bench_sb(a.reps, "off", None, a.headful)
        elif impl == "sb-lite-media":
            rows += await bench_sb(a.reps, "media", None, a.headful)
        elif impl == "sb-lite-max":
            rows += await bench_sb(a.reps, "max", None, a.headful)
        elif impl.startswith("sb-b"):
            rows += await bench_sb(a.reps, "off", int(impl[4:]), a.headful)
    print()
    print(table(rows))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        with open(a.out, "a") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
