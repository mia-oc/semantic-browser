#!/usr/bin/env python3
"""Time and journal *any* browser CLI while a real model (a person or an LLM agent) drives it by hand.

No automation lives here: the model chooses every command after reading the previous output. This wrapper only runs the
command, measures wall time (including CLI start-up, which agents really pay) and the size of everything printed, and keeps
the model's own verdict per task, so tools can be compared like for like.

    tj.py sb  wiki goto https://en.wikipedia.org/wiki/Eiffel_Tower     # TOOL TASK command...
    tj.py ab  wiki open https://en.wikipedia.org/wiki/Eiffel_Tower
    tj.py pw  wiki goto https://en.wikipedia.org/wiki/Eiffel_Tower
    tj.py --done sb wiki success "330 m"       # verdict: success | fail | partial (+ note)
    tj.py --stop sb wiki                       # end that tool's session for the task
    tj.py --report [JOURNAL]                   # per task/tool: calls, tool seconds, tokens read, verdict

TOOL: sb (semantic-browser), ab (agent-browser), pw (playwright-cli), bse (browse / Browserbase), raw (run argv as is).
Environment: TJ_JOURNAL (default ./tj-journal.jsonl), TJ_MODEL (who drives; recorded), TJ_CAP (chars shown, default 3000; the
FULL size is always what is counted), TJ_BIN (extra PATH dir for node CLIs), TJ_SB (sb executable), TJ_HEADED=1.
Tokens are estimated as characters / 4 of the full output.
"""

from __future__ import annotations

import json
import os
import re
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

TOOLS = ("sb", "ab", "pw", "bse", "raw")


def _journal() -> Path:
    return Path(os.environ.get("TJ_JOURNAL", "tj-journal.jsonl"))


def _append(row: dict) -> None:
    with _journal().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def session_name(tool: str, task: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "-", f"{tool}-{task}")[:32]


def build(tool: str, task: str, words: list[str], *, stop: bool = False) -> tuple[list[str], dict[str, str]]:
    """The real argv + extra environment for `tool` on `task`'s private session."""
    s = session_name(tool, task)
    env: dict[str, str] = {}
    headed = os.environ.get("TJ_HEADED") == "1"
    if tool == "sb":
        exe = os.environ.get("TJ_SB", "sb")
        base = [exe, "--session", s] + ([] if headed else ["--headless"])
        return (base + ["stop", s] if stop else base + words), env
    if tool == "ab":
        env["AGENT_BROWSER_SESSION"] = s
        return (["agent-browser", "close"] if stop else ["agent-browser", *words]), env
    if tool == "pw":
        return (["playwright-cli", f"-s={s}", "close"] if stop else ["playwright-cli", f"-s={s}", *words]), env
    if tool == "bse":
        base = ["browse", "--session", s] + ([] if headed else ["--headless"])
        return (base + ["stop"] if stop else base + words), env
    if tool == "raw":
        return words, env
    raise SystemExit(f"unknown tool {tool!r}; use one of {', '.join(TOOLS)}")


def cap_text(text: str, cap: int) -> str:
    if cap <= 0 or len(text) <= cap:
        return text
    return text[:cap] + f"\n… [{len(text) - cap} more chars not shown here; counted in full]"


