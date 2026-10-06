"""v1.4 engine against deterministic local fixtures (no network): the 'hard web patterns' regression suite."""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "dogfood"))
from fixtures import FixtureServer  # noqa: E402

from semantic_browser.agent import AgentSession  # noqa: E402

pytestmark = pytest.mark.asyncio

PARIS, DAY17, SETTINGS, ANVILS = r"^\s*Paris", r"^\s*17\s*$", r"^\s*Settings", r"^\s*Anvils"


@pytest.fixture(scope="module")
def site():
    srv = FixtureServer().start()
    yield srv.base
    srv.stop()


@pytest_asyncio.fixture()
async def sb(monkeypatch):
    home = Path(tempfile.mkdtemp(prefix="sbi", dir="/tmp"))
    monkeypatch.setenv("SB_HOME", str(home))  # captcha images / screenshots land in a throwaway dir
    try:
        s = await AgentSession.launch(headful=False)
    except Exception as exc:  # no browser installed on this machine
        if "Executable doesn't exist" in str(exc) or "playwright install" in str(exc):
            pytest.skip(f"chromium not installed: {exc}")
        raise
    yield s
    await s.close()
    shutil.rmtree(home, ignore_errors=True)


def ref_of(view: str, label: str, nth: int = 0) -> str:
    """The [n] number whose element matches `label` (what a model does by eye).

    Inputs/selects carry their label inside the brackets (`[3 input "Email"]`); links/buttons right after (`[3]Docs`).
    """
    hits = []
    for m in re.finditer(r"\[(\d+)((?: [^\]]*)?)\]([^\[\n|]*)", view):
        inner, after = m.group(2), m.group(3).strip()
        text = inner if '"' in inner else after
        if re.search(label, text, re.I):
            hits.append(m.group(1))
    assert len(hits) > nth, f"no [{label}] #{nth} in view:\n{view}"
    return hits[nth]


async def title(sb: AgentSession) -> str:
    return await sb.runtime.page.title()


async def test_duplicate_buttons_are_disambiguated_by_context(sb, site):
    v = await sb.run(f"goto {site}/shop")
    assert v.count("Add to basket") >= 6
    assert "Blue Mug" in v
    # the model picks the Blue Mug's button using whatever context the view gives it
    out = await sb.run(f"click {_blue_mug_button(v)}")
    assert await title(sb) == "basket:Blue Mug", out


def _blue_mug_button(view: str) -> str:
    """Reading order gives the context: heading, price, then that product's button."""
    m = re.search(r"Blue Mug\n[^\n]*\n\[(\d+) button[^\]]*\]Add to basket", view)
    assert m, f"no Blue Mug button in:\n{view}"
    return m.group(1)


async def test_blocking_overlay_is_announced_and_blocks_clicks_clearly(sb, site):
    v = await sb.run(f"goto {site}/cookie")
    assert "BLOCKING OVERLAY" in v
    accept = ref_of(v, "Accept all")
    assert f"dismiss with [{accept}]" in v or "Accept all" in v
    out = await sb.run(f"click {accept}")
    assert "BLOCKING OVERLAY" not in out
    pricing = ref_of(out, r"^\s*Pricing")
    out = await sb.run(f"click {pricing}")
    assert await title(sb) == "Pricing", out


async def test_shadow_dom_and_custom_elements(sb, site):
    v = await sb.run(f"goto {site}/shadow")
    await sb.run(f'type {ref_of(v, "Username")} matt')
    await sb.run(f'type {ref_of(v, "Password")} hunter2')
    await sb.run(f"click {ref_of(v, 'Sign in')}")
    assert await title(sb) == "welcome:matt"


async def test_cross_origin_iframe_content_is_visible_and_usable(sb, site):
    v = await sb.run(f"goto {site}/iframe")
    assert "Card number" in v
    await sb.run(f'type {ref_of(v, "Card number")} 4242')
    await sb.run(f"click {ref_of(v, 'Pay now')}")
    assert await title(sb) == "paid:4242"


