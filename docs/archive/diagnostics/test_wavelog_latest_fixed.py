#!/usr/bin/env python3
"""
Test script to verify the Wavelog API fix retrieves the LATEST (newest) contacts.
This tests the discovery-based approach to fetch only the most recent 100 QSOs.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from radio_control.wavelog_api import WavelogClient

async def test_latest_contacts():
    """Test fetching latest contacts with the fixed API"""
    print("=" * 60)
    print("Testing Wavelog API Fix - Fetching Latest Contacts")
    print("=" * 60)
    
    client = WavelogClient()
    
    try:
        print("\n📡 Calling get_contacts_from_wavelog_api(limit=100)...")
        result = await client.get_contacts_from_wavelog_api(limit=100)
        
        if result.get('success'):
            qsos = result.get('data', [])
            print(f"\n✅ Successfully retrieved {len(qsos)} contacts\n")
            
            if qsos:
                print("NEWEST (First 3 contacts):")
                print("-" * 60)
                for i, qso in enumerate(qsos[:3], 1):
                    print(f"{i}. {qso.get('datetime')} - {qso.get('callsign')} from {qso.get('country')} ({qso.get('name')})")
                
                print("\n...and OLDEST (Last 3 contacts):")
                print("-" * 60)
                for i, qso in enumerate(qsos[-3:], len(qsos)-2):
                    print(f"{i}. {qso.get('datetime')} - {qso.get('callsign')} from {qso.get('country')} ({qso.get('name')})")
                
                # Verify ordering
                first_date = qsos[0].get('datetime')
                last_date = qsos[-1].get('datetime')
                print(f"\n📅 Date range: {last_date} to {first_date}")
                print(f"✓ Contacts are in newest-first order: {first_date >= last_date}")
            else:
                print("No contacts retrieved")
        else:
            print(f"❌ API Error: {result.get('message')}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_latest_contacts())