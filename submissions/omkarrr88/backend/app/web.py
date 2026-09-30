"""Serves the built web UI from the API's own origin, so the UI needs no CORS and no second host.

The Docker image copies the Vite build (frontend/dist) to STATIC_DIR. Files under /assets have
content hashes in their names and are cached for a year; every other path that is not part of the
API gets index.html, so the single-page app can handle it.
"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

logger = logging.getLogger(__name__)

# Paths the API owns: an unknown one is a JSON 404, never the web UI.
API_PATHS = ("api", "docs", "redoc", "openapi.json", "health")


class HashedAssets(StaticFiles):
    """Static files whose names change with their content, so browsers may keep them forever."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def mount_web_ui(app: FastAPI, static_dir: Path) -> bool:
    """Adds the web UI routes if a build is present. Returns whether it was mounted."""
    root = static_dir.resolve()
    index = root / "index.html"
    if not index.is_file():
        logger.info("web_ui.not_mounted", extra={"static_dir": str(root)})
        return False
    if (root / "assets").is_dir():
        app.mount("/assets", HashedAssets(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def web_ui(path: str) -> FileResponse:
        if path.split("/", 1)[0] in API_PATHS:
            raise StarletteHTTPException(status_code=404)
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)  # favicon.svg and other files at the root
        # Always revalidate the page itself, so a new deploy is picked up on the next load.
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return True
