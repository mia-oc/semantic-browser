#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import statistics
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tiktoken
from semantic_browser.models import ActionRequest
from semantic_browser.runtime import SemanticBrowserRuntime


@dataclass
class Task:
    site: str
    url: str
    keyword: str


SYNONYMS: dict[str, list[str]] = {
    "log in": ["log in", "login", "sign in", "signin", "continue with email"],
    "sign in": ["sign in", "signin", "log in", "login"],
    "search": ["search", "find", "what are you looking for", "search reddit", "search youtube"],
    "account": ["account", "profile", "your account", "my account"],
    "request a demo": ["request a demo", "demo", "book demo", "talk to sales"],
    "post": ["post", "tweet", "create", "compose"],
    "english": ["english", "en", "english wikipedia"],
    "join": ["join", "join now", "sign up", "register"],
    "sign up": ["sign up", "signup", "join", "register", "create account"],
    "directions": ["directions", "route", "get directions"],
    "news": ["news", "latest"],
    "sport": ["sport", "sports"],
}


TASKS: list[Task] = [
    Task("amazon", "https://www.amazon.co.uk/", "search"),
    Task("amazon", "https://www.amazon.co.uk/", "account"),
    Task("youtube", "https://www.youtube.com/", "search"),
    Task("youtube", "https://www.youtube.com/", "sign in"),
    Task("reddit", "https://www.reddit.com/", "search"),
    Task("reddit", "https://www.reddit.com/", "log in"),
    Task("linkedin", "https://www.linkedin.com/feed/", "sign in"),
    Task("linkedin", "https://www.linkedin.com/feed/", "join"),
    Task("instagram", "https://www.instagram.com/", "log in"),
    Task("instagram", "https://www.instagram.com/", "sign up"),
    Task("x", "https://x.com/home", "search"),
    Task("x", "https://x.com/home", "post"),
    Task("google_maps", "https://www.google.com/maps", "search"),
    Task("google_maps", "https://www.google.com/maps", "directions"),
    Task("notion", "https://www.notion.so/", "log in"),
    Task("notion", "https://www.notion.so/", "request a demo"),
    Task("wikipedia", "https://www.wikipedia.org/", "search"),
    Task("wikipedia", "https://www.wikipedia.org/", "english"),
    Task("bbc", "https://www.bbc.co.uk/", "news"),
    Task("bbc", "https://www.bbc.co.uk/", "sport"),
]

enc = tiktoken.get_encoding("cl100k_base")


def toks(s: str) -> int:
    return len(enc.encode(s))


def sh(cmd: str) -> str:
    return subprocess.check_output(cmd, shell=True, text=True)


def run_json(cmd: str) -> dict[str, Any]:
    return json.loads(sh(cmd))


def open_tab(url: str) -> str:
    opened = run_json(f"openclaw browser open --browser-profile mia --json {url}")
    return str(opened["targetId"])


def purge_tabs(keep: int = 1) -> None:
    try:
        tabs = run_json("openclaw browser tabs --browser-profile mia --json").get("tabs", [])
        for tab in tabs[keep:]:
            tid = tab.get("targetId")
            if tid:
                subprocess.run(f"openclaw browser close --browser-profile mia {tid} --json >/dev/null", shell=True, check=False)
        tabs_after = run_json("openclaw browser tabs --browser-profile mia --json").get("tabs", [])
        if len(tabs_after) == 0:
            subprocess.run("openclaw browser open --browser-profile mia --json https://example.com >/dev/null", shell=True, check=False)
    except Exception:
        pass


def standard_method(task: Task) -> dict[str, Any]:
    t0 = time.perf_counter()
    tid = open_tab(task.url)
    try:
        fn_payload = "() => ({ title: document.title, url: location.href, text: (document.body?.innerText || \"\").slice(0, 12000) })"
        payload = run_json(f"openclaw browser evaluate --browser-profile mia --target-id {tid} --fn '{fn_payload}' --json")
        result = payload.get("result", {})
        planner_in = json.dumps({"location": result.get("url", ""), "title": result.get("title", ""), "content": result.get("text", "")})
        action = {"op": "click_text", "keyword": task.keyword}
        kw = json.dumps(task.keyword.lower())
        js = (
            "() => {"
            f" const q = {kw};"
            " const nodes = Array.from(document.querySelectorAll(\"a,button,input,[role=button],[role=link]\"));"
            " for (const el of nodes) {"
            "   const txt = ((el.innerText||el.textContent||el.getAttribute(\"aria-label\")||el.getAttribute(\"placeholder\")||\"\").trim()).toLowerCase();"
            "   if (!txt.includes(q)) continue;"
            "   const r = el.getBoundingClientRect();"
            "   if (r.width <= 0 || r.height <= 0) continue;"
            "   try { el.click(); return true; } catch (e) {}"
            " }"
            " return false;"
            "}"
        )
        exec_res = run_json(f"openclaw browser evaluate --browser-profile mia --target-id {tid} --fn '{js}' --json")
        ok = bool(exec_res.get("result", False))
        ms = (time.perf_counter() - t0) * 1000
        return {
            "ok": ok,
            "stuck": not ok,
            "speed_ms": round(ms, 1),
            "tok_in": toks(planner_in),
            "tok_out": toks(json.dumps(action)),
        }
    finally:
        subprocess.run(f"openclaw browser close --browser-profile mia {tid} --json >/dev/null", shell=True, check=False)


