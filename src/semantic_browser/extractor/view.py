"""Render a PageSnapshot as a compact reading-order page view with inline numbered refs.

Example::

    # Hacker News — https://news.ycombinator.com/   [screen 1/9]
    nav: [1]Hacker News [2]new [3]past [4]comments ... (+4)
    - 1. [5]Mistral Large 4 ([6]mistral.ai)
      523 points by [7]Philpax [8]4 hours ago | [9]hide | [10]628 comments

Why: a model gets the page's *content and its options in one place*, and every option is a short number.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from semantic_browser.extractor.snapshot import PageSnapshot

_DISMISS_RE = re.compile(
    r"^(accept|agree|allow|ok|okay|got it|i agree|i accept|continue|close|dismiss|reject|decline|no thanks|not now|maybe later|skip|×|x|✕)\b|accept all|reject all|allow all|agree and|close",
    re.I,
)
_WS = re.compile(r"\s+")


@dataclass
class ViewOptions:
    budget: int = 5000
    page: int | None = None
    expand: set[str] = field(default_factory=set)
    mode: str = "view"  # view | read
    all_layers: bool = False
    line_cap: int = 420
    start_y: float | None = None


@dataclass
class _Line:
    text: str
    y: float | None
    refs: list[int]
    elems: list[str]
    kind: str = "text"
    in_layer: bool = False


@dataclass
class RenderedView:
    text: str
    shown_refs: list[int]
    total_lines: int
    pages: int
    page: int
    more_below: bool
    layer_dismiss: list[int] = field(default_factory=list)
    all_lines: list[str] = field(default_factory=list)


def format_element(node: dict[str, Any], *, collapsed: bool = False) -> str:
    ref = node.get("ref")
    kind = node.get("kind") or "button"
    label = (node.get("name") or "").strip() or "(unlabeled)"
    flags = ""
    if node.get("disabled"):
        flags += " disabled"
    if node.get("covered"):
        flags += " covered"
    if collapsed or kind == "link":
        return f"[{ref}{flags}]{label}"
    if kind == "input":
        val = node.get("value") or ""
        t = node.get("type") or ""
        tag = "input" if t in ("", "text") else f"input:{t}"
        v = f'="{val}"' if val else ""
        return f'[{ref} {tag}{flags} "{label}"{v}]'
    if kind == "select":
        opts = node.get("options") or []
        shown = "|".join(opts[:8]) + ("|…" if len(opts) > 8 else "")
        return f'[{ref} select{flags} "{label}"="{node.get("value", "")}" {{{shown}}}]'
    if kind in ("checkbox", "radio", "switch"):
        mark = " ✓" if node.get("checked") else ""
        return f"[{ref} {kind}{mark}{flags}]{label}"
    if kind == "combobox" and node.get("expanded") is not None:
        return f"[{ref} combobox{flags} {'open' if node.get('expanded') == 'true' else 'closed'}]{label}"
    return f"[{ref} {kind}{flags}]{label}"


def _clean(s: str) -> str:
    return _WS.sub(" ", s.replace("\u200b", "")).strip()


class _Builder:
    def __init__(self, nodes_by_ref: dict[int, dict[str, Any]], opts: ViewOptions) -> None:
        self.nodes = nodes_by_ref
        self.opts = opts
        self.lines: list[_Line] = []
        self.parts: list[str] = []
        self.elems: list[str] = []
        self.refs: list[int] = []
        self.prefix = ""
        self.y: float | None = None
        self.kind = "text"
        self.regions: list[tuple[str, str, int]] = []
        self.layer_depth = 0

    # -- line assembly ------------------------------------------------------------------------------
    def _joined(self) -> str:
        return "".join(self.parts)

    def flush(self) -> None:
        text = _clean(self._joined()).strip(" |")
        if text or self.elems:
            full = (self.prefix + text) if text else self.prefix.strip()
            self.lines.append(
                _Line(text=full, y=self.y, refs=list(self.refs), elems=list(self.elems), kind=self.kind, in_layer=self.layer_depth > 0)
            )
        self.parts, self.elems, self.refs = [], [], []
        self.prefix, self.kind, self.y = "", "text", None

    def add_text(self, s: str) -> None:
        if s and s[0] in ").,;:!?]" and self.parts and self.parts[-1] == " " and len(self.parts) > 1:
            self.parts.pop()  # no space between an element and the punctuation that follows it
        self.parts.append(s)

    def add_elem(self, node: dict[str, Any], y: float | None) -> None:
        label = (node.get("name") or "").strip()
        if node.get("kind") in ("input", "select", "combobox", "file") and label:
            joined = self._joined().rstrip()
            if joined.endswith(label):  # <label>Foo <input></label> would print "Foo [3 input "Foo"]"
                cut = len(joined) - len(label)
                self.parts = [joined[:cut]]
        s = format_element(node)
        j = self._joined()
        if j and not j.endswith((" ", "(", "[", "\u2022", "-", "|")):
            self.parts.append(" ")
        self.parts.append(s)
        self.elems.append(format_element(node, collapsed=True))
        self.refs.append(int(node["ref"]))
        if self.y is None and y is not None:
            self.y = y
        self.parts.append(" ")

    # -- regions ---------------------------------------------------------------------------------------
    def region_start(self, kind: str, name: str) -> None:
        self.flush()
        self.regions.append((kind, name, len(self.lines)))
        if kind == "layer":
            self.layer_depth += 1

    def region_end(self) -> None:
        self.flush()
        if not self.regions:
            return
        kind, _name, start = self.regions.pop()
        if kind == "layer":
            self.layer_depth = max(0, self.layer_depth - 1)
            return
        inner = self.lines[start:]
        if not inner:
            return
        elems = [e for ln in inner for e in ln.elems]
        refs = [r for ln in inner for r in ln.refs]
        has_heading = any(ln.kind == "heading" for ln in inner)
        wanted = self.opts.expand
        expand = "all" in wanted or kind in wanted
        collapse = False
        if kind in ("nav", "footer") and not expand:
            collapse = True
        elif kind == "header" and not expand and not has_heading:
            collapse = True
        elif kind == "aside" and not expand and len(elems) >= 5:
            collapse = True
        if not collapse or not elems:
            return
        limit = 12 if kind != "footer" else 6
        shown = elems[:limit]
        more = len(elems) - len(shown)
        text = f"{kind}: " + " ".join(shown) + (f" … (+{more} more: view --expand {kind})" if more > 0 else "")
        y = inner[0].y
        in_layer = inner[0].in_layer
        del self.lines[start:]
        self.lines.append(_Line(text=text, y=y, refs=refs[:limit], elems=shown, kind="collapsed", in_layer=in_layer))

    # -- consume tokens ------------------------------------------------------------------------------
    def consume(self, flow: list[list[Any]]) -> None:
        for tok in flow:
            t = tok[0]
            if t == "t":
                self.add_text(tok[1])
            elif t == "e":
                node = self.nodes.get(int(tok[1]))
                if node is not None:
                    self.add_elem(node, tok[2] if len(tok) > 2 else None)
            elif t == "b":
                self.flush()
                self.y = tok[1] if len(tok) > 1 else None
            elif t == "h":
                self.flush()
                self.prefix = "#" * min(int(tok[1]), 3) + " "
                self.kind = "heading"
            elif t == "H":
                self.flush()
            elif t == "li":
                self.flush()
                self.prefix = "- "
            elif t == "c":
                if _clean(self._joined()) or self.elems:
                    self.parts.append(" | ")
            elif t == "r":
                self.region_start(str(tok[1]), str(tok[2]) if len(tok) > 2 else "")
            elif t == "R":
                self.region_end()
            elif t == "fs":
                self.flush()
                title = tok[1] or ""
                self.parts.append(f"⟦frame{': ' + title if title else ''}⟧")
                self.flush()
            elif t == "fe":
                self.flush()
        self.flush()
        while self.regions:
            self.region_end()

    # -- post-processing -----------------------------------------------------------------------------
    def finalize(self) -> list[_Line]:
        out: list[_Line] = []
        last: str | None = None
        cap = self.opts.line_cap
        carry: float | None = None
        for ln in self.lines:
            if ln.y is None:
                ln.y = carry
            else:
                carry = ln.y
            txt = ln.text
            if txt == last:
                continue
            last = txt
            if len(txt) > cap and ln.kind != "collapsed":
                cut = txt.rfind(" ", 0, cap)
                cut = cut if cut > cap * 0.6 else cap
                txt = txt[:cut] + f" …(+{len(ln.text) - cut} chars)"
            ln.text = txt
            if re.fullmatch(r"[\s|\-•·]*", txt):
                continue
            out.append(ln)
        return out


def render_view(
    snap: PageSnapshot,
    *,
    options: ViewOptions | None = None,
    notes: list[str] | None = None,
    tabs: list[str] | None = None,
) -> RenderedView:
    opts = options or ViewOptions()
    nodes_by_ref = {int(n["ref"]): n for n in snap.nodes if n.get("ref") is not None}
    b = _Builder(nodes_by_ref, opts)
    b.consume(snap.flow)
    lines = b.finalize()

    head: list[str] = []
    sc = snap.scroll or {}
    vh = float(sc.get("vh") or 800)
    total_h = float(sc.get("h") or vh)
    screens = max(1, math.ceil(total_h / vh))
    cur_screen = min(screens, int((float(sc.get("y") or 0)) // vh) + 1)
    head.append(f"@ {snap.title or '(untitled)'} — {snap.url}   [screen {cur_screen}/{screens}]")
    if tabs and len(tabs) > 1:
        head.append("tabs: " + " | ".join(tabs))
    for n in notes or []:
        head.append(n)

    layer_dismiss: list[int] = []
    layer_mode = bool(snap.layer) and not opts.all_layers
    if layer_mode:
        layer_lines = [ln for ln in lines if ln.in_layer]
        if layer_lines:
            for ln in layer_lines:
                for r in ln.refs:
                    nd = nodes_by_ref.get(r)
                    if nd and nd.get("op") and _DISMISS_RE.search((nd.get("name") or "").strip()):
                        layer_dismiss.append(r)
            nm = (snap.layer or {}).get("name") or ""
            hint = f" — dismiss with [{layer_dismiss[0]}]" if layer_dismiss else ""
            head.append(f'! BLOCKING OVERLAY "{nm[:60]}" covers the page{hint}. Page content is hidden until it is handled (view --all shows it).')
            lines = layer_lines
        else:
            layer_mode = False

    all_lines = [ln.text for ln in lines]

    # windowing
    pages = 1
    page_no = 1
    body: list[_Line]
    more_below = False
    remaining_chars = 0
    budget = opts.budget
    if opts.page:
        parts: list[list[_Line]] = [[]]
        used = 0
        for ln in lines:
            if used + len(ln.text) > budget and parts[-1]:
                parts.append([])
                used = 0
            parts[-1].append(ln)
            used += len(ln.text) + 1
        pages = len(parts)
        page_no = max(1, min(opts.page, pages))
        body = parts[page_no - 1]
        more_below = page_no < pages
        remaining_chars = sum(len(x.text) for p in parts[page_no:] for x in p)
    else:
        start_y = opts.start_y if opts.start_y is not None else (max(0.0, float(sc.get("y") or 0) - 60) if float(sc.get("y") or 0) > 0 else 0.0)
        above = 0
        if start_y > 0 and not layer_mode:
            kept = [ln for ln in lines if ln.y is None or ln.y >= start_y]
            above = len(lines) - len(kept)
            lines = kept
        body, used = [], 0
        for i, ln in enumerate(lines):
            if used + len(ln.text) > budget and body:
                more_below = True
                remaining_chars = sum(len(x.text) for x in lines[i:])
                break
            body.append(ln)
            used += len(ln.text) + 1
        if above:
            head.append(f"↑ {above} lines above (scroll up / view --page 1)")

    out = head + [ln.text for ln in body]
    shown_refs = [r for ln in body for r in ln.refs]
    if more_below:
        total_remaining = max(1, remaining_chars)
        nxt = page_no + 1
        out.append(f"… more below (~{total_remaining // 4} tokens) — `scroll down` or `view --page {nxt}`")
    elif not body:
        out.append("(no visible content yet — try `wait` then `view`)")
    return RenderedView(
        text="\n".join(out), shown_refs=shown_refs, total_lines=len(lines), pages=pages, page=page_no,
        more_below=more_below, layer_dismiss=layer_dismiss, all_lines=all_lines,
    )
