#!/usr/bin/env python3
"""
Quick test to verify QSO logging works correctly
"""
import asyncio
import aiohttp
import json
from datetime import datetime

# Sample QSO data (similar to what frontend sends)
test_qso = {
    "callsign": "W1ABC",
    "frequency": 14.250,  # MHz
    "mode": "SSB",
    "rst_sent": 59,
    "rst_received": 59,
    "date": "2025-01-18",
    "time_off": "20:30:00",
    "name": "Test User",
    "qth": "Test QTH",
    "gridsquare": "FN20",
    "notes": "Test QSO",
    "pota": "",
    "sota": "",
    "iota": "",
    "wwff": ""
}

async def test_qso_logging():
    """Test the QSO logging endpoint"""
    url = "http://localhost:8000/api/qso/log"
    
    print(f"Testing QSO logging to {url}")
    print(f"Test data: {json.dumps(test_qso, indent=2)}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, 
                json=test_qso,
                headers={'Content-Type': 'application/json'},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                print(f"\nResponse status: {resp.status}")
                print(f"Response headers: {resp.headers}")
                
                content_type = resp.headers.get('content-type', '')
                if 'application/json' in content_type:
                    data = await resp.json()
                    print(f"Response body: {json.dumps(data, indent=2)}")
                else:
                    text = await resp.text()
                    print(f"Response body (text):\n{text}")
                
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test_qso_logging())