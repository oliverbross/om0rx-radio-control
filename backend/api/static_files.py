"""
Static file serving module for FlexRadio Web Control
Handles frontend asset serving and static file endpoints
"""

import logging
from pathlib import Path
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

_IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
_REVALIDATE_CACHE = "no-cache"
_HTML_CACHE = "no-cache, no-store, must-revalidate"

LEGACY_SINGLE_PAGE_ROUTES = {
    "radio-control.html",
    "logging.html",
    "launcher.html",
}


class CacheAwareStaticFiles(StaticFiles):
    """Cache fingerprinted vendor files while keeping development assets fresh."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        query = scope.get("query_string", b"")
        response.headers["Cache-Control"] = (
            _IMMUTABLE_CACHE if b"v=" in query else _REVALIDATE_CACHE
        )
        return response


def _file_response(file: Path, media_type: str, *, versioned: bool = False) -> FileResponse:
    response = FileResponse(file, media_type=media_type)
    if file.suffix.lower() == ".html":
        response.headers["Cache-Control"] = _HTML_CACHE
    else:
        response.headers["Cache-Control"] = (
            _IMMUTABLE_CACHE if versioned else _REVALIDATE_CACHE
        )
    return response


def setup_static_files(app):
    """
    Set up static file serving for the FastAPI application.

    Args:
        app: FastAPI application instance
    """
    # Define paths
    frontend_path = Path(__file__).parent.parent.parent / "frontend"
    # Mount static files from frontend directory
    app.mount("/static", CacheAwareStaticFiles(directory=str(frontend_path)), name="static")

    # Register individual file endpoints
    register_static_endpoints(app, frontend_path)


def register_static_endpoints(app, frontend_path: Path):
    """
    Register individual static file endpoints.

    Args:
        app: FastAPI application instance
        frontend_path: Path to frontend directory
    """

    @app.get("/{file_path:path}")
    async def serve_frontend_files(file_path: str, request: Request):
        """Serve all other frontend files (HTML, JS, CSS, etc.)"""
        
        # ⚠️ CRITICAL: Don't intercept API routes!
        # If path starts with 'api/' or other known API patterns, let FastAPI handle it
        if file_path.startswith('api/'):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        
        if file_path in LEGACY_SINGLE_PAGE_ROUTES:
            index_file = frontend_path / "index.html"
            if index_file.exists():
                return _file_response(index_file, "text/html")

        file = frontend_path / file_path

        # Security check: prevent directory traversal
        try:
            file = file.resolve()
            if not file.is_relative_to(frontend_path.resolve()):
                raise HTTPException(status_code=403, detail="Access denied")
        except (OSError, RuntimeError, ValueError):
            raise HTTPException(status_code=403, detail="Access denied")

        if file.exists() and file.is_file():
            # Determine media type
            suffix = file.suffix.lower()
            media_types = {
                '.html': 'text/html',
                '.js': 'application/javascript',
                '.mjs': 'application/javascript',
                '.css': 'text/css',
                '.json': 'application/json',
                '.svg': 'image/svg+xml',
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.gif': 'image/gif',
                '.ico': 'image/x-icon',
                '.wasm': 'application/wasm',
            }
            media_type = media_types.get(suffix, 'application/octet-stream')
            return _file_response(
                file,
                media_type,
                versioned="v" in request.query_params,
            )

        # If file not found and it's a request for a page, try index.html (for SPA support)
        # Handle root path request (empty file_path) or pages without extension
        if not file_path or '.' not in file_path:
            index_file = frontend_path / "index.html"
            if index_file.exists():
                return _file_response(index_file, "text/html")

        # File not found
        raise HTTPException(status_code=404, detail="File not found")