async def test_div_widgets_and_calendar_cells_are_clickable(sb, site):
    v = await sb.run(f"goto {site}/dropdown")
    v = await sb.run(f"click {ref_of(v, 'Destination|Choose')}")
    v = await sb.run(f"click {ref_of(v, PARIS)}")
    v = await sb.run(f"click {ref_of(v, DAY17)}")
    await sb.run(f"click {ref_of(v, 'Search trips')}")
    assert await title(sb) == "trip:Paris:17"


async def test_spa_navigation_and_delayed_render(sb, site):
    v = await sb.run(f"goto {site}/spa/home")
    v = await sb.run(f"click {ref_of(v, SETTINGS)}")
    assert "Display name" in v, "settle must wait for the delayed SPA render"
    v = await sb.run(f"type {ref_of(v, 'Display name')} Zed")
    await sb.run(f"click {ref_of(v, 'Save settings')}")
    assert await title(sb) == "saved:Zed"


async def test_js_rendered_results_then_find_uses_live_page(sb, site):
    v = await sb.run(f"goto {site}/search")
    out = await sb.run(f"type {ref_of(v, 'Search catalogue')} anvil --enter")
    assert "24.99" in out, "results render 300ms after submit; the grace wait must catch them"
    found = await sb.run("find 24.99")
    assert "Anvil Mini" in found
    out = await sb.run(f"click {ref_of(found, 'Anvil Mini')}")
    assert await title(sb) == "item-opened", out


async def test_lazy_feed_needs_scroll_and_reports_more_below(sb, site):
    v = await sb.run(f"goto {site}/lazy")
    assert "Open item 35" not in v, "only the first screenful is rendered until the page is scrolled"
    for _ in range(12):
        if "Open item 35" in v:
            break
        v = await sb.run("scroll down")
    assert "Open item 35" in v


async def test_hover_menu(sb, site):
    v = await sb.run(f"goto {site}/hover")
    v = await sb.run(f"hover {ref_of(v, 'Products')}")
    await sb.run(f"click {ref_of(v, ANVILS)}")
    assert await title(sb) == "anvils-page"


async def test_bad_refs_fail_loudly_with_recovery_hint(sb, site):
    await sb.run(f"goto {site}/shop")
    out = await sb.run("click 9999")
    assert out.startswith("INVALID") and "view" in out
    assert (await sb.run("click banana")).startswith("ERROR")
    assert (await sb.run("frobnicate")).startswith("ERROR: unknown verb")


async def test_stale_ref_after_navigation_is_not_silently_retargeted(sb, site):
    v = await sb.run(f"goto {site}/cookie")
    old = ref_of(v, "Accept all")
    await sb.run(f"goto {site}/shop")
    out = await sb.run(f"click {old}")
    assert out.split(":")[0] in {"INVALID", "STALE", "FAILED", "ERROR"} or "not found" in out, out
    assert await title(sb) != "basket:Blue Mug"


async def test_captcha_grid_end_to_end(sb, site):
    await sb.run(f"goto {site}/captcha")
    out = await sb.run("captcha --pdf")
    assert "kind=grid" in out and "grid=3x3" in out and "red circle" in out
    png = Path(re.search(r"Image: (\S+)", out).group(1))
    pdf = Path(re.search(r"PDF: (\S+)", out).group(1))
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and pdf.read_bytes().startswith(b"%PDF")
    assert (await sb.run("captcha select 1 5 9")).startswith("clicked tile(s) [1, 5, 9]")
    await sb.run("captcha submit")
    assert await title(sb) == "captcha-solved"
    # wrong answer path: the failure is visible to the caller instead of silently 'succeeding'
    await sb.run(f"goto {site}/captcha")
    await sb.run("captcha")
    await sb.run("captcha select 2")
    out = await sb.run("captcha submit")
    assert await title(sb) == "captcha-failed" and "captcha-failed" in out


