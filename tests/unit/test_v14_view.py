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


def _overlay(nodes, extra_flow=()):
    flow = [["t", "Page behind"], ["b", 0], ["r", "layer", "Dialog"], ["t", "Some dialog text"]]
    flow += [["e", n["ref"], 5] for n in nodes] + [["R"], ["e", 99, 50]]
    return render_view(_snap([*nodes, _n(99, "link", "Pricing", "open")], flow, layer={"name": "Dialog"}))


def test_dismiss_hint_prefers_close_over_continue_and_never_suggests_sign_in_or_donations():
    """Seen live: 'Continue' (donation flow) and 'Continue with Phone Number' (login) were suggested as 'dismiss'."""
    v = _overlay([_n(1, "button", "Continue"), _n(2, "button", "Collapse banner"), _n(3, "button", "Continue with Phone Number")])
    assert "dismiss with [2]" in v.text and v.layer_dismiss[0] == 2
    v = _overlay([_n(1, "button", "Log in"), _n(2, "button", "Continue with Google"), _n(3, "button", "Subscribe now")])
    assert "dismiss with" not in v.text and v.layer_dismiss == []
    assert "no obvious dismiss control" in v.text and "[1]" in v.text  # lists what *is* there instead of guessing


def test_dismiss_hint_prefers_reject_then_short_accept_and_skips_pay_to_reject_buttons():
    v = _overlay([_n(1, "button", "Accept personalised advertising and all cookies"), _n(2, "button", "Accept all"),
                  _n(3, "button", "Reject all and subscribe for £5 per month")])
    assert v.layer_dismiss[0] == 2  # short accept beats a long sentence; the paid option is never a "dismiss"
    v = _overlay([_n(1, "button", "Accept all"), _n(2, "button", "Reject all")])
    assert v.layer_dismiss[0] == 2  # privacy-preserving choice first


def test_find_text_still_contains_the_whole_page_while_an_overlay_is_active():
    v = _overlay([_n(1, "button", "Accept all")])
    assert "Pricing" not in v.text
    assert any("Pricing" in ln for ln in v.all_lines)  # `find` must not go blind behind a banner


def test_repeat_links_to_the_same_place_are_folded_but_different_targets_are_not():
    nodes = [_n(1, "link", "Blue widget", "open", href="/p/1"), _n(2, "link", "Blue widget", "open", href="/p/1"),
             _n(3, "link", "", "open", href="/p/1"), _n(4, "link", "Blue widget", "open", href="/p/2")]
    flow = [["b", 0], ["e", 1, 0], ["b", 10], ["e", 2, 10], ["b", 20], ["e", 3, 20], ["b", 30], ["e", 4, 30]]
    v = render_view(_snap(nodes, flow))
    assert "[1]Blue widget" in v.text and "[4]Blue widget" in v.text
    assert "[2]" not in v.text and "[3" not in v.text


def test_blank_table_cells_keep_their_column_position_in_data_tables_only():
    # data table (has <th>): <tr><td></td><td>A</td><td></td><td>C</td></tr>
    d = ["c", "d"]
    flow = [["b", 0], d, d, ["t", "A"], d, d, ["t", "C"], ["b", 10], d, ["t", "1"], d, ["t", "2"]]
    text = render_view(_snap([], flow)).text
    assert "· | A | · | C" in text, text
    assert "1 | 2" in text
    # layout table (no <th>, e.g. Hacker News spacer cells): no placeholders, no noise
    layout = render_view(_snap([], [["b", 0], ["c"], ["c"], ["t", "1215 points"], ["c"], ["t", "hide"]])).text
    assert "·" not in layout and "1215 points | hide" in layout, layout


def test_label_text_repeated_after_its_own_toggle_is_not_printed_twice():
    nodes = [_n(1, "radio", "Yes", "toggle", checked=False), _n(2, "checkbox", "Remember me", "toggle"), _n(3, "radio", "No", "toggle")]
    flow = [["b", 0], ["e", 1, 0], ["b", 0], ["t", "Yes"], ["b", 10], ["e", 2, 10], ["t", "Remember me"], ["b", 20], ["e", 3, 20],
            ["t", "No thanks, really"]]
    v = render_view(_snap(nodes, flow)).text
    assert v.count("Yes") == 1 and v.count("Remember me") == 1
    assert "No thanks, really" in v  # different text is kept


def test_unlabeled_links_show_where_they_go():
    assert format_element(_n(5, "link", "", "open", href="/dp/B07DD5YHMH/ref=sr_1_1?dib=abc")) == "[5](unlabeled → /dp/B07DD5YHMH/ref=sr_1_1)"
    assert format_element(_n(6, "link", "", "open", href="https://shop.example.com/cart?x=1")) == "[6](unlabeled → shop.example.com/cart)"
    assert format_element(_n(7, "link", "", "open", href="#")) == "[7](unlabeled)"
    assert format_element(_n(8, "link", "Docs", "open", href="/docs")) == "[8]Docs"  # labelled links are unchanged
    assert format_element(_n(9, "button", "")) == "[9 button](unlabeled)"
