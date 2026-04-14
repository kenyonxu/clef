"""FastAPI application factory."""

import logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from clef_server.routes import create_router

_SERVER_ROOT = Path(__file__).resolve().parent.parent.parent
_LOG_DIR = _SERVER_ROOT / "logs"
_LOG_DIR.mkdir(exist_ok=True)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Add file handler to clef_server and agent_framework loggers.

    Uvicorn --reload on Windows does not forward worker stdout to the
    parent cmd window, so console-only logging is invisible.  We attach
    a RotatingFileHandler during lifespan startup so it runs after
    uvicorn's own dictConfig has finished configuring loggers.
    """
    handler = RotatingFileHandler(
        _LOG_DIR / "clef-server.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    ))
    for logger_name in ("clef_server", "agent_framework"):
        logger = logging.getLogger(logger_name)
        logger.addHandler(handler)
        logger.propagate = False

    # Configure session persistence and restore incomplete sessions
    from clef_server.orchestrator import get_session_manager
    persist_dir = _SERVER_ROOT / "data" / "sessions"
    mgr = get_session_manager()
    mgr._persist_dir = persist_dir
    restored = mgr.restore_all_incomplete()
    if restored:
        logger.info("Restored %d incomplete session(s) from %s", len(restored), persist_dir)

    yield

_HOME_HTML = """\
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>Clef Server</title>
<style>
body{font-family:system-ui,sans-serif;max-width:720px;margin:3rem auto;padding:0 1.5rem;color:#222}
h1{font-size:1.5rem;margin-bottom:.25rem}
p.sub{color:#888;margin-bottom:2rem}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:.5rem .75rem;border-bottom:1px solid #eee}
th{color:#555;font-weight:500;font-size:.85rem}
code{background:#f4f4f4;padding:.15rem .4rem;border-radius:4px;font-size:.85rem}
a{color:#0066cc;text-decoration:none}
a:hover{text-decoration:underline}
.footer{margin-top:2rem;color:#aaa;font-size:.8rem}
</style>
</head>
<body>
<h1>Clef Server</h1>
<p class="sub">Multi-agent music composition microservice &middot; v0.1.0</p>
<table>
<tr><th>Endpoint</th><th>Method</th><th>Description</th></tr>
<tr><td><code>/compose</code></td><td>POST</td><td>Create a new composition session</td></tr>
<tr><td><code>/status/{id}</code></td><td>GET</td><td>Get session status</td></tr>
<tr><td><code>/status/{id}/stream</code></td><td>GET</td><td>SSE real-time progress</td></tr>
<tr><td><code>/result/{id}</code></td><td>GET</td><td>Get composition output files</td></tr>
<tr><td><code>/confirm/{id}</code></td><td>POST</td><td>Confirm sample direction (Phase 2)</td></tr>
<tr><td><code>/cancel/{id}</code></td><td>POST</td><td>Cancel a session</td></tr>
<tr><td><code>/sessions</code></td><td>GET</td><td>List all sessions</td></tr>
</table>
<p style="margin-top:1.5rem"><a href="/docs">Swagger UI</a> &middot; <a href="/redoc">ReDoc</a></p>
<p class="footer">Powered by Microsoft Agent Framework</p>
</body>
</html>
"""


def create_app() -> FastAPI:
    app = FastAPI(
        title="Clef Server",
        description="Multi-agent music composition microservice",
        version="0.1.0",
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routes first (they take priority over StaticFiles mount)
    app.include_router(create_router())

    # Production: serve SPA from dist/ if it exists
    dist_dir = Path(__file__).resolve().parent.parent.parent / "web" / "dist"
    if dist_dir.exists():
        app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="spa")
    else:
        @app.get("/", response_class=HTMLResponse)
        async def root():
            return _HOME_HTML

    return app


app = create_app()
