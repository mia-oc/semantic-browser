"""v1.7 verbs and view details found while dogfooding: upload, drag, dblclick, right-click, slider values."""

from __future__ import annotations

import pytest

from semantic_browser.agent import AgentSession, _upload_paths
from semantic_browser.extractor.view import format_element
from semantic_browser.verbs_help import HELP


def _n(ref, kind, name, op="click", **kw):
    return {"ref": ref, "kind": kind, "name": name, "op": op, **kw}


def test_slider_shows_value_and_range():
    out = format_element(_n(37, "slider", "Volume", "fill", value="7", min="0", max="10"))
    assert out == '[37 slider "Volume"="7" 0..10]'
    assert format_element(_n(38, "slider", "Volume", "fill", value="7")) == '[38 slider "Volume"="7"]'


def test_file_input_is_labelled_as_a_file_chooser():
    assert format_element(_n(29, "file", "File input", "upload")) == '[29 file "File input"]'


def test_new_verbs_exist_and_are_documented():
    names = AgentSession._verb_names()
    for verb in ("upload", "drag", "dblclick"):
        assert verb in names
        assert verb in HELP
    assert "--right" in HELP


def test_upload_paths_accepts_a_normal_file(tmp_path):
    f = tmp_path / "cv.pdf"
    f.write_bytes(b"%PDF")
    assert _upload_paths([str(f)]) == [str(f)]


def test_upload_paths_rejects_missing_and_directories(tmp_path):
    with pytest.raises(ValueError, match="no such file"):
        _upload_paths([str(tmp_path / "nope.png")])
    with pytest.raises(ValueError, match="not a regular file"):
        _upload_paths([str(tmp_path)])
    with pytest.raises(ValueError, match="usage"):
        _upload_paths([])


@pytest.mark.parametrize("rel", [".env", ".env.production", ".ssh/id_rsa", ".aws/credentials", "server.pem", "id_ed25519"])
def test_upload_paths_refuses_credential_looking_files(tmp_path, rel):
    f = tmp_path / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("secret")
    with pytest.raises(ValueError, match="refusing to upload"):
        _upload_paths([str(f)])


def test_upload_paths_refuses_symlink_to_credentials(tmp_path):
    real = tmp_path / ".env"
    real.write_text("TOKEN=x")
    link = tmp_path / "innocent.txt"
    link.symlink_to(real)
    with pytest.raises(ValueError, match="refusing to upload"):
        _upload_paths([str(link)])
