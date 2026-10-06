"""Thin client <-> daemon protocol, using a fake daemon on a real unix socket (no browser)."""

from __future__ import annotations

import json
import shutil
import socket
import tempfile
import threading
from pathlib import Path

import pytest

from semantic_browser.daemon import client


@pytest.fixture()
def fake_daemon(monkeypatch):
    home = Path(tempfile.mkdtemp(prefix="sbt", dir="/tmp"))  # short: AF_UNIX paths are limited to ~104 bytes
    monkeypatch.setenv("SB_HOME", str(home))
    run = client._run_dir()
    sock_path = run / "default.sock"
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(sock_path))
    srv.listen(4)
    seen: list[list[str]] = []
    reply = {"text": "ok", "ok": True}

    def serve():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            with conn:
                line = b""
                while not line.endswith(b"\n"):
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    line += chunk
                argv = json.loads(line)["argv"]
                seen.append(argv)
                out = {"ok": True, "text": "pong"} if argv == ["__ping__"] else dict(reply)
                conn.sendall((json.dumps(out) + "\n").encode())

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    yield seen, reply, sock_path
    srv.close()
    shutil.rmtree(home, ignore_errors=True)


def test_command_round_trip_prints_text(fake_daemon, capsys):
    seen, reply, _ = fake_daemon
    reply["text"] = "navigated\n\n@ T — http://x"
    client.main(["goto", "example.com"])
    assert capsys.readouterr().out.startswith("navigated")
    assert ["goto", "example.com"] in seen


def test_failure_prefix_gives_nonzero_exit(fake_daemon, capsys):
    _, reply, _ = fake_daemon
    reply["text"] = "INVALID: ref 9 not found"
    with pytest.raises(SystemExit) as e:
        client.main(["click", "9"])
    assert e.value.code == 1
    assert "INVALID" in capsys.readouterr().out


def test_ordinary_text_that_mentions_error_is_not_a_failure(fake_daemon, capsys):
    _, reply, _ = fake_daemon
    reply["text"] = "page changed: an error message appeared"
    client.main(["view"])  # must not raise SystemExit
    assert "error message" in capsys.readouterr().out


def test_session_option_is_validated(capsys):
    with pytest.raises(SystemExit) as e:
        client.main(["--session", "../evil", "view"])
    assert "session name" in str(e.value)


def test_help_does_not_need_a_daemon(capsys, monkeypatch):
    monkeypatch.setenv("SB_HOME", "/tmp/sbt-none")
    client.main(["help"])
    out = capsys.readouterr().out
    assert "goto URL" in out and "captcha" in out


def test_sessions_lists_live_and_stale(fake_daemon, capsys):
    _, _, sock_path = fake_daemon
    Path(sock_path.parent / "ghost.sock").write_text("")  # a leftover non-socket file
    client.main(["sessions"])
    out = capsys.readouterr().out
    assert "default\trunning" in out and "ghost\tstale" in out


def test_run_dir_is_private(monkeypatch):
    home = Path(tempfile.mkdtemp(prefix="sbp", dir="/tmp"))
    monkeypatch.setenv("SB_HOME", str(home))
    try:
        d = client._run_dir()
        assert (d.stat().st_mode & 0o077) == 0
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_long_home_falls_back_to_a_short_socket_dir(monkeypatch):
    monkeypatch.setenv("SB_HOME", "/tmp/" + "x" * 120)
    d = client._run_dir()
    assert len(str(d / ("n" * 32 + ".sock"))) < 100
    assert (d.stat().st_mode & 0o077) == 0


def test_private_dir_creates_0700_and_accepts_own_dir(tmp_path):
    from semantic_browser.daemon import paths

    d = paths.private_dir(tmp_path / "a" / "b")
    assert d.is_dir() and (d.stat().st_mode & 0o077) == 0


def test_private_dir_refuses_symlink_planted_by_someone_else(tmp_path):
    """Short-path fallback lives in /tmp: a pre-planted symlink/foreign dir must not become our socket dir."""
    from semantic_browser.daemon import paths

    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "sb-link"
    link.symlink_to(real)
    with pytest.raises(PermissionError):
        paths.private_dir(link)


def test_private_dir_refuses_group_accessible_dir_it_cannot_fix(tmp_path, monkeypatch):
    from semantic_browser.daemon import paths

    d = tmp_path / "open"
    d.mkdir()
    d.chmod(0o777)
    monkeypatch.setattr(Path, "chmod", lambda self, mode, **kw: None)  # simulate a dir we do not own/cannot fix
    with pytest.raises(PermissionError):
        paths.private_dir(d)
