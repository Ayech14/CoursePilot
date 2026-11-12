"""Serving the built web app from the API, so production is one service on one origin.

The sign-in cookie is ``SameSite=Strict``. With the pages and the API on the same origin it is
always a first-party cookie, with no cross-site setup and no third-party cookie blocking to fight.
"""

import base64
import hashlib
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from starlette.types import Scope

# Paths the web app never owns. Unknown paths under them stay JSON 404s.
_RESERVED = ("api/", "api", "health", "docs", "redoc", "openapi.json")
_INLINE_SCRIPT = re.compile(r"<script>(.*?)</script>", re.DOTALL)


def web_policy(index_html: str) -> str:
    """The page's Content-Security-Policy.

    Scripts: only the app's own files, plus the one small inline script that picks the theme
    before the first paint, allowed by its hash rather than by allowing inline scripts in general.
    Styles allow inline because the calendar library inserts its stylesheet at run time.
    """
    hashes = " ".join(
        "'sha256-" + base64.b64encode(hashlib.sha256(body.encode()).digest()).decode() + "'"
        for body in _INLINE_SCRIPT.findall(index_html)
    )
    script = f"'self' {hashes}".strip()
    return (
        "default-src 'self'; "
        f"script-src {script}; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        # The calendar library embeds its arrow icons as a data: font.
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'none'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )


class _ImmutableAssets(StaticFiles):
    """Vite names every asset after its content, so a file never changes once published."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def mount_web_app(app: FastAPI, directory: str) -> str:
    """Serve the app's files and send every other page route to ``index.html``.

    Returns the page policy for the security headers. Call after every API route is added.
    """
    root = Path(directory).resolve()
    index = root / "index.html"
    if not index.is_file():
        raise RuntimeError(f"STATIC_DIR has no index.html: {root}")
    policy = web_policy(index.read_text(encoding="utf-8"))

    if (root / "assets").is_dir():
        # Compressed here rather than trusting the platform to do it: the main script shrinks
        # from about 500 KB to 150 KB. Only the public files, never the API's private answers.
        assets = GZipMiddleware(_ImmutableAssets(directory=root / "assets"), minimum_size=1024)
        app.mount("/assets", assets, name="assets")

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def page(path: str) -> FileResponse:
        if path.startswith(_RESERVED):
            raise HTTPException(status_code=404)
        candidate = (root / path).resolve()
        # A real top-level file such as the icon, never anything outside the folder.
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        # Every app route (/dashboard, /tasks/…) is drawn in the browser from index.html.
        # No caching, so a new release reaches the student on their next visit.
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return policy