def run_step(tool: str, task: str, words: list[str], *, stop: bool = False) -> int:
    argv, extra = build(tool, task, words, stop=stop)
    env = dict(os.environ, **extra)
    if os.environ.get("TJ_BIN"):
        env["PATH"] = os.environ["TJ_BIN"] + os.pathsep + env.get("PATH", "")
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=180)
        out, code = (proc.stdout or "") + (proc.stderr or ""), proc.returncode
    except subprocess.TimeoutExpired:
        out, code = "TIMEOUT after 180s", 124
    except FileNotFoundError as exc:
        out, code = f"not installed: {exc}", 127
    ms = int((time.perf_counter() - t0) * 1000)
    _append({
        "kind": "step", "ts": time.time(), "tool": tool, "task": task, "cmd": " ".join(words) if not stop else "(stop)",
        "ms": ms, "chars": len(out), "exit": code, "model": os.environ.get("TJ_MODEL", "unknown"),
    })
    print(cap_text(out, int(os.environ.get("TJ_CAP", "3000"))))
    print(f"[{tool}/{task}: {ms} ms, {len(out)} chars (~{len(out) // 4} tokens), exit {code}]", file=sys.stderr)
    return 0 if code in (0, 1) else code


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def aggregate(rows: list[dict]) -> tuple[dict[tuple[str, str], dict], dict[str, dict]]:
    """Per (task, tool) stats and per-tool summary (medians over tasks)."""
    per: dict[tuple[str, str], dict] = defaultdict(lambda: {"calls": 0, "ms": 0, "chars": 0, "verdict": "-", "note": ""})
    for r in rows:
        key = (r["task"], r["tool"])
        if r["kind"] == "step":
            d = per[key]
            d["calls"] += 1
            d["ms"] += r["ms"]
            d["chars"] += r["chars"]
        elif r["kind"] == "done":
            per[key]["verdict"] = r["verdict"]
            per[key]["note"] = r.get("note", "")
    tools: dict[str, dict] = {}
    for tool in sorted({k[1] for k in per}):
        items = [v for k, v in per.items() if k[1] == tool]
        done = [v for v in items if v["verdict"] != "-"]
        ok = [v for v in done if v["verdict"] == "success"]
        tools[tool] = {
            "tasks": len(done),
            "success": len(ok),
            "partial": sum(1 for v in done if v["verdict"] == "partial"),
            "median_calls": statistics.median(v["calls"] for v in done) if done else 0,
            "median_s": round(statistics.median(v["ms"] for v in done) / 1000, 2) if done else 0,
            "median_tokens": int(statistics.median(v["chars"] for v in done) / 4) if done else 0,
        }
    return per, tools


def report(path: Path) -> str:
    per, tools = aggregate(_rows(path))
    out = ["task".ljust(18) + "tool  calls  secs   tokens  verdict   note"]
    for (task, tool), d in sorted(per.items()):
        out.append(f"{task[:17].ljust(18)}{tool.ljust(5)} {str(d['calls']).rjust(5)}  {d['ms'] / 1000:5.1f}  {d['chars'] // 4:7d}  {d['verdict'].ljust(8)}  {d['note'][:60]}")
    out.append("")
    out.append("tool  tasks  success  partial  median calls  median secs  median tokens/task")
    for tool, s in tools.items():
        out.append(f"{tool.ljust(5)} {str(s['tasks']).rjust(5)}  {str(s['success']).rjust(7)}  {str(s['partial']).rjust(7)}  {str(s['median_calls']).rjust(12)}  {str(s['median_s']).rjust(11)}  {str(s['median_tokens']).rjust(18)}")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help"}:
        print(__doc__)
        return 0
    if argv[0] == "--report":
        print(report(Path(argv[1]) if len(argv) > 1 else _journal()))
        return 0
    if argv[0] == "--done":
        if len(argv) < 4 or argv[3] not in {"success", "fail", "partial"}:
            print("usage: tj.py --done TOOL TASK success|fail|partial [NOTE]", file=sys.stderr)
            return 2
        _append({"kind": "done", "ts": time.time(), "tool": argv[1], "task": argv[2], "verdict": argv[3], "note": " ".join(argv[4:])})
        print(f"recorded {argv[1]}/{argv[2]}: {argv[3]}")
        return 0
    if argv[0] == "--stop":
        return run_step(argv[1], argv[2], [], stop=True)
    if len(argv) < 3:
        print("usage: tj.py TOOL TASK command...", file=sys.stderr)
        return 2
    return run_step(argv[0], argv[1], argv[2:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
