"""`sb` — thin, stdlib-only client. Starts the daemon on first use, then each call is one socket round trip.

    sb goto news.ycombinator.com
    sb click 12
    sb type 3 "hello" --enter
    sb --session work --headless goto example.com      # options only matter when the daemon is first started
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

from semantic_browser.daemon import paths

NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
FAIL_PREFIXES = ("ERROR", "FAILED", "STALE", "INVALID", "BLOCKED")


def _run_dir() -> Path:
    return paths.run_dir()


def _request(sock_file: Path, argv: list[str], timeout: float) -> dict:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(str(sock_file))
        s.sendall((json.dumps({"argv": argv}) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        return json.loads(buf or b'{"ok": false, "text": "ERROR: empty reply from daemon"}')
    finally:
        s.close()


def _ping(sock_file: Path) -> dict | None:
    if not sock_file.exists():
        return None
    try:
        reply = _request(sock_file, ["__ping__"], 3)
    except (OSError, ValueError):
        return None
    return reply if reply.get("ok") else None


def _alive(sock_file: Path) -> bool:
    return _ping(sock_file) is not None


def _code_mtime(pkg_dir: Path | None = None) -> float:
    """Newest modification time of the installed package's source (python + the snapshot script)."""
    root = pkg_dir or Path(__file__).resolve().parent.parent
    newest = 0.0
    for pattern in ("*.py", "*.js"):
        for p in root.rglob(pattern):
            with contextlib.suppress(OSError):
                newest = max(newest, p.stat().st_mtime)
    return newest


def _is_stale(ping: dict, pkg_dir: Path | None = None) -> bool:
    """True when the library changed on disk after the daemon started (e.g. `pip install -U`), so it runs old code."""
    started = ping.get("started")
    return isinstance(started, (int, float)) and _code_mtime(pkg_dir) > started + 1


def _spawn(name: str, opts: dict) -> subprocess.Popen:
    cmd = [sys.executable, "-m", "semantic_browser.daemon.server", "--name", name, "--lite", opts["lite"]]
    if opts["headless"]:
        cmd.append("--headless")
    if opts["profile"]:
        cmd += ["--profile", opts["profile"]]
    if opts["cdp"]:
        cmd += ["--cdp", opts["cdp"]]
    if opts.get("budget"):
        cmd += ["--budget", str(opts["budget"])]
    log = open(_run_dir() / f"{name}.log", "wb")  # noqa: SIM115 - handed to the child; fresh per start so errors are current
    return subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)


def _ensure_daemon(name: str, opts: dict) -> Path:
    sock_file = _run_dir() / f"{name}.sock"
    ping = _ping(sock_file)
    if ping is not None and not _is_stale(ping):
        return sock_file
    if ping is not None:  # running old code: restart it (the browser session is lost; say so)
        print(f"note: restarting session '{name}' because semantic-browser was updated since it started (page state reset).", file=sys.stderr)
        _stop(name)
        time.sleep(0.3)
    with contextlib.suppress(FileNotFoundError):
        sock_file.unlink()
    proc = _spawn(name, opts)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if _alive(sock_file):
            return sock_file
        if proc.poll() is not None:
            break
        time.sleep(0.1)
    tail = ""
    with contextlib.suppress(OSError):
        tail = (_run_dir() / f"{name}.log").read_text(errors="replace")[-4000:]
    raise SystemExit(f"ERROR: could not start the browser daemon.\n{_root_cause(tail)}")


def _root_cause(log: str) -> str:
    """The one line that explains a daemon start failure (plus the usual fix), not the head of a traceback."""
    lines = [ln.strip() for ln in log.splitlines() if ln.strip()]
    if not lines:
        return "(the daemon exited without writing a log)"
    cause = next((ln for ln in reversed(lines) if re.match(r"^[\w.]*(Error|Exception|Exit)\b.*:|^[\w.]+Error\b", ln)), lines[-1])
    hint = ""
    if "ECONNREFUSED" in cause or "connect_over_cdp" in cause:
        hint = "\nIs the browser running with remote debugging on that port? (chrome --remote-debugging-port=PORT)"
    elif "Executable doesn't exist" in log or "playwright install" in log:
        hint = "\nRun: python -m playwright install chromium"
    return cause[:400] + hint


def _list_daemons() -> str:
    rows = []
    for p in sorted(_run_dir().glob("*.sock")):
        rows.append(f"{p.stem}\t{'running' if _alive(p) else 'stale'}")
    return "\n".join(rows) or "no sessions running"


def _stop(name: str | None) -> str:
    out = []
    targets = [p for p in _run_dir().glob("*.sock") if name is None or p.stem == name]
    for p in targets:
        try:
            _request(p, ["close"], 30)
            out.append(f"stopped {p.stem}")
        except (OSError, ValueError):
            with contextlib.suppress(FileNotFoundError):
                p.unlink()
            out.append(f"removed stale {p.stem}")
    return "\n".join(out) or "nothing to stop"


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    env = os.environ
    name = env.get("SB_SESSION", "default")
    opts = {
        "headless": env.get("SB_HEADLESS") == "1",
        "profile": env.get("SB_PROFILE"),
        "cdp": env.get("SB_CDP"),
        "lite": env.get("SB_LITE", "off"),
        "budget": env.get("SB_BUDGET"),
    }
    timeout = 120.0
    while args and args[0].startswith("--") and args[0] in {
        "--session", "--headless", "--headful", "--profile", "--cdp", "--lite", "--timeout", "--budget"
    }:
        flag = args.pop(0)
        if flag == "--headless":
            opts["headless"] = True
        elif flag == "--headful":
            opts["headless"] = False
        else:
            if not args:
                raise SystemExit(f"{flag} needs a value")
            val = args.pop(0)
            if flag == "--session":
                name = val
            elif flag == "--timeout":
                timeout = float(val)
            else:
                opts[flag[2:]] = val
    if not NAME_RE.match(name):
        raise SystemExit("ERROR: session name must be 1-32 chars of letters, digits, _ or -")
    if opts["lite"] not in {"off", "media", "max"}:
        raise SystemExit("ERROR: --lite must be off, media or max")

    verb = args[0].lower() if args else "help"
    if verb in {"help", "-h", "--help"}:
        from semantic_browser.verbs_help import HELP

        print(HELP + "\nsession options (first call only): --session NAME  --headless  --profile DIR  --cdp URL  --lite media|max  --budget CHARS")
        print("other: sb sessions | sb stop [NAME|--all] | sb version")
        return
    if verb == "version":
        from semantic_browser import __version__

        print(__version__)
        return
    if verb == "sessions":
        print(_list_daemons())
        return
    if verb == "stop":
        target = args[1] if len(args) > 1 and args[1] != "--all" else (None if "--all" in args else name)
        print(_stop(target))
        return

    sock_file = _ensure_daemon(name, opts)
    try:
        reply = _request(sock_file, args, timeout)
    except TimeoutError:
        raise SystemExit(f"ERROR: timed out after {timeout:.0f}s waiting for `{verb}` (the browser may be busy; try `sb view`).") from None
    except OSError as exc:
        raise SystemExit(f"ERROR: lost connection to the daemon ({exc}). Run the command again to restart it.") from None
    text = str(reply.get("text", ""))
    print(text)
    if not reply.get("ok") or text.lstrip().startswith(FAIL_PREFIXES):
        sys.exit(1)


if __name__ == "__main__":
    main()
