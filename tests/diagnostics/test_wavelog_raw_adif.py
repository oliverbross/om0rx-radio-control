#!/usr/bin/env python3
"""
Check the raw ADIF response from Wavelog
"""
import asyncio
import json
import aiohttp
import config

async def main():
    api_url = config.WAVELOG_API_URL
    api_key = config.WAVELOG_API_KEY
    station_id = config.WAVELOG_STATION_ID
    
    endpoint = f"{api_url}/api/get_contacts_adif"
    
    payload = {
        'key': api_key,
        'station_id': station_id,
        'fetchfromid': -1,
        'limit': 5
    }
    
    print(f"Querying: {endpoint}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print("\n" + "="*80 + "\n")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                response_text = await resp.text()
                print(f"Status: {resp.status}")
                print(f"Response ({len(response_text)} chars):\n")
                print(response_text[:2000])  # Print first 2000 chars
                
                if resp.status == 200:
                    try:
                        result = json.loads(response_text)
                        print(f"\n\nParsed JSON keys: {list(result.keys())}")
                        print(f"Message: {result.get('message')}")
                        print(f"Exported QSOs: {result.get('exported_qsos')}")
                        adif = result.get('adif', '')
                        print(f"\nADIF length: {len(adif)}")
                        print(f"First 1500 chars of ADIF:\n{adif[:1500]}")
                    except:
                        print("\nFailed to parse JSON")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    asyncio.run(main())