async def test_dynamic_captcha_grid_is_reported_after_tiles_settle(sb, site):
    """reCAPTCHA 'none left' grids swap the picked tiles for new images shortly after Verify: show the NEW state."""
    await sb.run(f"goto {site}/captcha_dynamic")
    await sb.run("captcha")
    await sb.run("captcha select 1 3")
    out = await sb.run("captcha submit")
    gens = await sb.runtime.page.evaluate("[...document.querySelectorAll('.tile')].map(t => t.dataset.gen)")
    assert gens[0] == "1" and gens[2] == "1", f"the image was taken before the tiles were replaced: {gens}"
    assert "dynamic" in out.lower() and "replaced" in out.lower(), out  # explains why 'same challenge' is not necessarily an error


async def test_no_captcha_is_reported_plainly(sb, site):
    await sb.run(f"goto {site}/shop")
    assert (await sb.run("captcha")).startswith("No CAPTCHA detected")


async def test_screenshot_with_ref_marks(sb, site, tmp_path):
    await sb.run(f"goto {site}/shop")
    target = tmp_path / "s.png"
    out = await sb.run(f"shot --marks {target}")
    assert target.read_bytes()[:4] == b"\x89PNG" and "[n] boxes" in out
    # marks are removed afterwards so they never pollute the page the model reads
    assert await sb.runtime.page.evaluate("!document.getElementById('__sb_marks')")


async def test_view_pages_and_back_forward_tabs(sb, site):
    await sb.run(f"goto {site}/lazy")
    assert "screen" in (await sb.run("view --page 1"))
    await sb.run(f"goto {site}/shop")
    assert not (await sb.run("back")).startswith("ERROR")
    assert (await sb.run("tabs")).strip()


async def test_lite_mode_blocks_images_but_keeps_text(site, monkeypatch):
    home = Path(tempfile.mkdtemp(prefix="sbl", dir="/tmp"))
    monkeypatch.setenv("SB_HOME", str(home))
    try:
        s = await AgentSession.launch(headful=False, lite="media")
    except Exception as exc:
        if "Executable doesn't exist" in str(exc) or "playwright install" in str(exc):
            pytest.skip(f"chromium not installed: {exc}")
        raise
    try:
        out = await s.run(f"goto {site}/shop")
        assert "Add to basket" in out
        assert s.runtime._lite_sessions, "blocking should be active"
        await s.run("captcha")  # captcha verb lifts lite blocking for the session
        assert not s.runtime._lite_sessions
    finally:
        await s.close()
        shutil.rmtree(home, ignore_errors=True)


async def test_secret_fields_are_masked_in_the_view(sb):
    """Passwords, card numbers and one-time codes must never be echoed back into the model's context."""
    page = sb.runtime.page
    await page.set_content(
        '<input id=u aria-label="User" value="alice">'
        '<input id=p type=password aria-label="Pass" value="hunter2-secret">'
        '<input id=c aria-label="Card" autocomplete="cc-number" value="4111111111111111">'
        '<input id=o aria-label="Code" autocomplete="one-time-code" value="987654">'
    )
    out = await sb.run("view")
    assert "alice" in out
    for secret in ("hunter2-secret", "4111111111111111", "987654"):
        assert secret not in out


async def test_label_targets_work_when_unique_and_list_candidates_when_not(sb):
    await sb.runtime.page.set_content(
        "<title>start</title>"
        "<button onclick=\"document.title='saved'\">Save</button>"
        "<button>Cancel</button><button>Cancel</button>"
    )
    await sb.run("view")
    out = await sb.run('click "Cancel"')  # two of them: must not guess
    assert out.startswith("ERROR") and "2 elements match" in out and "[" in out
    assert (await sb.run('click "no such thing anywhere"')).startswith("ERROR: no element labelled")
    assert await title(sb) == "start"
    await sb.run('click "save"')  # unique, case-insensitive -> acts
    assert await title(sb) == "saved"


