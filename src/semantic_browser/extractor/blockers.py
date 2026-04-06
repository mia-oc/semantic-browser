"""Basic blocker and reliability detection."""

from __future__ import annotations

from typing import Any

from semantic_browser.config import ExtractionConfig
from semantic_browser.models import Blocker, ConfidenceReport, WarningNotice


def detect_blockers(nodes: list[dict[str, Any]]) -> list[Blocker]:
    blockers: list[Blocker] = []
    names = " ".join((n.get("name", "") + " " + n.get("text", "")) for n in nodes).lower()
    if "cookie" in names and ("accept" in names or "consent" in names or "allow" in names):
        blockers.append(
            Blocker(kind="cookie_banner", severity="medium", description="Cookie consent likely visible.")
        )
    if any("captcha" in (n.get("name", "") + n.get("text", "")).lower() for n in nodes):
        blockers.append(
            Blocker(kind="captcha_like", severity="high", description="CAPTCHA-like challenge detected.")
        )
    if any(n["tag"] == "input" and n.get("type") == "password" for n in nodes):
        blockers.append(
            Blocker(kind="login_wall", severity="low", description="Password field present; login may gate content.")
        )
    for n in nodes:
        if n["role"] == "dialog" and n.get("in_viewport", False):
            rect = n.get("rect", {})
            vp_w = max(1, n.get("viewport_width", 1920))
            vp_h = max(1, n.get("viewport_height", 1080))
            coverage = (rect.get("width", 0) * rect.get("height", 0)) / (vp_w * vp_h)
            if coverage > 0.3:
                blockers.append(
                    Blocker(kind="modal", severity="medium", description="Dialog or modal is active.")
                )
                break

    modal_tag_keywords = {"modal", "overlay", "dialog", "popup"}
    for n in nodes:
        tag = n.get("tag", "")
        if "-" not in tag:
            continue
        if any(kw in tag for kw in modal_tag_keywords):
            if not n.get("disabled") and n.get("in_viewport", False):
                blockers.append(
                    Blocker(
                        kind="modal",
                        severity="medium",
                        description=f"Custom element <{tag}> likely a modal/overlay.",
                    )
                )
                break

    return blockers


def confidence_from_nodes(
    nodes: list[dict[str, Any]], actions_count: int, cfg: ExtractionConfig
) -> tuple[ConfidenceReport, list[WarningNotice]]:
    if not nodes:
        return (
            ConfidenceReport(overall=0.2, extraction=0.2, actionability=0.1, reasons=["No visible nodes"]),
            [WarningNotice(kind="empty_page", description="No visible semantic nodes found.", severity="high")],
        )
    named = [n for n in nodes if (n.get("name") or "").strip()]
    named_ratio = len(named) / max(1, len(nodes))
    coverage = actions_count / max(1, len(nodes))
    warnings: list[WarningNotice] = []
    reasons: list[str] = []
    if named_ratio < cfg.low_name_threshold:
        warnings.append(
            WarningNotice(
                kind="low_semantic_quality",
                description="Many visible elements lack useful names.",
                severity="high",
            )
        )
        reasons.append("Low named element ratio")
    if coverage < cfg.low_action_coverage_threshold:
        warnings.append(
            WarningNotice(
                kind="low_action_coverage",
                description="Action coverage is lower than expected.",
                severity="medium",
            )
        )
        reasons.append("Low action coverage")
    base = min(1.0, 0.5 + (named_ratio * 0.3) + (coverage * 0.2))
    return (
        ConfidenceReport(
            overall=round(base, 3),
            extraction=round(min(1.0, 0.5 + named_ratio * 0.5), 3),
            grouping=0.75,
            actionability=round(min(1.0, 0.4 + coverage * 0.6), 3),
            stability=0.8,
            reasons=reasons,
        ),
        warnings,
    )
