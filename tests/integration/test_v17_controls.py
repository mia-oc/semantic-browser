"""v1.7: drag and drop, upload, double/right click and sliders against a deterministic local page."""

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


@pytest.fixture(scope="module")
def site():
    srv = FixtureServer().start()
    yield srv.base
    srv.stop()


@pytest_asyncio.fixture()
async def sb(monkeypatch):
    home = Path(tempfile.mkdtemp(prefix="sbc", dir="/tmp"))
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


def ref(view: str, label: str) -> str:
    for m in re.finditer(r"\[(\d+)((?: [^\]]*)?)\]([^\[\n|]*)", view):
        inner, after = m.group(2), m.group(3).strip()
        if re.search(label, inner if '"' in inner else after, re.I):
            return m.group(1)
    raise AssertionError(f"no [{label}] in view:\n{view}")


async def test_slider_value_is_visible_and_settable(sb, site):
    v = await sb.run(f"goto {site}/controls")
    assert re.search(r'slider "Volume"="3" 0\.\.10', v), v
    v = await sb.run(f'type {ref(v, "Volume")} 8')
    assert "volume:8" in v and '="8"' in v, v


async def test_upload_one_and_many(sb, site, tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("a")
    b.write_text("b")
    v = await sb.run(f"goto {site}/controls")
    v = await sb.run(f"upload {ref(v, 'Upload')} {a}")
    assert "file:a.txt" in v, v
    v = await sb.run(f"upload {ref(v, 'Upload')} {a} {b}")
    assert "file:a.txt,b.txt" in v, v


async def test_click_on_file_input_explains_upload(sb, site):
    v = await sb.run(f"goto {site}/controls")
    out = await sb.run(f"click {ref(v, 'Upload')}")
    assert out.startswith("FAILED") and re.search(r"use `upload \d+ /path", out) and "None" not in out.splitlines()[0], out


async def test_upload_refuses_credentials(sb, site, tmp_path):
    (tmp_path / ".env").write_text("TOKEN=1")
    v = await sb.run(f"goto {site}/controls")
    out = await sb.run(f"upload {ref(v, 'Upload')} {tmp_path / '.env'}")
    assert out.startswith("INVALID") or out.startswith("ERROR") or "refusing" in out.splitlines()[0], out


async def test_dblclick_and_right_click(sb, site):
    v = await sb.run(f"goto {site}/controls")
    v = await sb.run(f"dblclick {ref(v, 'Edit item')}")
    assert "double-clicked" in v, v
    v = await sb.run(f"click {ref(v, 'Right-click area')} --right")
    assert "context-menu" in v, v


async def test_drag_and_drop(sb, site):
    v = await sb.run(f"goto {site}/controls")
    v = await sb.run(f"drag {ref(v, 'Alpha')} {ref(v, 'Drop zone')}")
    assert "dropped:Alpha" in v, v
    out = await sb.run('drag 9999 1')
    assert out.startswith(("FAILED", "STALE", "INVALID")), out


async def test_bare_text_next_to_a_radio_or_checkbox_is_its_label(sb, site):
    v = await sb.run(f"goto {site}/bare_labels")
    assert re.search(r"\[\d+ radio\]Cheese\n", v), v
    assert re.search(r"\[\d+ radio\]Peas\n", v), v
    assert re.search(r"\[\d+ radio ✓\]Cheese and peas\n", v), v
    assert not re.search(r"\]snack|\]nl |\]terms", v), v   # the name= attribute must not leak in as the label
    assert re.search(r"checkbox\]Subscribe to the newsletter", v), v
    assert re.search(r"checkbox\]I accept the terms", v), v
    assert re.search(r"checkbox\]buy milk", v) and "(unlabeled)" not in v, v   # sibling <label> without `for` (TodoMVC)
    v = await sb.run('click "Peas"')
    assert re.search(r"radio ✓\]Peas", v), v


async def test_refless_verbs_do_not_echo_synthetic_labels(sb, site):
    await sb.run(f"goto {site}/controls")
    w = (await sb.run("wait 100")).splitlines()[0]
    s = (await sb.run("scroll down")).splitlines()[0]
    assert "'Wait'" not in w and w.startswith("waited"), w
    assert "'Scroll" not in s and s.startswith("scrolled"), s


async def test_small_modal_dialog_in_shadow_root_inside_header_is_the_overlay(sb, site):
    v = await sb.run(f"goto {site}/modal_header")
    assert "BLOCKING OVERLAY" not in v, v
    v = await sb.run('click "Search the site"')
    assert "BLOCKING OVERLAY" in v, v          # a 300x40 <dialog> opened with showModal() is still a blocking layer
    assert re.search(r'\[\d+ input:search "Search"\]', v), v
    assert "Getting started" not in v, v        # the page behind is hidden until the modal is handled
    v = await sb.run("type Search flatMap")  # a `Search` button behind the modal must not make this ambiguous
    assert "flatMap" in v, v
    await sb.run("press Escape")           # first Escape clears a type=search input (browser behaviour)...
    v = await sb.run("press Escape")       # ...the second closes the dialog
    assert "BLOCKING OVERLAY" not in v and "Getting started" in v, v


async def test_ad_frames_identified_by_title_are_left_out_but_real_frames_stay(sb, site):
    v = await sb.run(f"goto {site}/ads")
    assert "Buy now" not in v and "doubleclick" not in v and "3rd party ad" not in v, v
    assert "Second story" in v and "Card number" in v, v