async def test_submit_button_named_like_captcha_is_not_a_text_challenge(sb):
    """Regression from Google's reCAPTCHA demo page: <input type=submit id=recaptcha-demo-submit> is not an answer box."""
    await sb.runtime.page.set_content(
        '<form><input type=text aria-label="Name"><input type=submit id="recaptcha-demo-submit" value="Submit"></form>'
    )
    await sb.run("view")
    assert (await sb.run("captcha")).startswith("No CAPTCHA detected")


async def test_view_expand_unfolds_the_collapsed_nav_the_view_advertises(sb):
    """The view says `(+N more: view --expand nav)`; that command must exist and show every link."""
    links = "".join(f'<a href="#p{i}">Section{i}</a>' for i in range(30))
    await sb.runtime.page.set_content(f"<nav>{links}</nav><main><h1>Body</h1><p>text</p></main>")
    out = await sb.run("view")
    assert "view --expand nav" in out and "Section29" not in out
    full = await sb.run("view --expand nav")
    assert "Section29" in full and "view --expand nav" not in full


def _split_price(offscreen_css: str) -> str:
    """Amazon: the visual price hides the decimal point; the real '£5.69' sits in an off-screen accessible span."""
    return (
        f"<style>.a-offscreen{{{offscreen_css}}}.a-price-decimal{{display:block;position:absolute;opacity:0}}.a-price-whole{{font-size:28px}}</style>"
        '<span class="a-price"><span class="a-offscreen">£5.69</span><span aria-hidden="true">'
        '<span class="a-price-symbol">£</span><span class="a-price-whole">5<span class="a-price-decimal">.</span></span>'
        '<span class="a-price-fraction">69</span></span></span>'
    )


@pytest.mark.parametrize(
    "offscreen_css",
    [
        "position:absolute;left:-10000px",
        "position:absolute;clip:rect(0 0 0 0);width:1px;height:1px;overflow:hidden",
        "position:absolute;display:block;opacity:0",  # what amazon.co.uk really does: on-screen, just transparent
    ],
)
async def test_split_price_markup_keeps_its_decimal_point(sb, offscreen_css):
    """Regression from Amazon: '£5.69' was shown as '£569' (a wrong price is worse than no price)."""
    await sb.runtime.page.set_content(f"<a href='#p'>USB cable {_split_price(offscreen_css)}</a><p>Total {_split_price(offscreen_css)}</p>")
    out = await sb.run("view")
    assert "£569" not in out, out
    assert out.count("£5.69") == 2 and "£5.69£5.69" not in out, out  # once per product, never doubled


async def test_skip_links_and_unrelated_sr_only_text_are_still_hidden(sb):
    await sb.runtime.page.set_content(
        '<span style="position:absolute;opacity:0">Ghost text nobody sees</span>'
        '<a style="position:absolute;left:-10000px" href="#m">Skip to main content</a><h1>Shop</h1>'
        '<span style="position:absolute;left:-10000px">Opens in a new window</span><p>Hello</p>'
    )
    out = await sb.run("view")
    assert "Skip to main" not in out and "Opens in a new window" not in out and "Ghost text" not in out and "Hello" in out


async def test_view_all_shows_page_behind_overlay_and_find_still_sees_it(sb, site):
    v = await sb.run(f"goto {site}/cookie")
    assert "BLOCKING OVERLAY" in v and "Pricing" not in v
    assert "view --all" in v  # the output advertises it...
    behind = await sb.run("view --all")  # ...so it must work
    assert "Pricing" in behind
    found = await sb.run("find Pricing")
    assert "Pricing" in found and "no match" not in found.lower()


async def test_unknown_view_option_fails_loudly(sb):
    await sb.runtime.page.set_content("<p>x</p>")
    out = await sb.run("view --bogus")
    assert out.startswith("ERROR: unknown option --bogus") and "--all" in out, out


