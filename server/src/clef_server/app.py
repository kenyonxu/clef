"""FastAPI application factory."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from clef_server.routes import create_router

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
