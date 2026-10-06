"""CAPTCHA helpers that do not need a browser, and lite-mode patterns."""

from __future__ import annotations

import re

from semantic_browser import lite
from semantic_browser.captcha import Challenge, _jpeg_size, _pdf_escape, jpeg_to_pdf


def _fake_jpeg(w: int, h: int) -> bytes:
    # SOI + SOF0 (len 17, 8-bit, height, width, 3 components) + EOI: enough for the size parser and PDF embedding
    return b"\xff\xd8\xff\xc0\x00\x11\x08" + h.to_bytes(2, "big") + w.to_bytes(2, "big") + b"\x03" + b"\x01\x22\x00\x02\x11\x01\x03\x11\x01" + b"\xff\xd9"


def test_jpeg_size_reads_sof_marker():
    assert _jpeg_size(_fake_jpeg(320, 240)) == (320, 240)


def test_pdf_is_structurally_valid():
    pdf = jpeg_to_pdf(_fake_jpeg(300, 200), 300, 200, caption="Select all (traffic) lights \\ ok")
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    assert b"/DCTDecode" in pdf and b"/Width 300" in pdf and b"/Height 200" in pdf
    # xref offsets must point at "N 0 obj"
    startxref = int(re.search(rb"startxref\n(\d+)\n", pdf).group(1))
    assert pdf[startxref:startxref + 4] == b"xref"
    table = pdf[startxref:].split(b"\n")[3:9]
    for n, row in enumerate(table, start=1):
        off = int(row.split()[0])
        assert pdf[off:off + len(f"{n} 0 obj")] == f"{n} 0 obj".encode()


def test_pdf_caption_escapes_parentheses_and_backslashes():
    assert _pdf_escape("a(b)c\\d") == "a\\(b\\)c\\\\d"
    assert "\\(traffic\\)" in jpeg_to_pdf(_fake_jpeg(10, 10), 10, 10, "(traffic)").decode("latin-1")


def test_challenge_describe_none_and_grid():
    assert "No CAPTCHA" in Challenge(provider="x", kind="none").describe()
    text = Challenge(provider="recaptcha", kind="grid", prompt="Select traffic lights", rows=3, cols=3, tiles=9, image_path="/tmp/a.png").describe()
    assert "grid=3x3" in text and "Select traffic lights" in text and "captcha select" in text and "/tmp/a.png" in text


def test_lite_levels():
    assert lite.patterns_for("off") == [] and lite.patterns_for("media") == []
    mx = lite.patterns_for("max")
    assert any("googletagmanager" in p for p in mx)
    assert lite.blocks_media("media") and lite.blocks_media("max") and not lite.blocks_media("off")


def test_lite_blocks_by_resource_type_not_url_text():
    """Regression: URL globs once blocked Wikipedia's load.php CSS/JS because its query string contained '.png?'."""
    css = "https://en.wikipedia.org/w/load.php?modules=ext.foo.png%7Cbar&only=styles"
    assert not lite.should_block(css, "Stylesheet")
    assert not lite.should_block(css, "Script")
    assert not lite.should_block("https://x.test/app.js", "Script")
    assert not lite.should_block("https://x.test/api/data.json", "XHR")
    assert lite.should_block("https://x.test/hero.png", "Image")
    assert lite.should_block("https://x.test/f.woff2", "Font")
    assert lite.should_block("https://x.test/v.mp4", "Media")


def test_lite_never_blocks_captcha_images():
    for u in (
        "https://www.google.com/recaptcha/api2/payload?c=abc&k=key",
        "https://imgs.hcaptcha.com/5fa8e6c1d2",
        "https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/orchestrate",
        "https://www.gstatic.com/recaptcha/api2/logo_48.png",
    ):
        assert not lite.should_block(u, "Image"), u