async def test_stretched_link_card_is_not_reported_as_covered(sb):
    """Cards often overlay a same-href <a> over the title link; the title is clickable, so it must not say 'covered'."""
    await sb.runtime.page.set_content(
        "<div style='position:relative;width:300px;height:80px'><h3><a href='#p'>Blue widget</a></h3><p>£4</p>"
        "<a href='#p' aria-label='Blue widget' style='position:absolute;inset:0'></a></div>"
        "<div style='position:relative;width:200px;height:40px;margin-top:20px'><button>Real target</button>"
        "<div style='position:absolute;inset:0;background:rgba(0,0,0,.01)'></div></div>"
    )
    out = await sb.run("view")
    assert "Blue widget" in out
    line = next(ln for ln in out.splitlines() if "Blue widget" in ln)
    assert "covered" not in line, out
    assert "covered" in next(ln for ln in out.splitlines() if "Real target" in ln), out  # genuine occlusion still flagged


async def test_find_centres_long_lines_and_gives_table_column_context(sb):
    filler = "lorem ipsum dolor sit amet " * 30
    await sb.runtime.page.set_content(
        f"<p>{filler} NEEDLE-ONE {filler}</p>"
        "<table><tr><th>Team</th><th>Played</th><th>Points</th></tr>"
        "<tr><td>Arsenal</td><td>8</td><td>19</td></tr><tr><td>Chelsea</td><td>8</td><td>14</td></tr></table>"
    )
    out = await sb.run("find NEEDLE-ONE")
    assert "NEEDLE-ONE" in out, out  # the match itself must be inside the snippet, not cut off
    out = await sb.run("find Chelsea")
    assert "Chelsea" in out and "Points" in out, out  # header row tells you which number is which


FORM_PAGE = (
    "<input id=q placeholder='Search'><button onclick=\"document.getElementById('out').textContent='Result for '+"
    "document.getElementById('q').value\">Go</button><p id=out></p><div style='height:3000px'>tall</div>"
)


async def test_do_runs_a_sequence_and_stops_at_the_first_failure(sb):
    await sb.runtime.page.set_content(FORM_PAGE)
    v = await sb.run("view")
    q, go = ref_of(v, "Search"), ref_of(v, r"button\]Go|Go")
    out = await sb.run(["do", f'type {q} "boots"', f"click {go}", "view"])
    assert "Result for boots" in out, out
    assert out.count("@ (untitled)") == 1, "only the last step prints a full view"  # intermediate steps are one-liners
    assert "1." in out and "3." in out  # numbered steps

    out = await sb.run(["do", "click 9999", "type 1 never-runs"])
    assert "stopped at step 1 of 2" in out and "never-runs" not in out, out


async def test_scroll_accepts_a_count(sb):
    await sb.runtime.page.set_content(FORM_PAGE)
    await sb.run("view")
    out = await sb.run("scroll down 2")
    assert not out.startswith("ERROR"), out
    y = await sb.runtime.page.evaluate("window.scrollY")
    one = await sb.runtime.page.evaluate("window.innerHeight")
    assert y > one * 0.9, (y, one)  # moved at least about a screen; two steps beat one


async def test_label_target_with_same_destination_duplicates_just_works(sb):
    """Seen on theguardian.com: three 'Sport' links (nav, menu, footer) all going to /sport. That is not ambiguous."""
    await sb.runtime.page.set_content(
        "<a href='#sport'>Sport</a><a href='#sport'>Sport</a><a href='#tech'>Tech</a><a href='#a'>More</a><a href='#b'>More</a>"
    )
    await sb.run("view")
    out = await sb.run("click Sport")
    assert not out.startswith("ERROR"), out
    assert "#sport" in sb.runtime.page.url
    out = await sb.run("click More")  # different destinations: still asks which, and shows where each goes
    assert out.startswith("ERROR") and "2 elements match" in out and "#a" in out and "#b" in out, out


