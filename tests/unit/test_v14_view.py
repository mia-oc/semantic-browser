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


# ---- bot / verification gates (seen live: PyPI "Client Challenge", Hacker News "Sorry", Reddit) -------------------

def _gate(title, text):
    return render_view(_snap([], [["t", text]], title=title)).text


def test_gate_pages_are_flagged_with_the_right_next_step():
    for title, text in [
        ("Client Challenge", "Enter the characters seen in the image below:"),
        ("Just a moment...", "Checking your browser before accessing example.com"),
        ("Reddit - Please wait", "Verify you are human by completing the action below."),
        ("Attention Required! | Cloudflare", "Please complete the security check to access the site"),
        ("Sorry", "We're not able to serve your requests this quickly."),
        ("", "Too many requests. Please slow down."),
    ]:
        out = _gate(title, text)
        assert "! This looks like a bot/verification page" in out, (title, out)
        assert "sb captcha" in out and "do not retry in a loop" in out.lower()


def test_gate_flag_ignores_normal_and_long_pages():
    assert "bot/verification" not in _gate("Weather", "Sunny with a chance of rain. Humans welcome.")
    assert "bot/verification" not in _gate("Sign in", "Email Password This site is protected by reCAPTCHA and the Google Privacy Policy applies.")
    article = "How CAPTCHAs work and why you must verify you are human on some sites. " * 60
    assert len(article) > 2500
    assert "bot/verification" not in _gate("Blog: CAPTCHA history", article)


def test_find_ranks_whole_word_hits_before_substrings():
    from semantic_browser.agent import _rank_hits

    lines = ["82 Commits", "Open commit details", "Version 1 · License: MIT", "Submit", "MIT — see LICENSE."]
    idx, whole = _rank_hits(lines, "mit")
    assert whole == 2
    assert idx[:2] == [2, 4]            # whole-word hits first, in page order
    assert idx[2:] == [0, 1, 3]         # then substrings, in page order
    # nothing whole-word: plain page order, whole == 0
    assert _rank_hits(["alpha beta", "betamax"], "eta") == ([0, 1], 0)
    # regex metacharacters in the query are literal
    assert _rank_hits(["price (£5.69)", "x"], "(£5.69)") == ([0], 1)


def test_collapsed_header_keeps_inputs_recognisable():
    # DuckDuckGo: the search box lives in <header>; it must not look like a link
    nodes = [_n(1, "link", "Logo", "open"), _n(2, "input", "Search with DuckDuckGo", "fill"), _n(3, "button", "Search")]
    flow = [["r", "header", ""], ["e", 1, 0], ["e", 2, 0], ["e", 3, 0], ["R"], ["t", "Body"]]
    out = render_view(_snap(nodes, flow)).text
    assert '[2 input "Search with DuckDuckGo"]' in out
    assert "[1]Logo" in out


def test_collapsing_never_drops_a_fillable_control_past_the_cap():
    nodes = [_n(i, "link", f"L{i}", "open") for i in range(1, 21)]
    nodes.append(_n(21, "input", "Site search", "fill"))
    nodes.append(_n(22, "select", "Language", "select_option", value="EN", options=["EN", "FR"]))
    flow = [["r", "nav", "Main"], *[["e", n["ref"], 0] for n in nodes], ["R"], ["t", "Body"]]
    v = render_view(_snap(nodes, flow))
    line = next(ln for ln in v.text.splitlines() if ln.startswith("nav: "))
    assert '[21 input "Site search"]' in line and '[22 select "Language"="EN" {EN|FR}]' in line
    assert "[1]L1" in line and "more" in line
    assert 21 in v.shown_refs and 22 in v.shown_refs


def _long_page(covered: bool):
    nodes = [_n(i, "link", f"Menu item {i}", "open", **({"covered": True} if covered else {})) for i in range(1, 9)]
    filler = ["Learn more about our browser and products. " * 30]
    flow = [["t", filler[0]]] + [["e", n["ref"], 0] for n in nodes] + [
        ["t", "Unfortunately, bots use DuckDuckGo too. Please complete the following challenge to confirm this search was made by a human."]
    ]
    return render_view(_snap(nodes, flow, title="python release at DuckDuckGo")).text


def test_gate_on_long_page_needs_the_page_to_be_covered():
    # DuckDuckGo's anomaly modal: lots of page text, but a mask covers every control
    assert "bot/verification" in _long_page(covered=True)
    # the same sentence on a page whose controls are usable (e.g. a blog quoting it) is not a gate
    assert "bot/verification" not in _long_page(covered=False)


