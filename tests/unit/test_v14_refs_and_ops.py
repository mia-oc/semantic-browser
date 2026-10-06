"""Numeric ref resolution, op overrides, safe failure modes."""

from __future__ import annotations

import pytest

from semantic_browser.errors import ActionNotFoundError, ActionStaleError
from semantic_browser.executor.validation import _as_ref, resolve_action
from semantic_browser.models import (
    ActionDescriptor,
    ActionRequest,
    Observation,
    PageInfo,
    PageSummary,
)


def _obs(*actions: ActionDescriptor) -> Observation:
    return Observation(
        session_id="s", mode="summary", page=PageInfo(
            url="http://x", title="t", domain="x", page_type="generic", page_identity="x:t",
            ready_state="complete", modal_active=False, frame_count=1,
        ),
        summary=PageSummary(headline="h"),
        available_actions=list(actions),
    )


def _a(id_, ref, op="click", enabled=True, label="L") -> ActionDescriptor:
    return ActionDescriptor(id=id_, op=op, label=label, ref=ref, enabled=enabled, confidence=0.9)


@pytest.mark.parametrize("raw,expected", [("7", 7), ("[7]", 7), ("e7", 7), ("#7", 7), (" 12 ", 12), ("a7", None), ("x", None), ("more", None)])
def test_as_ref_accepts_the_shapes_a_model_will_type(raw, expected):
    assert _as_ref(raw) == expected


def test_resolves_by_numeric_ref():
    obs = _obs(_a("7", 7), _a("8", 8))
    assert resolve_action(ActionRequest(action_id="[8]"), obs).ref == 8


def test_unknown_ref_is_not_found_with_recovery_hint():
    with pytest.raises(ActionNotFoundError, match="view"):
        resolve_action(ActionRequest(action_id="99"), _obs(_a("7", 7)))


def test_disabled_ref_is_reported_stale():
    with pytest.raises(ActionStaleError, match="disabled"):
        resolve_action(ActionRequest(action_id="7"), _obs(_a("7", 7, enabled=False)))


def test_op_override_applies_only_to_whitelisted_ops():
    obs = _obs(_a("7", 7, op="open"))
    assert resolve_action(ActionRequest(action_id="7", op="hover"), obs).op == "hover"
    assert resolve_action(ActionRequest(action_id="7", op="press", value="Enter"), obs).op == "press"
    assert resolve_action(ActionRequest(action_id="7", op="delete_everything"), obs).op == "open"  # ignored
    assert resolve_action(ActionRequest(action_id="7"), obs).op == "open"  # no override => element default (keeps nav settle)


def test_override_does_not_mutate_the_observation():
    a = _a("7", 7, op="open")
    obs = _obs(a)
    resolve_action(ActionRequest(action_id="7", op="hover"), obs)
    assert obs.available_actions[0].op == "open"


def test_refs_are_never_reused_after_a_new_document():
    """Regression: `click 3` after navigation used to hit whatever became [3] on the new page."""
    from semantic_browser.extractor.snapshot import RefTable

    t = RefTable()
    first = [t.next_ref, t.next_ref + 1]
    t.next_ref += 2
    t.reset("new-doc")
    assert t.next_ref > max(first) and not t.entries


@pytest.mark.asyncio
async def test_tab_scope_hides_foreign_tabs_when_attached_to_a_shared_browser():
    """Attach mode must not leak (or switch to) the titles/tabs of a person's other tabs."""
    from semantic_browser.runtime import SemanticBrowserRuntime

    class _Page:
        def __init__(self, title):
            self._t = title
            self.context = None

        def is_closed(self):
            return False

        async def title(self):
            return self._t

        url = "https://x"

    class _Ctx:
        pages: list = []

    mine, theirs = _Page("mine"), _Page("Search results - private@example.com")
    ctx = _Ctx()
    ctx.pages = [theirs, mine]
    mine.context = theirs.context = ctx
    rt = SemanticBrowserRuntime.__new__(SemanticBrowserRuntime)
    rt._page, rt._owned, rt._popup = mine, None, None
    assert len(rt._context_pages()) == 2  # unscoped (own browser): both visible
    rt.restrict_tabs_to([mine])
    titles = await rt.tab_titles()
    assert titles == ["*1:mine"]
    assert "private@example.com" not in " ".join(titles)