async def test_find_never_invents_table_columns_when_there_is_no_header_row(sb):
    await sb.runtime.page.set_content(
        "<table><tr><td>World</td><td>126</td><td>118</td></tr><tr><td>Japan</td><td>4.3</td><td>4.4</td></tr></table>"
        "<table><thead><tr><th>Country</th><th>IMF</th><th>UN</th></tr></thead>"
        "<tr><td>Chad</td><td>1</td><td>2</td></tr><tr><td>Fiji</td><td>3</td><td>4</td></tr></table>"
    )
    out = await sb.run("find Japan")
    assert "Japan" in out and "columns" not in out, out  # no <th>: say nothing rather than mislabel with the 'World' row
    out = await sb.run("find Fiji")
    assert "columns: Country | IMF | UN" in out, out


async def test_delegated_handler_widgets_get_refs_and_work(sb):
    """jQuery UI datepicker Prev/Next: <a data-handler=next data-event=click> with no href/role and cursor:auto."""
    await sb.runtime.page.set_content(
        "<div id=cal><a data-handler='prev' data-event='click' title='Prev'><span>Prev</span></a>"
        "<a data-handler='next' data-event='click' title='Next'><span>Next</span></a><b id=month>October</b></div>"
        "<span data-bs-toggle='dropdown'>Options</span><span data-event='pageview'>tracking only</span>"
        "<script>document.getElementById('cal').addEventListener('click',e=>{const a=e.target.closest('[data-handler]');"
        "if(a)document.getElementById('month').textContent=a.dataset.handler==='next'?'November':'September'})</script>"
    )
    out = await sb.run("view")
    nxt = ref_of(out, r"Next")
    assert re.search(r"\[\d+[^\]]*\]Prev", out) and re.search(r"\[\d+[^\]]*\]Options", out), out
    assert not re.search(r"\[\d+[^\]]*\]tracking only", out), out  # a bare analytics attribute is not a control
    out = await sb.run(f"click {nxt}")
    assert "November" in out, out


async def test_delegating_wrapper_around_one_control_is_not_a_second_control(sb):
    await sb.runtime.page.set_content(
        "<table><tr><td data-handler='selectDay' data-event='click'><a href='#d1'>1</a></td>"
        "<td data-handler='selectDay' data-event='click'><a href='#d2'>2</a></td></tr></table>"
    )
    out = await sb.run("view")
    assert out.count("1") >= 1 and not re.search(r"\[\d+\]1 \[\d+[^\]]*\]1|\[\d+ button\]1", out), out
    assert len(re.findall(r"\[\d+", out)) == 2, out  # exactly one ref per day


GOVUK_RADIOS = (
    "<style>.r{position:relative;min-height:44px;padding-left:44px}.r input{position:absolute;left:0;top:0;width:44px;height:44px;"
    "margin:0;opacity:0;z-index:1;cursor:pointer}.r label{display:block;padding:8px}</style>"
    "<h1>Are you a dual citizen?</h1>"
    "<div class=r><input type=radio id=y name=d value=yes><label for=y>Yes</label></div>"
    "<div class=r><input type=radio id=n name=d value=no><label for=n>No</label></div>"
    "<div class=r><input type=checkbox id=c><label for=c>Remember me</label></div><button>Continue</button>"
)


async def test_opacity_zero_radios_and_checkboxes_over_their_labels_are_usable(sb):
    """GOV.UK design system: the real input is transparent and sits on top of its label. It must still get a ref."""
    await sb.runtime.page.set_content(GOVUK_RADIOS)
    out = await sb.run("view")
    assert re.search(r"\[\d+ radio\]Yes", out) and "[3 checkbox]Remember me" in out, out
    assert out.count("Yes") == 1 and out.count("Remember me") == 1, out  # the label is not repeated after its own control
    yes = ref_of(out, "Yes")
    out = await sb.run(f"check {yes}")
    assert not out.startswith(("ERROR", "FAILED")), out
    assert await sb.runtime.page.evaluate("document.getElementById('y').checked") is True
    box = ref_of(await sb.run("view"), "Remember me")
    await sb.run(f"check {box}")
    assert await sb.runtime.page.evaluate("document.getElementById('c').checked") is True


