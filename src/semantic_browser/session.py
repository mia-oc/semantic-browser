"""Managed session API."""

from __future__ import annotations

from semantic_browser.browser_manager import BrowserManager
from semantic_browser.config import RuntimeConfig
from semantic_browser.runtime import SemanticBrowserRuntime


class ManagedSession:
    """Managed browser lifecycle container."""

    def __init__(self, manager: BrowserManager, runtime: SemanticBrowserRuntime) -> None:
        self._manager = manager
        self._runtime = runtime

    @classmethod
    async def launch(
        cls,
        headful: bool = True,
        user_data_dir: str | None = None,
        browser_path: str | None = None,
        config: RuntimeConfig | None = None,
    ):
        manager = BrowserManager(headful=headful, user_data_dir=user_data_dir)
        artifacts = await manager.launch(browser_path=browser_path)
        runtime = SemanticBrowserRuntime(
            page=artifacts.page, config=config, managed=True, manager=manager, attached_kind="managed"
        )
        return cls(manager=manager, runtime=runtime)

    @property
    def runtime(self) -> SemanticBrowserRuntime:
        return self._runtime

    async def new_page(self):
        artifacts = self._manager.artifacts
        return await artifacts.context.new_page()

    async def close(self) -> None:
        await self._runtime.close()
