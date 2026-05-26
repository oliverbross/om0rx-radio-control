"""
Wavelog API Integration
Handles QSO logging and DXCC lookups via Wavelog API
"""

import asyncio
import aiohttp
import logging
import re
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from radio_control import config
from radio_control.utils import generate_callsign_variants
from radio_control.wavelog_db import get_wavelog_db

logger = logging.getLogger(__name__)

# Cache file location in /data folder
CACHE_DIR = config.DATA_DIR
ADIF_CACHE_FILE = CACHE_DIR / 'wavelog_adif.cache'
ADIF_CACHE_META_FILE = CACHE_DIR / 'wavelog_adif.meta'


class WavelogClient:
    """Wavelog API client for QSO operations"""
    
    # Class-level cache for ADIF data (shared across all instances)
    _adif_cache = None
    _adif_cache_time = None
    _adif_cache_ttl = 30 * 60  # Cache for 30 minutes (1800 seconds)
    
    # Class-level HTTP session for persistent connections
    _session = None
    
    def __init__(self):
        # Store API URL base - keep /index.php as it's part of Wavelog API endpoint
        self.api_url = config.WAVELOG_API_URL.rstrip('/')
        self.api_key = config.WAVELOG_API_KEY
        self.station_id = config.WAVELOG_STATION_ID
    
    @classmethod
    async def _get_session(cls) -> aiohttp.ClientSession:
        """Get or create a persistent HTTP session"""
        if cls._session is None or cls._session.closed:
            try:
                # Create connector with connection pooling
                connector = aiohttp.TCPConnector(
                    limit=10,  # Max connections
                    limit_per_host=5,  # Max per host
                    ttl_dns_cache=300  # DNS cache for 5 minutes
                )
                timeout = aiohttp.ClientTimeout(total=30)  # 30 second timeout
                cls._session = aiohttp.ClientSession(connector=connector, timeout=timeout)
                logger.debug("✅ Created new persistent HTTP session")
            except Exception as e:
                logger.error(f"Failed to create HTTP session: {str(e)}")
                # Fallback to creating a new session for this request
                cls._session = None
                raise
        return cls._session
    
    @classmethod
    async def close_session(cls):
        """Properly close the HTTP session"""
        if cls._session and not cls._session.closed:
            try:
                await cls._session.close()
                cls._session = None
                logger.debug("✅ Closed HTTP session")
            except Exception as e:
                logger.warning(f"Error closing HTTP session: {str(e)}")
    
    @classmethod
    def _is_cache_valid(cls) -> bool:
        """Check if ADIF cache is still valid (from disk or memory)"""
        # Try to load cache metadata from disk
        try:
            if ADIF_CACHE_META_FILE.exists():
                with open(ADIF_CACHE_META_FILE, 'r') as f:
                    meta = json.load(f)
                    cache_time = datetime.fromisoformat(meta.get('timestamp'))
                    elapsed = (datetime.utcnow() - cache_time).total_seconds()
                    is_valid = elapsed < cls._adif_cache_ttl
                    
                    if not is_valid:
                        logger.debug(f"ADIF cache expired after {elapsed:.0f} seconds (TTL: {cls._adif_cache_ttl}s)")
                    return is_valid
        except Exception as e:
            logger.debug(f"Error checking cache metadata: {str(e)}")
        
        # Fallback to in-memory cache check
        if cls._adif_cache is None or cls._adif_cache_time is None:
            return False
        
        elapsed = (datetime.utcnow() - cls._adif_cache_time).total_seconds()
        is_valid = elapsed < cls._adif_cache_ttl
        
        if not is_valid:
            logger.debug(f"ADIF cache expired after {elapsed:.0f} seconds (TTL: {cls._adif_cache_ttl}s)")
        
        return is_valid
    
    @classmethod
    def _get_cached_adif(cls) -> Optional[str]:
        """Get ADIF data from cache (disk first, then memory)"""
        try:
            # Try to load from disk first
            if ADIF_CACHE_FILE.exists() and cls._is_cache_valid():
                with open(ADIF_CACHE_FILE, 'r', encoding='utf-8') as f:
                    adif_data = f.read()
                    logger.debug(f"Using cached ADIF data from disk ({len(adif_data)} bytes)")
                    # Also store in memory for faster access
                    cls._adif_cache = adif_data
                    try:
                        with open(ADIF_CACHE_META_FILE, 'r') as mf:
                            meta = json.load(mf)
                            cls._adif_cache_time = datetime.fromisoformat(meta.get('timestamp'))
                    except:
                        pass
                    return adif_data
        except Exception as e:
            logger.debug(f"Error reading cache from disk: {str(e)}")
        
        # Fall back to in-memory cache
        if cls._is_cache_valid() and cls._adif_cache:
            logger.debug(f"Using cached ADIF data from memory ({len(cls._adif_cache)} bytes)")
            return cls._adif_cache
        
        return None
    
    @classmethod
    def _set_adif_cache(cls, adif_data: str) -> None:
        """Set ADIF cache (both disk and memory)"""
        try:
            # Ensure cache directory exists
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            
            # Save to disk
            with open(ADIF_CACHE_FILE, 'w', encoding='utf-8') as f:
                f.write(adif_data)
            
            # Save metadata
            cache_time = datetime.utcnow()
            with open(ADIF_CACHE_META_FILE, 'w') as f:
                json.dump({'timestamp': cache_time.isoformat()}, f)
            
            logger.debug(f"Cached ADIF data to disk ({len(adif_data)} bytes) at {ADIF_CACHE_FILE}")
        except Exception as e:
            logger.warning(f"Error writing cache to disk: {str(e)}")
        
        # Also store in memory
        cls._adif_cache = adif_data
        cls._adif_cache_time = datetime.utcnow()
        logger.debug(f"Cached ADIF data in memory ({len(adif_data)} bytes)")
        
    def build_adif_string(self, qso_data: Dict[str, Any]) -> str:
        """Build ADIF format string from QSO data"""
        callsign = (qso_data.get('callsign') or '').strip().upper()
        frequency = qso_data.get('frequency', 0)
        
        # Ensure frequency is a valid number
        try:
            frequency = float(frequency)
        except (TypeError, ValueError):
            logger.warning(f"Invalid frequency: {frequency}, defaulting to 0")
            frequency = 0
        
        mode = (qso_data.get('mode') or 'SSB').strip().upper()
        rst_sent = qso_data.get('rst_sent', '')
        rst_received = qso_data.get('rst_received', '')
        
        # Handle RST values - can be integers or FT8/FT4 SNR strings like "-12", "+15"
        # For digital modes (FT8, FT4), SNR values are reported as strings
        # For SSB/CW, use standard 599 format
        try:
            # Convert to string first to handle both int and str inputs
            rst_sent_str = str(rst_sent).strip() if rst_sent else ''
            rst_received_str = str(rst_received).strip() if rst_received else ''
            
            # If mode is digital and RST is empty or SNR format, keep as-is
            # Wavelog API handles SNR values in ADIF for digital modes
            if mode in ['FT8', 'FT4', 'JT65', 'JT9', 'WSPR']:
                # For digital modes, use the SNR values if present, otherwise use defaults
                rst_sent = rst_sent_str if rst_sent_str else 599
                rst_received = rst_received_str if rst_received_str else 599
            else:
                # For SSB/CW, ensure they're proper RST format (3 digits)
                # Try to parse as int
                if rst_sent_str:
                    try:
                        rst_sent = int(rst_sent_str)
                    except ValueError:
                        # If not a valid int, try to extract digits
                        digits = ''.join(c for c in rst_sent_str if c.isdigit())
                        rst_sent = int(digits) if digits else 599
                else:
                    rst_sent = 599
                
                if rst_received_str:
                    try:
                        rst_received = int(rst_received_str)
                    except ValueError:
                        # If not a valid int, try to extract digits
                        digits = ''.join(c for c in rst_received_str if c.isdigit())
                        rst_received = int(digits) if digits else 599
                else:
                    rst_received = 599
        except Exception as e:
            logger.warning(f"Error parsing RST values ({rst_sent}, {rst_received}): {str(e)}")
            rst_sent = 599
            rst_received = 599
        
        name = (qso_data.get('name') or '').strip()
        qth = (qso_data.get('qth') or '').strip()
        notes = (qso_data.get('notes') or '').strip()
        
        # Parse datetime - use provided date/time if available
        date_str = (qso_data.get('date') or '').strip()
        time_off_str = (qso_data.get('time_off') or '').strip()
        
        if date_str and time_off_str:
            try:
                # Combine date and time
                datetime_str = f"{date_str}T{time_off_str}"
                dt = datetime.fromisoformat(datetime_str)
            except Exception as e:
                logger.warning(f"Invalid date/time format: {date_str}/{time_off_str}, using current time. Error: {e}")
                dt = datetime.utcnow()
        elif qso_data.get('date_time'):
            try:
                dt = datetime.fromisoformat(qso_data['date_time'].replace('Z', '+00:00'))
            except Exception as e:
                logger.warning(f"Invalid date_time format: {qso_data['date_time']}, using current time. Error: {e}")
                dt = datetime.utcnow()
        else:
            dt = datetime.utcnow()
        
        qso_date = dt.strftime('%Y%m%d')
        time_on = dt.strftime('%H%M%S')
        
        # Start building ADIF string
        adif_parts = []
        
        # Required fields
        adif_parts.append(f"<call:{len(callsign)}>{callsign}")
        adif_parts.append(f"<mode:{len(mode)}>{mode}")
        adif_parts.append(f"<freq:{len(str(frequency))}>{frequency}")
        adif_parts.append(f"<qso_date:8>{qso_date}")
        adif_parts.append(f"<time_on:6>{time_on}")
        adif_parts.append(f"<time_off:6>{time_on}")  # Same as time_on
        adif_parts.append(f"<rst_sent:{len(str(rst_sent))}>{rst_sent}")
        adif_parts.append(f"<rst_rcvd:{len(str(rst_received))}>{rst_received}")
        
        # Station & Location fields
        if name:
            adif_parts.append(f"<name:{len(name)}>{name}")
        if qth:
            adif_parts.append(f"<qth:{len(qth)}>{qth}")
        
        gridsquare = (qso_data.get('gridsquare') or '').strip()
        if gridsquare:
            adif_parts.append(f"<gridsquare:{len(gridsquare)}>{gridsquare}")
        
        # Award/Reference programs
        pota = (qso_data.get('pota') or '').strip()
        if pota:
            adif_parts.append(f"<pota_ref:{len(pota)}>{pota}")
        
        sota = (qso_data.get('sota') or '').strip()
        if sota:
            adif_parts.append(f"<sota_ref:{len(sota)}>{sota}")
        
        iota = (qso_data.get('iota') or '').strip()
        if iota:
            adif_parts.append(f"<iota:{len(iota)}>{iota}")
        
        wwff = (qso_data.get('wwff') or '').strip()
        if wwff:
            adif_parts.append(f"<wwff_ref:{len(wwff)}>{wwff}")
        
        # General/Location information
        continent = (qso_data.get('continent') or '').strip()
        if continent:
            adif_parts.append(f"<cont:{len(continent)}>{continent}")
        
        country = (qso_data.get('country') or '').strip()
        if country:
            adif_parts.append(f"<country:{len(country)}>{country}")
        
        state = (qso_data.get('state') or '').strip()
        if state:
            adif_parts.append(f"<state:{len(state)}>{state}")
        
        cq_zone = qso_data.get('cq_zone')
        if cq_zone and str(cq_zone).strip() and str(cq_zone) != '0':
            adif_parts.append(f"<cqz:{len(str(cq_zone))}>{cq_zone}")
        
        itu_zone = qso_data.get('itu_zone')
        if itu_zone and str(itu_zone).strip() and str(itu_zone) != '0':
            adif_parts.append(f"<ituz:{len(str(itu_zone))}>{itu_zone}")
        
        us_county = (qso_data.get('us_county') or '').strip()
        if us_county:
            adif_parts.append(f"<county:{len(us_county)}>{us_county}")
        
        # Power & Equipment
        tx_pwr = (qso_data.get('tx_pwr') or '').strip()
        if tx_pwr:
            adif_parts.append(f"<tx_pwr:{len(tx_pwr)}>{tx_pwr}")
        
        ant = (qso_data.get('ant') or '').strip()
        if ant:
            adif_parts.append(f"<ant:{len(ant)}>{ant}")
        
        # QSL information
        qsl_rcvd = (qso_data.get('qsl_rcvd') or '').strip()
        if qsl_rcvd:
            adif_parts.append(f"<qsl_rcvd:{len(qsl_rcvd)}>{qsl_rcvd}")
        
        qsl_sent = (qso_data.get('qsl_sent') or '').strip()
        if qsl_sent:
            adif_parts.append(f"<qsl_sent:{len(qsl_sent)}>{qsl_sent}")
        
        qsl_manager = (qso_data.get('qsl_manager') or '').strip()
        if qsl_manager:
            adif_parts.append(f"<qsl_via:{len(qsl_manager)}>{qsl_manager}")
        
        email = (qso_data.get('email') or '').strip()
        if email:
            adif_parts.append(f"<email:{len(email)}>{email}")
        
        # LoTW Member
        if qso_data.get('lotw_member'):
            adif_parts.append(f"<lotw_member:1>Y")
        
        # Satellite & Propagation information
        prop_mode = (qso_data.get('prop_mode') or '').strip()
        if prop_mode:
            adif_parts.append(f"<prop_mode:{len(prop_mode)}>{prop_mode}")
        
        ant_path = (qso_data.get('ant_path') or '').strip()
        if ant_path:
            adif_parts.append(f"<ant_path:{len(ant_path)}>{ant_path}")
        
        sat_name = (qso_data.get('sat_name') or '').strip()
        if sat_name:
            adif_parts.append(f"<sat_name:{len(sat_name)}>{sat_name}")
        
        sat_mode = (qso_data.get('sat_mode') or '').strip()
        if sat_mode:
            adif_parts.append(f"<sat_mode:{len(sat_mode)}>{sat_mode}")
        
        freq_rx = qso_data.get('freq_rx')
        if freq_rx and str(freq_rx).strip():
            adif_parts.append(f"<freq_rx:{len(str(freq_rx))}>{freq_rx}")
        
        mode_rx = (qso_data.get('mode_rx') or '').strip()
        if mode_rx:
            adif_parts.append(f"<mode_rx:{len(mode_rx)}>{mode_rx}")
        
        # Add comments/notes if provided
        if notes:
            adif_parts.append(f"<comments:{len(notes)}>{notes}")
        
        # End of record
        adif_parts.append("<eor>")
        
        return "".join(adif_parts)

    def _build_adif_string(self, qso_data: Dict[str, Any]) -> str:
        """Backward-compatible wrapper for older callers."""
        return self.build_adif_string(qso_data)

    async def submit_adif_string(self, adif_string: str) -> Dict[str, Any]:
        """Submit an already formatted ADIF record/string to Wavelog."""
        session = None
        try:
            endpoint = f"{self.api_url}/api/qso"
            payload = {
                'key': self.api_key,
                'station_profile_id': self.station_id,
                'type': 'adif',
                'string': adif_string,
            }

            try:
                session = await self._get_session()
                use_persistent = True
            except Exception as e:
                logger.warning(f"Failed to get persistent session, creating temporary: {str(e)}")
                session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
                use_persistent = False

            try:
                async with session.post(endpoint, json=payload) as resp:
                    response_text = await resp.text()
                    if resp.status in (200, 201):
                        try:
                            result = json.loads(response_text)
                        except Exception:
                            result = {'response': response_text}

                        if result.get('status') in ('ok', 'success', 'successful', 'created'):
                            return {
                                'success': True,
                                'message': 'QSO logged successfully',
                                'data': result,
                            }

                        logger.error(f"Wavelog API response unclear: {response_text}")
                        return {
                            'success': False,
                            'message': 'Unclear response from Wavelog',
                            'error': response_text,
                        }

                    logger.error(f"Wavelog API error ({resp.status}): {response_text}")
                    return {
                        'success': False,
                        'message': f'Wavelog API error: {resp.status}',
                        'error': response_text,
                    }
            finally:
                if not use_persistent and session and not session.closed:
                    await session.close()

        except asyncio.TimeoutError:
            logger.error("Wavelog API timeout")
            return {'success': False, 'message': 'Wavelog API timeout'}
        except Exception as e:
            logger.error(f"Wavelog QSO logging error: {str(e)}", exc_info=True)
            return {'success': False, 'message': str(e)}
    
    async def log_qso(self, qso_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Log a QSO to Wavelog via API
        
        Args:
            qso_data: Dictionary with QSO details
                {
                    'callsign': str,
                    'frequency': float,
                    'mode': str,
                    'rst_sent': int,
                    'rst_received': int,
                    'name': str (optional),
                    'qth': str (optional),
                    'notes': str (optional),
                    'pota': str (optional),
                    'sota': str (optional),
                    'iota': str (optional),
                    'wwff': str (optional),
                    'date_time': str ISO format (optional, defaults to now)
                }
        
        Returns:
            Response dict with success status and message
        """
        try:
            # Build ADIF format string
            adif_string = self.build_adif_string(qso_data)
            
            logger.debug(f"Submitting QSO to Wavelog: {adif_string[:100]}...")
            result = await self.submit_adif_string(adif_string)
            if result.get('success'):
                logger.info(f"✅ QSO logged to Wavelog: {qso_data['callsign']} on {qso_data.get('frequency')} MHz")
            return result
                        
        except asyncio.TimeoutError:
            logger.error("Wavelog API timeout")
            return {'success': False, 'message': 'Wavelog API timeout'}
        except Exception as e:
            logger.error(f"Wavelog QSO logging error: {str(e)}", exc_info=True)
            return {'success': False, 'message': str(e)}
    
    async def _lookup_private_internal(self, callsign: str, band: Optional[str] = None, mode: Optional[str] = None) -> Dict[str, Any]:
        """
        Internal method to perform actual Wavelog private lookup for a single callsign.
        This does NOT implement fallback - that's handled by private_lookup.
        
        Args:
            callsign: The callsign to look up
            band: Optional band (e.g., "20m", "40m")
            mode: Optional mode (e.g., "SSB", "CW")
        
        Returns:
            Dictionary with success flag and lookup data
        """
        try:
            endpoint = f"{self.api_url}/api/private_lookup"
            
            payload = {
                'key': self.api_key,
                'callsign': callsign.upper()
            }
            
            # Add optional parameters
            if band:
                payload['band'] = band
            if mode:
                payload['mode'] = mode.upper()
            
            logger.debug(f"Private lookup for {callsign} with band={band}, mode={mode}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    endpoint, 
                    json=payload, 
                    timeout=aiohttp.ClientTimeout(total=10),
                    headers={'Content-Type': 'application/json', 'Accept': 'application/json'}
                ) as resp:
                    response_text = await resp.text()
                    
                    if resp.status == 200:
                        # Try to parse JSON response (Wavelog API sometimes returns JSON with text/html content-type)
                        try:
                            result = await resp.json()
                            logger.info(f"✅ Private lookup successful for {callsign}")
                            return {'success': True, 'data': result}
                        except:
                            # Try manual JSON parsing
                            try:
                                import json
                                result = json.loads(response_text)
                                logger.info(f"✅ Private lookup successful for {callsign}")
                                return {'success': True, 'data': result}
                            except:
                                # If content-type is HTML and we can't parse JSON, it's likely an error
                                if 'text/html' in resp.headers.get('content-type', ''):
                                    logger.debug(f"Private lookup returned HTML for {callsign}")
                                    return {'success': False, 'message': 'HTML response - likely not found'}
                                else:
                                    logger.debug(f"Failed to parse private lookup response for {callsign}: {response_text[:200]}")
                                    return {'success': False, 'message': 'Invalid response format'}
                    else:
                        logger.debug(f"Private lookup failed for {callsign}: {resp.status}")
                        return {'success': False, 'message': f'Lookup failed: {resp.status}'}
                        
        except asyncio.TimeoutError:
            logger.debug(f"Private lookup timeout for {callsign}")
            return {'success': False, 'message': 'Lookup timeout'}
        except Exception as e:
            logger.error(f"Private lookup error for {callsign}: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    async def private_lookup(self, callsign: str, band: Optional[str] = None, mode: Optional[str] = None) -> Dict[str, Any]:
        """
        Perform private lookup in Wavelog logbook for a callsign.
        Uses fallback strategy: tries original callsign first, then variants (with/without prefixes/suffixes).
        Returns comprehensive information about worked/confirmed status
        
        Args:
            callsign: The callsign to look up
            band: Optional band (e.g., "20m", "40m")
            mode: Optional mode (e.g., "SSB", "CW")
        
        Returns:
            Dictionary with DXCC info, worked/confirmed status, and other details
        """
        logger.info(f"🔍 Wavelog private lookup for callsign: {callsign}")
        
        # Generate list of callsigns to try (original first, then fallbacks)
        variants = generate_callsign_variants(callsign)
        
        for variant in variants:
            logger.debug(f"  Trying Wavelog lookup for variant: {variant}")
            result = await self._lookup_private_internal(variant, band, mode)
            
            if result.get('success'):
                logger.info(f"✅ Wavelog lookup succeeded with variant: {variant} (requested: {callsign})")
                return result
            else:
                logger.debug(f"  Wavelog lookup failed for variant {variant}: {result.get('message', 'Unknown error')}")
        
        # All variants failed
        logger.warning(f"❌ Wavelog lookup failed for all variants of {callsign}")
        return {'success': False, 'message': f'Callsign not found (tried: {", ".join(variants)})'}
    
    async def _get_dxcc_internal(self, callsign: str) -> Dict[str, Any]:
        """
        Internal method to get DXCC status for a single callsign.
        This does NOT implement fallback - that's handled by get_dxcc_status.
        """
        try:
            endpoint = f"{self.api_url}/api/dxcc/{callsign}"
            params = {
                'api_key': self.api_key,
                'station_id': self.station_id
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        logger.info(f"✅ DXCC status retrieved for {callsign}")
                        return {'success': True, 'data': result}
                    else:
                        logger.debug(f"DXCC lookup failed for {callsign}: {resp.status}")
                        return {'success': False, 'message': f'DXCC lookup failed: {resp.status}'}
                        
        except asyncio.TimeoutError:
            logger.debug(f"DXCC lookup timeout for {callsign}")
            return {'success': False, 'message': 'Lookup timeout'}
        except Exception as e:
            logger.error(f"DXCC lookup error for {callsign}: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    async def get_dxcc_status(self, callsign: str) -> Dict[str, Any]:
        """
        Get DXCC status for a callsign from Wavelog database.
        Uses fallback strategy: tries original callsign first, then variants (with/without prefixes/suffixes).
        
        Returns:
            Dictionary with band/mode worked/confirmed status
        """
        logger.info(f"🔍 Wavelog DXCC status for callsign: {callsign}")
        
        # Generate list of callsigns to try (original first, then fallbacks)
        variants = generate_callsign_variants(callsign)
        
        for variant in variants:
            logger.debug(f"  Trying DXCC lookup for variant: {variant}")
            result = await self._get_dxcc_internal(variant)
            
            if result.get('success'):
                logger.info(f"✅ DXCC lookup succeeded with variant: {variant} (requested: {callsign})")
                return result
            else:
                logger.debug(f"  DXCC lookup failed for variant {variant}: {result.get('message', 'Unknown error')}")
        
        # All variants failed
        logger.warning(f"❌ DXCC lookup failed for all variants of {callsign}")
        return {'success': False, 'message': f'Callsign not found (tried: {", ".join(variants)})'}
    
    @staticmethod
    def _frequency_to_band(freq_mhz: float) -> str:
        """Convert frequency in MHz to band designation"""
        try:
            freq = float(freq_mhz)
        except (ValueError, TypeError):
            return ''
        
        # Band definitions (160m to 70cm) - standard ITU band limits
        bands = [
            (1.8, 2.0, '160m'),
            (3.5, 4.0, '80m'),      # Extended to 4.0 MHz
            (5.25, 5.45, '60m'),    # 60m band
            (7.0, 7.3, '40m'),
            (10.1, 10.15, '30m'),
            (14.0, 14.35, '20m'),
            (18.068, 18.168, '17m'),
            (21.0, 21.45, '15m'),
            (24.89, 24.99, '12m'),
            (28.0, 29.7, '10m'),
            (50.0, 54.0, '6m'),
            (144.0, 148.0, '2m'),
            (222.0, 225.0, '1.25m'),
            (420.0, 450.0, '70cm'),
        ]
        
        for low, high, band in bands:
            if low <= freq <= high:
                return band
        
        return ''

    def _transform_wavelog_qso(self, qso_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform Wavelog API QSO response into standard format expected by frontend.
        
        Args:
            qso_data: QSO data from Wavelog API (field names may vary)
        
        Returns:
            Standardized QSO record with required fields
        """
        try:
            # Handle various possible field names from Wavelog API
            # Wavelog uses: call, date, time_on, time_off, band, mode, rst_sent, rst_rcvd, lotw_qsl, freq
            
            # Extract and normalize all fields
            result = {}
            
            # Call sign (handle various field names)
            result['call'] = qso_data.get('call', qso_data.get('callsign', ''))
            
            # Date fields - try multiple variations
            qso_date = qso_data.get('qso_date') or qso_data.get('date')
            if qso_date:
                # Ensure it's in YYYYMMDD format
                if isinstance(qso_date, str):
                    qso_date = qso_date.replace('-', '')
                result['qso_date'] = str(qso_date)[-8:] if len(str(qso_date)) >= 8 else qso_date
            else:
                result['qso_date'] = ''
            
            # Time on - try multiple variations
            time_on = qso_data.get('time_on') or qso_data.get('time')
            if time_on:
                # Ensure it's in HHMMSS format
                if isinstance(time_on, str):
                    time_on = time_on.replace(':', '')
                result['time_on'] = str(time_on)[-6:] if len(str(time_on)) >= 6 else time_on
            else:
                result['time_on'] = ''
            
            # Mode
            result['mode'] = (qso_data.get('mode', '')).upper()
            
            # Frequency
            freq = qso_data.get('freq') or qso_data.get('frequency')
            try:
                result['frequency'] = float(freq) if freq else 0
            except (ValueError, TypeError):
                result['frequency'] = 0
            
            # RST Sent
            result['rst_sent'] = str(qso_data.get('rst_sent', qso_data.get('rst_s', ''))).strip()
            
            # RST Received
            result['rst_rcvd'] = str(qso_data.get('rst_rcvd', qso_data.get('rst_r', ''))).strip()
            
            # Band - derive from frequency if not present
            band = qso_data.get('band', '')
            if not band and result['frequency']:
                band = self._frequency_to_band(result['frequency'])
            result['band'] = band
            
            # LoTW status - check if we RECEIVED confirmation via LOTW
            # Wavelog ADIF uses: lotw_qsl_rcvd (Y/N) - whether we received LOTW confirmation
            lotw_rcvd = qso_data.get('lotw_qsl_rcvd', '')
            if lotw_rcvd:
                result['lotw_qsl'] = 'Y' if str(lotw_rcvd).upper() in ('Y', 'YES', '1', 'TRUE') else 'N'
            else:
                result['lotw_qsl'] = 'N'
            
            return result
        except Exception as e:
            logger.debug(f"Error transforming QSO data: {str(e)}")
            return qso_data  # Return original if transformation fails

    def _parse_adif_qsos(self, adif_string: str, target_callsign: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Parse ADIF string and extract QSOs matching the target callsign.
        Returns the last N QSOs (ordered by date ascending, take the last N).
        """
        qsos = []
        
        if not adif_string:
            logger.debug(f"   No ADIF string provided for {target_callsign}")
            return qsos
        
        logger.debug(f"   Parsing ADIF for {target_callsign}, ADIF length: {len(adif_string)} bytes")
        
        # Split by <EOR> (uppercase) to get individual QSO records - Wavelog returns uppercase tags
        records = adif_string.split('<EOR>')
        logger.debug(f"   Found {len(records)} records in ADIF")
        
        unique_calls = set()
        
        for idx, record in enumerate(records):
            record = record.strip()
            if not record:
                continue
            
            # Extract all ADIF fields
            qso_data = {}
            
            # Parse ADIF format: <fieldname:length>value
            pattern = r'<([^:>]+):(\d+)>([^<]*)'
            matches = re.findall(pattern, record)
            
            for field_name, field_len, field_value in matches:
                qso_data[field_name.lower()] = field_value.strip()
            
            # Check if this QSO matches the target callsign
            call = qso_data.get('call', '').upper()
            unique_calls.add(call)
            
            if call == target_callsign.upper():
                logger.debug(f"   ✅ Match found at record {idx}: {call}")
                
                # Extract LOTW status - check if we received LOTW confirmation (Y/N)
                lotw_status = qso_data.get('lotw_qsl_rcvd', 'N')
                if lotw_status and str(lotw_status).upper() in ('Y', 'YES', '1', 'TRUE'):
                    lotw_status = 'Y'
                else:
                    lotw_status = 'N'
                
                # Extract relevant fields for response
                qso_dict = {
                    'call': call,
                    'qso_date': qso_data.get('qso_date', ''),
                    'time_on': qso_data.get('time_on', ''),
                    'mode': qso_data.get('mode', ''),
                    'frequency': float(qso_data.get('freq', 0)) if qso_data.get('freq') else 0,
                    'rst_sent': qso_data.get('rst_sent', ''),
                    'rst_rcvd': qso_data.get('rst_rcvd', ''),
                    'band': qso_data.get('band', ''),
                    'lotw_qsl': lotw_status,
                }
                qsos.append(qso_dict)
        
        logger.debug(f"   Unique callsigns in ADIF: {len(unique_calls)}")
        if len(unique_calls) <= 10:
            logger.debug(f"   Sample calls: {sorted(list(unique_calls))[:10]}")
        logger.debug(f"   Target callsign '{target_callsign.upper()}' found in {len(qsos)} records")
        
        # Return last N QSOs (most recent)
        result = qsos[-limit:] if qsos else []
        logger.debug(f"   Returning {len(result)} QSOs (limit={limit})")
        return result
    
    async def _get_recent_qsos_internal(self, callsign: str, limit: int = 5) -> Dict[str, Any]:
        """
        Internal method to get recent QSOs for a single callsign.
        Uses local SQLite database (synced from Wavelog every 5 minutes).
        """
        try:
            logger.debug(f"🔍 Getting recent QSOs for {callsign} from local database")
            
            db = get_wavelog_db()
            
            # Query local database for QSOs
            qsos_rows = db.get_qsos_by_callsign(callsign, limit=limit)
            
            if qsos_rows:
                # Transform database rows to QSO format
                qsos = []
                for row in qsos_rows:
                    qso = self._transform_wavelog_qso(row)
                    qsos.append(qso)
                
                logger.info(f"✅ Found {len(qsos)} QSOs for {callsign} in local database")
                return {'success': True, 'data': qsos}
            else:
                logger.debug(f"❌ No QSOs found for {callsign} in local database")
                return {'success': False, 'message': 'No QSOs found'}
                        
        except Exception as e:
            logger.error(f"Error getting recent QSOs from database: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def _parse_adif_record(self, adif_record: str) -> Dict[str, Any]:
        """
        Parse a single ADIF record into a QSO dictionary.
        ADIF format: <field_name:length>value<eor> or <field_name:length:type>value
        
        Args:
            adif_record: A single ADIF QSO record (without <eor>)
        
        Returns:
            Dictionary with parsed QSO data
        """
        qso = {}
        
        # Find all ADIF fields: <name:length:type>value or <name:length>value
        # Pattern: <fieldname:length> or <fieldname:length:type>
        pattern = r'<([a-zA-Z_]+):(\d+)(?::[a-zA-Z])??>([^<]*)'
        matches = re.findall(pattern, adif_record)
        
        for field_name, length, value in matches:
            field_lower = field_name.lower()
            # IMPORTANT: Strip whitespace including \r\n from Wavelog ADIF export
            # This is crucial because Wavelog returns ADIF with embedded line endings
            qso[field_lower] = value.strip()
        
        return qso
    
    def _adif_to_qsos(self, adif_string: str) -> List[Dict[str, Any]]:
        """
        Convert ADIF string to list of QSO dictionaries.
        ADIF records are separated by <eor> tags.
        
        Args:
            adif_string: The complete ADIF string
        
        Returns:
            List of QSO dictionaries
        """
        qsos = []
        record_count = 0
        
        # Split by <eor> (lowercase) or <EOR> (uppercase)
        # Wavelog returns lowercase
        records = adif_string.lower().split('<eor>')
        
        for record in records:
            record = record.strip()
            if not record:
                continue
            
            qso = self._parse_adif_record(record)
            if qso and qso.get('call'):  # Only include if it has a callsign
                record_count += 1
                
                # Extract country - Wavelog uses 'country' field in ADIF export
                country = qso.get('country', '')
                if not country:
                    # Fallback: try to get from dxcc_name if available
                    country = qso.get('dxcc_name', '')
                
                # Convert to display format
                qso_display = {
                    'call': qso.get('call', '').upper(),
                    'qso_date': qso.get('qso_date', ''),  # YYYYMMDD format
                    'time_on': qso.get('time_on', ''),     # HHMMSS format
                    'frequency': qso.get('freq', ''),      # MHz as string
                    'band': qso.get('band', ''),
                    'mode': qso.get('mode', '').upper(),
                    'rst_sent': qso.get('rst_sent', '-'),
                    'rst_rcvd': qso.get('rst_rcvd', '-'),
                    'country': country.upper(),  # UPPERCASE for display
                    'name': qso.get('name', '').upper(),  # UPPERCASE for display
                    'qth': qso.get('qth', ''),
                    'gridsquare': qso.get('gridsquare', ''),
                    'lotw_qsl': qso.get('lotw_qsl', ''),
                    'pota_ref': qso.get('pota_ref', ''),
                    'sota_ref': qso.get('sota_ref', ''),
                    'wwff_ref': qso.get('wwff_ref', ''),
                    'iota': qso.get('iota', ''),
                }
                qsos.append(qso_display)
        
        logger.debug(f"Parsed {record_count} ADIF records, returning {len(qsos)} valid QSOs")
        return qsos
    
    async def get_contacts_from_wavelog_api(self, limit: int = 100) -> Dict[str, Any]:
        """
        Get the LAST N recent contacts directly from Wavelog API (NOT local database).
        This calls the Wavelog /api/get_contacts_adif endpoint to fetch fresh data.
        
        IMPORTANT: Only fetches the last 100-200 contacts (newest first) to avoid
        long loading times. Users can go directly to Wavelog to see their full logbook.
        
        Args:
            limit: Maximum number of QSOs to return (default: 100, max: 200)
        
        Returns:
            Dictionary with success status and list of QSOs
        """
        try:
            # Cap limit to prevent excessive data transfer
            limit = min(limit, 200)
            logger.info(f"🌐 Fetching last {limit} contacts from Wavelog API...")
            
            endpoint = f"{self.api_url}/api/get_contacts_adif"
            
            # Create a single session to reuse for both discovery and main query
            connector = aiohttp.TCPConnector(limit=5, limit_per_host=3)
            timeout = aiohttp.ClientTimeout(total=60)  # 60 second timeout
            session = aiohttp.ClientSession(connector=connector, timeout=timeout)
            
            try:
                # Step 1: Find the actual last QSO ID to get the newest records
                # NOTE: Wavelog's exported_qsos field is misleading - it's not the total count
                # but the count of records AVAILABLE from fetchfromid onwards.
                # We need to binary search for the actual last ID.
                logger.debug("Step 1: Locating the most recent QSOs in Wavelog...")
                
                # Binary search for the last QSO ID
                # We know records exist at various IDs, we find where they stop
                last_id = 0
                step = 10000  # Initial step size
                search_id = 10000
                
                while step > 0:
                    test_payload = {
                        'key': self.api_key,
                        'station_id': self.station_id,
                        'fetchfromid': search_id,
                        'limit': 1
                    }
                    
                    try:
                        async with session.post(endpoint, json=test_payload) as resp:
                            if resp.status == 200:
                                test_result = json.loads(await resp.text())
                                if test_result.get('exported_qsos', 0) > 0:
                                    # Records exist at this ID or later, try higher
                                    last_id = search_id
                                    search_id += step
                                else:
                                    # No records at this ID, go back
                                    search_id -= step
                                    step = step // 2
                            else:
                                # API error, reduce step
                                step = step // 2
                                search_id -= step
                    except Exception as e:
                        logger.debug(f"Search iteration error: {e}")
                        step = step // 2
                        search_id -= step
                
                # Adjust if we went too far
                if last_id > 0:
                    logger.info(f"📊 Found latest QSOs near ID {last_id}")
                else:
                    # Fallback: use current approach with a reasonable high ID
                    logger.warning(f"⚠️ Could not locate exact last ID, using safe fallback")
                    last_id = limit * 10  # Reasonable estimate
                
                # Step 2: Calculate the starting ID to get the LAST N records
                # Fetch from (last_id - limit) to get the most recent records
                start_id = max(0, last_id - limit)
                logger.debug(f"Step 2: Fetching {limit} records starting from ID {start_id}")
                
                # Build request payload to fetch the LAST N records
                payload = {
                    'key': self.api_key,
                    'station_id': self.station_id,
                    'fetchfromid': start_id,  # Start from calculated ID to get newest records
                    'limit': limit  # Request exactly what we need
                }
                
                logger.info(f"Requesting {limit} recent contacts from Wavelog API endpoint: {endpoint}")
                async with session.post(endpoint, json=payload) as resp:
                    response_text = await resp.text()
                    
                    if resp.status == 200:
                        try:
                            result = json.loads(response_text)
                        except:
                            logger.error(f"Failed to parse JSON response from Wavelog: {response_text[:200]}")
                            return {'success': False, 'message': 'Invalid JSON response from Wavelog API'}
                        
                        # Check if API indicates success
                        message = result.get('message', '').lower()
                        logger.debug(f"Wavelog API message: {message}")
                        logger.debug(f"API response keys: {list(result.keys())}")
                        
                        if 'successful' in message or 'export' in message or 'adif' in result:
                            # Extract ADIF string and parse it
                            adif_string = result.get('adif', '')
                            exported_qsos = int(result.get('exported_qsos', 0))
                            
                            logger.debug(f"ADIF data length: {len(adif_string)} chars, exported_qsos: {exported_qsos}")
                            
                            if adif_string:
                                # Parse ADIF to QSOs
                                qsos = self._adif_to_qsos(adif_string)
                                
                                # Log the parsed records
                                logger.debug(f"Parsed {len(qsos)} QSOs from ADIF")
                                if qsos:
                                    logger.debug(f"Sample QSO: {qsos[0]}")
                                
                                # REVERSE to get newest first (Wavelog ADIF comes in ascending order)
                                qsos = list(reversed(qsos))
                                
                                # Limit to requested amount
                                qsos = qsos[:limit]
                                
                                logger.info(f"✅ Retrieved {len(qsos)} recent contacts from Wavelog API (API returned {exported_qsos} total)")
                                return {'success': True, 'data': qsos}
                            else:
                                logger.warning(f"No ADIF data in response (exported_qsos: {exported_qsos})")
                                logger.debug(f"Full response: {result}")
                                return {'success': True, 'data': []}
                        else:
                            logger.warning(f"Wavelog API response: {result.get('message', 'Unknown error')}")
                            return {'success': False, 'message': result.get('message', 'Unknown error')}
                    else:
                        logger.error(f"Wavelog API error ({resp.status}): {response_text[:200]}")
                        return {'success': False, 'message': f'Wavelog API error: {resp.status}'}
            finally:
                # Always close the session we created
                if session and not session.closed:
                    try:
                        await session.close()
                    except:
                        pass
                    
        except asyncio.TimeoutError:
            logger.error(f"⏱️ Wavelog API timeout - request took too long. Try accessing Wavelog directly for full logbook.")
            return {'success': False, 'message': 'Wavelog API request timed out. Please try again or access Wavelog directly.'}
        except Exception as e:
            logger.error(f"Error fetching contacts from Wavelog API: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())
            return {'success': False, 'message': str(e)}
    
    async def get_all_contacts(self, limit: int = 100) -> Dict[str, Any]:
        """
        Get all recent contacts from Wavelog database (local cached copy).
        This retrieves all QSOs sorted by date (newest first).
        
        DEPRECATED: Use get_contacts_from_wavelog_api() instead for fresh data.
        
        Args:
            limit: Maximum number of QSOs to return
        
        Returns:
            Dictionary with success status and list of QSOs
        """
        try:
            logger.info(f"🔍 Fetching all contacts from Wavelog (limit: {limit})")
            
            db = get_wavelog_db()
            
            # Get all QSOs sorted by date descending (newest first)
            qsos_rows = db.get_all_qsos(limit=limit, offset=0)
            
            if qsos_rows:
                # Transform database rows to QSO format
                qsos = []
                for row in qsos_rows:
                    qso = self._transform_wavelog_qso(row)
                    qsos.append(qso)
                
                logger.info(f"✅ Retrieved {len(qsos)} contacts from Wavelog database")
                return {'success': True, 'data': qsos}
            else:
                logger.debug(f"ℹ️ No contacts found in database")
                return {'success': True, 'data': []}
                        
        except Exception as e:
            logger.error(f"Error getting all contacts: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())
            return {'success': False, 'message': str(e), 'data': []}
    
    async def get_recent_qsos(self, callsign: str, limit: int = 5) -> Dict[str, Any]:
        """
        Get recent QSOs with a callsign from Wavelog API.
        Calls api/get_contacts_adif and filters results for the specified callsign.
        """
        logger.info(f"🔍 Fetching recent QSOs from Wavelog API for: {callsign}")
        
        # Try the main callsign first
        result = await self._get_recent_qsos_internal(callsign, limit)
        
        if result.get('success'):
            logger.info(f"✅ Recent QSOs lookup succeeded for {callsign}")
            return result
        
        # If main callsign didn't match, try variants (with/without prefixes/suffixes)
        logger.debug(f"No QSOs found for main callsign, trying variants...")
        variants = generate_callsign_variants(callsign)
        
        for variant in variants:
            if variant == callsign:
                continue  # Already tried the main callsign
            
            logger.debug(f"  Trying variant: {variant}")
            result = await self._get_recent_qsos_internal(variant, limit)
            
            if result.get('success'):
                logger.info(f"✅ Recent QSOs lookup succeeded with variant: {variant}")
                return result
        
        # No variants matched either
        logger.debug(f"❌ No recent QSOs found for {callsign} or any variants")
        return {'success': False, 'message': 'No QSOs found'}
    
    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get general statistics from Wavelog API (api/statistics)
        Returns today's, month's, year's, and total QSOs
        """
        try:
            logger.info("🔍 Fetching statistics from Wavelog API")
            
            # Build the API endpoint URL
            url = f"{self.api_url}/api/statistics/{self.api_key}"
            
            logger.debug(f"  Request URL: {url}")
            
            session = await self._get_session()
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status in [200, 201]:  # Wavelog returns 201 for statistics
                    data = await response.json()
                    logger.info(f"✅ Statistics fetched successfully")
                    logger.debug(f"  Statistics data: {data}")
                    return {'success': True, 'data': data}
                else:
                    text = await response.text()
                    logger.error(f"❌ Wavelog API error {response.status}: {text}")
                    return {'success': False, 'message': f'API returned status {response.status}'}
        
        except asyncio.TimeoutError:
            logger.error("⏱️ Wavelog API timeout fetching statistics")
            return {'success': False, 'message': 'Request timed out'}
        except Exception as e:
            logger.error(f"Error fetching statistics from Wavelog API: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())
            return {'success': False, 'message': str(e)}
    
    async def get_wp_stats(self) -> Dict[str, Any]:
        """
        Get detailed statistics from Wavelog API (api/get_wp_stats)
        Returns total QSOs, this year's QSOs, and grouped by modes
        """
        try:
            logger.info("🔍 Fetching WP statistics from Wavelog API")
            
            # Build the API endpoint URL
            url = f"{self.api_url}/api/get_wp_stats"
            
            # Payload for the request
            payload = {
                "key": self.api_key,
                "station_id": self.station_id
            }
            
            logger.debug(f"  Request URL: {url}")
            logger.debug(f"  Payload: {payload}")
            
            session = await self._get_session()
            
            async with session.post(
                url,
                json=payload,
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"✅ WP Statistics fetched successfully")
                    logger.debug(f"  WP Statistics data: {data}")
                    return {'success': True, 'data': data}
                else:
                    text = await response.text()
                    logger.error(f"❌ Wavelog API error {response.status}: {text}")
                    return {'success': False, 'message': f'API returned status {response.status}'}
        
        except asyncio.TimeoutError:
            logger.error("⏱️ Wavelog API timeout fetching WP statistics")
            return {'success': False, 'message': 'Request timed out'}
        except Exception as e:
            logger.error(f"Error fetching WP statistics from Wavelog API: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())
            return {'success': False, 'message': str(e)}