async def test_title_only_change_is_reported_as_the_effect(sb):
    """A click whose only visible effect is document.title (the success signal on many forms) must say so."""
    await sb.runtime.page.set_content("<button onclick=\"document.title='saved:Zed'\">Save settings</button>")
    await sb.run("view")
    out = await sb.run("click Save settings")  # unquoted multi-word label
    assert "saved:Zed" in out.splitlines()[0] and "no visible change" not in out, out


async def test_hung_blocking_script_does_not_stall_goto(sb, site):
    """the-internet.herokuapp.com: HTML arrives instantly, a blocking script hangs for ages. Return what rendered, fast."""
    import time

    t0 = time.perf_counter()
    out = await sb.run(f"goto {site}/hung_script")
    took = time.perf_counter() - t0
    assert took < 10, f"goto waited {took:.1f}s on a hung subresource"
    assert "[1 button]Start" in out, out
    assert "still loading" in out.lower(), out
    clicked = await sb.run("click Start")
    assert "Hello World!" in clicked, clicked


async def test_stalled_head_script_is_skipped_so_the_body_renders(sb, site):
    """A blocking <head> script that never arrives hides the whole body. After the grace, skip it and reload."""
    import time

    t0 = time.perf_counter()
    out = await sb.run(f"goto {site}/hung_head")
    took = time.perf_counter() - t0
    assert took < 14, f"goto took {took:.1f}s"
    assert "[1 button]Start" in out, out
    assert "skipped" in out.lower() and "hang.js" in out, out
    assert "Hello World!" in await sb.run("click Start")


async def test_stalled_asset_is_retried_individually_not_thrown_away(sb, site):
    """A jammed connection pool stalls good assets too (the-internet.herokuapp.com): retry each, keep what arrives."""
    import time

    import fixtures

    fixtures.FLAKY_HITS["n"] = 0
    t0 = time.perf_counter()
    out = await sb.run(f"goto {site}/flaky_head")
    assert time.perf_counter() - t0 < 14, out
    assert "[1 button]Start" in out, out
    assert "skipped" not in out.lower(), f"the retry succeeded, nothing should be reported as skipped: {out}"
    assert "Hello World!" in await sb.run("click Start"), "the retried script must have run"


async def test_identical_buttons_say_which_card_they_belong_to(sb, site):
    """saucedemo: six 'Add to cart' buttons; the view must tell them apart, concisely and without doubled words."""
    out = await sb.run(f"goto {site}/cards")
    assert "Add to cart — Sauce Backpack" in out and "Add to cart — Bike Light" in out and "Add to cart — Bolt T-Shirt" in out, out
    assert "Sauce Backpack Sauce Backpack" not in out, out
    line = next(ln for ln in out.splitlines() if "Add to cart — Sauce Backpack" in ln)
    assert "carry all" not in line, f"context should be the card's name, not its whole text: {line}"
    clicked = await sb.run('click "Add to cart — Bike Light"')
    assert not clicked.startswith("ERROR"), clicked


async def test_label_prefers_the_control_that_starts_with_it(sb, site):
    """`click Cart` must pick "Cart, 2 items", not the three "Add to cart — …" buttons that merely contain the word."""
    await sb.run(f"goto {site}/cards")
    out = await sb.run("click Cart")
    assert not out.startswith("ERROR"), out
    assert "Your cart" in out, out
    await sb.run(f"goto {site}/cards")
    amb = await sb.run("click Add")                      # genuinely ambiguous: still an error that lists the candidates
    assert amb.startswith("ERROR") and "3 elements match" in amb, amb
