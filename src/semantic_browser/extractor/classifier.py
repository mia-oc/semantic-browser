"""Simple page type classifier."""

from __future__ import annotations


def classify_page(nodes: list[dict]) -> str:
    tags = [n.get("tag") for n in nodes]
    roles = [n.get("role") for n in nodes]
    if any(n.get("type") == "password" for n in nodes):
        return "login"
    if "table" in tags or "row" in roles:
        return "table"
    if "article" in tags:
        return "article"
    if "form" in tags:
        return "form"
    if tags.count("a") > 20:
        return "navigation-heavy"
    return "generic"
