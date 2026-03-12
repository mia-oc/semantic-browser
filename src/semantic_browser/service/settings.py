"""Service configuration from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceSettings:
    api_token: str | None
    allow_origins: list[str]
    session_ttl_seconds: int

    @property
    def auth_enabled(self) -> bool:
        return bool(self.api_token)


def load_service_settings() -> ServiceSettings:
    token = os.getenv("SEMANTIC_BROWSER_API_TOKEN")
    origins_raw = os.getenv("SEMANTIC_BROWSER_CORS_ORIGINS", "http://127.0.0.1,http://localhost")
    origins = [origin.strip() for origin in origins_raw.split(",") if origin.strip()]
    ttl_seconds_raw = os.getenv("SEMANTIC_BROWSER_SESSION_TTL_SECONDS", "1800")
    try:
        ttl_seconds = max(60, int(ttl_seconds_raw))
    except ValueError:
        ttl_seconds = 1800
    return ServiceSettings(api_token=token or None, allow_origins=origins, session_ttl_seconds=ttl_seconds)
