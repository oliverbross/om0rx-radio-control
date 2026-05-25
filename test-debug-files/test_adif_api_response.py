#!/usr/bin/env python3
"""
Test script to check what the get_contacts_adif API returns
"""

import asyncio
import aiohttp
import json
from config import WAVELOG_API_URL, WAVELOG_API_KEY, WAVELOG_STATION_ID

async def test():
    endpoint = f"{WAVELOG_API_URL}/api/get_contacts_adif"
    
    payload = {
        'key': WAVELOG_API_KEY,
        'station_id': WAVELOG_STATION_ID,
        'fetchfromid': 0
    }
    
    print(f"Testing endpoint: {endpoint}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    async with aiohttp.ClientSession() as session:
        async with session.post(endpoint, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            print(f"Status: {resp.status}")
            text = await resp.text()
            print(f"Response length: {len(text)} bytes")
            print(f"First 500 chars:\n{text[:500]}")
            
            # Try to parse as JSON
            try:
                data = json.loads(text)
                print(f"\nJSON keys: {list(data.keys())}")
                
                # Check for ADIF key
                if 'adif' in data:
                    adif_data = data['adif']
                    print(f"ADIF size: {len(adif_data)} bytes")
                    print(f"ADIF first 300 chars:\n{adif_data[:300]}")
                    
                    # Count EOR tags
                    eor_count = adif_data.count('<EOR>')
                    eor_lower_count = adif_data.count('<eor>')
                    print(f"\nEOR tags (uppercase): {eor_count}")
                    print(f"eor tags (lowercase): {eor_lower_count}")
                    
                    # Check if any data
                    if eor_count == 0 and eor_lower_count == 0:
                        print("WARNING: No EOR tags found!")
                else:
                    print("No ADIF key found in response")
                    print(f"Available keys: {list(data.keys())}")
                    
                    # Print the whole response if it's small
                    if len(text) < 2000:
                        print(f"Full response:\n{text}")
                        
            except json.JSONDecodeError as e:
                print(f"Could not parse as JSON: {e}")
                
                # Check if it's ADIF data directly
                if '<' in text[:100]:
                    print("Response looks like ADIF data (contains < symbols)")
                    eor_count = text.count('<EOR>')
                    eor_lower_count = text.count('<eor>')
                    print(f"EOR tags (uppercase): {eor_count}")
                    print(f"eor tags (lowercase): {eor_lower_count}")

if __name__ == "__main__":
    asyncio.run(test())