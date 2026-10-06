#!/usr/bin/env python3
"""Journal a *real model* driving `sb` (instead of the scripted oracle in runner.py).

The model (a person or an LLM agent) runs one command at a time and only sees what is printed:

    sbj.py TASK goto https://example.com        # runs `sb --session TASK ... goto ...`, prints output, logs timing
    sbj.py TASK click 3
    sbj.py --done TASK success "found the price: 12.99"   # the model's own verdict (success|fail|partial) + note
    sbj.py --report [JOURNAL]                              # per-task steps, tool time, tokens read, verdict
    sbj.py --sanitize IN OUT                               # rewrite an old journal with typed text removed

Environment: SBJ_JOURNAL (default ./sbj-journal.jsonl), SBJ_MODEL (who is driving; recorded), SBJ_HEADFUL=1 for a
visible browser, SBJ_CDP=http://127.0.0.1:PORT to attach to a running Chrome (own tab only), SB_HOME for the daemon state dir, SBJ_SB for the sb executable.
Tokens are estimated as characters / 4 of everything the model had to read for that step.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path


def _journal() -> Path:
    return Path(os.environ.get("SBJ_JOURNAL", "sbj-journal.jsonl"))


def _append(row: dict) -> None:
    with _journal().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _redact_words(words: list[str]) -> list[str]:
    """`type N text... [--flags]` and `captcha text ANSWER`: keep the shape, drop what was typed."""
    if words[:1] == ["type"] and len(words) >= 3:
        flags = [w for w in words[2:] if w.startswith("--") and w in {"--enter", "--append"}]
        typed = " ".join(w for w in words[2:] if w not in flags)
        return [words[0], words[1], f"<redacted {len(typed)} chars>", *flags]
    if words[:2] == ["captcha", "text"] and len(words) >= 3:
        return [words[0], words[1], f"<redacted {len(' '.join(words[2:]))} chars>"]
    return words


def redact_argv(argv: list[str]) -> list[str]:
    """What gets written to the journal. Typed text is never kept (it may be a credential); everything else is."""
    if argv[:1] == ["do"]:
        steps = []
        for step in argv[1:]:
            try:
                words = shlex.split(step)
            except ValueError:
                steps.append(step)
                continue
            red = _redact_words(words)
            steps.append(step if red == words else " ".join(red))
        return ["do", *steps]
    return _redact_words(argv)


def sanitize(src: Path, dst: Path) -> None:
    """Rewrite an existing journal with typed text removed (for journals recorded before redaction existed)."""
    with src.open(encoding="utf-8") as fin, dst.open("w", encoding="utf-8") as fout:
        for line in fin:
            row = json.loads(line)
            if "argv" in row:
                row["argv"] = redact_argv(row["argv"])
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")


def run_step(task: str, args: list[str]) -> int:
    sb = os.environ.get("SBJ_SB") or str(Path(sys.executable).with_name("sb"))
    opts = ["--session", task]
    if os.environ.get("SBJ_CDP"):
        opts += ["--cdp", os.environ["SBJ_CDP"]]
    elif os.environ.get("SBJ_HEADFUL") != "1":
        opts.append("--headless")
    t0 = time.perf_counter()
    proc = subprocess.run([sb, *opts, *args], capture_output=True, text=True)
    ms = int((time.perf_counter() - t0) * 1000)
    out = (proc.stdout or "") + (proc.stderr or "")
    sys.stdout.write(out)
    if not out.endswith("\n"):
        sys.stdout.write("\n")
    sys.stdout.write(f"[sbj {ms} ms, ~{len(out) // 4} tokens]\n")
    _append(
        {
            "kind": "step",
            "task": task,
            "model": os.environ.get("SBJ_MODEL", "unknown"),
            "argv": args if os.environ.get("SBJ_KEEP_TYPED") == "1" else redact_argv(args),
            "ms": ms,
            "out_chars": len(out),
            "exit": proc.returncode,
            "ts": time.time(),
        }
    )
    return proc.returncode


def done(task: str, verdict: str, note: str) -> None:
    _append({"kind": "verdict", "task": task, "verdict": verdict, "note": note, "ts": time.time()})
    print(f"recorded {task}: {verdict}")


def report(path: Path) -> None:
    tasks: dict[str, dict] = defaultdict(lambda: {"steps": 0, "ms": 0, "chars": 0, "errors": 0, "verdict": "-", "note": ""})
    for line in path.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        t = tasks[r["task"]]
        if r["kind"] == "step":
            t["steps"] += 1
            t["ms"] += r["ms"]
            t["chars"] += r["out_chars"]
            t["errors"] += 1 if r["exit"] else 0
        else:
            t["verdict"], t["note"] = r["verdict"], r["note"]
    print(f"{'task':28} {'verdict':8} {'steps':>5} {'err':>3} {'tool_ms':>8} {'tokens':>7}  note")
    ok = 0
    for name, t in tasks.items():
        ok += t["verdict"] == "success"
        print(f"{name:28} {t['verdict']:8} {t['steps']:5d} {t['errors']:3d} {t['ms']:8d} {t['chars'] // 4:7d}  {t['note'][:70]}")
    n = len(tasks)
    steps = sorted(t["steps"] for t in tasks.values())
    ms = sorted(t["ms"] for t in tasks.values())
    toks = sorted(t["chars"] // 4 for t in tasks.values())
    if n:
        print(f"\nsuccess {ok}/{n}; median steps {steps[n // 2]}, median tool time {ms[n // 2]} ms, median tokens read {toks[n // 2]}")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "--done":
        done(argv[1], argv[2], " ".join(argv[3:]))
        return 0
    if argv[0] == "--sanitize":
        sanitize(Path(argv[1]), Path(argv[2]))
        return 0
    if argv[0] == "--report":
        report(Path(argv[1]) if len(argv) > 1 else _journal())
        return 0
    return run_step(argv[0], argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
