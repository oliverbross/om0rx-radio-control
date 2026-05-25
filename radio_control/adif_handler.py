"""
ADIF File Handler
Creates and maintains local ADIF log files for QSO backup
"""

import logging
from typing import Dict, Any
from datetime import datetime
from pathlib import Path
from radio_control import config
logger = logging.getLogger(__name__)


class ADIFHandler:
    """Handles ADIF file operations for local QSO backup"""
    
    ADIF_HEADER = """Amateur Radio Logbook
<ADIF_VER:4>3.1.0
<PROGRAMID:13>WaveFlex Spots
<PROGRAMVERSION:5>1.0.0
<EOH>"""

    def __init__(self, log_path: str = None):
        self.log_path = Path(log_path or config.ADIF_LOG_PATH)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        
    def _format_adif_field(self, field_name: str, value: Any) -> str:
        """Format a single ADIF field"""
        if value is None or value == '':
            return ''
        
        value_str = str(value).upper() if isinstance(value, str) else str(value)
        length = len(value_str)
        return f"<{field_name}:{length}>{value_str}"
    
    def _qso_to_adif_record(self, qso: Dict[str, Any]) -> str:
        """Convert QSO dictionary to ADIF record format"""
        
        # Mandatory fields
        record = self._format_adif_field("CALL", qso.get('callsign', ''))
        
        # Frequency (in MHz)
        freq = qso.get('frequency', 0)
        record += f"\n{self._format_adif_field('FREQ', f'{freq:.6f}')}"
        
        # Mode
        mode = qso.get('mode', 'SSB').upper()
        record += f"\n{self._format_adif_field('MODE', mode)}"
        
        # Band (CRITICAL for "Worked b4" feature - matches spots by CALL-BAND-MODE)
        band = qso.get('band', '')
        if band:
            record += f"\n{self._format_adif_field('BAND', band)}"
        
        # Date and Time (UTC)
        date_str = qso.get('date_time', datetime.utcnow().isoformat())
        # Parse ISO format datetime
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except:
            dt = datetime.utcnow()
        
        adif_date = dt.strftime("%Y%m%d")
        adif_time = dt.strftime("%H%M%S")
        record += f"\n{self._format_adif_field('QSO_DATE', adif_date)}"
        record += f"\n{self._format_adif_field('TIME_ON', adif_time)}"
        
        # RST Sent/Received
        record += f"\n{self._format_adif_field('RST_SENT', qso.get('rst_sent', 599))}"
        record += f"\n{self._format_adif_field('RST_RCVD', qso.get('rst_received', 599))}"
        
        # Operator station
        record += f"\n{self._format_adif_field('STATION_CALLSIGN', config.MY_STATION)}"
        
        # Optional fields
        if qso.get('name'):
            record += f"\n{self._format_adif_field('NAME', qso['name'])}"
        
        if qso.get('qth'):
            record += f"\n{self._format_adif_field('QTH', qso['qth'])}"
        
        # Check both 'grid' and 'gridsquare' keys (frontend uses 'gridsquare')
        grid = qso.get('gridsquare') or qso.get('grid')
        if grid:
            record += f"\n{self._format_adif_field('GRIDSQUARE', grid)}"
        
        # Special references
        if qso.get('pota'):
            record += f"\n{self._format_adif_field('POTA_REF', qso['pota'])}"
        
        if qso.get('sota'):
            record += f"\n{self._format_adif_field('SOTA_REF', qso['sota'])}"
        
        if qso.get('iota'):
            record += f"\n{self._format_adif_field('IOTA', qso['iota'])}"
        
        if qso.get('wwff'):
            record += f"\n{self._format_adif_field('WWFF_REF', qso['wwff'])}"
        
        # Comments/Notes
        if qso.get('notes'):
            record += f"\n{self._format_adif_field('COMMENT', qso['notes'])}"
        
        # End of record
        record += "\n<EOR>"
        
        return record
    
    def add_qso(self, qso: Dict[str, Any]) -> bool:
        """
        Add a QSO record to the ADIF log file
        
        Args:
            qso: Dictionary with QSO details
        
        Returns:
            True if successful, False otherwise
        """
        import time
        max_retries = 3
        retry_delay = 0.1  # Start with 100ms
        
        for attempt in range(max_retries):
            try:
                # Create file if it doesn't exist
                if not self.log_path.exists():
                    try:
                        with open(self.log_path, 'w', encoding='utf-8') as f:
                            f.write(self.ADIF_HEADER + "\n\n")
                        logger.info(f"✅ Created ADIF log file: {self.log_path}")
                    except (IOError, OSError) as e:
                        logger.warning(f"Failed to create ADIF file on attempt {attempt+1}: {str(e)}")
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                            continue
                        raise
                
                # Append QSO record with explicit encoding and error handling
                adif_record = self._qso_to_adif_record(qso)
                try:
                    with open(self.log_path, 'a', encoding='utf-8') as f:
                        f.write(adif_record + "\n\n")
                        f.flush()  # Explicitly flush to disk
                except (IOError, OSError) as e:
                    logger.warning(f"Failed to write ADIF record on attempt {attempt+1}: {str(e)}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                        continue
                    raise
                
                logger.info(f"✅ QSO added to ADIF log: {qso.get('callsign')}")
                return True
                
            except Exception as e:
                logger.error(f"ADIF write error (attempt {attempt+1}/{max_retries}): {str(e)}", exc_info=True)
                if attempt == max_retries - 1:
                    # Final attempt failed, log and return False
                    return False
    
    def read_qso_count(self) -> int:
        """Get number of QSOs in log file"""
        try:
            if not self.log_path.exists():
                return 0
            
            with open(self.log_path, 'r', encoding='utf-8') as f:
                content = f.read()
                return content.count('<EOR>')
                
        except Exception as e:
            logger.error(f"ADIF read error: {str(e)}")
            return 0
    
    def read_all_qsos(self) -> list:
        """
        Read all QSOs from ADIF log file
        
        Returns:
            List of all QSO records (most recent first)
        """
        try:
            if not self.log_path.exists():
                return []
            
            qsos = []
            
            with open(self.log_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Split by EOR markers to get individual records
                records = content.split('<EOR>')
                
                for record in records:
                    if not record.strip():
                        continue
                    
                    # Parse the ADIF record
                    qso_data = self._parse_adif_record(record)
                    qsos.append(qso_data)
            
            # Sort by date AND time (most recent first)
            # Use tuple sort: (qso_date, time_on) in descending order
            qsos.sort(key=lambda x: (x.get('qso_date', ''), x.get('time_on', '')), reverse=True)
            return qsos
                
        except Exception as e:
            logger.error(f"ADIF read all QSOs error: {str(e)}")
            return []
    
    def read_recent_qsos_by_callsign(self, callsign: str, limit: int = 5) -> list:
        """
        Read recent QSOs for a specific callsign from ADIF log file
        
        Args:
            callsign: Call sign to search for
            limit: Maximum number of QSOs to return
        
        Returns:
            List of QSO records matching the callsign (most recent first)
        """
        try:
            if not self.log_path.exists():
                return []
            
            callsign_upper = callsign.upper()
            qsos = []
            
            with open(self.log_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Split by EOR markers to get individual records
                records = content.split('<EOR>')
                
                for record in records:
                    if not record.strip():
                        continue
                    
                    # Parse the ADIF record
                    qso_data = self._parse_adif_record(record)
                    
                    # Check if this QSO matches the callsign
                    if qso_data.get('call', '').upper() == callsign_upper:
                        qsos.append(qso_data)
            
            # Sort by date AND time (most recent first) and limit results
            qsos.sort(key=lambda x: (x.get('qso_date', ''), x.get('time_on', '')), reverse=True)
            return qsos[:limit]
                
        except Exception as e:
            logger.error(f"ADIF read recent QSOs error for {callsign}: {str(e)}")
            return []
    
    def _parse_adif_record(self, record: str) -> dict:
        """Parse a single ADIF record into a dictionary with required fields"""
        # Initialize with defaults for all required fields
        result = {
            'call': '',
            'qso_date': '',
            'time_on': '',
            'mode': '',
            'frequency': 0,
            'rst_sent': '',
            'rst_rcvd': '',
            'band': '',
            'lotw_qsl': '',
            'name': '',
            'qth': '',
            'gridsquare': '',
            'pota_ref': '',
            'sota_ref': '',
            'iota': '',
            'wwff_ref': '',
            'comment': ''
        }
        
        # Parse all ADIF fields - MUST respect the length field!
        import re
        pattern = r'<([A-Z_]+):(\d+)>'
        
        pos = 0
        for match in re.finditer(pattern, record):
            field_name = match.group(1).lower()
            field_length = int(match.group(2))
            
            # Extract exactly field_length characters after the >
            value_start = match.end()
            field_value = record[value_start:value_start + field_length].strip()
            
            # Skip empty fields
            if not field_value:
                continue
            
            # Map ADIF field names to our output format
            if field_name == 'call':
                result['call'] = field_value
            elif field_name == 'qso_date':
                result['qso_date'] = field_value
            elif field_name == 'time_on':
                result['time_on'] = field_value
            elif field_name == 'mode':
                result['mode'] = field_value
            elif field_name == 'freq':
                try:
                    result['frequency'] = float(field_value)
                except ValueError:
                    result['frequency'] = 0
            elif field_name == 'rst_sent':
                result['rst_sent'] = field_value
            elif field_name == 'rst_rcvd':
                result['rst_rcvd'] = field_value
            elif field_name == 'rst_received':
                result['rst_rcvd'] = field_value
            elif field_name == 'band':
                result['band'] = field_value
            elif field_name == 'lotw_qsl':
                result['lotw_qsl'] = field_value
            elif field_name == 'name':
                result['name'] = field_value
            elif field_name == 'qth':
                result['qth'] = field_value
            elif field_name == 'gridsquare':
                result['gridsquare'] = field_value
            elif field_name == 'pota_ref':
                result['pota_ref'] = field_value
            elif field_name == 'sota_ref':
                result['sota_ref'] = field_value
            elif field_name == 'iota':
                result['iota'] = field_value
            elif field_name == 'wwff_ref':
                result['wwff_ref'] = field_value
            elif field_name == 'comment':
                result['comment'] = field_value
        
        # Derive band from frequency if not present
        if not result['band'] and result['frequency']:
            result['band'] = self._frequency_to_band(result['frequency'])
        
        return result
    
    def _frequency_to_band(self, freq_mhz: float) -> str:
        """Convert frequency in MHz to band designation"""
        freq = float(freq_mhz)
        
        # Band definitions
        bands = [
            (1.8, 2.0, '160m'),
            (3.5, 3.6, '80m'),
            (5.3, 5.4, '60m'),
            (7.0, 7.3, '40m'),
            (10.1, 10.15, '30m'),
            (14.0, 14.35, '20m'),
            (18.068, 18.168, '17m'),
            (21.0, 21.45, '15m'),
            (24.89, 24.99, '12m'),
            (28.0, 29.7, '10m'),
            (50.0, 54.0, '6m'),
            (144.0, 148.0, '2m'),
            (220.0, 225.0, '1.25m'),
            (430.0, 450.0, '70cm'),
        ]
        
        for low, high, band in bands:
            if low <= freq <= high:
                return band
        
        return 'Unknown'