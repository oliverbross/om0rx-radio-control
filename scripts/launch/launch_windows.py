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
import json
from pathlib import Path

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
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_HOST = os.environ.get("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "8080"))
BACKEND_CONNECT_HOST = "127.0.0.1" if BACKEND_HOST == "0.0.0.0" else BACKEND_HOST
BASE_URL = f"http://{BACKEND_CONNECT_HOST}:{BACKEND_PORT}"
REMEMBER_WINDOW_LAYOUT = os.environ.get("OM0RX_REMEMBER_WINDOW_LAYOUT", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
WINDOW_LAYOUT_PATH = PROJECT_ROOT / "settings" / "window_layout.json"
WINDOW_CONFIG = {
    "key": "main",
    "title": "OM0RX Radio Control",
    "url": f"{BASE_URL}/",
    "width": 1500,
    "height": 950,
}
DIGITAL_WINDOW_CONFIG = {
    "key": "digital",
    "title": "OM0RX Radio Control - DIGITAL",
    "url": f"{BASE_URL}/ft8.html",
    "width": 1260,
    "height": 860,
}
VISUAL_MAP_WINDOW_CONFIG = {
    "key": "visual_map",
    "title": "OM0RX Radio Control - Visual Map",
    "url": f"{BASE_URL}/visual-map.html",
    "width": 1320,
    "height": 920,
}
SPOTS_WINDOW_CONFIG = {
    "key": "filters",
    "title": "OM0RX Radio Control - Filters",
    "url": f"{BASE_URL}/spots.html",
    "width": 1320,
    "height": 860,
}
ROTOR_COMPASS_WINDOW_CONFIG = {
    "key": "rotor_compass",
    "title": "OM0RX Radio Control - Compass",
    "url": f"{BASE_URL}/rotor-compass.html",
    "width": 720,
    "height": 760,
}


class WindowLayoutStore:
    """Persist and restore native pywebview window bounds."""

    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._last_save_at = {}
        self._data = self._load()

    def _load(self):
        if not REMEMBER_WINDOW_LAYOUT or not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                return data
        except Exception as exc:
            print(f"⚠️ Could not load window layout: {exc}")
        return {}

    def geometry_for(self, key, defaults):
        geometry = self._data.get(key) if REMEMBER_WINDOW_LAYOUT else None
        if not isinstance(geometry, dict):
            return {}

        restored = {}
        width = self._int_in_range(geometry.get("width"), 360, 4000)
        height = self._int_in_range(geometry.get("height"), 260, 3000)
        x = self._int_in_range(geometry.get("x"), -10000, 10000)
        y = self._int_in_range(geometry.get("y"), -10000, 10000)
        if width:
            restored["width"] = width
        if height:
            restored["height"] = height
        if x is not None:
            restored["x"] = x
        if y is not None:
            restored["y"] = y

        if restored:
            print(f"↔️ Restoring window layout for {key}: {restored}")
        return restored

    def attach(self, key, window):
        if not REMEMBER_WINDOW_LAYOUT or not window:
            return

        def save_now():
            self.save_window(key, window)

        window.events.moved += save_now
        window.events.resized += save_now
        window.events.restored += save_now
        window.events.maximized += save_now
        window.events.closed += save_now

    def save_window(self, key, window, throttle=True):
        if not REMEMBER_WINDOW_LAYOUT or not window:
            return

        now = time.monotonic()
        if throttle and now - self._last_save_at.get(key, 0) < 0.4:
            return
        self._last_save_at[key] = now

        try:
            geometry = {
                "x": int(window.x),
                "y": int(window.y),
                "width": int(window.width),
                "height": int(window.height),
                "maximized": bool(getattr(window, "state", "") == "maximized"),
                "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        except Exception as exc:
            print(f"⚠️ Could not read window geometry for {key}: {exc}")
            return

        if geometry["width"] < 200 or geometry["height"] < 100:
            return

        with self._lock:
            self._data[key] = geometry
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("w", encoding="utf-8") as handle:
                    json.dump(self._data, handle, indent=2)
            except Exception as exc:
                print(f"⚠️ Could not save window layout: {exc}")

    @staticmethod
    def _int_in_range(value, low, high):
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        if low <= parsed <= high:
            return parsed
        return None


LAYOUT_STORE = WindowLayoutStore(WINDOW_LAYOUT_PATH)


def create_managed_window(config, **kwargs):
    """Create a pywebview window with persisted bounds when enabled."""
    key = config["key"]
    options = {
        "title": config["title"],
        "url": config["url"],
        "width": config["width"],
        "height": config["height"],
        "resizable": True,
    }
    options.update(LAYOUT_STORE.geometry_for(key, config))
    options.update(kwargs)
    window = webview.create_window(**options)
    LAYOUT_STORE.attach(key, window)
    return window


class DesktopApi:
    """Small pywebview bridge for opening app-owned secondary windows."""

    def __init__(self):
        self._digital_window = None
        self._visual_map_window = None
        self._spots_window = None
        self._rotor_compass_window = None
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

                self._digital_window = create_managed_window(
                    DIGITAL_WINDOW_CONFIG,
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
                visual_map_config = dict(VISUAL_MAP_WINDOW_CONFIG)
                visual_map_config["url"] = target_url
                self._visual_map_window = create_managed_window(
                    visual_map_config,
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

    def open_spots_window(self):
        """Open or focus the native Filters window without using browser tabs."""
        with self._lock:
            try:
                if self._spots_window:
                    try:
                        self._spots_window.restore()
                        self._spots_window.show()
                        self._spots_window.evaluate_js("window.focus && window.focus();")
                        return {"success": True, "reused": True}
                    except Exception:
                        self._spots_window = None

                self._spots_window = create_managed_window(
                    SPOTS_WINDOW_CONFIG,
                    focus=True,
                )
                print(
                    f"✅ Created window: {SPOTS_WINDOW_CONFIG['title']} -> "
                    f"{SPOTS_WINDOW_CONFIG['url']}"
                )
                return {"success": True, "reused": False}
            except Exception as exc:
                print(f"❌ Failed to create Filters window: {exc}")
                return {"success": False, "error": str(exc)}

    def open_rotor_compass_window(self):
        """Open or focus the native rotor compass window without using browser tabs."""
        with self._lock:
            try:
                if self._rotor_compass_window:
                    try:
                        self._rotor_compass_window.restore()
                        self._rotor_compass_window.show()
                        self._rotor_compass_window.evaluate_js("window.focus && window.focus();")
                        return {"success": True, "reused": True}
                    except Exception:
                        self._rotor_compass_window = None

                self._rotor_compass_window = create_managed_window(
                    ROTOR_COMPASS_WINDOW_CONFIG,
                    focus=True,
                )
                print(
                    f"✅ Created window: {ROTOR_COMPASS_WINDOW_CONFIG['title']} -> "
                    f"{ROTOR_COMPASS_WINDOW_CONFIG['url']}"
                )
                return {"success": True, "reused": False}
            except Exception as exc:
                print(f"❌ Failed to create rotor compass window: {exc}")
                return {"success": False, "error": str(exc)}

    def close_spots_window(self):
        """Close the native Filters window if it is open."""
        with self._lock:
            try:
                if self._spots_window:
                    try:
                        self._spots_window.destroy()
                    finally:
                        self._spots_window = None
                return {"success": True}
            except Exception as exc:
                print(f"❌ Failed to close Filters window: {exc}")
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
        create_managed_window(
            WINDOW_CONFIG,
            js_api=api,
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
