"""Tests for v1.3 extraction improvements: framework discovery, modal detection, curation."""

from __future__ import annotations

from semantic_browser.extractor.blockers import detect_blockers
from semantic_browser.extractor.engine import (
    _CURATED_ROOM_BUDGET,
    _EXPANDED_ROOM_BUDGET,
    _MAX_CURATED_ACTIONS,
    _action_for_node,
    _curate_actions,
)
from semantic_browser.models import ActionDescriptor

# ---------------------------------------------------------------------------
# Framework binding op inference
# ---------------------------------------------------------------------------


def test_action_for_node_ng_click_infers_click():
    node = {
        "tag": "btn-odds",
        "role": "btn-odds",
        "name": "3/1",
        "type": "",
        "href": "",
        "id": "",
        "tabindex": "",
        "has_click_handler": True,
        "is_custom_element": True,
        "css_selector": "btn-odds.odds",
        "framework_attrs": {"ng-click": "addToBetslip(sel)"},
    }
    action = _action_for_node(node, "elm-abc-0", "act-abc-0", 0)
    assert action is not None
    assert action.op == "click"


def test_action_for_node_ng_model_input_infers_fill():
    node = {
        "tag": "input",
        "role": "textbox",
        "name": "Stake",
        "type": "text",
        "href": "",
        "id": "",
        "tabindex": "",
        "has_click_handler": False,
        "is_custom_element": False,
        "css_selector": "input.stake",
        "framework_attrs": {"ng-model": "bet.stake"},
    }
    action = _action_for_node(node, "elm-def-0", "act-def-0", 0)
    assert action is not None
    assert action.op == "fill"
    assert action.requires_value


def test_action_for_node_vue_click_infers_click():
    node = {
        "tag": "app-button",
        "role": "app-button",
        "name": "Add to cart",
        "type": "",
        "href": "",
        "id": "",
        "tabindex": "",
        "has_click_handler": True,
        "is_custom_element": True,
        "css_selector": "app-button.cta",
        "framework_attrs": {"v-on:click": "addToCart()"},
    }
    action = _action_for_node(node, "elm-vue-0", "act-vue-0", 0)
    assert action is not None
    assert action.op == "click"


def test_action_for_node_alpine_click_infers_click():
    node = {
        "tag": "x-toggle",
        "role": "x-toggle",
        "name": "Dark mode",
        "type": "",
        "href": "",
        "id": "",
        "tabindex": "",
        "has_click_handler": True,
        "is_custom_element": True,
        "css_selector": "x-toggle",
        "framework_attrs": {"x-on:click": "toggle()"},
    }
    action = _action_for_node(node, "elm-alp-0", "act-alp-0", 0)
    assert action is not None
    assert action.op == "click"


def test_action_for_node_no_framework_attrs_no_op():
    """Custom element with no interactive signals should not produce an action."""
    node = {
        "tag": "coupon-card",
        "role": "coupon-card",
        "name": "Premier League",
        "type": "",
        "href": "",
        "id": "",
        "tabindex": "",
        "has_click_handler": False,
        "is_custom_element": True,
        "css_selector": "coupon-card",
        "framework_attrs": {},
    }
    action = _action_for_node(node, "elm-cc-0", "act-cc-0", 0)
    assert action is None


# ---------------------------------------------------------------------------
# Custom element blocker detection
# ---------------------------------------------------------------------------


def test_blocker_detects_custom_element_modal():
    nodes = [
        {"tag": "safety-message-modal", "role": "safety-message-modal",
         "name": "Responsible Gambling", "text": "", "disabled": False, "in_viewport": True},
    ]
    blockers = detect_blockers(nodes)
    assert any(b.kind == "modal" and "safety-message-modal" in b.description for b in blockers)


def test_blocker_detects_abc_modal():
    nodes = [
        {"tag": "abc-modal", "role": "abc-modal", "name": "Promo",
         "text": "", "disabled": False, "in_viewport": True},
    ]
    blockers = detect_blockers(nodes)
    assert any(b.kind == "modal" for b in blockers)


def test_blocker_detects_overlay_tag():
    nodes = [
        {"tag": "background-overlay", "role": "background-overlay",
         "name": "", "text": "", "disabled": False, "in_viewport": True},
    ]
    blockers = detect_blockers(nodes)
    assert any(b.kind == "modal" for b in blockers)


def test_blocker_ignores_non_modal_custom_elements():
    nodes = [
        {"tag": "coupon-card", "role": "coupon-card", "name": "EPL",
         "text": "", "disabled": False, "in_viewport": True},
    ]
    blockers = detect_blockers(nodes)
    assert not any(b.kind == "modal" for b in blockers)


# ---------------------------------------------------------------------------
# Curation: custom element promotion
# ---------------------------------------------------------------------------


def test_custom_element_open_promoted_to_primary():
    """Custom elements with 'open' op should be in primary tier, not normal."""
    actions = [
        ActionDescriptor(id="a1", op="open", label="Match Page",
                         locator_recipe={"is_custom_element": True}, enabled=True),
        ActionDescriptor(id="a2", op="open", label="Home Link",
                         locator_recipe={}, enabled=True),
    ]
    curated, _ = _curate_actions(actions, [], limit=1)
    assert curated[0].id == "a1"


def test_custom_element_toggle_promoted_to_primary():
    actions = [
        ActionDescriptor(id="a1", op="toggle", label="Show odds",
                         locator_recipe={"is_custom_element": True}, enabled=True),
        ActionDescriptor(id="a2", op="open", label="Some link",
                         locator_recipe={}, enabled=True),
    ]
    curated, _ = _curate_actions(actions, [], limit=1)
    assert curated[0].id == "a1"


# ---------------------------------------------------------------------------
# Budget constants
# ---------------------------------------------------------------------------


def test_max_curated_actions_is_25():
    assert _MAX_CURATED_ACTIONS == 25


def test_curated_room_budget_is_2000():
    assert _CURATED_ROOM_BUDGET == 2000


def test_expanded_room_budget_is_8000():
    assert _EXPANDED_ROOM_BUDGET == 8000
