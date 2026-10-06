"""Optional 'lite' page loading: skip bytes an agent never reads (images/fonts/video, trackers) and kill animations.

Blocking is done by CDP *resource type* (Fetch domain), not URL globs: globs matched real CSS/JS whose query string
happened to contain ``.png?`` and broke pages (found by the real-site benchmark). Only Image/Font/Media requests are
paused, so everything else bypasses Python entirely. CAPTCHA providers are allow-listed.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

BLOCK_TYPES = ["Image", "Font", "Media"]
# never starve a CAPTCHA of its images
ALLOW_URL_PARTS = (
    "recaptcha", "gstatic.com/recaptcha", "hcaptcha.com", "challenges.cloudflare.com", "arkoselabs.com",
    "funcaptcha", "geetest", "captcha",
)
TRACKER_PATTERNS: list[str] = [
    "*://*.google-analytics.com/*", "*://*.googletagmanager.com/*", "*://*.doubleclick.net/*",
    "*://*.googlesyndication.com/*", "*://connect.facebook.net/*", "*://*.hotjar.com/*", "*://*.segment.io/*",
    "*://*.scorecardresearch.com/*", "*://*.amazon-adsystem.com/*", "*://*.criteo.com/*", "*://*.criteo.net/*",
    "*://*.taboola.com/*", "*://*.outbrain.com/*", "*://*.clarity.ms/*", "*://*.nr-data.net/*",
    "*://*.optimizely.com/*", "*://*.quantserve.com/*", "*://bat.bing.com/*",
]
NO_MOTION_CSS = (
    "(() => { const s = document.createElement('style');"
    "s.textContent='*,*::before,*::after{animation-duration:0s!important;animation-delay:0s!important;"
    "transition-duration:0s!important;transition-delay:0s!important;scroll-behavior:auto!important}';"
    "(document.head||document.documentElement).appendChild(s); })()"
)
_INIT = f"document.addEventListener('DOMContentLoaded', () => {{ {NO_MOTION_CSS} }}, {{once: true}});"


def patterns_for(level: str) -> list[str]:
    """URL patterns for Network.setBlockedURLs (trackers only; media is blocked by resource type)."""
    return list(TRACKER_PATTERNS) if level == "max" else []


def blocks_media(level: str) -> bool:
    return level in {"media", "max"}


def should_block(url: str, resource_type: str) -> bool:
    if resource_type not in BLOCK_TYPES:
        return False
    low = url.lower()
    return not any(part in low for part in ALLOW_URL_PARTS)


async def apply(page: Any, level: str, sessions: dict[int, Any]) -> bool:
    """Best-effort: returns True when blocking is active on `page`. Safe to call repeatedly."""
    if level == "off":
        return False
    key = id(page)
    if key in sessions:
        return True
    try:
        ctx = page.context
        ctx = ctx() if callable(ctx) else ctx
        await ctx.add_init_script(_INIT)
        cdp = await ctx.new_cdp_session(page)

        def _paused(ev: dict[str, Any]) -> None:
            rid = ev.get("requestId")
            req = ev.get("request", {})
            block = should_block(str(req.get("url", "")), str(ev.get("resourceType", "")))

            async def _answer() -> None:
                with contextlib.suppress(Exception):
                    if block:
                        await cdp.send("Fetch.failRequest", {"requestId": rid, "errorReason": "BlockedByClient"})
                    else:
                        await cdp.send("Fetch.continueRequest", {"requestId": rid})

            asyncio.ensure_future(_answer())

        cdp.on("Fetch.requestPaused", _paused)
        await cdp.send("Fetch.enable", {"patterns": [{"resourceType": t, "requestStage": "Request"} for t in BLOCK_TYPES]})
        pats = patterns_for(level)
        if pats:
            await cdp.send("Network.enable")
            await cdp.send("Network.setBlockedURLs", {"urls": pats})
        sessions[key] = cdp
        return True
    except Exception:
        return False


async def lift(page: Any, sessions: dict[int, Any]) -> None:
    cdp = sessions.pop(id(page), None)
    if cdp is None:
        return
    with contextlib.suppress(Exception):
        await cdp.send("Fetch.disable")
    with contextlib.suppress(Exception):
        await cdp.send("Network.setBlockedURLs", {"urls": []})
