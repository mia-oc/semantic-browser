"""v2 observation path: single-pass snapshot -> Observation + page view (see snapshot.js / view.py)."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

from semantic_browser.config import RuntimeConfig
from semantic_browser.extractor.snapshot import PageSnapshot, RefTable, capture_snapshot
from semantic_browser.extractor.view import RenderedView, ViewOptions, render_view
from semantic_browser.models import (
    ActionDescriptor,
    Blocker,
    Observation,
    ObservationMetrics,
    PageInfo,
    PageSummary,
    PlannerAction,
    PlannerView,
)

from .blockers import confidence_from_nodes, detect_blockers
from .classifier import classify_page
from .diff import build_delta
from .grouping import build_forms, build_regions
from .ids import assign_node_ids, fingerprint_for
from .redaction import redact_nodes


def _global_actions() -> list[ActionDescriptor]:
    return [
        ActionDescriptor(id="back", op="back", label="Back", enabled=True, navigational=True, confidence=0.9),
        ActionDescriptor(id="fwd", op="forward", label="Forward", enabled=True, navigational=True, confidence=0.9),
        ActionDescriptor(id="reload", op="reload", label="Reload", enabled=True, navigational=True, confidence=0.9),
        ActionDescriptor(
            id="scroll", op="scroll", label="Scroll down", enabled=True, requires_value=False,
            value_schema={"type": "string", "enum": ["down", "up", "top", "bottom"]}, confidence=1.0,
        ),
        ActionDescriptor(
            id="wait", op="wait", label="Wait", enabled=True, requires_value=True,
            value_schema={"type": "integer", "description": "Milliseconds"}, confidence=1.0,
        ),
        ActionDescriptor(
            id="press", op="press", label="Press key", enabled=True, requires_value=True,
            value_schema={"type": "string", "description": "Key name, e.g. Enter, Escape, Tab, ArrowDown"}, confidence=1.0,
        ),
        ActionDescriptor(
            id="nav", op="navigate", label="Navigate to URL", enabled=True, requires_value=True,
            value_schema={"type": "string", "description": "URL"}, navigational=True, confidence=1.0,
        ),
    ]


def action_from_v2_node(node: dict[str, Any], node_id: str, action_id: str) -> ActionDescriptor | None:
    op = node.get("op")
    if not op or node.get("ref") is None:
        return None
    name = (node.get("name") or "").strip()
    ctx = (node.get("ctx") or "").strip()
    label = f"{name} — {ctx}" if (ctx and name) else (name or f"{node.get('kind') or node.get('tag')}-{node['ref']}")
    recipe: dict[str, Any] = {
        "name": name, "role": node.get("role", ""), "tag": node.get("tag", ""), "type": node.get("type", ""),
        "dom_id": node.get("id", ""), "href": node.get("href", ""), "ref": node["ref"],
        "frame_id": node.get("frame_id", "main"), "kind": node.get("kind", ""),
    }
    if node.get("css_selector"):
        recipe["css_selector"] = node["css_selector"]
    if node.get("is_custom_element"):
        recipe["is_custom_element"] = True
    return ActionDescriptor(
        id=action_id, op=op, label=label[:200], target_id=node_id, enabled=not node.get("disabled", False),
        requires_value=bool(node.get("requires_value")), navigational=op == "open",
        confidence=0.85, locator_recipe=recipe, ref=int(node["ref"]), kind=node.get("kind"),
        context=ctx or None, value=(node.get("value") or None),
    )


async def observe_page_v2(
    *,
    session_id: str,
    page: Any,
    mode: str,
    config: RuntimeConfig,
    previous_observation: Observation | None,
    previous_ids: dict[str, str] | None,
    refs: RefTable,
    view_options: ViewOptions | None = None,
    tabs: list[str] | None = None,
    notes: list[str] | None = None,
) -> tuple[Observation, dict[str, str], PageSnapshot, RenderedView]:
    start = time.perf_counter()
    snap = await capture_snapshot(
        page, refs, include_frames=config.extraction.include_frames, max_nodes=config.extraction.max_elements
    )
    nodes = redact_nodes(snap.nodes, config.redaction)
    snap.nodes = nodes
    id_map = assign_node_ids(nodes, previous=previous_ids)

    domain = urlparse(snap.url).netloc
    page_info = PageInfo(
        url=snap.url, title=snap.title, domain=domain, page_type=classify_page(nodes),
        page_identity=f"{domain}:{(snap.title or '').strip().lower()[:64]}", ready_state=snap.ready,
        modal_active=bool(snap.layer), frame_count=snap.frame_count,
    )

    actions = _global_actions()
    seen: dict[str, int] = {}
    ref_to_action: dict[int, str] = {}
    for node in nodes:
        if not node.get("op"):
            continue
        fp = fingerprint_for(node)
        ordinal = seen.get(fp, 0)
        seen[fp] = ordinal + 1
        node_id = id_map.get(f"{fp}#{ordinal}", f"elm-{fp[:8]}-{ordinal}")
        action = action_from_v2_node(node, node_id, f"act-{node_id.replace('elm-', '')}")
        if action is not None:
            actions.append(action)
            ref_to_action[action.ref or -1] = action.id

    regions = build_regions(nodes)
    blockers: list[Blocker] = detect_blockers(nodes)
    if snap.layer:
        probe = render_view(snap, options=ViewOptions(budget=1))  # cheap: finds dismiss candidates
        blockers.append(
            Blocker(
                kind="modal", severity="high",
                description=f'Overlay "{(snap.layer.get("name") or "")[:60]}" covers the page',
                related_action_ids=[ref_to_action[r] for r in probe.layer_dismiss if r in ref_to_action],
            )
        )
    forms = build_forms(nodes, actions)
    confidence, warnings = confidence_from_nodes(nodes, len(actions), config.extraction)

    vo = view_options or ViewOptions(budget=config.extraction.view_budget)
    view = render_view(snap, options=vo, notes=notes, tabs=tabs)
    if view.more_below:
        actions.append(
            ActionDescriptor(id="more", op="see_more", label="Show next part of the page view", enabled=True, confidence=1.0)
        )

    headings = [n["name"] for n in nodes if n.get("kind") == "heading" and n.get("name")][:3]
    narration = (page_info.title or domain) + (f'. Main content: "{headings[0][:80]}".' if headings else ".")
    summary = PageSummary(headline=page_info.title or domain, key_points=[narration])
    shown = set(view.shown_refs)
    planner = PlannerView(
        location=f"{page_info.title or domain} ({domain})",
        what_you_see=[narration],
        available_actions=[
            PlannerAction(id=str(a.ref), label=a.label, op=a.op) for a in actions if a.ref is not None and a.ref in shown
        ],
        blockers=[b.description for b in blockers[:5]],
        room_text=view.text,
        has_more_actions=view.more_below,
        total_action_count=sum(1 for a in actions if a.enabled),
    )
    obs = Observation(
        session_id=session_id, mode=mode,  # type: ignore[arg-type]
        page=page_info, summary=summary, blockers=blockers, warnings=warnings, regions=regions, forms=forms,
        content_groups=[], available_actions=actions, planner=planner,
        metrics=ObservationMetrics(
            extraction_ms=int((time.perf_counter() - start) * 1000), action_count=len(actions),
            interactable_count=len(nodes), region_count=len(regions), form_count=len(forms),
            content_group_count=0, extraction_route="v2", aria_quality=None,
            scoped_interactable_count=len(shown), total_interactable_count=len(nodes),
            full_bytes=len(view.text), delta_bytes=0,
        ),
        confidence=confidence,
    )
    delta = build_delta(previous_observation, obs)
    obs.metrics.delta_bytes = len(delta.notes)
    if mode == "delta":
        obs.summary = PageSummary(headline="Delta observation", key_points=delta.notes)
    return obs, id_map, snap, view
