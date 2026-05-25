#!/usr/bin/env python3
"""
Test caching performance - measure time for first vs subsequent calls
"""

import asyncio
import time
from wavelog_api import WavelogClient

async def test():
    client = WavelogClient()
    
    callsign = "SV2HJQ"
    
    print("="*70)
    print("Testing ADIF Cache Performance")
    print("="*70)
    
    # First call - should download and cache
    print(f"\n1️⃣ First call (CACHE MISS - will download from Wavelog)...")
    start = time.time()
    result1 = await client._get_recent_qsos_internal(callsign)
    elapsed1 = time.time() - start
    
    if result1.get('success'):
        print(f"   ✅ Got {len(result1['data'])} QSOs in {elapsed1:.2f} seconds")
    else:
        print(f"   ❌ Failed: {result1.get('message')}")
    
    # Second call - should use cache
    print(f"\n2️⃣ Second call (CACHE HIT - will use cached data)...")
    start = time.time()
    result2 = await client._get_recent_qsos_internal(callsign)
    elapsed2 = time.time() - start
    
    if result2.get('success'):
        print(f"   ✅ Got {len(result2['data'])} QSOs in {elapsed2:.2f} seconds")
    else:
        print(f"   ❌ Failed: {result2.get('message')}")
    
    # Third call - should use cache
    print(f"\n3️⃣ Third call (CACHE HIT - will use cached data)...")
    start = time.time()
    result3 = await client._get_recent_qsos_internal("OM0AAO")
    elapsed3 = time.time() - start
    
    if result3.get('success'):
        print(f"   ✅ Got {len(result3['data'])} QSOs in {elapsed3:.2f} seconds")
    else:
        print(f"   ❌ Failed: {result3.get('message')}")
    
    # Summary
    print(f"\n" + "="*70)
    print(f"Summary:")
    print(f"  First call (download):  {elapsed1:.2f}s")
    print(f"  Second call (cached):   {elapsed2:.2f}s ({elapsed1/elapsed2:.1f}x faster)")
    print(f"  Third call (cached):    {elapsed3:.2f}s ({elapsed1/elapsed3:.1f}x faster)")
    print("="*70)

if __name__ == "__main__":
    asyncio.run(test())