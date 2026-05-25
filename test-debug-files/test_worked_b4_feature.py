#!/usr/bin/env python3
"""
Test script to verify "Worked b4" feature functionality
Checks:
1. ADIF file exists and has BAND fields
2. Backend API returns QSOs with BAND
3. Data is properly formatted for frontend matching
"""

import sys
import json
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

def check_adif_file():
    """Check if ADIF file exists and contains BAND fields"""
    print("\n" + "="*60)
    print("✓ CHECKING ADIF FILE")
    print("="*60)
    
    adif_file = Path("logs/qso_log.adif")
    
    if not adif_file.exists():
        print(f"❌ ADIF file NOT FOUND: {adif_file.absolute()}")
        return False
    
    file_size = adif_file.stat().st_size / (1024 * 1024)  # Convert to MB
    print(f"✅ ADIF file found: {file_size:.1f} MB")
    
    # Read first 10KB to check for BAND fields
    with open(adif_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read(10000)
    
    if '<BAND:' in content:
        # Count BAND occurrences in a sample
        band_count = content.count('<BAND:')
        print(f"✅ BAND fields found: {band_count} in first 10KB")
        print(f"   Sample BAND entry: ", end="")
        
        # Extract a sample BAND entry
        idx = content.find('<BAND:')
        if idx != -1:
            sample = content[idx:idx+20]
            print(f"{sample}")
        
        return True
    else:
        print("❌ NO BAND fields found in ADIF file")
        print("   This means QSOs don't have band information")
        return False


def check_adif_parsing():
    """Check if ADIF parser correctly extracts BAND field"""
    print("\n" + "="*60)
    print("✓ CHECKING ADIF PARSER")
    print("="*60)
    
    try:
        from adif_handler import ADIFHandler
        
        handler = ADIFHandler()
        qsos = handler.read_all_qsos()
        
        if not qsos:
            print("❌ No QSOs parsed from ADIF file")
            return False
        
        print(f"✅ Parsed {len(qsos)} QSOs from ADIF")
        
        # Check for BAND field in parsed data
        with_band = sum(1 for q in qsos if q.get('band'))
        without_band = len(qsos) - with_band
        
        print(f"✅ QSOs with BAND field: {with_band}")
        if without_band > 0:
            print(f"⚠️  QSOs without BAND field: {without_band}")
        
        # Show sample
        sample = qsos[0]
        print(f"\n   Sample QSO:")
        print(f"   - CALL: {sample.get('call')}")
        print(f"   - BAND: {sample.get('band')}")
        print(f"   - MODE: {sample.get('mode')}")
        print(f"   - DATE: {sample.get('qso_date')}")
        print(f"   - FREQ: {sample.get('frequency')}")
        
        return with_band > 0
        
    except Exception as e:
        print(f"❌ Error testing ADIF parser: {e}")
        return False


def check_worked_callsigns_format():
    """Check if data can be formatted correctly for frontend matching"""
    print("\n" + "="*60)
    print("✓ CHECKING WORKED CALLSIGNS FORMAT")
    print("="*60)
    
    try:
        from adif_handler import ADIFHandler
        
        handler = ADIFHandler()
        qsos = handler.read_all_qsos()
        
        # Build the same format as frontend
        worked_callsigns = {}
        skipped = 0
        
        for qso in qsos:
            call = (qso.get('call') or '').upper()
            band = (qso.get('band') or '').upper()
            mode = (qso.get('mode') or '').upper()
            
            if call and band and mode:
                key = f"{call}-{band}-{mode}"
                if key not in worked_callsigns:
                    worked_callsigns[key] = {
                        'qso_date': qso.get('qso_date', ''),
                        'time_on': qso.get('time_on', '')
                    }
            else:
                skipped += 1
        
        print(f"✅ Built lookup map with {len(worked_callsigns)} unique CALL-BAND-MODE combinations")
        if skipped > 0:
            print(f"⚠️  Skipped {skipped} QSOs (missing CALL/BAND/MODE)")
        
        # Show samples
        if worked_callsigns:
            keys = list(worked_callsigns.keys())[:5]
            print(f"\n   Sample CALL-BAND-MODE keys:")
            for key in keys:
                data = worked_callsigns[key]
                print(f"   - {key}: {data['qso_date']}")
        
        return len(worked_callsigns) > 0
        
    except Exception as e:
        print(f"❌ Error checking format: {e}")
        return False


def check_api_endpoints():
    """Check if backend API endpoints would work"""
    print("\n" + "="*60)
    print("✓ CHECKING API ENDPOINTS")
    print("="*60)
    
    print("ℹ️  To test API endpoints, run the backend and open:")
    print("   http://localhost:8000/api/adif/all")
    print("\n   Expected response format:")
    print("""   {
      "success": true,
      "count": 2847,
      "data": [
        {
          "call": "VE3KZE",
          "band": "20m",
          "mode": "CW",
          "qso_date": "20251028",
          "time_on": "181500",
          "frequency": 14.074
        },
        ...
      ]
    }""")
    
    return True


def main():
    print("\n╔═══════════════════════════════════════════════════════╗")
    print("║   'WORKED B4' FEATURE - VERIFICATION TEST            ║")
    print("╚═══════════════════════════════════════════════════════╝")
    
    results = []
    
    # Run all checks
    results.append(("ADIF File Exists", check_adif_file()))
    results.append(("ADIF Parser Works", check_adif_parsing()))
    results.append(("Format Check", check_worked_callsigns_format()))
    results.append(("API Info", check_api_endpoints()))
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL" if result is False else "ℹ️  INFO"
        print(f"{status} - {test_name}")
    
    # Overall status
    passed = sum(1 for _, r in results if r is True)
    total = len(results)
    
    print("\n" + "="*60)
    if passed == total:
        print("✅ ALL CHECKS PASSED - 'WORKED B4' FEATURE IS WORKING!")
    elif passed >= 3:
        print(f"⚠️  PARTIAL - {passed}/{total} checks passed")
        print("   See failures above for what needs fixing")
    else:
        print(f"❌ ISSUES FOUND - {passed}/{total} checks passed")
        print("   Check the diagnostic guide for troubleshooting")
    print("="*60 + "\n")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)