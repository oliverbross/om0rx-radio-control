#!/usr/bin/env python3
"""
FlexRadio Multi-Window Launcher
Launches three synchronized windows using pywebview for a native desktop experience
"""

import sys
import threading
import time
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
    print("   http://localhost:8000/launcher.html")
    sys.exit(1)

# Configuration
BASE_URL = "http://localhost:8000"
WINDOWS_CONFIG = [
    {
        "title": "FlexRadio - Radio Control",
        "url": f"{BASE_URL}/radio-control.html",
        "width": 1000,
        "height": 600,
        "x": 100,
        "y": 100,
    },
    {
        "title": "FlexRadio - Logging & QRZ",
        "url": f"{BASE_URL}/logging.html",
        "width": 1200,
        "height": 700,
        "x": 1150,
        "y": 100,
    },
    {
        "title": "FlexRadio - DX Spots",
        "url": f"{BASE_URL}/spots.html",
        "width": 1400,
        "height": 800,
        "x": 150,
        "y": 750,
    },
]


def launch_windows():
    """Launch all three windows"""
    windows = []
    
    for config in WINDOWS_CONFIG:
        try:
            window = webview.create_window(
                title=config["title"],
                url=config["url"],
                width=config["width"],
                height=config["height"],
                resizable=True
            )
            windows.append(window)
            print(f"✅ Created window: {config['title']}")
        except Exception as e:
            print(f"❌ Failed to create window '{config['title']}': {e}")
    
    if windows:
        print(f"\n🚀 Launching {len(windows)} synchronized windows...")
        print("💡 All windows are connected to the same backend and will sync in real-time")
        print("📝 Tip: You can resize, move, and arrange windows as you like!\n")
        webview.start()
    else:
        print("❌ No windows could be created")
        sys.exit(1)


def check_backend_ready(max_attempts=30, delay=1):
    """Check if backend is ready before launching windows"""
    import socket
    
    print("⏳ Checking if backend is ready...")
    for attempt in range(max_attempts):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', 8000))
            sock.close()
            
            if result == 0:
                print("✅ Backend is ready!\n")
                return True
            
            if attempt == 0:
                print(f"   (will wait up to {max_attempts} seconds...)")
            
        except Exception:
            pass
        
        time.sleep(delay)
    
    print("❌ Backend is not responding on localhost:8000")
    print("   Please make sure the backend app is running:")
    print("   Run: .\\start_all.ps1")
    return False


if __name__ == "__main__":
    # Check if backend is running
    if not check_backend_ready():
        sys.exit(1)
    
    # Launch windows
    launch_windows()
