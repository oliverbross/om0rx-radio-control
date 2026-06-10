"""
Static file serving module for FlexRadio Web Control
Handles frontend asset serving and static file endpoints
"""

import logging
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from radio_control import config

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
    logs_path = config.LOGS_DIR

    # Mount static files from frontend directory
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

    # Mount logs directory for ADIF and other log files
    app.mount("/logs", StaticFiles(directory=str(logs_path)), name="logs")

    # Register individual file endpoints
    register_static_endpoints(app, frontend_path, logs_path)


def register_static_endpoints(app, frontend_path: Path, logs_path: Path):
    """
    Register individual static file endpoints.

    Args:
        app: FastAPI application instance
        frontend_path: Path to frontend directory
        logs_path: Path to logs directory
    """

    @app.get("/logs/qso_log.adif")
    async def serve_adif_log():
        """Serve ADIF log file"""
        adif_file = logs_path / "qso_log.adif"
        if adif_file.exists():
            return FileResponse(adif_file, media_type="text/plain")
        raise HTTPException(status_code=404, detail="qso_log.adif not found")

    @app.get("/app.js")
    async def serve_app_js():
        """Serve app.js directly"""
        js_file = frontend_path / "app.js"
        if js_file.exists():
            return FileResponse(js_file, media_type="application/javascript")
        raise HTTPException(status_code=404, detail="app.js not found")

    @app.get("/logging-panel.css")
    async def serve_logging_panel_css():
        """Serve logging-panel.css directly"""
        css_file = frontend_path / "logging-panel.css"
        if css_file.exists():
            return FileResponse(css_file, media_type="text/css")
        raise HTTPException(status_code=404, detail="logging-panel.css not found")

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
            if not str(file).startswith(str(frontend_path.resolve())):
                raise HTTPException(status_code=403, detail="Access denied")
        except:
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
