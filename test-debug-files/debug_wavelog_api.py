#!/usr/bin/env python3
"""Debug Wavelog API endpoint"""

import aiohttp
import asyncio
import json

async def test_api():
    api_url = "https://om0rx.wavelog.online/index.php"
    api_key = "<wavelog_api_key>"
    callsign = "OM0AAO"
    
    # Try with /api/private_lookup
    endpoint = f"{api_url}/api/private_lookup"
    print(f"Testing endpoint: {endpoint}")
    print(f"Payload: {{'key': '<wavelog_api_key>', 'callsign': '{callsign}'}}")
    print()
    
    payload = {
        'key': api_key,
        'callsign': callsign
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                endpoint, 
                json=payload, 
                timeout=aiohttp.ClientTimeout(total=10),
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'}
            ) as resp:
                print(f"Status: {resp.status}")
                print(f"Content-Type: {resp.headers.get('content-type')}")
                response_text = await resp.text()
                print(f"\nResponse ({len(response_text)} bytes):")
                print(response_text[:1000])
                
                # Try to parse as JSON
                try:
                    data = json.loads(response_text)
                    print(f"\nJSON Parsed Successfully:")
                    print(json.dumps(data, indent=2))
                except:
                    print(f"\nCould not parse as JSON")
    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_api())