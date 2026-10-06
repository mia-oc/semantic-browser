"""Long-lived browser process behind the `sb` CLI.

One daemon == one named session == one Chromium. Clients talk newline-delimited JSON over a user-private unix socket
(`~/.semantic-browser/run/<name>.sock`, dir 0700, socket 0600). The daemon exits after an idle timeout or on `close`.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import re
import signal
import sys
import time
from pathlib import Path

from semantic_browser.daemon import paths

NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
MAX_LINE = 1 << 20


def run_dir() -> Path:
    return paths.run_dir()


def sock_path(name: str) -> Path:
    return run_dir() / f"{name}.sock"


async def _serve(args: argparse.Namespace) -> None:
    from semantic_browser.agent import AgentSession

    name = args.name
    sock = sock_path(name)
    with contextlib.suppress(FileNotFoundError):
        sock.unlink()
    session = await AgentSession.launch(
        headful=not args.headless, profile_dir=args.profile, cdp=args.cdp, name=name, lite=args.lite,
        budget=args.budget,
    )
    started_at = time.time()
    lock = asyncio.Lock()
    stop = asyncio.Event()
    last = {"t": time.monotonic()}

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            raw = await reader.readline()
            if not raw or len(raw) > MAX_LINE:
                return
            msg = json.loads(raw)
            argv = msg.get("argv") or []
            if not isinstance(argv, list) or not all(isinstance(a, str) for a in argv):
                reply = {"ok": False, "text": "ERROR: bad request"}
            elif argv[:1] == ["__ping__"]:
                reply = {"ok": True, "text": "pong", "started": started_at, "pid": os.getpid()}
            else:
                last["t"] = time.monotonic()
                t0 = time.perf_counter()
                async with lock:
                    text = await session.run(argv)
                last["t"] = time.monotonic()
                reply = {"ok": True, "text": text, "ms": int((time.perf_counter() - t0) * 1000)}
                if argv[:1] == ["close"]:
                    stop.set()
            writer.write((json.dumps(reply) + "\n").encode())
            await writer.drain()
        except Exception as exc:  # never let one client kill the daemon
            with contextlib.suppress(Exception):
                writer.write((json.dumps({"ok": False, "text": f"ERROR: daemon: {exc}"}) + "\n").encode())
                await writer.drain()
        finally:
            with contextlib.suppress(Exception):
                writer.close()

    server = await asyncio.start_unix_server(handle, path=str(sock), limit=MAX_LINE)
    os.chmod(sock, 0o600)
    (run_dir() / f"{name}.pid").write_text(str(os.getpid()))
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    async def watchdog() -> None:
        while not stop.is_set():
            await asyncio.sleep(5)
            if time.monotonic() - last["t"] > args.idle:
                stop.set()

    wd = asyncio.ensure_future(watchdog())
    await stop.wait()
    wd.cancel()
    server.close()
    with contextlib.suppress(Exception):
        await session.close()
    for p in (sock, run_dir() / f"{name}.pid"):
        with contextlib.suppress(FileNotFoundError):
            p.unlink()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="semantic_browser.daemon.server")
    ap.add_argument("--name", default="default")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--profile", default=None)
    ap.add_argument("--cdp", default=None)
    ap.add_argument("--lite", default="off", choices=["off", "media", "max"])
    ap.add_argument("--budget", type=int, default=None, help="view size in characters (default 5000)")
    ap.add_argument("--idle", type=int, default=900, help="exit after this many idle seconds")
    args = ap.parse_args(argv)
    if not NAME_RE.match(args.name):
        sys.exit("invalid session name")
    asyncio.run(_serve(args))


if __name__ == "__main__":
    main()