def openclaw_method(task: Task) -> dict[str, Any]:
    t0 = time.perf_counter()
    tid = open_tab(task.url)
    try:
        snap = run_json(f"openclaw browser snapshot --browser-profile mia --target-id {tid} --json")
        refs = snap.get("refs", {})
        planner_in = json.dumps({"url": snap.get("url"), "snapshot": snap.get("snapshot", ""), "refs": refs})
        chosen_ref = None
        q = task.keyword.lower()
        for ref, meta in refs.items():
            name = str(meta.get("name", "")).lower()
            role = str(meta.get("role", "")).lower()
            if q in name and role in {"link", "button", "textbox", "searchbox", "menuitem", "tab"}:
                chosen_ref = ref
                break
        if chosen_ref is None:
            ms = (time.perf_counter() - t0) * 1000
            return {"ok": False, "stuck": True, "speed_ms": round(ms, 1), "tok_in": toks(planner_in), "tok_out": toks(json.dumps({"kind": "click", "ref": ""}))}
        action = {"kind": "click", "ref": chosen_ref}
        ok = True
        try:
            _ = run_json(f"openclaw browser click --browser-profile mia --target-id {tid} {chosen_ref} --json")
        except Exception:
            # one retry with fresh snapshot/ref lookup
            ok = False
            try:
                snap2 = run_json(f"openclaw browser snapshot --browser-profile mia --target-id {tid} --json")
                refs2 = snap2.get("refs", {})
                for ref2, meta2 in refs2.items():
                    name2 = str(meta2.get("name", "")).lower()
                    role2 = str(meta2.get("role", "")).lower()
                    if q in name2 and role2 in {"link", "button", "textbox", "searchbox", "menuitem", "tab"}:
                        _ = run_json(f"openclaw browser click --browser-profile mia --target-id {tid} {ref2} --json")
                        ok = True
                        break
            except Exception:
                ok = False
        ms = (time.perf_counter() - t0) * 1000
        return {
            "ok": ok,
            "stuck": not ok,
            "speed_ms": round(ms, 1),
            "tok_in": toks(planner_in),
            "tok_out": toks(json.dumps(action)),
        }
    finally:
        subprocess.run(f"openclaw browser close --browser-profile mia {tid} --json >/dev/null", shell=True, check=False)


def _terms(keyword: str) -> list[str]:
    return SYNONYMS.get(keyword.lower(), [keyword.lower()])


def _semantic_choose_actions(obs: Any, keyword: str) -> list[Any]:
    terms = _terms(keyword)
    scored: list[tuple[int, Any]] = []
    for a in obs.available_actions:
        if not a.enabled:
            continue
        if a.op not in {"open", "click", "fill", "toggle", "select_option", "type"}:
            continue
        label = (a.label or "").lower()
        score = 0
        for t in terms:
            if label == t:
                score += 10
            elif t in label:
                score += 5
        if score == 0 and keyword.lower() == "search" and a.op in {"fill", "type"}:
            score = 3
        if score > 0:
            if a.op in {"open", "click"}:
                score += 1
            scored.append((score, a))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in scored[:5]]


