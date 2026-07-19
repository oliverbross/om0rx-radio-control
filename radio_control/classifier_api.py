"""
Classifier API - QSO classification using Wavelog API and local QSO status.
"""

import logging
import asyncio
from typing import Tuple, Optional, Dict, Any
from datetime import datetime
from radio_control.wavelog_api import WavelogClient
from radio_control.qso_status_store import DuckDBQSOStatusStore
from radio_control.spot_classification import (
    call_bandmode_from_lookup,
    call_overall_from_lookup,
    dxcc_confirmation_from_lookup,
)

logger = logging.getLogger(__name__)


class ClassifierAPI:
    """
    Classify spots based on worked/confirmed status.
    
    Features:
    - Per-callsign API lookups for accurate call status
    - Local DuckDB QSO mirror for true DXCC worked status
    - LRU cache to minimize API calls
    - Same interface as original Classifier for compatibility
    - Async-compatible for FastAPI integration
    """
    
    def __init__(
        self,
        api_client: Optional[WavelogClient] = None,
        qso_status_store: Optional[DuckDBQSOStatusStore] = None,
    ):
        """
        Initialize the API-based classifier.
        
        Args:
            api_client: WavelogClient instance (will create one if not provided)
        """
        self.api_client = api_client
        self.qso_status_store = qso_status_store or DuckDBQSOStatusStore()
        
        # Simple LRU cache for lookups (callsign -> lookup_result)
        self.lookup_cache: Dict[str, Dict[str, Any]] = {}
        self.cache_max_size = 500  # Keep last 500 lookups
        self.cache_ttl = 3600  # Cache for 1 hour
        self.cache_timestamps: Dict[str, datetime] = {}
        self.lookup_inflight: Dict[str, asyncio.Task] = {}

    def _cache_key(self, callsign: str, band: Optional[str] = None, mode: Optional[str] = None) -> str:
        callsign_upper = (callsign or "").upper()
        if band or mode:
            return f"{callsign_upper}|{(band or '').strip()}|{(mode or '').strip().upper()}"
        return callsign_upper
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache entry is still valid"""
        if cache_key not in self.cache_timestamps:
            return False
        elapsed = (datetime.utcnow() - self.cache_timestamps[cache_key]).total_seconds()
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

    async def _lookup(self, callsign: str, band: Optional[str] = None,
                      mode: Optional[str] = None) -> Dict[str, Any]:
        """Return a cached/in-flight Wavelog lookup for this callsign context."""
        cache_key = self._cache_key(callsign, band, mode)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        task = self.lookup_inflight.get(cache_key)
        if task is None:
            task = asyncio.create_task(self._do_lookup((callsign or "").upper(), band=band, mode=mode))
            self.lookup_inflight[cache_key] = task

        try:
            data = await task
        finally:
            if self.lookup_inflight.get(cache_key) is task:
                self.lookup_inflight.pop(cache_key, None)

        if data:
            self._set_cache(cache_key, data)
        return data or {}
    
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
        
        data = await self._lookup(callsign_upper)
        if data:
            return call_overall_from_lookup(data)
        
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
        
        data = await self._lookup(callsign_upper, band=band, mode=mode)
        
        # Process results
        if data:
            return call_bandmode_from_lookup(data)
        
        # No data - treat as all new
        return True, False, False

    async def call_status_flags(
        self,
        callsign: str,
        band: str,
        mode: str,
    ) -> Tuple[bool, bool, bool, bool, bool]:
        """
        Return call worked plus band/mode flags from one private_lookup call.

        Wavelog's band/mode lookup payload includes the overall call flags, so
        live spot classification should not pay for a separate overall lookup.
        """
        data = await self._lookup(callsign, band=band, mode=mode)
        if data:
            call_worked, call_confirmed = call_overall_from_lookup(data)
            new_band, new_mode, bandmode_conf = call_bandmode_from_lookup(data)
            resolved_call = str(data.get("callsign") or callsign).strip().upper()
            try:
                local_flags = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.qso_status_store.call_flags,
                        resolved_call,
                        band,
                        mode,
                    ),
                    timeout=0.75,
                )
            except asyncio.TimeoutError:
                logger.debug(
                    "Timed out reading call band/mode confirmation cache for %s %s %s",
                    resolved_call,
                    band,
                    mode,
                )
                local_flags = None
            if local_flags is not None:
                # Wavelog's API applies all account-default confirmation
                # methods. Spots intentionally accepts only LoTW/paper, which
                # is derived from the synced QSO rows by the local store.
                bandmode_conf = local_flags[4]
            else:
                # The API flag does not expose which confirmation method
                # matched, so it cannot safely prove the LoTW/paper-only rule.
                bandmode_conf = False
            return call_worked, call_confirmed, new_band, new_mode, bandmode_conf

        return False, False, True, False, False
    
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
        confirmed, band_confirmed, bandmode_confirmed = dxcc_confirmation_from_lookup(data)
        result = {
            'dxcc_worked': confirmed,
            'dxcc_confirmed': confirmed,
            'dxcc_worked_band': band_confirmed if band else False,
            'dxcc_confirmed_band': band_confirmed if band else False,
            'dxcc_worked_band_mode': bandmode_confirmed if band and mode else False,
            'dxcc_confirmed_band_mode': bandmode_confirmed if band and mode else False,
        }
        return result
    
    async def dxcc_overall(
        self,
        dxcc: Optional[int],
        callsign: Optional[str] = None,
        allow_unconfirmed_fallback: bool = True,
    ) -> Optional[Tuple[bool, bool]]:
        """
        Check if DXCC is worked and/or confirmed overall.
        
        Wavelog private_lookup exposes DXCC confirmation fields only. Worked
        status comes from the local Wavelog DuckDB mirror when available.
        
        Args:
            dxcc: DXCC number (for compatibility, but callsign lookup is more accurate)
            callsign: Optional callsign to look up DXCC status for
        
        Args:
            allow_unconfirmed_fallback: When False, an unavailable local
                worked-status cache returns None instead of treating the DXCC
                as not worked. This prevents false ATNO classifications while
                the local Wavelog mirror is warming or temporarily unavailable.

        Returns:
            Tuple of (worked, confirmed), or None when the worked-status source
            is unavailable and an unconfirmed fallback would be unsafe.
        """
        if dxcc is None:
            return False, False

        try:
            local_status = await asyncio.wait_for(
                asyncio.to_thread(self.qso_status_store.dxcc_overall, dxcc),
                timeout=0.75,
            )
        except asyncio.TimeoutError:
            logger.debug("Timed out reading DXCC overall status cache for %s", dxcc)
            local_status = None
        if local_status is not None:
            return local_status

        # private_lookup does not identify which confirmation method matched,
        # so it cannot safely satisfy the LoTW/paper-only Spots policy.
        return (False, False) if allow_unconfirmed_fallback else None
    
    async def dxcc_bandmode_flags(self, dxcc: Optional[int], band: str, 
                                  mode: str, callsign: Optional[str] = None,
                                  allow_unconfirmed_fallback: bool = True) -> Optional[Tuple[bool, bool, bool]]:
        """
        Check DXCC band/mode specific flags.
        
        Args:
            dxcc: DXCC number (for compatibility)
            band: Band designation
            mode: Mode designation
            callsign: Optional callsign to look up DXCC status for (more accurate)
        
        Returns:
            Tuple of (new_band, new_mode, bandmode_conf), or None when the
            local worked-status source is unavailable and an unconfirmed
            fallback would be unsafe.
        """
        if dxcc is None or not callsign:
            return (False, False, False) if allow_unconfirmed_fallback else None

        try:
            local_flags = await asyncio.wait_for(
                asyncio.to_thread(self.qso_status_store.dxcc_bandmode_flags, dxcc, band, mode),
                timeout=0.75,
            )
        except asyncio.TimeoutError:
            logger.debug("Timed out reading DXCC band/mode status cache for %s %s %s", dxcc, band, mode)
            local_flags = None
        if local_flags is not None:
            return local_flags

        # private_lookup does not identify which confirmation method matched,
        # so it cannot safely satisfy the LoTW/paper-only Spots policy. Do not
        # invent a confirmed/new-slot result when the QSO mirror is unavailable.
        return (True, False, False) if allow_unconfirmed_fallback else None

    async def grid_flags(self, grid: Optional[str], band: str, mode: str) -> Optional[Tuple[bool, bool, bool]]:
        """Check whether a grid square is new overall, on this band, or on this mode."""
        if not grid:
            return False, False, False
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self.qso_status_store.grid_flags, grid, band, mode),
                timeout=0.75,
            )
        except asyncio.TimeoutError:
            logger.debug("Timed out reading grid status cache for %s %s %s", grid, band, mode)
            return None


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
