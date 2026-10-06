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
