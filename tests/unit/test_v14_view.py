"""Page view renderer: the text an LLM actually reads."""

from __future__ import annotations

from semantic_browser.extractor.snapshot import PageSnapshot
from semantic_browser.extractor.view import ViewOptions, format_element, render_view


def _snap(nodes, flow, *, layer=None, scroll=None, title="T", url="http://x/") -> PageSnapshot:
    return PageSnapshot(
        title=title, url=url, ready="complete", gen="g", scroll=scroll or {"y": 0, "h": 800, "vh": 800},
        nodes=nodes, flow=flow, layer=layer, frame_count=1, stats={},
    )


def _n(ref, kind, name, op="click", **kw):
    return {"ref": ref, "kind": kind, "name": name, "op": op, **kw}


def test_inline_links_and_buttons_use_numbered_refs():
    snap = _snap(
        [_n(1, "link", "Docs", "open"), _n(2, "button", "Save")],
        [["h", 1], ["t", "Welcome"], ["H"], ["t", "See the "], ["e", 1, 10], ["t", " then "], ["e", 2, 10]],
    )
    v = render_view(snap)
    assert "# Welcome" in v.text
    assert "[1]Docs" in v.text
    assert "[2 button]Save" in v.text
    assert v.shown_refs == [1, 2]


def test_input_select_checkbox_formats():
    assert format_element(_n(3, "input", "Email", "fill", type="email", value="a@b.c")) == '[3 input:email "Email"="a@b.c"]'
    assert format_element(_n(4, "input", "Name", "fill")) == '[4 input "Name"]'
    sel = format_element(_n(5, "select", "Size", "select_option", value="M", options=["S", "M", "L"]))
    assert sel == '[5 select "Size"="M" {S|M|L}]'
    assert format_element(_n(6, "checkbox", "Agree", "toggle", checked=True)) == "[6 checkbox ✓]Agree"
    assert "covered" in format_element(_n(7, "button", "Go", covered=True))
    assert "disabled" in format_element(_n(8, "button", "Go", disabled=True))
    assert "(unlabeled)" in format_element(_n(9, "button", ""))


def test_nav_region_is_collapsed_to_one_line():
    nodes = [_n(i, "link", f"L{i}", "open") for i in range(1, 6)]
    flow = [["r", "nav", "Main"], *[["e", i, 0] for i in range(1, 6)], ["R"], ["t", "Body text"]]
    v = render_view(_snap(nodes, flow))
    assert any(ln.startswith("nav: ") and "[1]L1" in ln and "[5]L5" in ln for ln in v.text.splitlines())
    assert "Body text" in v.text


def test_budget_windows_and_reports_more_below():
    flow = []
    for i in range(200):
        flow += [["b", i * 20], ["t", f"line number {i} with some padding text to take space"]]
    v = render_view(_snap([], flow, scroll={"y": 0, "h": 4000, "vh": 800}), options=ViewOptions(budget=600))
    assert v.more_below and v.pages == 1 and "more below" in v.text
    p2 = render_view(_snap([], flow), options=ViewOptions(budget=600, page=2))
    assert p2.page == 2 and "line number 0 " not in p2.text
    assert p2.all_lines and len(p2.all_lines) == 200  # all_lines is the whole page, for `find`/diffing


def test_blocking_overlay_hides_page_and_names_dismiss_ref():
    nodes = [_n(1, "button", "Accept all"), _n(2, "link", "Pricing", "open")]
    flow = [["t", "Page behind"], ["b", 0], ["r", "layer", "Cookies"], ["t", "We use cookies"], ["e", 1, 5], ["R"], ["e", 2, 50]]
    # mark which lines are in the layer: renderer derives this from the region
    v = render_view(_snap(nodes, flow, layer={"name": "Cookies", "area": 0.5}))
    assert "BLOCKING OVERLAY" in v.text and "dismiss with [1]" in v.text
    assert "Pricing" not in v.text  # the covered page is hidden until the overlay is handled
    assert v.layer_dismiss == [1]
    # escape hatch: all_layers shows everything
    v2 = render_view(_snap(nodes, flow, layer={"name": "Cookies"}), options=ViewOptions(all_layers=True))
    assert "Pricing" in v2.text


def test_empty_page_gives_actionable_hint():
    v = render_view(_snap([], []))
    assert "no visible content" in v.text


def test_duplicate_adjacent_lines_are_collapsed():
    flow = [["b", 0], ["t", "same"], ["b", 1], ["t", "same"], ["b", 2], ["t", "other"]]
    v = render_view(_snap([], flow))
    assert v.text.count("same") == 1
