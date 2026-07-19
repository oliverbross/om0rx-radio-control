"""
QRZ XML Data Service Integration
Handles callsign lookups and profile information
"""

import aiohttp
import asyncio
import logging
from typing import Optional, Dict, Any
from defusedxml import ElementTree as ET
from urllib.parse import urlencode
from datetime import datetime, timezone
from radio_control import config
from radio_control.utils import generate_callsign_variants
from radio_control.persistence import atomic_write_json, read_json_object

logger = logging.getLogger(__name__)
MAX_XML_RESPONSE_BYTES = 2 * 1024 * 1024


async def _bounded_response_text(response, max_bytes: int = MAX_XML_RESPONSE_BYTES) -> str:
    content_length = response.headers.get("Content-Length")
    if content_length and int(content_length) > max_bytes:
        raise ValueError("QRZ response exceeded the allowed size")
    payload = await response.content.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise ValueError("QRZ response exceeded the allowed size")
    return payload.decode(response.charset or "utf-8", errors="replace")

QRZ_HTTP_TIMEOUT_SEC = 6
QRZ_PROFILE_CACHE_TTL_SEC = 24 * 60 * 60


class QRZClient:
    """QRZ XML data service client for profile and callsign lookups"""
    
    def __init__(self):
        self.username = config.QRZ_USERNAME
        self.password = config.QRZ_PASSWORD
        self.api_url = "https://xmldata.qrz.com/xml/current/"
        self.session_key = None
        self.last_session_error = ""
        self.cache_path = config.DATA_DIR / "qrz_profile_cache.json"
        self.profile_cache: Dict[str, Dict[str, Any]] = self._load_profile_cache()
        logger.info(f"🔌 QRZ Client initialized for user: {self.username}")

    def _load_profile_cache(self) -> Dict[str, Dict[str, Any]]:
        try:
            data = read_json_object(self.cache_path, quarantine_corrupt=True)
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.debug("Could not load QRZ profile cache: %s", exc)
            return {}

    def _save_profile_cache(self) -> None:
        try:
            atomic_write_json(self.cache_path, self.profile_cache)
        except Exception as exc:
            logger.debug("Could not save QRZ profile cache: %s", exc)

    def _cache_entry_for(self, callsign: str) -> Optional[Dict[str, Any]]:
        key = (callsign or "").strip().upper()
        entry = self.profile_cache.get(key)
        if not isinstance(entry, dict):
            return None
        timestamp = entry.get("timestamp")
        profile = entry.get("profile")
        if not isinstance(timestamp, (int, float)) or not isinstance(profile, dict):
            return None
        if datetime.now(timezone.utc).timestamp() - timestamp > QRZ_PROFILE_CACHE_TTL_SEC:
            return None
        return profile

    def _store_profile_cache(self, requested: str, resolved: str, profile: Dict[str, Any]) -> None:
        if not profile.get("success"):
            return
        now = datetime.now(timezone.utc).timestamp()
        profile = {
            **profile,
            "cache_timestamp": now,
            "cache_ttl_sec": QRZ_PROFILE_CACHE_TTL_SEC,
            "cache_source": "qrz_live",
        }
        for key in {requested.strip().upper(), resolved.strip().upper()}:
            if key:
                self.profile_cache[key] = {"timestamp": now, "profile": profile}
        self._save_profile_cache()
        
    async def _get_session_key(self) -> Optional[str]:
        """Authenticate with QRZ and get session key using XML API"""
        try:
            params = {
                'username': self.username,
                'password': self.password,
                'agent': 'OM0RXRadioControl/2.0'
            }
            
            url = f"{self.api_url}?{urlencode(params)}"
            logger.info(f"🔐 Attempting QRZ authentication for user: {self.username}")
            logger.debug(f"QRZ auth URL: {url[:100]}...")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=QRZ_HTTP_TIMEOUT_SEC)
                ) as resp:
                    logger.info("QRZ authentication response status: %s", resp.status)
                    
                    if resp.status == 200:
                        response_text = await _bounded_response_text(resp)
                        
                        try:
                            # Parse XML response
                            root = ET.fromstring(response_text)
                            logger.debug(f"✅ Successfully parsed XML, root tag: {root.tag}")
                            
                            # Handle XML namespace - QRZ uses xmlns="http://xmldata.qrz.com"
                            ns = {'qrz': 'http://xmldata.qrz.com'}
                            
                            # QRZ XML format: <QRZDatabase><Session><Key>...</Key></Session></QRZDatabase>
                            # Try with namespace first, then without
                            session_elem = root.find("qrz:Session", ns)
                            if session_elem is None:
                                session_elem = root.find("Session")
                            
                            if session_elem is not None:
                                # Check for error first
                                error_elem = session_elem.find("qrz:Error", ns)
                                if error_elem is None:
                                    error_elem = session_elem.find("Error")
                                    
                                if error_elem is not None and error_elem.text:
                                    self.last_session_error = error_elem.text.strip()
                                    logger.error(f"❌ QRZ authentication failed: {self.last_session_error}")
                                    return None
                                
                                # Get session key
                                key_elem = session_elem.find("qrz:Key", ns)
                                if key_elem is None:
                                    key_elem = session_elem.find("Key")
                                    
                                if key_elem is not None and key_elem.text:
                                    self.session_key = key_elem.text
                                    logger.info("QRZ session established")
                                    return self.session_key
                                else:
                                    logger.error("❌ No session key in QRZ response")
                                    logger.debug(f"Full response: {response_text[:1000]}")
                                    return None
                            else:
                                logger.error("❌ No Session element in QRZ response")
                                logger.debug(f"Full response: {response_text[:1000]}")
                                return None
                                
                        except ET.ParseError as pe:
                            logger.error(f"❌ Failed to parse QRZ XML response: {pe}")
                            logger.debug(f"Response text (first 1000 chars): {response_text[:1000]}")
                            return None
                    else:
                        response_text = await _bounded_response_text(resp)
                        logger.error(f"❌ QRZ session request failed: HTTP {resp.status}")
                        logger.debug(f"Error response: {response_text[:500]}")
                        return None
                        
        except (asyncio.TimeoutError, TimeoutError):
            self.last_session_error = "QRZ session request timed out"
            logger.warning(self.last_session_error)
            return None
        except Exception as e:
            self.last_session_error = str(e)
            logger.error(f"❌ QRZ session error: {str(e)}", exc_info=True)
            return None
    
    def _auth_failure_result(self) -> Dict[str, Any]:
        message = self.last_session_error or "QRZ authentication failed"
        return {
            'success': False,
            'message': f'QRZ authentication failed: {message}',
            'error_type': 'auth',
            'retryable': False,
        }

    @staticmethod
    def _is_qrz_not_found(message: str) -> bool:
        value = str(message or "").lower()
        return "not found" in value or "not in database" in value

    @staticmethod
    def _is_qrz_session_error(message: str) -> bool:
        value = str(message or "").lower()
        return "timeout" in value or "session" in value or "key" in value

    async def _lookup_profile_internal(self, callsign: str, *, retry_session: bool = True) -> Dict[str, Any]:
        """
        Internal method to perform actual QRZ profile lookup for a single callsign.
        This does NOT implement fallback - that's handled by get_profile_picture.
        """
        try:
            # Re-authenticate if needed
            if not self.session_key:
                logger.info("ℹ️ No session key, re-authenticating...")
                await self._get_session_key()
            
            if not self.session_key:
                logger.error("❌ Failed to obtain QRZ session key")
                return self._auth_failure_result()
            
            # Build callsign lookup request
            params = {
                's': self.session_key,
                'callsign': callsign.upper()
            }
            
            url = f"{self.api_url}?{urlencode(params)}"
            logger.debug(f"QRZ profile URL: {url[:100]}...")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=QRZ_HTTP_TIMEOUT_SEC)
                ) as resp:
                    logger.info(f"📊 QRZ profile response status: {resp.status} for {callsign}")
                    
                    if resp.status == 200:
                        response_text = await _bounded_response_text(resp)
                        logger.debug(f"📝 QRZ profile response (first 200 chars): {response_text[:200]}")
                        
                        try:
                            root = ET.fromstring(response_text)
                            logger.debug(f"✅ Successfully parsed XML, root tag: {root.tag}")
                            
                            # Handle XML namespace - QRZ uses xmlns="http://xmldata.qrz.com"
                            ns = {'qrz': 'http://xmldata.qrz.com'}
                            
                            # Check session/error first
                            session_elem = root.find("qrz:Session", ns)
                            if session_elem is None:
                                session_elem = root.find("Session")
                                
                            if session_elem is not None:
                                error_elem = session_elem.find("qrz:Error", ns)
                                if error_elem is None:
                                    error_elem = session_elem.find("Error")
                                    
                                if error_elem is not None and error_elem.text:
                                    error_text = error_elem.text
                                    logger.debug(f"QRZ error for {callsign}: {error_text}")
                                    
                                    # Check if it's a session timeout - need to re-authenticate and retry once.
                                    if retry_session and self._is_qrz_session_error(error_text):
                                        logger.info("🔄 Session expired, re-authenticating...")
                                        self.session_key = None
                                        if await self._get_session_key():
                                            return await self._lookup_profile_internal(callsign, retry_session=False)
                                        return self._auth_failure_result()
                                    
                                    return {
                                        'success': False,
                                        'message': error_text,
                                        'error_type': 'not_found' if self._is_qrz_not_found(error_text) else 'qrz_error',
                                        'retryable': not self._is_qrz_not_found(error_text),
                                    }
                                
                                # Update session key from response if provided
                                key_elem = session_elem.find("qrz:Key", ns)
                                if key_elem is None:
                                    key_elem = session_elem.find("Key")
                                    
                                if key_elem is not None and key_elem.text:
                                    self.session_key = key_elem.text
                            
                            # Extract callsign data
                            callsign_elem = root.find("qrz:Callsign", ns)
                            if callsign_elem is None:
                                callsign_elem = root.find("Callsign")
                                
                            if callsign_elem is not None:
                                def get_text(elem, tag: str, namespace_dict=None) -> str:
                                    """Helper to extract text from XML element with namespace support"""
                                    # Try with namespace first
                                    if namespace_dict:
                                        child = elem.find(f"qrz:{tag}", namespace_dict)
                                    else:
                                        child = None
                                    # Fall back to no namespace
                                    if child is None:
                                        child = elem.find(tag)
                                    return child.text if child is not None and child.text else ''
                                
                                fname = get_text(callsign_elem, 'fname', ns)
                                lname = get_text(callsign_elem, 'name', ns)  # Note: 'name' is last name in QRZ XML
                                image_url = get_text(callsign_elem, 'image', ns)
                                country = get_text(callsign_elem, 'country', ns)
                                state = get_text(callsign_elem, 'state', ns)
                                grid = get_text(callsign_elem, 'grid', ns)
                                email = get_text(callsign_elem, 'email', ns)
                                
                                # Additional fields
                                nickname = get_text(callsign_elem, 'nickname', ns)
                                name_fmt = get_text(callsign_elem, 'name_fmt', ns)
                                addr1 = get_text(callsign_elem, 'addr1', ns)
                                addr2 = get_text(callsign_elem, 'addr2', ns)
                                zip_code = get_text(callsign_elem, 'zip', ns)
                                county = get_text(callsign_elem, 'county', ns)
                                url = get_text(callsign_elem, 'url', ns)
                                iota = get_text(callsign_elem, 'iota', ns)
                                cqzone = get_text(callsign_elem, 'cqzone', ns)
                                ituzone = get_text(callsign_elem, 'ituzone', ns)
                                class_license = get_text(callsign_elem, 'class', ns)
                                born = get_text(callsign_elem, 'born', ns)
                                eqsl = get_text(callsign_elem, 'eqsl', ns)
                                mqsl = get_text(callsign_elem, 'mqsl', ns)
                                lotw = get_text(callsign_elem, 'lotw', ns)
                                qslmgr = get_text(callsign_elem, 'qslmgr', ns)
                                
                                logger.debug(f"QRZ extracted values - fname: {fname}, lname: {lname}, image: {image_url[:50] if image_url else 'None'}, country: {country}")
                                
                                # Build name - use name_fmt if available, otherwise build manually
                                if name_fmt:
                                    name = name_fmt
                                else:
                                    name_parts = [n for n in [fname, lname] if n]
                                    name = ' '.join(name_parts) if name_parts else callsign.upper()
                                
                                result = {
                                    'success': True,
                                    'image_url': image_url,
                                    'name': name,
                                    'nickname': nickname,
                                    'country': country,
                                    'state': state,
                                    'grid': grid,
                                    'email': email,
                                    'address': f"{addr1} {addr2}".strip() if (addr1 or addr2) else '',
                                    'zip': zip_code,
                                    'county': county,
                                    'url': url,
                                    'iota': iota,
                                    'cqzone': cqzone,
                                    'ituzone': ituzone,
                                    'class': class_license,
                                    'born': born,
                                    'eqsl': eqsl,
                                    'mqsl': mqsl,
                                    'lotw': lotw,
                                    'qslmgr': qslmgr,
                                }
                                
                                logger.info(f"✅ QRZ profile retrieved for {callsign}: {name} from {country if country else state}")
                                return result
                            else:
                                # No callsign element
                                logger.debug(f"No Callsign element in response for {callsign}")
                                return {'success': False, 'message': 'Callsign not found', 'error_type': 'not_found'}
                        
                        except ET.ParseError as pe:
                            logger.error(f"Failed to parse QRZ profile XML: {pe}")
                            return {'success': False, 'message': f'XML parse error: {str(pe)}'}
                    else:
                        response_text = await _bounded_response_text(resp)
                        logger.error(f"QRZ profile request failed: HTTP {resp.status}")
                        return {'success': False, 'message': f'QRZ lookup failed: HTTP {resp.status}'}
                        
        except (asyncio.TimeoutError, TimeoutError):
            logger.warning("QRZ profile lookup timed out for %s", callsign)
            return {'success': False, 'message': 'QRZ lookup timed out', 'error_type': 'timeout', 'retryable': True}
        except Exception as e:
            logger.error(f"❌ QRZ profile lookup error for {callsign}: {str(e)}", exc_info=True)
            return {'success': False, 'message': str(e), 'error_type': 'qrz_error', 'retryable': True}
    
    async def lookup(self, callsign: str) -> Dict[str, Any]:
        """
        Simplified QRZ lookup for QSO enrichment.
        Returns only the essential fields needed for logging:
        fname, grid, state, country, cqzone, ituzone, continent, lat, lon, email, lotw
        
        Used by WSJT-X auto-logging and other services.
        """
        try:
            profile = await self.get_profile_picture(callsign)
            
            if not profile.get('success'):
                return {}
            
            # Map profile fields to the simplified format
            return {
                'fname': profile.get('name', ''),  # Full name from profile
                'grid': profile.get('grid', ''),
                'state': profile.get('state', ''),
                'country': profile.get('country', ''),
                'cqzone': profile.get('cqzone', ''),
                'ituzone': profile.get('ituzone', ''),
                'continent': '',  # QRZ doesn't directly provide continent - would need separate mapping
                'lat': '',  # QRZ XML API doesn't return lat/lon directly in the profile
                'lon': '',
                'email': profile.get('email', ''),
                'lotw': profile.get('lotw', False),
            }
        except Exception as e:
            logger.error(f"❌ QRZ lookup error for {callsign}: {str(e)}")
            return {}

    async def get_profile_picture(self, callsign: str) -> Dict[str, Any]:
        """
        Get QRZ profile picture URL and info for a callsign.
        Uses fallback strategy: tries original callsign first, then variants (with/without prefixes/suffixes).
        
        Returns:
            Dict with success flag and profile data
        """
        callsign_upper = (callsign or "").strip().upper()
        cached = self._cache_entry_for(callsign_upper)
        if cached:
            logger.debug("Using cached QRZ profile for %s", callsign_upper)
            return {**cached, "cache_source": "qrz_file_cache"}

        logger.info(f"🔍 Fetching QRZ profile for callsign: {callsign_upper}")
        
        # Generate list of callsigns to try (original first, then fallbacks)
        variants = generate_callsign_variants(callsign_upper)
        
        failures = []
        for variant in variants:
            cached_variant = self._cache_entry_for(variant)
            if cached_variant:
                logger.debug("Using cached QRZ profile for variant %s (requested %s)", variant, callsign_upper)
                return {**cached_variant, "cache_source": "qrz_file_cache"}

            logger.debug(f"  Trying QRZ lookup for variant: {variant}")
            result = await self._lookup_profile_internal(variant)
            
            if result.get('success'):
                self._store_profile_cache(callsign_upper, variant, result)
                logger.info(f"✅ QRZ lookup succeeded with variant: {variant} (requested: {callsign_upper})")
                return result
            else:
                failures.append(result)
                logger.debug(f"  QRZ lookup failed for variant {variant}: {result.get('message', 'Unknown error')}")
                if result.get("error_type") in {"auth", "timeout", "qrz_error"} and not self._is_qrz_not_found(result.get("message", "")):
                    return result
        
        # All variants failed
        logger.warning(f"❌ QRZ lookup failed for all variants of {callsign}")
        message = f'Callsign not found (tried: {", ".join(variants)})'
        return {'success': False, 'message': message, 'error_type': 'not_found', 'failures': failures[-3:]}
    
    async def get_contact_history(self, callsign: str, limit: int = 20) -> Dict[str, Any]:
        """
        Get recent contact history with a callsign
        
        Returns:
            List of recent QSOs
        """
        try:
            logger.info(f"🔍 Fetching QRZ history for callsign: {callsign}")
            
            if not self.session_key:
                await self._get_session_key()
            
            if not self.session_key:
                logger.warning("Cannot fetch history without session key")
                return {'success': False, 'data': []}
            
            # Get profile first (which updates session)
            profile = await self.get_profile_picture(callsign)
            
            if not profile.get('success'):
                return {'success': False, 'data': []}
            
            # Note: QRZ XML API doesn't directly expose QSO history for other stations
            # The history would only be available for the logged-in user's own logbook
            # For now, return empty list as QRZ doesn't provide public QSO history
            
            logger.debug(f"QRZ history for {callsign}: Not available (QRZ doesn't expose other user QSOs)")
            return {'success': True, 'data': []}
                        
        except Exception as e:
            logger.error(f"❌ QRZ contact history error: {str(e)}", exc_info=True)
            return {'success': False, 'data': []}
