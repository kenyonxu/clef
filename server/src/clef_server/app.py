"""FastAPI application factory."""

from fastapi import FastAPI

from clef_server.routes import create_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Clef Server",
        description="Multi-agent music composition microservice",
        version="0.1.0",
    )
    app.include_router(create_router())
    return app
