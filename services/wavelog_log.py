"""
Wavelog Log Service - Direct database access for log viewing
Provides fast, direct access to Wavelog database for displaying QSO log
"""

import logging
from typing import List, Dict
from datetime import datetime
import pymysql
from pymysql.cursors import DictCursor
from radio_control import config
logger = logging.getLogger(__name__)


class WavelogLogService:
    """Service for accessing Wavelog log data directly from database"""
    
    def __init__(self):
        self.db_config = {
            'host': config.DB_HOST,
            'port': config.DB_PORT,
            'user': config.DB_USER,
            'password': config.DB_PASS,
            'database': config.DB_NAME,
            'charset': 'utf8mb4',
            'cursorclass': DictCursor
        }
        logger.info(f"WavelogLogService initialized for database {config.DB_NAME}")
    
    def _get_connection(self):
        """Create a new database connection"""
        try:
            return pymysql.connect(**self.db_config)
        except Exception as e:
            logger.error(f"Failed to connect to Wavelog database: {e}")
            raise
    
    def get_log_entries(self, limit: int = 100, station_id: int = 1) -> List[Dict]:
        """
        Fetch log entries from Wavelog database
        
        Args:
            limit: Maximum number of entries to return (default 100)
            station_id: Station profile ID (default 1)
            
        Returns:
            List of log entries with relevant fields
        """
        try:
            conn = self._get_connection()
            
            # Query to fetch log entries with all relevant fields
            query = """
                SELECT 
                    COL_PRIMARY_KEY as id,
                    COL_TIME_ON as time_on,
                    COL_TIME_OFF as time_off,
                    COL_CALL as callsign,
                    COL_BAND as band,
                    COL_FREQ as frequency,
                    COL_MODE as mode,
                    COL_SUBMODE as submode,
                    COL_RST_SENT as rst_sent,
                    COL_RST_RCVD as rst_rcvd,
                    COL_NAME as name,
                    COL_QTH as qth,
                    COL_GRIDSQUARE as gridsquare,
                    COL_COUNTRY as country,
                    COL_DXCC as dxcc,
                    COL_CQZ as cqz,
                    COL_ITUZ as ituz,
                    COL_STATE as state,
                    COL_CNTY as county,
                    COL_IOTA as iota,
                    COL_CONT as continent,
                    COL_TX_PWR as tx_pwr,
                    COL_COMMENT as comment,
                    COL_LOTW_QSL_SENT as lotw_sent,
                    COL_LOTW_QSL_RCVD as lotw_rcvd,
                    COL_QSL_SENT as qsl_sent,
                    COL_QSL_RCVD as qsl_rcvd,
                    COL_EQSL_QSL_SENT as eqsl_sent,
                    COL_EQSL_QSL_RCVD as eqsl_rcvd,
                    COL_POTA_REF as pota_ref,
                    COL_SOTA_REF as sota_ref,
                    COL_WWFF_REF as wwff_ref,
                    COL_SIG as sig,
                    COL_SIG_INFO as sig_info,
                    station_id
                FROM TABLE_HRD_CONTACTS_V01
                WHERE station_id = %s
                ORDER BY COL_TIME_ON DESC
                LIMIT %s
            """
            
            with conn.cursor() as cursor:
                cursor.execute(query, (station_id, limit))
                results = cursor.fetchall()
                
                # Process results to format dates and handle nulls
                processed_results = []
                for row in results:
                    processed_row = {}
                    for key, value in row.items():
                        # Format datetime objects
                        if isinstance(value, datetime):
                            processed_row[key] = value.strftime('%Y-%m-%d %H:%M:%S')
                        # Convert frequency from Hz to MHz
                        elif key == 'frequency' and value:
                            processed_row[key] = float(value) / 1000000
                        # Handle None values
                        else:
                            processed_row[key] = value if value is not None else ''
                    
                    processed_results.append(processed_row)
                
                logger.info(f"Fetched {len(processed_results)} log entries from Wavelog database")
                return processed_results
                
        except Exception as e:
            logger.error(f"Error fetching log entries: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def get_log_stats(self, station_id: int = 1) -> Dict:
        """
        Get statistics about the log
        
        Args:
            station_id: Station profile ID (default 1)
            
        Returns:
            Dictionary with log statistics
        """
        try:
            conn = self._get_connection()
            
            query = """
                SELECT 
                    COUNT(*) as total_qsos,
                    COUNT(DISTINCT COL_DXCC) as unique_dxcc,
                    COUNT(DISTINCT COL_CALL) as unique_calls,
                    MIN(COL_TIME_ON) as first_qso,
                    MAX(COL_TIME_ON) as last_qso
                FROM TABLE_HRD_CONTACTS_V01
                WHERE station_id = %s
            """
            
            with conn.cursor() as cursor:
                cursor.execute(query, (station_id,))
                result = cursor.fetchone()
                
                # Format datetime objects
                if result['first_qso']:
                    result['first_qso'] = result['first_qso'].strftime('%Y-%m-%d %H:%M:%S')
                if result['last_qso']:
                    result['last_qso'] = result['last_qso'].strftime('%Y-%m-%d %H:%M:%S')
                
                logger.info(f"Log stats: {result}")
                return result
                
        except Exception as e:
            logger.error(f"Error fetching log stats: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def search_callsign(self, callsign: str, station_id: int = 1, limit: int = 20) -> Dict:
        """
        Search for all QSOs with a specific callsign and return detailed information
        
        Args:
            callsign: Callsign to search for (supports base callsign and variations with suffixes)
            station_id: Station profile ID (default 1)
            limit: Maximum number of QSOs to return (default 20)
            
        Returns:
            Dictionary with QSO list, summary data, and band/mode matrix
        """
        try:
            conn = self._get_connection()
            
            # Strip suffix to get base callsign for flexible matching
            # Supports searching for OH2NOS to find OH2NOS, OH2NOS/P, OH2NOS/M, etc.
            # Also supports searching for OH2NOS/P to find both OH2NOS/P and OH2NOS
            base_callsign = callsign.upper().split('/')[0]
            
            # Query to fetch all QSOs with this callsign (base or with suffix)
            qso_query = """
                SELECT 
                    COL_PRIMARY_KEY as id,
                    COL_TIME_ON as time_on,
                    COL_CALL as callsign,
                    COL_BAND as band,
                    COL_MODE as mode,
                    COL_SUBMODE as submode,
                    COL_RST_SENT as rst_sent,
                    COL_RST_RCVD as rst_rcvd,
                    COL_LOTW_QSL_SENT as lotw_sent,
                    COL_LOTW_QSL_RCVD as lotw_rcvd,
                    COL_QSL_SENT as qsl_sent,
                    COL_QSL_RCVD as qsl_rcvd,
                    COL_NAME as name,
                    COL_QTH as qth,
                    COL_GRIDSQUARE as gridsquare,
                    COL_COUNTRY as country,
                    COL_DXCC as dxcc,
                    COL_CQZ as cqz,
                    COL_ITUZ as ituz,
                    COL_CONT as continent,
                    COL_STATE as state,
                    COL_IOTA as iota,
                    COL_POTA_REF as pota_ref,
                    COL_SOTA_REF as sota_ref,
                    COL_WWFF_REF as wwff_ref,
                    COL_SAT_NAME as satellite,
                    COL_DARC_DOK as dok
                FROM TABLE_HRD_CONTACTS_V01
                WHERE station_id = %s AND (COL_CALL = %s OR COL_CALL LIKE %s)
                ORDER BY COL_TIME_ON DESC
                LIMIT %s
            """
            
            # Search for exact match OR anything starting with base callsign followed by /
            search_pattern = f"{base_callsign}/%"
            
            with conn.cursor() as cursor:
                cursor.execute(qso_query, (station_id, base_callsign, search_pattern, limit))
                qsos = cursor.fetchall()
                
                # Process QSO results
                processed_qsos = []
                for qso in qsos:
                    processed_qso = {}
                    for key, value in qso.items():
                        if isinstance(value, datetime):
                            processed_qso[key] = value.strftime('%Y-%m-%d %H:%M:%S')
                        else:
                            processed_qso[key] = value if value is not None else ''
                    processed_qsos.append(processed_qso)
                
                # If no QSOs found, return empty result
                if len(processed_qsos) == 0:
                    return {
                        'qsos': [],
                        'summary': {},
                        'matrix': {}
                    }
                
                # Get summary data from most recent QSO
                latest_qso = processed_qsos[0]
                summary = {
                    'dxcc': latest_qso.get('dxcc', ''),
                    'dxcc_name': latest_qso.get('country', ''),
                    'country': latest_qso.get('country', ''),
                    'cq': latest_qso.get('cqz', ''),
                    'itu': latest_qso.get('ituz', ''),
                    'continent': latest_qso.get('continent', ''),
                    'gridsquare': latest_qso.get('gridsquare', ''),
                    'iota': latest_qso.get('iota', ''),
                    'state': latest_qso.get('state', ''),
                    'pota': latest_qso.get('pota_ref', ''),
                    'sota': latest_qso.get('sota_ref', ''),
                    'wwff': latest_qso.get('wwff_ref', ''),
                    'satellite': latest_qso.get('satellite', ''),
                    'dok': latest_qso.get('dok', '')
                }
                
                # Build band/mode matrix
                matrix = {}
                for qso in processed_qsos:
                    band = qso.get('band', '')
                    mode = qso.get('mode', '')
                    if not band or not mode:
                        continue
                    
                    if mode not in matrix:
                        matrix[mode] = {}
                    
                    if band not in matrix[mode]:
                        matrix[mode][band] = {
                            'worked': False,
                            'confirmed': False
                        }
                    
                    # Mark as worked
                    matrix[mode][band]['worked'] = True
                    
                    # Mark as confirmed if LoTW confirmed
                    if qso.get('lotw_rcvd') == 'Y':
                        matrix[mode][band]['confirmed'] = True
                
                logger.info(f"Found {len(processed_qsos)} QSOs for callsign {callsign}")
                
                return {
                    'qsos': processed_qsos,
                    'summary': summary,
                    'matrix': matrix
                }
                
        except Exception as e:
            logger.error(f"Error searching for callsign {callsign}: {e}")
            raise
        finally:
            if conn:
                conn.close()


# Singleton instance
_wavelog_log_service = None

def get_wavelog_log_service() -> WavelogLogService:
    """Get or create the WavelogLogService singleton"""
    global _wavelog_log_service
    if _wavelog_log_service is None:
        _wavelog_log_service = WavelogLogService()
    return _wavelog_log_service