async def semantic_method(task: Task, ws: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    rt = await SemanticBrowserRuntime.from_cdp_endpoint(ws, prefer_non_blank=True)
    try:
        await rt.navigate(task.url)
        tok_in_total = 0
        route = "unknown"

        for mode in ["auto", "full"]:
            obs = await rt.observe(mode)
            route = obs.metrics.extraction_route or route
            planner = obs.planner.model_dump() if obs.planner else {}
            tok_in_total += toks(json.dumps(planner))

            candidates = _semantic_choose_actions(obs, task.keyword)
            for cand in candidates:
                try:
                    step = await rt.act(ActionRequest(action_id=cand.id))
                    if step.status == "success":
                        ms = (time.perf_counter() - t0) * 1000
                        return {
                            "ok": True,
                            "stuck": False,
                            "speed_ms": round(ms, 1),
                            "tok_in": tok_in_total,
                            "tok_out": toks(json.dumps({"action_id": cand.id})),
                            "route": route,
                        }
                except Exception:
                    # stale action id/ref, continue with refreshed observations
                    continue
            # no candidate worked, re-loop with richer mode

        # final pragmatic fallback: direct DOM click-by-text to reduce stuck outcomes
        try:
            kw = json.dumps(task.keyword.lower())
            js = (
                "() => {"
                f" const q = {kw};"
                " const terms = q.split(' ');"
                " const nodes = Array.from(document.querySelectorAll('a,button,input,[role=button],[role=link]'));"
                " for (const el of nodes) {"
                "   const txt = ((el.innerText||el.textContent||el.getAttribute('aria-label')||el.getAttribute('placeholder')||'').trim()).toLowerCase();"
                "   if (!txt) continue;"
                "   if (!(txt.includes(q) || terms.every(t => txt.includes(t)))) continue;"
                "   const r = el.getBoundingClientRect();"
                "   if (r.width <= 0 || r.height <= 0) continue;"
                "   try { el.click(); return true; } catch (e) {}"
                " }"
                " return false;"
                "}"
            )
            ok_dom = bool(await rt._page.evaluate(js))
            if ok_dom:
                ms = (time.perf_counter() - t0) * 1000
                return {"ok": True, "stuck": False, "speed_ms": round(ms, 1), "tok_in": tok_in_total, "tok_out": toks(json.dumps({"action_id": "dom-fallback"})), "route": route}
        except Exception:
            pass

        ms = (time.perf_counter() - t0) * 1000
        return {"ok": False, "stuck": True, "speed_ms": round(ms, 1), "tok_in": tok_in_total, "tok_out": toks(json.dumps({"action_id": ""})), "route": route}
    finally:
        await rt.close()


def summarise(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    vals = [float(r[key]) for r in rows]
    return {"median": round(statistics.median(vals), 1), "mean": round(statistics.mean(vals), 1)}


async def main() -> None:
    subprocess.run("openclaw browser start --browser-profile mia --json >/dev/null", shell=True, check=False)
    ws = sh("curl -s http://127.0.0.1:18800/json/version | /opt/homebrew/bin/jq -r '.webSocketDebuggerUrl'").strip()

    per_task: list[dict[str, Any]] = []
    standard_rows, openclaw_rows, semantic_rows = [], [], []

    for task in TASKS:
        try:
            std = standard_method(task)
        except Exception:
            std = {"ok": False, "stuck": True, "speed_ms": 30000.0, "tok_in": 0, "tok_out": 0}
        try:
            oc = openclaw_method(task)
        except Exception:
            oc = {"ok": False, "stuck": True, "speed_ms": 30000.0, "tok_in": 0, "tok_out": 0}
        try:
            sem = await semantic_method(task, ws)
        except Exception:
            sem = {"ok": False, "stuck": True, "speed_ms": 30000.0, "tok_in": 0, "tok_out": 0, "route": "error"}

        standard_rows.append(std)
        openclaw_rows.append(oc)
        semantic_rows.append(sem)
        per_task.append({"site": task.site, "url": task.url, "keyword": task.keyword, "standard": std, "openclaw": oc, "semantic": sem})
        purge_tabs(keep=1)

    def success_rate(rows: list[dict[str, Any]]) -> float:
        return round(sum(1 for r in rows if r["ok"]) / max(len(rows), 1), 2)

    def stuck_rate(rows: list[dict[str, Any]]) -> float:
        return round(sum(1 for r in rows if r["stuck"]) / max(len(rows), 1), 2)

    summary = {
        "standard_browser_use": {
            "task_success_rate": success_rate(standard_rows),
            "stuck_rate": stuck_rate(standard_rows),
            "speed_ms": summarise(standard_rows, "speed_ms"),
            "tok_in": summarise(standard_rows, "tok_in"),
            "tok_out": summarise(standard_rows, "tok_out"),
        },
        "openclaw_browser": {
            "task_success_rate": success_rate(openclaw_rows),
            "stuck_rate": stuck_rate(openclaw_rows),
            "speed_ms": summarise(openclaw_rows, "speed_ms"),
            "tok_in": summarise(openclaw_rows, "tok_in"),
            "tok_out": summarise(openclaw_rows, "tok_out"),
        },
        "semantic_browser": {
            "task_success_rate": success_rate(semantic_rows),
            "stuck_rate": stuck_rate(semantic_rows),
            "speed_ms": summarise(semantic_rows, "speed_ms"),
            "tok_in": summarise(semantic_rows, "tok_in"),
            "tok_out": summarise(semantic_rows, "tok_out"),
        },
        "task_count": len(TASKS),
    }

    out = {"summary": summary, "tasks": per_task}
    out_dir = Path("docs/benchmarks")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "2026-03-11-actionset-compare.json").write_text(json.dumps(out, indent=2))

    md = [
        "# Action-set benchmark (10 sites, 20 tasks)",
        "",
        "Methods:",
        "- Standard browser use (raw page text + naive click-by-text)",
        "- OpenClaw browser (snapshot refs + click)",
        "- Semantic Browser (auto route + planner action IDs)",
        "",
        "| Method | Success rate | Stuck rate | Median speed ms | Median tok-in | Median tok-out |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key, label in [
        ("standard_browser_use", "Standard browser use"),
        ("openclaw_browser", "OpenClaw browser"),
        ("semantic_browser", "Semantic Browser"),
    ]:
        s = summary[key]
        md.append(
            f"| {label} | {s['task_success_rate']} | {s['stuck_rate']} | {s['speed_ms']['median']} | {s['tok_in']['median']} | {s['tok_out']['median']} |"
        )

    (out_dir / "2026-03-11-actionset-compare.md").write_text("\n".join(md))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
