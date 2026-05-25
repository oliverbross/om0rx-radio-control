#!/usr/bin/env python3
"""
Debug script to test Wavelog API directly
Run this to see what the API is returning and help debug the issue
"""

import asyncio
import aiohttp
import json
import logging
from radio_control.config import WAVELOG_API_URL, WAVELOG_API_KEY, WAVELOG_STATION_ID
from radio_control.wavelog_api import WavelogClient

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s | %(levelname)-8s | %(message)s'
)
logger = logging.getLogger(__name__)

async def test_api():
    """Test the Wavelog API directly"""
    
    logger.info("=" * 80)
    logger.info("WAVELOG API DEBUG TEST")
    logger.info("=" * 80)
    
    # Show config
    logger.info(f"API URL: {WAVELOG_API_URL}")
    logger.info(f"API Key: {WAVELOG_API_KEY[:20]}..." if WAVELOG_API_KEY else "NOT SET")
    logger.info(f"Station ID: {WAVELOG_STATION_ID}")
    logger.info("")
    
    # Test the client
    client = WavelogClient()
    
    logger.info("🌐 Calling get_contacts_from_wavelog_api(limit=100)...")
    result = await client.get_contacts_from_wavelog_api(limit=100)
    
    logger.info("")
    logger.info("=" * 80)
    logger.info("RESULT:")
    logger.info("=" * 80)
    logger.info(f"Success: {result.get('success')}")
    logger.info(f"Message: {result.get('message')}")
    
    if result.get('success') and result.get('data'):
        data = result.get('data', [])
        logger.info(f"Number of contacts: {len(data)}")
        logger.info("")
        
        if data:
            logger.info("First contact:")
            logger.info(json.dumps(data[0], indent=2))
            logger.info("")
            
            logger.info(f"All fields in first contact: {list(data[0].keys())}")
            logger.info("")
            
            logger.info("Sample of first 3 contacts:")
            for i, qso in enumerate(data[:3]):
                logger.info(f"  {i+1}. {qso.get('call', 'N/A')} - {qso.get('qso_date', 'N/A')} {qso.get('time_on', 'N/A')} - {qso.get('frequency', 'N/A')} MHz")
    else:
        logger.error(f"Error: {result.get('message')}")

if __name__ == '__main__':
    asyncio.run(test_api())