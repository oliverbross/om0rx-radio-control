#!/usr/bin/env python3
"""
Verify that the Wavelog API fix returns NEWEST (most recent) contacts first.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from wavelog_api import WavelogClient

async def test_newest_contacts():
    """Verify API returns newest contacts first"""
    print("=" * 70)
    print("WAVELOG API FIX VERIFICATION - Latest Contacts Test")
    print("=" * 70)
    
    client = WavelogClient()
    
    try:
        result = await client.get_contacts_from_wavelog_api(limit=100)
        
        if result.get('success'):
            qsos = result.get('data', [])
            print(f"\n✅ Successfully retrieved {len(qsos)} contacts from Wavelog\n")
            
            if qsos:
                print("NEWEST (First 5 contacts - should be from February 2025):")
                print("-" * 70)
                for i, qso in enumerate(qsos[:5], 1):
                    qso_date = qso.get('qso_date', 'UNKNOWN')  # YYYYMMDD format
                    time_on = qso.get('time_on', 'UNKNOWN')     # HHMMSS format
                    call = qso.get('call', 'UNKNOWN')
                    country = qso.get('country', 'UNKNOWN')
                    name = qso.get('name', 'UNKNOWN')
                    mode = qso.get('mode', 'UNKNOWN')
                    freq = qso.get('frequency', 'UNKNOWN')
                    
                    # Format date nicely if valid
                    if qso_date != 'UNKNOWN' and len(qso_date) == 8:
                        formatted_date = f"{qso_date[0:4]}-{qso_date[4:6]}-{qso_date[6:8]}"
                    else:
                        formatted_date = qso_date
                    
                    print(f"  {i:2}. {formatted_date} {time_on} - {call:8} ({country:30}) - {name}")
                
                print("\nOLDEST (Last 5 contacts - should be from October 2022):")
                print("-" * 70)
                for i, qso in enumerate(qsos[-5:], len(qsos)-4):
                    qso_date = qso.get('qso_date', 'UNKNOWN')
                    time_on = qso.get('time_on', 'UNKNOWN')
                    call = qso.get('call', 'UNKNOWN')
                    country = qso.get('country', 'UNKNOWN')
                    name = qso.get('name', 'UNKNOWN')
                    
                    if qso_date != 'UNKNOWN' and len(qso_date) == 8:
                        formatted_date = f"{qso_date[0:4]}-{qso_date[4:6]}-{qso_date[6:8]}"
                    else:
                        formatted_date = qso_date
                    
                    print(f"  {i:2}. {formatted_date} {time_on} - {call:8} ({country:30}) - {name}")
                
                # Analyze date range
                first_qso_date = qsos[0].get('qso_date', '')
                last_qso_date = qsos[-1].get('qso_date', '')
                
                if first_qso_date and last_qso_date:
                    try:
                        first_dt = datetime.strptime(first_qso_date, '%Y%m%d')
                        last_dt = datetime.strptime(last_qso_date, '%Y%m%d')
                        
                        if first_dt >= last_dt:
                            print(f"\n✅ CORRECT: Contacts are newest-first! ({first_qso_date} → {last_qso_date})")
                            print(f"   Newest: {first_dt.strftime('%B %d, %Y')}")
                            print(f"   Oldest: {last_dt.strftime('%B %d, %Y')}")
                            print(f"   Span: {(first_dt - last_dt).days} days")
                        else:
                            print(f"\n❌ ERROR: Contacts are oldest-first! ({first_qso_date} → {last_qso_date})")
                    except Exception as e:
                        print(f"\n⚠️  Could not parse dates: {e}")
                else:
                    print(f"\n⚠️  Date fields are missing or empty")
            else:
                print("No contacts retrieved")
        else:
            print(f"❌ API Error: {result.get('message')}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_newest_contacts())