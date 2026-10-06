from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location("replay", Path(__file__).resolve().parents[2] / "scripts" / "dogfood" / "replay.py")
assert _SPEC and _SPEC.loader
replay = importlib.util.module_from_spec(_SPEC)
sys.modules["replay"] = replay
_SPEC.loader.exec_module(replay)


def test_every_task_has_a_sequence_for_every_tool_and_a_success_pattern() -> None:
    tasks = replay._tasks()
    assert {"wiki", "hn", "todo", "shop", "dnd"} <= set(tasks)
    for name, spec in tasks.items():
        assert set(spec["seq"]) == {"sb", "ab", "pw"}, name
        assert spec["ok"], name
        assert all(spec["seq"][t] for t in spec["seq"]), name


def test_password_comes_from_the_environment_not_the_source(monkeypatch) -> None:
    src = (Path(replay.__file__)).read_text()
    assert "secret_sauce" not in src
    monkeypatch.setenv("SAUCEDEMO_PASSWORD", "hunter2")
    assert any("hunter2" in c for c in replay._tasks()["shop"]["seq"]["sb"])


def _row(tool: str, task: str, ok: bool, calls: int, ms: int, chars: int) -> dict:
    return {"tool": tool, "task": task, "ok": ok, "calls": calls, "ms": ms, "chars": chars}


def test_report_uses_medians_and_pass_counts() -> None:
    rows = [_row("sb", "t", True, 2, 2000, 400), _row("sb", "t", True, 2, 3000, 800), _row("sb", "t", False, 9, 9000, 4000),
            _row("ab", "t", True, 10, 2000, 4000)]
    text = replay.report(rows)
    assert "2/3 · 2 · 3.0 · 0.2k" in text  # median ms 3000 -> 3.0 s, median chars 800 -> 200 tokens
    assert "`ab` | 1/1 | 10 |" in text
    assert "pw" not in text  # tools without rows are omitted
