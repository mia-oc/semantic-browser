"""Coordinate challenges (drag puzzles, click-on-canvas): parsing and mapping of image coordinates."""

from __future__ import annotations

import pytest

from semantic_browser import captcha as cap


def test_parse_points_accepts_common_spellings():
    assert cap.parse_points(["50,90"]) == [(50.0, 90.0)]
    assert cap.parse_points(["50,90", "(60,70)"]) == [(50.0, 90.0), (60.0, 70.0)]
    assert cap.parse_points(["50", "90", "60", "70"]) == [(50.0, 90.0), (60.0, 70.0)]
    assert cap.parse_points(["x=12.5,y=3"]) == [(12.5, 3.0)]
    assert cap.parse_points(["50,90;60,70"]) == [(50.0, 90.0), (60.0, 70.0)]


@pytest.mark.parametrize("bad", [[], ["abc"], ["1,2,3"], ["50"], ["1", "2", "3"], ["nan,1"], ["-5,10"]])
def test_parse_points_rejects_garbage(bad):
    with pytest.raises(ValueError):
        cap.parse_points(bad)


def test_to_page_maps_image_coordinates_through_the_origin():
    ch = cap.Challenge(provider="generic", kind="canvas", origin=(100.0, 200.0), size=(320.0, 200.0))
    assert cap.to_page(ch, (10.0, 20.0)) == (110.0, 220.0)
    with pytest.raises(ValueError, match="outside the challenge image"):
        cap.to_page(ch, (400.0, 20.0))


def test_to_page_needs_an_active_coordinate_challenge():
    with pytest.raises(RuntimeError, match="no coordinate challenge"):
        cap.to_page(cap.Challenge(provider="generic", kind="grid"), (1.0, 1.0))
