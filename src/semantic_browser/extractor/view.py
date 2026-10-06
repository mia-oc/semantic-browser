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

# Ranking of controls that can clear a blocking overlay. Lower rank = better. Anything that sounds like signing in,
# paying or subscribing is never a "dismiss", even if it also says "reject" or "continue".
_CLOSE_RE = re.compile(
    r"^(close|dismiss|collapse|hide|no,? thanks|no thank you|not now|maybe later|skip|got it|×|x|✕|reject|decline|deny|refuse|"
    r"only (strictly )?necessary|necessary only|essential only|cancel)\b",
    re.I,
)
_ACCEPT_RE = re.compile(r"^(accept|agree|allow|ok|okay|i agree|i accept|yes,? i)\b|accept all|allow all|agree and", re.I)
_RISKY_RE = re.compile(
    r"subscri|sign ?in|sign ?up|log ?in|register|create|donat|support|\bpay\b|buy|purchase|premium|trial|£|\$|€|"
    r"google|apple|facebook|phone|e-?mail|continue with|account",
    re.I,
)


def _dismiss_rank(name: str) -> int | None:
    name = name.strip()
    if not name or len(name) > 60 or _RISKY_RE.search(name):
        return None
    if _CLOSE_RE.search(name):
        return 0
    if _ACCEPT_RE.search(name):
        return 1
    if name.lower().rstrip(".!") == "continue":
        return 2  # last resort: bare "Continue" on an age/consent gate
    return None


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
    header: bool = False  # contains <th> cells (a table header row)
    toggle_label: str = ""  # name of a trailing checkbox/radio/switch, so a repeated label line can be dropped


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
    header_rows: list[bool] = field(default_factory=list)  # parallel to all_lines: True for <th> rows


def _unlabeled(node: dict[str, Any]) -> str:
    """Nothing to read on this control: for links, at least say where they go (path only, no query/tracking noise)."""
    href = str(node.get("href") or "").strip()
    if node.get("kind") != "link" or not href or href.startswith(("#", "javascript:")):
        return "(unlabeled)"
    path = href.split("?", 1)[0].split("#", 1)[0]
    path = re.sub(r"^https?://", "", path)
    return f"(unlabeled → {path[:60]})"


def format_element(node: dict[str, Any], *, collapsed: bool = False) -> str:
    ref = node.get("ref")
    kind = node.get("kind") or "button"
    label = (node.get("name") or "").strip() or _unlabeled(node)
    flags = ""
    if node.get("disabled"):
        flags += " disabled"
    if node.get("covered"):
        flags += " covered"
    if kind == "link" or (collapsed and kind in ("button", "menuitem", "tab")):
        return f"[{ref}{flags}]{label}"  # fillable controls keep their full form even inside a collapsed landmark
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


def _norm_label(s: str) -> str:
    return " ".join(s.lower().split())


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
        self._th = False
        self._toggle = ""  # label of the checkbox/radio/switch emitted last on this line
        self._prev_cell = False  # previous token was a cell start, i.e. that cell was empty
        self._recent_links: list[tuple[str, str]] = []  # (href, name) of the last few links, to fold exact repeats

    # -- line assembly ------------------------------------------------------------------------------
    def _joined(self) -> str:
        return "".join(self.parts)

    def flush(self) -> None:
        text = _clean(self._joined()).strip(" |")
        if text or self.elems:
            full = (self.prefix + text) if text else self.prefix.strip()
            self.lines.append(
                _Line(text=full, y=self.y, refs=list(self.refs), elems=list(self.elems), kind=self.kind,
                      in_layer=self.layer_depth > 0, header=self._th, toggle_label=self._toggle)
            )
        self.parts, self.elems, self.refs = [], [], []
        self.prefix, self.kind, self.y = "", "text", None
        self._prev_cell = False
        self._th = False
        self._toggle = ""

    def add_text(self, s: str) -> None:
        if s.strip():
            self._prev_cell = False
            if self._toggle and _norm_label(s) == self._toggle:
                self._toggle = ""
                return  # "[1 radio]Yes Yes": the visible label of the control we just printed
            self._toggle = ""
        if s and s[0] in ").,;:!?]" and self.parts and self.parts[-1] == " " and len(self.parts) > 1:
            self.parts.pop()  # no space between an element and the punctuation that follows it
        self.parts.append(s)

    def _is_repeat_link(self, node: dict[str, Any], label: str) -> bool:
        """A link to the same place as one of the last few, with the same (or no) text: image+title, stretched card links."""
        href = (node.get("href") or "").strip()
        if node.get("kind") != "link" or not href or href == "#" or href.lower().startswith("javascript"):
            return False
        name = " ".join(label.lower().split())
        if any(h == href and (n == name or not name) for h, n in self._recent_links):
            return True
        self._recent_links = [*self._recent_links[-3:], (href, name)]
        return False

    def add_elem(self, node: dict[str, Any], y: float | None) -> None:
        label = (node.get("name") or "").strip()
        if self._is_repeat_link(node, label):
            return
        if node.get("kind") in ("input", "select", "combobox", "file") and label:
            joined = self._joined().rstrip()
            if joined.endswith(label):  # <label>Foo <input></label> would print "Foo [3 input "Foo"]"
                cut = len(joined) - len(label)
                self.parts = [joined[:cut]]
        self._prev_cell = False
        self._toggle = _norm_label(label) if node.get("kind") in ("checkbox", "radio", "switch") else ""
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
        keep = list(range(min(limit, len(elems))))
        extra = [i for i in range(limit, len(elems)) if _FILLABLE_RE.match(elems[i])]
        if extra:  # a search box or dropdown must never vanish behind "(+N more)"
            keep = keep[: max(0, limit - len(extra))] + extra
        shown = [elems[i] for i in keep]
        more = len(elems) - len(shown)
        text = f"{kind}: " + " ".join(shown) + (f" … (+{more} more: view --expand {kind})" if more > 0 else "")
        y = inner[0].y
        in_layer = inner[0].in_layer
        del self.lines[start:]
        self.lines.append(_Line(text=text, y=y, refs=[refs[i] for i in keep if i < len(refs)], elems=shown, kind="collapsed", in_layer=in_layer))

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
                data_table = len(tok) > 1  # 'h' (header cell) or 'd' (cell in a table that has headers)
                if len(tok) > 1 and tok[1] == "h":
                    self._th = True
                if self._prev_cell and data_table:  # the cell before this one was empty: keep its slot so columns stay aligned
                    self.parts.append("·")
                    self.parts.append(" | ")
                elif _clean(self._joined()) or self.elems:
                    self.parts.append(" | ")
                self._prev_cell = data_table
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
        prev_toggle = ""
        for ln in self.lines:
            if ln.y is None:
                ln.y = carry
            else:
                carry = ln.y
            txt = ln.text
            if txt == last:
                continue
            if prev_toggle and _norm_label(txt.lstrip("-# ")) == prev_toggle:
                prev_toggle = ""
                continue  # the label of the checkbox/radio on the previous line, printed again on its own line
            prev_toggle = ln.toggle_label
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


