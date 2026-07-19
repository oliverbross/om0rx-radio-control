"""
Static file serving module for FlexRadio Web Control
Handles frontend asset serving and static file endpoints
"""

import logging
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

LEGACY_SINGLE_PAGE_ROUTES = {
    "radio-control.html",
    "logging.html",
    "launcher.html",
}


def setup_static_files(app):
    """
    Set up static file serving for the FastAPI application.

    Args:
        app: FastAPI application instance
    """
    # Define paths
    frontend_path = Path(__file__).parent.parent.parent / "frontend"
    # Mount static files from frontend directory
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

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
    async def serve_frontend_files(file_path: str):
        """Serve all other frontend files (HTML, JS, CSS, etc.)"""
        
        # ⚠️ CRITICAL: Don't intercept API routes!
        # If path starts with 'api/' or other known API patterns, let FastAPI handle it
        if file_path.startswith('api/'):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        
        if file_path in LEGACY_SINGLE_PAGE_ROUTES:
            index_file = frontend_path / "index.html"
            if index_file.exists():
                return FileResponse(index_file, media_type='text/html')

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
            response = FileResponse(file, media_type=media_type)
            # Add cache-busting headers for development
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

        # If file not found and it's a request for a page, try index.html (for SPA support)
        # Handle root path request (empty file_path) or pages without extension
        if not file_path or '.' not in file_path:
            index_file = frontend_path / "index.html"
            if index_file.exists():
                return FileResponse(index_file, media_type='text/html')

        # File not found
        raise HTTPException(status_code=404, detail="File not found")
