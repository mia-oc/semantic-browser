"""FastAPI app factory."""

from __future__ import annotations

from fastapi import FastAPI

from semantic_browser.service.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="semantic-browser", version="0.1.0")
    app.include_router(router)
    return app