_FILLABLE_RE = re.compile(r"\[\d+ (?:input|select|combobox|file)")
_GATE_RE = re.compile(
    r"client challenge|just a moment|attention required|checking your browser|security check|"
    r"verif(?:y|ying) (?:that )?you(?: are|'re) (?:a )?human|are you (?:a )?(?:human|robot)|press (?:and|&) hold|"
    r"unusual traffic|pardon our interruption|captcha (?:image|challenge|verification)|"
    r"not able to serve your requests this quickly|too many requests|rate.?limit|access denied|"
    r"(?:request|you have been) blocked|bots use \w+ too|made by a human|complete the following challenge",
    re.I,
)


def _gate_hint(snap: PageSnapshot, lines: list[str]) -> str | None:
    """Flag bot-wall / rate-limit pages. Only short pages qualify, so an article that mentions CAPTCHAs never trips it."""
    title = snap.title or ""
    source = [str(i[1]) for i in snap.flow if i and i[0] == "t" and len(i) > 1]  # rendered lines are truncated; use the source
    raw = sum(len(t) for t in source) + sum(len(str(n.get("name") or "")) for n in snap.nodes)
    refd = [n for n in snap.nodes if n.get("ref") is not None]
    mostly_covered = len(refd) >= 3 and sum(1 for n in refd if n.get("covered")) / len(refd) >= 0.5
    if raw > 1500 and not (mostly_covered or snap.layer):
        return None  # a long, usable page that merely mentions CAPTCHAs is not a gate
    text = "\n".join(source + lines)
    m = _GATE_RE.search(title or "") or _GATE_RE.search(text)
    if not m:
        return None
    return (
        f'! This looks like a bot/verification page ("{m.group(0)[:40]}"): the site is refusing automation. '
        "Do not retry in a loop. If solving it is part of your task and allowed: `sb captcha`; "
        "otherwise wait and retry once, then report that the site blocked you."
    )


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

    header_rows = [ln.header for ln in lines]
    all_lines = [ln.text for ln in lines]  # whole page, even behind an overlay: `find` must not go blind
    gate = _gate_hint(snap, all_lines)
    if gate:
        head.append(gate)
    layer_dismiss: list[int] = []
    layer_mode = bool(snap.layer) and not opts.all_layers
    if layer_mode:
        layer_lines = [ln for ln in lines if ln.in_layer]
        if layer_lines:
            ranked: list[tuple[int, int, int, int]] = []  # (rank, name length, order, ref)
            controls: list[tuple[int, str]] = []
            for ln in layer_lines:
                for r in ln.refs:
                    nd = nodes_by_ref.get(r)
                    if not (nd and nd.get("op")):
                        continue
                    nm_r = (nd.get("name") or "").strip()
                    controls.append((r, nm_r))
                    rk = _dismiss_rank(nm_r)
                    if rk is not None:
                        ranked.append((rk, len(nm_r), len(ranked), r))
            layer_dismiss = [r for *_k, r in sorted(ranked)]
            nm = (snap.layer or {}).get("name") or ""
            if layer_dismiss:
                hint = f" — dismiss with [{layer_dismiss[0]}]"
            else:
                shown = ", ".join(f'[{r}] "{n[:30]}"' for r, n in controls[:4] if n)
                hint = " — no obvious dismiss control" + (f" (options: {shown}; or `press Escape`)" if shown else " (try `press Escape`)")
            head.append(f'! BLOCKING OVERLAY{(" " + chr(34) + nm[:60] + chr(34)) if nm else ""} covers the page{hint}. Showing only the overlay; `view --all` shows the page behind it.')
            lines = layer_lines
        else:
            layer_mode = False

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
        more_below=more_below, layer_dismiss=layer_dismiss, all_lines=all_lines, header_rows=header_rows,
    )
