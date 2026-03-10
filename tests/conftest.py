"""Shared test fixtures."""

from __future__ import annotations

import pytest

from semantic_browser.config import RuntimeConfig


@pytest.fixture()
def runtime_config() -> RuntimeConfig:
    return RuntimeConfig()
