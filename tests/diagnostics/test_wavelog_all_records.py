#!/usr/bin/env python3
"""
Test Wavelog API to see:
1. How many total QSOs the user has
2. What date range they span
"""
import asyncio
import json
import aiohttp
import config
from wavelog_api import WavelogClient

async def main():
    client = WavelogClient()
    
    # Request 100 QSOs
    print("Fetching 100 QSOs from Wavelog (should be oldest to newest after reverse)...\n")
    result = await client.get_contacts_from_wavelog_api(limit=100)
    
    if result.get('success'):
        qsos = result.get('data', [])
        print(f"✅ Retrieved {len(qsos)} QSOs\n")
        
        if qsos:
            # Show first 3 (should be newest after reverse)
            print("FIRST 3 (should be newest):")
            for i in range(min(3, len(qsos))):
                qso = qsos[i]
                print(f"  {i+1}. {qso.get('qso_date')} {qso.get('time_on')} - {qso.get('call')} from {qso.get('country')}")
            
            print("\nLAST 3 (should be oldest):")
            for i in range(max(0, len(qsos)-3), len(qsos)):
                qso = qsos[i]
                print(f"  {i+1}. {qso.get('qso_date')} {qso.get('time_on')} - {qso.get('call')} from {qso.get('country')}")
            
            # Extract dates
            dates = [qso.get('qso_date', '') for qso in qsos if qso.get('qso_date')]
            if dates:
                dates_sorted = sorted(dates)
                print(f"\n📅 Date range: {dates_sorted[0]} to {dates_sorted[-1]}")
                print(f"   In {len(qsos)} QSOs, you have {len(set(dates))} unique dates")
    else:
        print(f"❌ Error: {result.get('message')}")

if __name__ == '__main__':
    asyncio.run(main())