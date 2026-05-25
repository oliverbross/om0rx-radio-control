"""
Test script to verify all FT8 decoder files are present and accessible
Run this before starting the backend to ensure everything is in place
"""

from pathlib import Path
import sys

def test_ft8_files():
    """Verify all required FT8 files exist"""
    
    frontend = Path(__file__).resolve().parents[2] / "frontend"
    
    required_files = {
        # Core FT8 decoder files
        "js/ft8-decoder.js": "Main FT8 decoder service",
        "js/ft8-modal.js": "FT8 modal UI controller",
        
        # ft8play wrapper files
        "ft8_extra.js": "LDPC matrices and FT8 constants",
        "ft8_ft8lib.js": "ft8_lib WASM wrapper",
        "mshv_ft8_wrap.js": "MSHV WASM wrapper",
        
        # Support libraries (copied from ft8play)
        "HamGridSquare.js": "Grid square coordinate conversion",
        "ft8_hashmgr.js": "Callsign hash management",
        "ctydata.js": "Country/prefix data",
        
        # WASM modules
        "ft8lib/ft8_wasm.js": "ft8_lib JavaScript loader",
        "ft8lib/ft8_wasm.wasm": "ft8_lib WASM binary (MIT license)",
        "ft8lib/LICENSE": "ft8_lib license file",
        
        "mshv/mshv_ft8.js": "MSHV JavaScript loader",
        "mshv/mshv_ft8.wasm": "MSHV WASM binary (GPLv3 license)",
        "mshv/COPYING.txt": "MSHV license file",
    }
    
    print("=" * 70)
    print("FT8 DECODER FILES VERIFICATION")
    print("=" * 70)
    print()
    
    all_ok = True
    total_size = 0
    
    for file_path, description in required_files.items():
        full_path = frontend / file_path
        
        if full_path.exists():
            size = full_path.stat().st_size
            total_size += size
            size_kb = size / 1024
            status = "✅"
            details = f"{size_kb:>8.1f} KB"
        else:
            status = "❌ MISSING"
            details = ""
            all_ok = False
        
        print(f"{status}  {file_path:<30} {details:>12}  {description}")
    
    print()
    print("=" * 70)
    print(f"Total size: {total_size / 1024:.1f} KB ({total_size / 1024 / 1024:.2f} MB)")
    print("=" * 70)
    print()
    
    if all_ok:
        print("✅ ALL FILES PRESENT - Ready to start backend")
        print()
        print("Next steps:")
        print("  1. Start backend: python -m backend.main")
        print("  2. Open browser: http://localhost:8000")
        print("  3. Click FT8 button and check console (F12)")
        print("  4. You should see:")
        print("     ✅ ft8_lib WASM module loaded")
        print("     ✅ MSHV WASM module loaded")
        print("     ✅ FT8 Decoder fully initialized")
        return 0
    else:
        print("❌ MISSING FILES DETECTED")
        print()
        print("Check frontend/ and restore missing tracked assets from Git.")
        print()
        return 1

if __name__ == "__main__":
    sys.exit(test_ft8_files())