def test_find_adds_the_previous_line_to_short_hits():
    from semantic_browser.agent import _hit_text

    lines = ["[1165]Under the Tuscan Sun", "£37.33", "In stock", "A long sentence that mentions £37.33 inside plenty of other words so it stands alone fine"]
    assert _hit_text(lines, 1, "£") == "[1165]Under the Tuscan Sun | £37.33"
    assert "Under the Tuscan" not in _hit_text(lines, 3, "£")      # long hits stand alone
    assert _hit_text(lines, 0, "tuscan") == "[1165]Under the Tuscan Sun"
    assert _hit_text(["£1", "£2"], 1, "£") == "£2"                 # previous line that is itself a hit is not repeated


def test_duplicate_label_context_is_shown_in_the_view():
    node = _n(15, "button", "Add to cart", "click", ctx="Sauce Labs Backpack")
    assert format_element(node) == "[15 button]Add to cart — Sauce Labs Backpack"
    assert format_element({**node, "ctx": "x" * 80}).endswith("— " + "x" * 39 + "…")
    assert format_element(_n(1, "button", "Save")) == "[1 button]Save"          # no ctx: unchanged
    assert format_element(_n(2, "link", "Docs", "open", ctx="Footer")) == "[2]Docs — Footer"


def test_link_context_only_when_the_duplicates_go_to_different_places():
    same = [_n(1, "link", "View details", "open", ctx="Backpack", href="/p/1"), _n(2, "link", "View details", "open", ctx="Backpack", href="/p/1")]
    out = render_view(_snap(same, [["e", 1, 0], ["t", " "], ["e", 2, 0]])).text
    assert "—" not in out.split("\n", 1)[1]                      # same destination: context is noise
    diff = [_n(1, "link", "Read more", "open", ctx="Anvils", href="/a"), _n(2, "link", "Read more", "open", ctx="Hammers", href="/h")]
    out2 = render_view(_snap(diff, [["e", 1, 0], ["t", " "], ["e", 2, 0]])).text
    assert "Read more — Anvils" in out2 and "Read more — Hammers" in out2
    btn = [_n(1, "button", "Add", ctx="Anvils"), _n(2, "button", "Add", ctx="Hammers")]
    out3 = render_view(_snap(btn, [["e", 1, 0], ["t", " "], ["e", 2, 0]])).text
    assert "Add — Anvils" in out3 and "Add — Hammers" in out3     # buttons have no destination: always show


def test_collapsed_footer_keeps_short_status_text_with_numbers():
    """A collapsed footer must not swallow live data ("1 item left", "Showing 1-10 of 94") but may drop boilerplate."""
    nodes = [_n(1, "link", "All", "open"), _n(2, "link", "Active", "open")]
    flow = [
        ["r", "footer", ""], ["b", 0], ["t", "1 item left!"], ["b", 1], ["e", 1, 2], ["t", " "], ["e", 2, 2], ["b", 3],
        ["t", "© 2026 Acme Inc. All rights reserved."], ["b", 4], ["t", "Created by the Acme team"], ["R"], ["t", "Body"],
    ]
    v = render_view(_snap(nodes, flow))
    footer = next(ln for ln in v.text.splitlines() if ln.startswith("footer:"))
    assert "1 item left!" in footer and "[1]All" in footer and "[2]Active" in footer
    assert "©" not in v.text and "Created by" not in v.text


def test_find_still_sees_text_inside_collapsed_regions():
    nodes = [_n(1, "link", "All", "open")]
    flow = [["r", "footer", ""], ["b", 0], ["e", 1, 2], ["b", 3], ["t", "© 2026 Acme Inc. All rights reserved."], ["b", 4], ["t", "Created by the Acme team"], ["R"], ["t", "Body"]]
    v = render_view(_snap(nodes, flow))
    assert "Created by" not in v.text                                     # the view stays compact
    assert any("Created by the Acme team" in ln for ln in v.all_lines)    # but `find` searches everything
    assert len(v.all_lines) == len(v.header_rows)                         # the parallel list stays aligned


def test_overlay_nested_in_a_collapsed_header_is_not_swallowed():
    """MDN: the search modal lives inside <header>; collapsing the header must not fold the modal's input into its link list."""
    nodes = [_n(1, "link", "Docs", "open"), _n(2, "link", "Blog", "open"), _n(3, "input", "Search", "fill", type="search")]
    flow = [
        ["r", "header", ""], ["e", 1, 0], ["e", 2, 0],
        ["r", "layer", "Search"], ["b", 20], ["e", 3, 20], ["R"],
        ["R"], ["t", "Body text"],
    ]
    v = render_view(_snap(nodes, flow, layer={"name": "Search", "area": 0.05}))
    assert "BLOCKING OVERLAY" in v.text and '[3 input:search "Search"]' in v.text
    assert "dismiss" in v.text or "Search" in v.text
    v2 = render_view(_snap(nodes, flow, layer={"name": "Search", "area": 0.05}), options=ViewOptions(all_layers=True))
    assert "header: [1]Docs [2]Blog" in v2.text           # the header still collapses...
    assert '[3 input:search "Search"]' in v2.text.split("header:")[1].split("\n", 1)[1]  # ...but the modal keeps its own line
