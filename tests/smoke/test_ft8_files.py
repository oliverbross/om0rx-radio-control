"""Verify the built-in FT8 frontend ships only the supported engine assets."""

from pathlib import Path
import sys

def test_ft8_files():
    """Verify all required FT8 files exist"""
    
    frontend = Path(__file__).resolve().parents[2] / "frontend"
    
    required_files = {
        # Core FT8 files
        "js/ft8-engine.js": "FT8 engine boundary",
        "js/ft8-modal.js": "FT8 modal UI controller",
        
        # MIT ft8_lib wrapper files
        "ft8_extra.js": "LDPC matrices and FT8 constants",
        "ft8_ft8lib.js": "ft8_lib WASM wrapper",
        
        # Support libraries (copied from ft8play)
        "HamGridSquare.js": "Grid square coordinate conversion",
        "ft8_hashmgr.js": "Callsign hash management",
        "ctydata.js": "Country/prefix data",
        
        # WASM modules
        "ft8lib/ft8_wasm.js": "ft8_lib JavaScript loader",
        "ft8lib/ft8_wasm.wasm": "ft8_lib WASM binary (MIT license)",
        "ft8lib/LICENSE": "ft8_lib license file",
    }

    retired_files = [
        "js/ft8-decoder.js",
        "mshv_ft8_wrap.js",
        "mshv/mshv_ft8.js",
        "mshv/mshv_ft8.wasm",
        "mshv/COPYING.txt",
    ]
    
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
    
    if not all_ok:
        print("❌ MISSING FILES DETECTED")
        print()
        print("Check frontend/ and restore missing tracked assets from Git.")
        print()
    else:
        print("✅ ALL FILES PRESENT - Ready to start backend")

    assert all_ok, "Missing required FT8 decoder frontend files"
    for retired_file in retired_files:
        assert not (frontend / retired_file).exists(), f"Retired FT8 asset is still present: {retired_file}"

if __name__ == "__main__":
    try:
        test_ft8_files()
    except AssertionError:
        sys.exit(1)
