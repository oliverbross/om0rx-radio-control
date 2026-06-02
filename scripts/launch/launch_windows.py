#!/usr/bin/env python3
"""
OM0RX Radio Control launcher.

The current frontend is a single application shell. Older builds launched
separate radio/logging/spots pages, but those standalone pages were retired.
"""

import sys
import threading
import time
import os

# Try to import webview, with fallback instructions
try:
    import webview
except ImportError:
    print("❌ pywebview is not installed!")
    print("\n📥 Installation Instructions:")
    print("   1. Upgrade pip, setuptools, and wheel:")
    print("      pip install --upgrade pip setuptools wheel")
    print("\n   2. Install pywebview:")
    print("      pip install pywebview --upgrade")
    print("\n   Or run: .\\launch_windows.ps1")
    print("\n💡 FALLBACK: Use the browser launcher instead:")
    print("   http://127.0.0.1:8080/launcher.html")
    sys.exit(1)

# Configuration
BACKEND_HOST = os.environ.get("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "8080"))
BACKEND_CONNECT_HOST = "127.0.0.1" if BACKEND_HOST == "0.0.0.0" else BACKEND_HOST
BASE_URL = f"http://{BACKEND_CONNECT_HOST}:{BACKEND_PORT}"
WINDOW_CONFIG = {
    "title": "OM0RX Radio Control",
    "url": f"{BASE_URL}/",
    "width": 1500,
    "height": 950,
}
DIGITAL_WINDOW_CONFIG = {
    "title": "OM0RX Radio Control - DIGITAL",
    "url": f"{BASE_URL}/ft8.html",
    "width": 1260,
    "height": 860,
}
VISUAL_MAP_WINDOW_CONFIG = {
    "title": "OM0RX Radio Control - Visual Map",
    "url": f"{BASE_URL}/visual-map.html",
    "width": 1320,
    "height": 920,
}


class DesktopApi:
    """Small pywebview bridge for opening app-owned secondary windows."""

    def __init__(self):
        self._digital_window = None
        self._visual_map_window = None
        self._lock = threading.Lock()

    def open_digital_window(self):
        """Open or focus the native Digital window without using browser tabs."""
        with self._lock:
            try:
                if self._digital_window:
                    try:
                        self._digital_window.restore()
                        self._digital_window.show()
                        self._digital_window.evaluate_js("window.focus && window.focus();")
                        return {"success": True, "reused": True}
                    except Exception:
                        self._digital_window = None

                self._digital_window = webview.create_window(
                    title=DIGITAL_WINDOW_CONFIG["title"],
                    url=DIGITAL_WINDOW_CONFIG["url"],
                    width=DIGITAL_WINDOW_CONFIG["width"],
                    height=DIGITAL_WINDOW_CONFIG["height"],
                    resizable=True,
                    focus=True,
                )
                print(
                    f"✅ Created window: {DIGITAL_WINDOW_CONFIG['title']} -> "
                    f"{DIGITAL_WINDOW_CONFIG['url']}"
                )
                return {"success": True, "reused": False}
            except Exception as exc:
                print(f"❌ Failed to create Digital window: {exc}")
                return {"success": False, "error": str(exc)}

    def open_visual_map_window(self, url=None):
        """Open or focus the native visual map window without using browser tabs."""
        with self._lock:
            try:
                if self._visual_map_window:
                    try:
                        self._visual_map_window.restore()
                        self._visual_map_window.show()
                        self._visual_map_window.evaluate_js("window.focus && window.focus();")
                        return {"success": True, "reused": True}
                    except Exception:
                        self._visual_map_window = None

                target_url = self._resolve_visual_map_url(url)
                self._visual_map_window = webview.create_window(
                    title=VISUAL_MAP_WINDOW_CONFIG["title"],
                    url=target_url,
                    width=VISUAL_MAP_WINDOW_CONFIG["width"],
                    height=VISUAL_MAP_WINDOW_CONFIG["height"],
                    resizable=True,
                    focus=True,
                )
                print(
                    f"✅ Created window: {VISUAL_MAP_WINDOW_CONFIG['title']} -> "
                    f"{target_url}"
                )
                return {"success": True, "reused": False}
            except Exception as exc:
                print(f"❌ Failed to create visual map window: {exc}")
                return {"success": False, "error": str(exc)}

    def _resolve_visual_map_url(self, url=None):
        """Resolve frontend-provided relative visual-map URLs against the backend base URL."""
        if not url:
            return VISUAL_MAP_WINDOW_CONFIG["url"]
        value = str(url)
        if value.startswith("http://") or value.startswith("https://"):
            return value
        if not value.startswith("/"):
            value = "/" + value
        return f"{BASE_URL}{value}"


def launch_windows():
    """Launch the single application window."""
    try:
        api = DesktopApi()
        webview.create_window(
            title=WINDOW_CONFIG["title"],
            url=WINDOW_CONFIG["url"],
            js_api=api,
            width=WINDOW_CONFIG["width"],
            height=WINDOW_CONFIG["height"],
            resizable=True,
        )
        print(f"✅ Created window: {WINDOW_CONFIG['title']} -> {WINDOW_CONFIG['url']}")
        webview.start()
    except Exception as e:
        print(f"❌ Failed to create application window: {e}")
        sys.exit(1)


def check_backend_ready(max_attempts=30, delay=1):
    """Check if backend is ready before launching windows"""
    import socket
    
    print("⏳ Checking if backend is ready...")
    for attempt in range(max_attempts):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((BACKEND_CONNECT_HOST, BACKEND_PORT))
            sock.close()
            
            if result == 0:
                print("✅ Backend is ready!\n")
                return True
            
            if attempt == 0:
                print(f"   (will wait up to {max_attempts} seconds...)")
            
        except Exception:
            pass
        
        time.sleep(delay)
    
    print(f"❌ Backend is not responding on {BASE_URL}")
    print("   Please make sure the backend app is running:")
    print("   Run: .\\start_all.ps1")
    return False


if __name__ == "__main__":
    # Check if backend is running
    if not check_backend_ready():
        sys.exit(1)
    
    # Launch windows
    launch_windows()
