"""
Classifier API - QSO classification using Wavelog API (reliable, async)
Replaces direct database access with API-based lookups for more accurate results
"""

import logging
import asyncio
from typing import Tuple, Optional, Dict, Any
from datetime import datetime, timedelta
from radio_control.wavelog_api import WavelogClient

logger = logging.getLogger(__name__)


class ClassifierAPI:
    """
    Classify spots based on worked/confirmed status using Wavelog API.
    Replaces direct MySQL database access with API calls for more reliable results.
    
    Features:
    - Per-callsign API lookups for accurate status
    - LRU cache to minimize API calls
    - Same interface as original Classifier for compatibility
    - Async-compatible for FastAPI integration
    """
    
    def __init__(self, api_client: Optional[WavelogClient] = None):
        """
        Initialize the API-based classifier.
        
        Args:
            api_client: WavelogClient instance (will create one if not provided)
        """
        self.api_client = api_client
        
        # Simple LRU cache for lookups (callsign -> lookup_result)
        self.lookup_cache: Dict[str, Dict[str, Any]] = {}
        self.cache_max_size = 500  # Keep last 500 lookups
        self.cache_ttl = 3600  # Cache for 1 hour
        self.cache_timestamps: Dict[str, datetime] = {}
    
    def _is_cache_valid(self, callsign: str) -> bool:
        """Check if cache entry is still valid"""
        if callsign not in self.cache_timestamps:
            return False
        elapsed = (datetime.utcnow() - self.cache_timestamps[callsign]).total_seconds()
        return elapsed < self.cache_ttl
    
    def _get_cached(self, callsign: str) -> Optional[Dict[str, Any]]:
        """Get cached lookup result if valid"""
        if self._is_cache_valid(callsign):
            logger.debug(f"Using cached lookup for {callsign}")
            return self.lookup_cache.get(callsign)
        else:
            # Remove expired cache entry
            self.lookup_cache.pop(callsign, None)
            self.cache_timestamps.pop(callsign, None)
            return None
    
    def _set_cache(self, callsign: str, data: Dict[str, Any]) -> None:
        """Cache lookup result with LRU eviction"""
        # Implement simple LRU eviction when cache gets too large
        if len(self.lookup_cache) >= self.cache_max_size:
            # Find and remove oldest entry
            oldest_callsign = min(self.cache_timestamps.keys(), 
                                key=lambda k: self.cache_timestamps[k])
            self.lookup_cache.pop(oldest_callsign, None)
            self.cache_timestamps.pop(oldest_callsign, None)
            logger.debug(f"LRU evicted cache entry for {oldest_callsign}")
        
        self.lookup_cache[callsign] = data
        self.cache_timestamps[callsign] = datetime.utcnow()
    
    async def _do_lookup(self, callsign: str, band: Optional[str] = None, 
                        mode: Optional[str] = None) -> Dict[str, Any]:
        """
        Perform Wavelog API lookup for a callsign.
        Returns normalized result for internal use.
        """
        if not self.api_client:
            logger.warning(f"No API client available for lookup of {callsign}")
            return {}
        
        try:
            # Call the private_lookup API method
            result = await self.api_client.private_lookup(callsign, band=band, mode=mode)
            
            if result.get('success'):
                # Extract the data
                data = result.get('data', {})
                logger.debug(f"✅ API lookup successful for {callsign}: worked={data.get('call_worked')}, confirmed={data.get('call_confirmed')}")
                return data
            else:
                logger.debug(f"API lookup failed for {callsign}: {result.get('message')}")
                return {}
        
        except Exception as e:
            logger.error(f"Error during API lookup for {callsign}: {str(e)}")
            return {}
    
    async def call_overall(self, callsign: str) -> Tuple[bool, bool]:
        """
        Check if call is worked and/or confirmed overall.
        
        Args:
            callsign: The callsign to check
        
        Returns:
            Tuple of (worked, confirmed)
        """
        callsign_upper = (callsign or "").upper()
        
        # Check cache first
        cached = self._get_cached(callsign_upper)
        if cached is not None:
            return (cached.get('call_worked', False), 
                   cached.get('call_confirmed', False))
        
        # Do API lookup
        data = await self._do_lookup(callsign_upper)
        
        # Cache result
        if data:
            self._set_cache(callsign_upper, data)
            worked = data.get('call_worked', False)
            confirmed = data.get('call_confirmed', False)
            return worked, confirmed
        
        # No data available - treat as not worked/not confirmed
        return False, False
    
    async def call_bandmode_flags(self, callsign: str, band: str, 
                                  mode: str) -> Tuple[bool, bool, bool]:
        """
        Check call band/mode specific flags.
        
        Args:
            callsign: The callsign to check
            band: Band designation (e.g., "20m", "40m")
            mode: Mode designation (e.g., "SSB", "CW")
        
        Returns:
            Tuple of (new_band, new_mode, bandmode_conf)
            - new_band: True if this band is new for this call
            - new_mode: True if this mode is new for this call on this band
            - bandmode_conf: True if this band+mode is confirmed for this call
        """
        callsign_upper = (callsign or "").upper()
        
        # Check cache first
        cache_key = f"{callsign_upper}_{band}_{mode}"
        cached = self.lookup_cache.get(cache_key)
        if cached and self._is_cache_valid(callsign_upper):
            return (cached.get('new_band', False),
                   cached.get('new_mode', False),
                   cached.get('call_confirmed_band_mode', False))
        
        # Do API lookup with band and mode
        data = await self._do_lookup(callsign_upper, band=band, mode=mode)
        
        # Process results
        if data:
            band_worked = data.get('call_worked_band', False)
            bandmode_worked = data.get('call_worked_band_mode', False)
            bandmode_conf = data.get('call_confirmed_band_mode', False)
            
            new_band = not band_worked
            new_mode = band_worked and not bandmode_worked
            
            # Cache the band+mode specific result
            self.lookup_cache[cache_key] = {
                'new_band': new_band,
                'new_mode': new_mode,
                'call_confirmed_band_mode': bandmode_conf
            }
            self.cache_timestamps[cache_key] = datetime.utcnow()
            
            return new_band, new_mode, bandmode_conf
        
        # No data - treat as all new
        return True, False, False
    
    def _extract_dxcc_status_from_call_lookup(self, data: Dict[str, Any], band: Optional[str] = None, 
                                              mode: Optional[str] = None) -> Dict[str, bool]:
        """
        Extract DXCC-specific status flags from a call lookup response.
        The Wavelog API's private_lookup returns DXCC status as part of the callsign lookup.
        
        Args:
            data: Response data from private_lookup
            band: Optional band for band-specific flags
            mode: Optional mode for band+mode-specific flags
        
        Returns:
            Dictionary with DXCC status flags
        """
        result = {
            'dxcc_worked': data.get('dxcc_confirmed', False),  # Note: API only returns 'worked' as True if confirmed
            'dxcc_confirmed': data.get('dxcc_confirmed', False),
            'dxcc_worked_band': data.get('dxcc_confirmed_on_band', False) if band else False,
            'dxcc_confirmed_band': data.get('dxcc_confirmed_on_band', False) if band else False,
            'dxcc_worked_band_mode': data.get('dxcc_confirmed_on_band_mode', False) if band and mode else False,
            'dxcc_confirmed_band_mode': data.get('dxcc_confirmed_on_band_mode', False) if band and mode else False,
        }
        return result
    
    async def dxcc_overall(self, dxcc: Optional[int], callsign: Optional[str] = None) -> Tuple[bool, bool]:
        """
        Check if DXCC is worked and/or confirmed overall.
        
        Note: In the Wavelog API model, DXCC status is queried through callsigns (via private_lookup).
        If a callsign is provided, we can get accurate DXCC status. Otherwise, we default to False.
        
        Args:
            dxcc: DXCC number (for compatibility, but callsign lookup is more accurate)
            callsign: Optional callsign to look up DXCC status for
        
        Returns:
            Tuple of (worked, confirmed) - Note: API doesn't distinguish between worked/confirmed for DXCC,
                                          so both may be True if confirmed
        """
        if dxcc is None or not callsign:
            return False, False
        
        # For DXCC overall (no band/mode specified), use a callsign lookup
        data = await self._do_lookup(callsign.upper())
        if data:
            # Extract DXCC status from call lookup response
            dxcc_worked = data.get('dxcc_confirmed', False)  # Fallback assumption
            dxcc_confirmed = data.get('dxcc_confirmed', False)
            return dxcc_worked, dxcc_confirmed
        
        return False, False
    
    async def dxcc_bandmode_flags(self, dxcc: Optional[int], band: str, 
                                  mode: str, callsign: Optional[str] = None) -> Tuple[bool, bool, bool]:
        """
        Check DXCC band/mode specific flags.
        
        Args:
            dxcc: DXCC number (for compatibility)
            band: Band designation
            mode: Mode designation
            callsign: Optional callsign to look up DXCC status for (more accurate)
        
        Returns:
            Tuple of (new_band, new_mode, bandmode_conf)
        """
        if dxcc is None or not callsign:
            return False, False, False
        
        # Do API lookup with band and mode for DXCC band/mode specific status
        data = await self._do_lookup(callsign.upper(), band=band, mode=mode)
        
        if data:
            band_worked = data.get('dxcc_confirmed_on_band', False)
            bandmode_worked = data.get('dxcc_confirmed_on_band_mode', False)
            bandmode_conf = data.get('dxcc_confirmed_on_band_mode', False)
            
            new_band = not band_worked
            new_mode = band_worked and not bandmode_worked
            
            return new_band, new_mode, bandmode_conf
        
        # If lookup fails, assume all new
        return True, False, False


# Global instance
_classifier_instance: Optional[ClassifierAPI] = None


async def get_classifier_api(api_client: Optional[WavelogClient] = None) -> ClassifierAPI:
    """
    Get or create the API-based classifier instance.
    
    Args:
        api_client: Optional WavelogClient to use
    
    Returns:
        ClassifierAPI instance
    """
    global _classifier_instance
    
    if _classifier_instance is None:
        if api_client is None:
            # Create default API client
            from radio_control.wavelog_api import WavelogClient
            api_client = WavelogClient()
        
        _classifier_instance = ClassifierAPI(api_client)
        logger.info("✅ API-based classifier initialized")
    
    return _classifier_instance
