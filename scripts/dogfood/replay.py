#!/usr/bin/env python3
"""Replay a fixed command sequence per tool, several times, and report medians (the repeat-run companion to tj.py).

tj.py journals a model driving a tool by hand once. This replays the *shortest working sequence* that hand-driven run found for
each tool (sequences live in TASKS below), so cold-start time, number of calls and tokens printed can be repeated and medianed
as docs/benchmark_protocol.md requires. It does not pick locators for a model: refs in a sequence were read from that tool's own
output in the hand-driven run, and a task passes only if its success pattern appears in the printed output.

    replay.py --runs 3 --out /tmp/replay.jsonl                 # all tasks, all installed tools
    replay.py --runs 1 --tasks hn,dnd --tools sb,pw --show     # print each step's output (sanity check)
    replay.py --report /tmp/replay.jsonl                       # markdown table from a saved run

Every run starts a fresh browser session (cold start counted) and ends it (not counted). Rounds are interleaved
(round -> task -> tool) so network drift hits every tool alike. Tokens = printed characters / 4.
Env: SAUCEDEMO_PASSWORD (the demo shop's published password) for the `shop` task; TJ_SB / TJ_BIN as in tj.py.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tj  # noqa: E402

WIKI = "https://en.wikipedia.org/wiki/Eiffel_Tower"
HN = "https://news.ycombinator.com/"
TODO = "https://todomvc.com/examples/react/dist/"
SHOP = "https://www.saucedemo.com/"
DND = "https://www.selenium.dev/selenium/web/droppableItems.html"


def _tasks() -> dict[str, dict]:
    pw = os.environ.get("SAUCEDEMO_PASSWORD", "")
    return {
        "wiki": {"ok": r"330", "what": "height of the Eiffel Tower", "seq": {
            "sb": [f"goto {WIKI}", "find Height"],
            "ab": [f"open {WIKI}", "read"],
            "pw": [f"open {WIKI}", "snapshot"]}},
        "hn": {"ok": r"points", "what": "read the Hacker News front page", "seq": {
            "sb": [f"goto {HN}"],
            "ab": [f"open {HN}", "read"],
            "pw": [f"open {HN}", "snapshot"]}},
        "todo": {"ok": r"2 items? left", "what": "add 3 todos, tick one", "seq": {
            "sb": [f"goto {TODO}", 'do "type 11 \'buy milk\' --enter" "type 11 \'write tests\' --enter" "type 11 \'ship 1.7\' --enter" "check \'write tests\'"'],
            "ab": [f"open {TODO}", "snapshot -i", "fill @e11 'buy milk'", "press Enter", "fill @e11 'write tests'", "press Enter",
                   "fill @e11 'ship 1.7'", "press Enter", "snapshot -i", "check @e22", "read"],
            "pw": [f"open {TODO}", "snapshot", "fill e38 'buy milk'", "press Enter", "fill e38 'write tests'", "press Enter",
                   "fill e38 'ship 1.7'", "press Enter", "snapshot", "check e62", "snapshot"]}},
        "shop": {"ok": r"Backpack[\s\S]*Bolt T-Shirt|Bolt T-Shirt[\s\S]*Backpack", "what": "log in, add 2 items, open the cart", "needs_env": "SAUCEDEMO_PASSWORD", "seq": {
            "sb": [f"goto {SHOP}", f'do "type Username standard_user" "type Password {pw} --enter" "click \'Add to cart — Sauce Labs Backpack\'" '
                   '"click \'Add to cart — Sauce Labs Bolt T-Shirt\'" "click Cart"'],
            "ab": [f"open {SHOP}", "snapshot -i", "fill @e5 standard_user", f"fill @e6 {pw}", "click @e4", "snapshot -i",
                   "click @e17", "click @e21", "click @e8", "read"],
            "pw": [f"open {SHOP}", "snapshot", "fill e11 standard_user", f"fill e13 {pw}", "click e15", "snapshot",
                   "click e54", "click e78", "click e32", "snapshot"]}},
        "dnd": {"ok": r"Dropped!", "what": "drag one box onto another", "seq": {
            "sb": [f"goto {DND}", "drag 1 2"],
            "ab": [f"open {DND}", "snapshot -i", "snapshot", "drag #draggable #droppable", "read"],
            "pw": [f"open {DND}", "snapshot", "drag e4 e6", "snapshot"]}},
    }


def _run(tool: str, task: str, cmd: str, session_task: str) -> tuple[int, int, str]:
    argv, extra = tj.build(tool, session_task, shlex.split(cmd))
    env = dict(os.environ, **extra)
    if os.environ.get("TJ_BIN"):
        env["PATH"] = os.environ["TJ_BIN"] + os.pathsep + env.get("PATH", "")
    t0 = time.perf_counter()
    try:
        p = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=120)
        out, code = (p.stdout or "") + (p.stderr or ""), p.returncode
    except subprocess.TimeoutExpired:
        out, code = "TIMEOUT", 124
    except FileNotFoundError as exc:
        out, code = f"not installed: {exc}", 127
    return int((time.perf_counter() - t0) * 1000), code, out


def one_run(tool: str, task: str, spec: dict, show: bool) -> dict:
    sess = f"rp{os.getpid() % 1000}-{task}"
    secret = os.environ.get("SAUCEDEMO_PASSWORD", "")
    steps, text = [], []
    for cmd in spec["seq"][tool]:
        ms, code, out = _run(tool, task, cmd, sess)
        shown = cmd.replace(secret, "[typed]") if secret else cmd
        steps.append({"cmd": shown[:120], "ms": ms, "chars": len(out), "exit": code})
        text.append(out)
        if show:
            print(f"--- {tool}/{task}: {shown[:90]} [{ms} ms, {len(out)} chars, exit {code}]\n{out[:600]}")
        if code == 127:
            break
    argv, extra = tj.build(tool, sess, [], stop=True)
    subprocess.run(argv, capture_output=True, env=dict(os.environ, **extra), timeout=60)
    blob = "\n".join(text)
    return {
        "tool": tool, "task": task, "calls": len(steps), "ms": sum(s["ms"] for s in steps), "chars": sum(s["chars"] for s in steps),
        "ok": bool(re.search(spec["ok"], blob)) and not any(s["exit"] == 127 for s in steps), "steps": steps,
    }


def report(rows: list[dict]) -> str:
    tasks = list(dict.fromkeys(r["task"] for r in rows))
    tools = [t for t in ("sb", "ab", "pw") if any(r["tool"] == t for r in rows)]
    lines = ["| Task | " + " | ".join(f"`{t}` pass · calls · s · tokens" for t in tools) + " |", "|---|" + "---|" * len(tools)]
    for task in tasks:
        cells = []
        for tool in tools:
            rs = [r for r in rows if r["task"] == task and r["tool"] == tool]
            if not rs:
                cells.append("–")
                continue
            ok = sum(r["ok"] for r in rs)
            calls, ms, chars = (statistics.median(r[k] for r in rs) for k in ("calls", "ms", "chars"))
            cells.append(f"{ok}/{len(rs)} · {calls:g} · {ms / 1000:.1f} · {chars / 4 / 1000:.1f}k")
        lines.append(f"| {task} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("| Tool | Runs passed | Median calls | Median seconds | Median tokens |")
    lines.append("|---|---:|---:|---:|---:|")
    for tool in tools:
        rs = [r for r in rows if r["tool"] == tool]
        lines.append(f"| `{tool}` | {sum(r['ok'] for r in rs)}/{len(rs)} | {statistics.median(r['calls'] for r in rs):g} | "
                     f"{statistics.median(r['ms'] for r in rs) / 1000:.1f} | {statistics.median(r['chars'] for r in rs) / 4:,.0f} |")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--tasks", default="")
    ap.add_argument("--tools", default="sb,ab,pw")
    ap.add_argument("--out", default="")
    ap.add_argument("--show", action="store_true", help="print each step's output (sanity check)")
    ap.add_argument("--report", default="", help="print the markdown table for a saved JSONL and exit")
    a = ap.parse_args()
    if a.report:
        print(report([json.loads(x) for x in Path(a.report).read_text().splitlines() if x.strip()]))
        return 0
    tasks = _tasks()
    want = [t for t in (a.tasks.split(",") if a.tasks else tasks) if t in tasks]
    rows: list[dict] = []
    for rnd in range(1, a.runs + 1):
        for task in want:
            spec = tasks[task]
            if spec.get("needs_env") and not os.environ.get(spec["needs_env"]):
                print(f"skip {task}: set {spec['needs_env']}", file=sys.stderr)
                continue
            for tool in a.tools.split(","):
                r = one_run(tool, task, spec, a.show)
                r["round"] = rnd
                rows.append(r)
                print(f"round {rnd} {task:5} {tool}: {'PASS' if r['ok'] else 'FAIL'} {r['calls']} calls {r['ms'] / 1000:.1f}s {r['chars'] // 4} tok", file=sys.stderr)
                if a.out:
                    with open(a.out, "a", encoding="utf-8") as fh:
                        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(report(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
