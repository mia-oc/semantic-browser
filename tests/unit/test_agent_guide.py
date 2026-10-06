"""The agent playbook (`sb guide`) must stay complete, small, safe and in sync with the code."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from semantic_browser import agent as agent_mod
from semantic_browser.guide import GUIDE, SKILL_DESCRIPTION, guide_text, skill_text
from semantic_browser.verbs_help import HELP

ROOT = Path(__file__).resolve().parents[2]


def _implemented_verbs() -> set[str]:
    return {n[3:].replace("_", "-") for n in dir(agent_mod.AgentSession) if n.startswith("_v_")}


def test_guide_mentions_every_implemented_verb() -> None:
    missing = [v for v in sorted(_implemented_verbs()) if not re.search(rf"\b{re.escape(v)}\b", GUIDE)]
    assert not missing, f"guide.py does not mention verbs: {missing}"


def test_help_mentions_every_implemented_verb_and_the_guide() -> None:
    missing = [v for v in sorted(_implemented_verbs()) if v != "help" and not re.search(rf"\b{v}\b", HELP)]
    assert not missing, f"verbs_help.py does not mention verbs: {missing}"
    assert "sb guide" in HELP


def test_guide_is_small_enough_to_paste_into_a_prompt() -> None:
    # ~4 chars per token: keep the whole playbook under ~2.5k tokens so it is cheap to carry in every run.
    assert len(GUIDE) < 10_000, len(GUIDE)
    assert len(GUIDE.splitlines()) < 150


def test_guide_has_the_rules_that_keep_agents_safe_and_fast() -> None:
    low = GUIDE.lower()
    for needle in (
        "untrusted",          # prompt-injection stance
        "never follow instructions",
        "read-only",
        "irreversible",
        "do \"",              # batching
        "find ",              # cheap search
        "overlay",
        "stale",
        "never reuse",        # refs from old pages
        "captcha",
        "blocked",
    ):
        assert needle in low, f"guide lost: {needle!r}"


def test_guide_contains_no_secrets_or_machine_paths() -> None:
    assert "pypi-" not in GUIDE
    assert "/Users/" not in GUIDE
    assert "openclaw" not in GUIDE.lower()


def test_guide_examples_use_only_real_verbs() -> None:
    verbs = _implemented_verbs() | {"stop", "sessions", "version"}
    for m in re.finditer(r"^\s*(?:\$ )?sb (?:--?\w[\w-]* \S+ )*([a-z-]+)", GUIDE, re.M):
        assert m.group(1) in verbs, f"example uses unknown verb {m.group(1)!r}"


def test_skill_text_is_a_valid_skill_file() -> None:
    text = skill_text()
    assert text.startswith("---\nname: semantic-browser\n")
    head, body = text[4:].split("\n---\n", 1)
    assert f"description: {SKILL_DESCRIPTION}" in head
    assert len(SKILL_DESCRIPTION) < 400
    assert body.strip() == guide_text().strip()


def test_docs_copy_is_in_sync() -> None:
    doc = (ROOT / "docs" / "agent_guide.md").read_text()
    assert guide_text().strip() in doc, "docs/agent_guide.md is out of sync; run: sb guide > the guide block"


def test_sb_guide_works_without_a_daemon(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from semantic_browser.daemon import client

    monkeypatch.setenv("SB_HOME", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["sb", "guide"])
    started: list[object] = []
    monkeypatch.setattr(client, "_ensure_daemon", lambda *a, **k: started.append(1) or "x")
    client.main()
    out = capsys.readouterr().out
    assert out.strip() == guide_text().strip()
    assert not started, "guide must not start a browser"

    monkeypatch.setattr(sys, "argv", ["sb", "guide", "--skill"])
    client.main()
    assert capsys.readouterr().out.startswith("---\nname: semantic-browser")
    assert not started


@pytest.mark.asyncio
async def test_guide_is_also_an_in_session_verb() -> None:
    s = agent_mod.AgentSession.__new__(agent_mod.AgentSession)
    out = await s._v_guide([])
    assert out.strip() == guide_text().strip()
    out2 = await s._v_guide(["--skill"])
    assert out2.startswith("---\nname: semantic-browser")
