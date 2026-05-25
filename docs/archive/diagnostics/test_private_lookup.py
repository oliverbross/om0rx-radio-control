#!/usr/bin/env python3
"""
Test Wavelog Private Lookup API Integration
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from radio_control import config
from radio_control.wavelog_api import WavelogClient

async def test_private_lookup():
    """Test the private_lookup method"""
    
    print("=" * 60)
    print("Testing Wavelog Private Lookup API")
    print("=" * 60)
    
    client = WavelogClient()
    
    # Test 1: Basic lookup without band/mode
    print("\n✓ Test 1: Basic lookup (no band/mode)")
    result = await client.private_lookup("IK0FFU")
    if result['success']:
        data = result['data']
        print(f"  Callsign: {data.get('callsign')}")
        print(f"  DXCC: {data.get('dxcc')} {data.get('dxcc_flag')}")
        print(f"  Name: {data.get('name')}")
        print(f"  Grid: {data.get('gridsquare')}")
        print(f"  Worked: {data.get('call_worked')}")
        print(f"  DXCC Confirmed: {data.get('dxcc_confirmed')}")
        print(f"  LoTW Member: {data.get('lotw_member')}")
    else:
        print(f"  ERROR: {result.get('message')}")
    
    # Test 2: Lookup with band
    print("\n✓ Test 2: Lookup with band (20m)")
    result = await client.private_lookup("IK0FFU", band="20m")
    if result['success']:
        data = result['data']
        print(f"  Callsign: {data.get('callsign')}")
        print(f"  Worked on 20m: {data.get('call_worked_band')}")
        print(f"  DXCC Confirmed on 20m: {data.get('dxcc_confirmed_on_band')}")
    else:
        print(f"  ERROR: {result.get('message')}")
    
    # Test 3: Lookup with band and mode
    print("\n✓ Test 3: Lookup with band and mode (20m SSB)")
    result = await client.private_lookup("IK0FFU", band="20m", mode="SSB")
    if result['success']:
        data = result['data']
        print(f"  Callsign: {data.get('callsign')}")
        print(f"  Worked on 20m SSB: {data.get('call_worked_band_mode')}")
        print(f"  DXCC Confirmed on 20m SSB: {data.get('dxcc_confirmed_on_band_mode')}")
    else:
        print(f"  ERROR: {result.get('message')}")
    
    print("\n" + "=" * 60)
    print("✅ Private Lookup API Tests Complete!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_private_lookup())