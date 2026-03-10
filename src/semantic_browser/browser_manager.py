"""Managed browser lifecycle support."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from semantic_browser.errors import BrowserNotReadyError


@dataclass
class BrowserArtifacts:
    playwright: Any
    browser: Any
    context: Any
    page: Any


class BrowserManager:
    """Owns Playwright objects for managed mode."""

    def __init__(self, headful: bool = True, user_data_dir: str | None = None) -> None:
        self._headful = headful
        self._user_data_dir = user_data_dir
        self._artifacts: BrowserArtifacts | None = None

    @property
    def artifacts(self) -> BrowserArtifacts:
        if self._artifacts is None:
            raise BrowserNotReadyError("Managed browser has not been launched.")
        return self._artifacts

    async def launch(self, browser_path: str | None = None) -> BrowserArtifacts:
        try:
            from playwright.async_api import async_playwright
        except Exception as exc:
            raise BrowserNotReadyError(
                "Playwright is not installed. Install semantic-browser[managed]."
            ) from exc

        pw = await async_playwright().start()
        launch_kwargs: dict[str, Any] = {"headless": not self._headful}
        if browser_path:
            launch_kwargs["executable_path"] = browser_path
        browser = await pw.chromium.launch(**launch_kwargs)
        context_kwargs: dict[str, Any] = {}
        if self._user_data_dir:
            context_kwargs["storage_state"] = self._user_data_dir
        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()
        self._artifacts = BrowserArtifacts(
            playwright=pw, browser=browser, context=context, page=page
        )
        return self._artifacts

    async def close(self) -> None:
        if self._artifacts is None:
            return
        try:
            await self._artifacts.context.close()
        finally:
            try:
                await self._artifacts.browser.close()
            finally:
                await self._artifacts.playwright.stop()
        self._artifacts = None
