#!/usr/bin/env python3
"""
Test script to verify LOTW field is correctly extracted from ADIF
"""

import asyncio
import sys
sys.path.insert(0, r'c:\Projects\om0rx-radio-control')

from wavelog_api import WavelogClient

async def test():
    client = WavelogClient()
    
    print("Testing LOTW field extraction...")
    print("=" * 60)
    
    # Test with a callsign that we know has data
    test_callsign = "OM0AAO"
    
    result = await client.get_recent_qsos(test_callsign, limit=5)
    
    if result.get('success'):
        qsos = result.get('data', [])
        print(f"\n✅ Found {len(qsos)} QSOs for {test_callsign}")
        
        for idx, qso in enumerate(qsos, 1):
            print(f"\nQSO {idx}:")
            print(f"  Date: {qso.get('qso_date')}")
            print(f"  Callsign: {qso.get('call')}")
            print(f"  Mode: {qso.get('mode')}")
            print(f"  Band: {qso.get('band')}")
            print(f"  RST Sent: {qso.get('rst_sent')}")
            print(f"  RST Rcvd: {qso.get('rst_rcvd')}")
            print(f"  LOTW: {qso.get('lotw_qsl')}")  # THIS IS THE KEY FIELD
    else:
        print(f"❌ Failed to get QSOs: {result.get('message')}")

if __name__ == "__main__":
    asyncio.run(test())