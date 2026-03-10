"""Composite settle strategy."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from semantic_browser.config import SettleConfig
from semantic_browser.errors import SettleTimeoutError


async def wait_for_settle(page: Any, config: SettleConfig) -> None:
    deadline = time.monotonic() + (config.max_settle_ms / 1000)
    stable_hits = 0
    previous_count: int | None = None

    while time.monotonic() < deadline:
        state = await page.evaluate("document.readyState")
        if state not in config.ready_states:
            await asyncio.sleep(0.05)
            continue

        interactable_count = await page.evaluate(
            """
            () => {
              const sel = 'a[href],button,input,select,textarea,[role="button"]';
              const all = Array.from(document.querySelectorAll(sel));
              return all.filter(el => {
                const s = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return s.display !== 'none' &&
                       s.visibility !== 'hidden' &&
                       rect.width > 0 &&
                       rect.height > 0;
              }).length;
            }
            """
        )
        if previous_count is None or previous_count == interactable_count:
            stable_hits += 1
        else:
            stable_hits = 0
        previous_count = interactable_count
        if stable_hits >= 2:
            await asyncio.sleep(config.mutation_quiet_ms / 1000)
            return
        await asyncio.sleep(config.interactable_stable_ms / 1000)

    raise SettleTimeoutError("Page did not settle before timeout.")
