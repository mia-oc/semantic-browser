"""FastAPI app factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from semantic_browser import __version__
from semantic_browser.service.routes import router
from semantic_browser.service.settings import load_service_settings


def create_app() -> FastAPI:
    settings = load_service_settings()
    app = FastAPI(title="semantic-browser", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allow_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Token"],
    )
    app.include_router(router)
    return app
