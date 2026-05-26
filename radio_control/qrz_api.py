"""
QRZ XML Data Service Integration
Handles callsign lookups and profile information
"""

import aiohttp
import logging
from typing import Optional, Dict, Any
import xml.etree.ElementTree as ET
from urllib.parse import urlencode
from radio_control import config
from radio_control.utils import generate_callsign_variants

logger = logging.getLogger(__name__)


class QRZClient:
    """QRZ XML data service client for profile and callsign lookups"""
    
    def __init__(self):
        self.username = config.QRZ_USERNAME
        self.password = config.QRZ_PASSWORD
        self.api_url = "https://xmldata.qrz.com/xml/current/"
        self.session_key = None
        logger.info(f"🔌 QRZ Client initialized for user: {self.username}")
        
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
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    logger.info(f"📊 QRZ session response status: {resp.status}")
                    
                    if resp.status == 200:
                        response_text = await resp.text()
                        logger.info(f"📝 QRZ session response (first 500 chars): {response_text[:500]}")
                        
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
                                    logger.error(f"❌ QRZ authentication failed: {error_elem.text}")
                                    return None
                                
                                # Get session key
                                key_elem = session_elem.find("qrz:Key", ns)
                                if key_elem is None:
                                    key_elem = session_elem.find("Key")
                                    
                                if key_elem is not None and key_elem.text:
                                    self.session_key = key_elem.text
                                    logger.info(f"✅ QRZ session established, key: {self.session_key[:15]}...")
                                    return self.session_key
                                else:
                                    logger.error(f"❌ No session key in QRZ response")
                                    logger.debug(f"Full response: {response_text[:1000]}")
                                    return None
                            else:
                                logger.error(f"❌ No Session element in QRZ response")
                                logger.debug(f"Full response: {response_text[:1000]}")
                                return None
                                
                        except ET.ParseError as pe:
                            logger.error(f"❌ Failed to parse QRZ XML response: {pe}")
                            logger.debug(f"Response text (first 1000 chars): {response_text[:1000]}")
                            return None
                    else:
                        response_text = await resp.text()
                        logger.error(f"❌ QRZ session request failed: HTTP {resp.status}")
                        logger.debug(f"Error response: {response_text[:500]}")
                        return None
                        
        except Exception as e:
            logger.error(f"❌ QRZ session error: {str(e)}", exc_info=True)
            return None
    
    async def _lookup_profile_internal(self, callsign: str) -> Dict[str, Any]:
        """
        Internal method to perform actual QRZ profile lookup for a single callsign.
        This does NOT implement fallback - that's handled by get_profile_picture.
        """
        try:
            # Re-authenticate if needed
            if not self.session_key:
                logger.info(f"ℹ️ No session key, re-authenticating...")
                await self._get_session_key()
            
            if not self.session_key:
                logger.error(f"❌ Failed to obtain QRZ session key")
                return {'success': False, 'message': 'QRZ authentication failed'}
            
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
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    logger.info(f"📊 QRZ profile response status: {resp.status} for {callsign}")
                    
                    if resp.status == 200:
                        response_text = await resp.text()
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
                                    
                                    # Check if it's a session timeout - need to re-authenticate
                                    if "timeout" in error_text.lower() or "session" in error_text.lower():
                                        logger.info("🔄 Session expired, re-authenticating...")
                                        self.session_key = None
                                        await self._get_session_key()
                                    
                                    return {'success': False, 'message': error_text}
                                
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
                                return {'success': False, 'message': 'Callsign not found'}
                        
                        except ET.ParseError as pe:
                            logger.error(f"Failed to parse QRZ profile XML: {pe}")
                            return {'success': False, 'message': f'XML parse error: {str(pe)}'}
                    else:
                        response_text = await resp.text()
                        logger.error(f"QRZ profile request failed: HTTP {resp.status}")
                        return {'success': False, 'message': f'QRZ lookup failed: HTTP {resp.status}'}
                        
        except Exception as e:
            logger.error(f"❌ QRZ profile lookup error for {callsign}: {str(e)}", exc_info=True)
            return {'success': False, 'message': str(e)}
    
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
        logger.info(f"🔍 Fetching QRZ profile for callsign: {callsign}")
        
        # Generate list of callsigns to try (original first, then fallbacks)
        variants = generate_callsign_variants(callsign)
        
        for variant in variants:
            logger.debug(f"  Trying QRZ lookup for variant: {variant}")
            result = await self._lookup_profile_internal(variant)
            
            if result.get('success'):
                logger.info(f"✅ QRZ lookup succeeded with variant: {variant} (requested: {callsign})")
                return result
            else:
                logger.debug(f"  QRZ lookup failed for variant {variant}: {result.get('message', 'Unknown error')}")
        
        # All variants failed
        logger.warning(f"❌ QRZ lookup failed for all variants of {callsign}")
        return {'success': False, 'message': f'Callsign not found (tried: {", ".join(variants)})'}
    
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
                logger.warning(f"Cannot fetch history without session key")
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
