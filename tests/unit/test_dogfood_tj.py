"""scripts/dogfood/tj.py: the timing journal must count full output, keep verdicts, and build per-tool argv."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("tj", Path(__file__).resolve().parents[2] / "scripts" / "dogfood" / "tj.py")
assert SPEC and SPEC.loader
tj = importlib.util.module_from_spec(SPEC)
sys.modules["tj"] = tj
SPEC.loader.exec_module(tj)


def test_build_argv_per_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TJ_HEADED", raising=False)
    monkeypatch.setenv("TJ_SB", "/x/sb")
    argv, env = tj.build("sb", "wiki", ["goto", "https://e.com"])
    assert argv == ["/x/sb", "--session", "sb-wiki", "--headless", "goto", "https://e.com"] and not env
    argv, env = tj.build("ab", "wiki", ["open", "u"])
    assert argv == ["agent-browser", "open", "u"] and env == {"AGENT_BROWSER_SESSION": "ab-wiki"}
    assert tj.build("pw", "wiki", ["goto", "u"])[0] == ["playwright-cli", "-s=pw-wiki", "goto", "u"]
    assert tj.build("bse", "t", ["open", "u"])[0] == ["browse", "--session", "bse-t", "--headless", "open", "u"]
    assert tj.build("sb", "t", [], stop=True)[0][-2:] == ["stop", "sb-t"]
    assert tj.build("ab", "t", [], stop=True)[0] == ["agent-browser", "close"]
    with pytest.raises(SystemExit):
        tj.build("nope", "t", [])


def test_session_names_are_safe() -> None:
    assert tj.session_name("sb", "a b/c;d") == "sb-a-b-c-d"
    assert len(tj.session_name("sb", "x" * 99)) <= 32


def test_cap_only_trims_display_not_the_count() -> None:
    assert tj.cap_text("abc", 10) == "abc"
    assert tj.cap_text("x" * 50, 10).startswith("x" * 10 + "\n… [40 more chars")
    assert tj.cap_text("x" * 50, 0) == "x" * 50


def test_run_step_counts_full_output_and_report_aggregates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    jf = tmp_path / "j.jsonl"
    monkeypatch.setenv("TJ_JOURNAL", str(jf))
    monkeypatch.setenv("TJ_CAP", "5")
    tj.run_step("raw", "t1", [sys.executable, "-c", "print('y' * 400)"])
    tj.main(["--done", "raw", "t1", "success", "ok"])
    tj.run_step("raw", "t2", [sys.executable, "-c", "print('z' * 40)"])
    tj.main(["--done", "raw", "t2", "fail", "nope"])
    rows = [json.loads(ln) for ln in jf.read_text().splitlines()]
    assert rows[0]["chars"] == 401 and rows[0]["tool"] == "raw"
    per, tools = tj.aggregate(rows)
    assert per[("t1", "raw")]["verdict"] == "success" and per[("t1", "raw")]["chars"] == 401
    assert tools["raw"]["tasks"] == 2 and tools["raw"]["success"] == 1
    text = tj.report(jf)
    assert "t1" in text and "success" in text and "median tokens" in text
    shown = capsys.readouterr().out
    assert "yyyyy" in shown and "yyyyyy" not in shown.replace("yyyyy\n", "")


def test_missing_tool_is_reported_not_raised(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TJ_JOURNAL", str(tmp_path / "j.jsonl"))
    assert tj.run_step("raw", "t", ["definitely-not-a-real-binary-xyz"]) == 127
