"""Region, form, and content grouping."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from semantic_browser.models import (
    ActionDescriptor,
    ContentGroupSummary,
    ContentItemPreview,
    FormSummary,
    RegionSummary,
)


def build_regions(nodes: list[dict[str, Any]]) -> list[RegionSummary]:
    region_like = {"main", "nav", "header", "footer", "aside", "section", "article", "dialog", "form"}
    regions: list[RegionSummary] = []
    order = 0
    for node in nodes:
        if node["tag"] in region_like or node["role"] in {"main", "navigation", "dialog", "form"}:
            rid = f"rgn-{order}"
            regions.append(
                RegionSummary(
                    id=rid,
                    kind=node["role"],
                    name=node["name"] or node["tag"],
                    frame_id="main",
                    order=order,
                    visible=True,
                    in_viewport=node["in_viewport"],
                    interactable_count=0,
                    content_item_count=0,
                    primary_action_ids=[],
                    preview_text=(node["text"] or None),
                )
            )
            order += 1
    if not regions:
        regions.append(
            RegionSummary(
                id="rgn-root",
                kind="root",
                name="Document",
                frame_id="main",
                order=0,
                visible=True,
                in_viewport=True,
                interactable_count=0,
                content_item_count=0,
                primary_action_ids=[],
            )
        )
    return regions


def build_forms(nodes: list[dict[str, Any]], actions: list[ActionDescriptor]) -> list[FormSummary]:
    forms: list[FormSummary] = []
    form_nodes = [n for n in nodes if n["tag"] == "form" or n["role"] == "form"]
    for idx, node in enumerate(form_nodes):
        fields = [
            a.target_id
            for a in actions
            if a.op in {"fill", "select_option", "toggle"} and (a.target_id or "").startswith("elm-")
        ]
        submit_ids = [a.id for a in actions if a.op in {"submit", "click"} and "submit" in a.label.lower()]
        forms.append(
            FormSummary(
                id=f"frm-{idx}",
                name=node["name"] or f"Form {idx+1}",
                frame_id="main",
                field_ids=[f for f in fields if f],
                submit_action_ids=submit_ids,
                validity="unknown",
                required_missing=[],
            )
        )
    return forms


def build_content_groups(nodes: list[dict[str, Any]]) -> list[ContentGroupSummary]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for n in nodes:
        if n["tag"] in {"li", "article"} or n["role"] in {"listitem", "row"}:
            key = n["role"] or n["tag"]
            buckets[key].append(n)
    groups: list[ContentGroupSummary] = []
    for idx, (kind, items) in enumerate(buckets.items()):
        previews = [
            ContentItemPreview(
                id=f"itm-{idx}-{i}",
                title=(item["name"] or item["text"][:80] or None),
                subtitle=item["text"][:120] or None,
            )
            for i, item in enumerate(items[:5])
        ]
        groups.append(
            ContentGroupSummary(
                id=f"grp-{idx}",
                kind=kind,
                name=f"{kind} items",
                item_count=len(items),
                visible_item_count=len(items),
                preview_items=previews,
            )
        )
    return groups
