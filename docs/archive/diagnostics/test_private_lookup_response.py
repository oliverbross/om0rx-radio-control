#!/usr/bin/env python3
"""
Test script to see what the private_lookup endpoint returns
"""

import asyncio
import aiohttp
import json
from radio_control.config import WAVELOG_API_URL, WAVELOG_API_KEY, WAVELOG_STATION_ID

async def test_private_lookup():
    """Test the /api/private_lookup endpoint"""
    
    endpoint = f"{WAVELOG_API_URL}/api/private_lookup"
    
    payload = {
        'key': WAVELOG_API_KEY,
        'callsign': 'MM3RA'
    }
    
    print(f"Testing private_lookup for MM3RA")
    print(f"Endpoint: {endpoint}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                endpoint,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'}
            ) as resp:
                print(f"\nStatus: {resp.status}")
                print(f"Content-Type: {resp.headers.get('Content-Type', 'N/A')}")
                
                text = await resp.text()
                print(f"\nRaw response (first 2000 chars):\n{text[:2000]}")
                
                if resp.status == 200:
                    try:
                        data = json.loads(text)
                        print(f"\n✅ JSON parsed successfully")
                        print(f"\nFull response (formatted):\n{json.dumps(data, indent=2)}")
                    except json.JSONDecodeError as e:
                        print(f"\n❌ Failed to parse JSON: {e}")
        except Exception as e:
            print(f"\n❌ Request failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_private_lookup())