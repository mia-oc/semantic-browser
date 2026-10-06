"""The dogfood journal must never keep what was typed into a page (it could be a credential)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("sbj", Path(__file__).resolve().parents[2] / "scripts" / "dogfood" / "sbj.py")
sbj = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(sbj)  # type: ignore[union-attr]


def test_typed_text_is_redacted_in_plain_and_batched_commands():
    assert sbj.redact_argv(["type", "7", "hunter2 is my password", "--enter"]) == ["type", "7", "<redacted 22 chars>", "--enter"]
    assert sbj.redact_argv(["do", 'type 3 "s3cret value" --enter', "click 5", "captcha text ABC123"]) == [
        "do", "type 3 <redacted 12 chars> --enter", "click 5", "captcha text <redacted 6 chars>",
    ]
    assert sbj.redact_argv(["captcha", "text", "XK3-92"]) == ["captcha", "text", "<redacted 6 chars>"]
    assert sbj.redact_argv(["goto", "https://example.com/?q=1"]) == ["goto", "https://example.com/?q=1"]


def test_sanitize_rewrites_an_existing_journal(tmp_path):
    src, dst = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    src.write_text('{"kind": "step", "task": "t", "argv": ["type", "1", "Jane Doe"], "ms": 1}\n{"kind": "verdict", "task": "t"}\n')
    sbj.sanitize(src, dst)
    out = dst.read_text()
    assert "Jane" not in out and "<redacted 8 chars>" in out and '"verdict"' in out
