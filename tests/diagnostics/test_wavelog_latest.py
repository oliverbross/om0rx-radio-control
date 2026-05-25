#!/usr/bin/env python3
"""
Quick test to see what Wavelog API returns for fetchfromid=0
"""
import asyncio
import json
from wavelog_api import WavelogClient

async def main():
    client = WavelogClient()
    print("Testing Wavelog API...")
    result = await client.get_contacts_from_wavelog_api(limit=5)
    
    if result.get('success'):
        qsos = result.get('data', [])
        print(f"\n✅ Got {len(qsos)} QSOs:")
        for i, qso in enumerate(qsos):
            print(f"\n{i+1}. Date: {qso.get('qso_date')} Time: {qso.get('time_on')} Call: {qso.get('call')}")
            print(f"   Country: {qso.get('country')} Name: {qso.get('name')}")
    else:
        print(f"❌ Error: {result.get('message')}")

if __name__ == '__main__':
    asyncio.run(main())