"""Canvas CAPTCHAs (drag-the-piece, click-the-squares) against local fixtures: sanctioned, deterministic, no network."""

from __future__ import annotations

import shutil
import struct
import sys
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "dogfood"))
from fixtures import FixtureServer  # noqa: E402

from semantic_browser.agent import AgentSession  # noqa: E402

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def site():
    srv = FixtureServer().start()
    yield srv.base
    srv.stop()


@pytest_asyncio.fixture()
async def sb(monkeypatch):
    home = Path(tempfile.mkdtemp(prefix="sbk", dir="/tmp"))
    monkeypatch.setenv("SB_HOME", str(home))
    try:
        s = await AgentSession.launch(headful=False)
    except Exception as exc:
        if "Executable doesn't exist" in str(exc) or "playwright install" in str(exc):
            pytest.skip(f"chromium not installed: {exc}")
        raise
    yield s
    await s.close()
    shutil.rmtree(home, ignore_errors=True)


def png_size(path: str) -> tuple[int, int]:
    data = Path(path).read_bytes()
    return struct.unpack(">II", data[16:24])


async def canvas_rect(sb):
    return await sb.runtime.page.evaluate("(() => { const r = document.getElementById('captcha-canvas').getBoundingClientRect(); return {x: r.x, y: r.y}; })()")


async def title(sb) -> str:
    return await sb.runtime.page.title()


async def test_canvas_challenge_is_described_with_prompt_image_and_ruler(sb, site):
    await sb.run(f"goto {site}/captcha_drag")
    out = await sb.run("captcha")
    assert "kind=canvas" in out, out
    assert 'Prompt: "Drag the puzzle piece into the gap"' in out, out
    assert "captcha drag X,Y X,Y" in out and "captcha click X,Y" in out, out
    ch = sb._challenge
    w, h = png_size(ch.image_path)
    assert w >= 300 and h >= 180, (w, h)
    assert "Widget message" not in out, out   # error texts that exist but are invisible (faded/scaled/off-screen) are not errors
    assert (w, h) == tuple(int(v) for v in ch.size)  # image pixels == the coordinate space the model uses


async def test_drag_puzzle_is_solved_with_image_coordinates(sb, site):
    await sb.run(f"goto {site}/captcha_drag")
    await sb.run("captcha")
    ox, oy = sb._challenge.origin
    r = await canvas_rect(sb)
    px, py = r["x"] - ox + 40, r["y"] - oy + 80     # centre of the piece, in IMAGE coordinates
    gx, gy = r["x"] - ox + 230, r["y"] - oy + 80    # centre of the gap
    out = await sb.run(f"captcha drag {px:.0f},{py:.0f} {gx:.0f},{gy:.0f}")
    assert out.startswith("dragged"), out
    assert await title(sb) == "captcha-solved", out


async def test_wrong_drag_is_reported_by_the_page_not_hidden(sb, site):
    await sb.run(f"goto {site}/captcha_drag")
    await sb.run("captcha")
    ox, oy = sb._challenge.origin
    r = await canvas_rect(sb)
    out = await sb.run(f"captcha drag {r['x'] - ox + 40:.0f},{r['y'] - oy + 80:.0f} {r['x'] - ox + 120:.0f},{r['y'] - oy + 30:.0f}")
    assert await title(sb) == "captcha-failed"
    assert "REJECTED" in out and "Please try again." in out, out   # the widget's own error text must reach the model


async def test_canvas_follow_up_message_is_not_written_for_tile_grids(sb, site):
    await sb.run(f"goto {site}/captcha_click")
    await sb.run("captcha")
    ox, oy = sb._challenge.origin
    r = await canvas_rect(sb)
    out = await sb.run(f"captcha click {r['x'] - ox + 50:.0f},{r['y'] - oy + 50:.0f}")  # one of two squares: the puzzle stays up
    assert "tiles" not in out and "dynamic grid" not in out, out
    assert "captcha submit" in out and "ruler" in out, out


async def test_click_puzzle_with_several_points(sb, site):
    await sb.run(f"goto {site}/captcha_click")
    out = await sb.run("captcha")
    assert "kind=canvas" in out and "Click on every red square" in out, out
    ox, oy = sb._challenge.origin
    r = await canvas_rect(sb)
    a = (r["x"] - ox + 50, r["y"] - oy + 50)
    b = (r["x"] - ox + 240, r["y"] - oy + 120)
    out = await sb.run(f"captcha click {a[0]:.0f},{a[1]:.0f} {b[0]:.0f},{b[1]:.0f}")
    assert out.startswith("clicked"), out
    assert await title(sb) == "captcha-solved", out


async def test_coordinates_outside_the_image_are_refused_with_a_hint(sb, site):
    await sb.run(f"goto {site}/captcha_drag")
    await sb.run("captcha")
    out = await sb.run("captcha drag 5000,5000 10,10")
    assert out.startswith("ERROR") and "outside the challenge image" in out, out


async def test_drag_without_a_coordinate_challenge_explains(sb, site):
    await sb.run(f"goto {site}/captcha")  # a tile grid, not a canvas
    await sb.run("captcha")
    out = await sb.run("captcha drag 1,1 2,2")
    assert out.startswith("ERROR") and "no coordinate challenge" in out, out


async def test_text_captcha_validate_button_is_found(sb, site):
    await sb.run(f"goto {site}/captcha_text")
    out = await sb.run("captcha")
    assert "kind=text" in out, out
    await sb.run("captcha text q7zp")
    out = await sb.run("captcha submit")
    assert not out.startswith("ERROR"), out
    assert await title(sb) == "captcha-solved", out
    assert "ACCEPTED" in out and "Correct!" in out and "still showing" not in out, out


async def test_text_captcha_wrong_answer_is_reported_as_rejected(sb, site):
    await sb.run(f"goto {site}/captcha_text")
    await sb.run("captcha")
    await sb.run("captcha text nope")
    out = await sb.run("captcha submit")
    assert "REJECTED" in out and "Incorrect" in out and "ACCEPTED" not in out, out
