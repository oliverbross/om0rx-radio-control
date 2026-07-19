#!/usr/bin/env python3
"""
Test script to verify WSJT-X QSO logging with ADIF backup
"""

import asyncio
import json

import _bootstrap  # noqa: F401
from services.wsjtx import WSJTXService
from radio_control.adif_handler import ADIFHandler
from radio_control.wavelog_api import WavelogClient
from radio_control.qrz_api import QRZClient
from radio_control.cty_resolvers import CtyDatResolver


async def test_wsjtx_qso_with_adif():
    """Test WSJT-X QSO logging with ADIF backup"""
    
    print("🧪 Testing WSJT-X QSO logging with ADIF backup...")
    print("=" * 60)
    
    # Initialize dependencies
    print("\n1️⃣  Initializing dependencies...")
    try:
        wavelog_client = WavelogClient()
        print("   ✅ WavelogClient initialized")
    except Exception as e:
        print(f"   ❌ WavelogClient init failed: {e}")
        wavelog_client = None
    
    try:
        qrz_client = QRZClient()
        print("   ✅ QRZClient initialized")
    except Exception as e:
        print(f"   ❌ QRZClient init failed: {e}")
        qrz_client = None
    
    try:
        cty_resolver = CtyDatResolver()
        print("   ✅ CtyDatResolver initialized")
    except Exception as e:
        print(f"   ❌ CtyDatResolver init failed: {e}")
        cty_resolver = None
    
    try:
        rotor = None  # Not needed for this test
        adif_handler = ADIFHandler()
        print("   ✅ ADIFHandler initialized")
        print(f"      Log path: {adif_handler.log_path}")
    except Exception as e:
        print(f"   ❌ ADIFHandler init failed: {e}")
        adif_handler = None
    
    # Initialize WSJT-X service
    print("\n2️⃣  Initializing WSJT-X service...")
    service = WSJTXService()
    service.set_dependencies(wavelog_client, qrz_client, rotor, cty_resolver, adif_handler)
    print("   ✅ WSJT-X service configured")
    
    # Check ADIF handler is set
    if service.adif_handler:
        print(f"   ✅ ADIF handler is SET: {service.adif_handler}")
    else:
        print("   ❌ ADIF handler is NOT SET!")
    
    # Simulate a WSJT-X QSO (similar to your screenshot)
    print("\n3️⃣  Simulating WSJT-X QSO...")
    qso_request = {
        'call': 'BD6IIC',
        'frequency_hz': 24916000,  # 24.916 MHz
        'mode': 'FT8',
        'grid': 'OM63aa',
        'rst_sent': '-07',
        'rst_received': '-06',
        'comments': 'Test QSO from WSJT-X'
    }
    print(f"   QSO: {qso_request['call']} on {qso_request['frequency_hz']/1_000_000} MHz {qso_request['mode']}")
    
    # Log the QSO
    print("\n4️⃣  Logging QSO...")
    try:
        result = await service.log_qso(qso_request)
        print(f"   Result: {json.dumps(result, indent=2)}")
        
        if result.get('adif_saved'):
            print("   ✅ QSO saved to ADIF!")
        else:
            print("   ❌ QSO NOT saved to ADIF")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Check ADIF file
    print("\n5️⃣  Checking ADIF file...")
    if adif_handler and adif_handler.log_path.exists():
        count = adif_handler.read_qso_count()
        print(f"   ✅ ADIF file exists: {adif_handler.log_path}")
        print(f"   📊 Total QSOs in file: {count}")
        
        # Show last few lines
        try:
            with open(adif_handler.log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                print("\n   📄 Last 20 lines of ADIF file:")
                for line in lines[-20:]:
                    print(f"      {line.rstrip()}")
        except Exception as e:
            print(f"   ❌ Failed to read file: {e}")
    else:
        print("   ❌ ADIF file does not exist or handler not set")
    
    print("\n" + "=" * 60)
    print("✅ Test completed!")


if __name__ == "__main__":
    asyncio.run(test_wsjtx_qso_with_adif())
