"""
Wavelog Local SQLite Database
Caches all Wavelog ADIF data locally with automatic 5-minute sync
"""

import sqlite3
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from contextlib import contextmanager
from radio_control import config

logger = logging.getLogger(__name__)

# Database location
DB_DIR = config.DATA_DIR
DB_FILE = DB_DIR / 'wavelog.db'


class WavelogDatabase:
    """Local SQLite database for Wavelog QSOs"""
    
    # Schema version for migrations
    SCHEMA_VERSION = 1
    
    def __init__(self):
        self.db_file = DB_FILE
        self._ensure_db_exists()
    
    def _ensure_db_exists(self):
        """Create database and tables if they don't exist"""
        DB_DIR.mkdir(parents=True, exist_ok=True)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if tables exist
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='qsos'
            """)
            
            if not cursor.fetchone():
                logger.info("Creating Wavelog database schema...")
                self._create_schema(cursor)
                conn.commit()
            else:
                logger.debug("Wavelog database already exists")
                # Run schema migrations if needed
                self._run_migrations(cursor)
                conn.commit()
                # Schedule whitespace cleanup to run in background (don't block startup)
                asyncio.create_task(self._cleanup_whitespace_async())
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(str(self.db_file))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _create_schema(self, cursor):
        """Create the database schema"""
        # Main QSOs table
        cursor.execute("""
            CREATE TABLE qsos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                callsign TEXT NOT NULL,
                qso_date TEXT NOT NULL,
                time_on TEXT NOT NULL,
                time_off TEXT,
                frequency REAL,
                mode TEXT,
                rst_sent INTEGER,
                rst_rcvd INTEGER,
                name TEXT,
                qth TEXT,
                state TEXT,
                country TEXT,
                continent TEXT,
                cq_zone INTEGER,
                itu_zone INTEGER,
                gridsquare TEXT,
                pota_ref TEXT,
                sota_ref TEXT,
                iota TEXT,
                wwff_ref TEXT,
                lotw_qsl_rcvd TEXT,
                lotw_qsl_sent TEXT,
                email TEXT,
                ant TEXT,
                tx_pwr REAL,
                prop_mode TEXT,
                ant_path TEXT,
                sat_name TEXT,
                sat_mode TEXT,
                freq_rx REAL,
                mode_rx TEXT,
                comments TEXT,
                qsl_rcvd TEXT,
                qsl_sent TEXT,
                qsl_via TEXT,
                us_county TEXT,
                notes TEXT,
                raw_adif TEXT,
                synced_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(callsign, qso_date, time_on)
            )
        """)
        
        # Sync status table
        cursor.execute("""
            CREATE TABLE sync_status (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_full_sync TEXT,
                last_delta_sync TEXT,
                total_qsos INTEGER DEFAULT 0
            )
        """)
        
        # Create indexes for faster queries
        cursor.execute("""
            CREATE INDEX idx_callsign ON qsos(callsign)
        """)
        cursor.execute("""
            CREATE INDEX idx_qso_date ON qsos(qso_date)
        """)
        cursor.execute("""
            CREATE INDEX idx_synced_at ON qsos(synced_at DESC)
        """)
        cursor.execute("""
            CREATE INDEX idx_callsign_date ON qsos(callsign, qso_date DESC)
        """)
        
        # Initialize sync status
        cursor.execute("""
            INSERT INTO sync_status (id, last_full_sync, last_delta_sync, total_qsos)
            VALUES (1, NULL, NULL, 0)
        """)
        
        logger.info("✅ Wavelog database schema created")
    
    def _run_migrations(self, cursor) -> None:
        """Run database schema migrations for backwards compatibility"""
        try:
            # Check if 'band' column exists in qsos table
            cursor.execute("PRAGMA table_info(qsos)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'band' not in columns:
                logger.info("🔄 Adding missing 'band' column to qsos table...")
                cursor.execute("ALTER TABLE qsos ADD COLUMN band TEXT")
                logger.info("✅ Added 'band' column")
        except Exception as e:
            logger.debug(f"Migration check completed (band column may already exist): {str(e)}")
    
    async def _cleanup_whitespace_async(self) -> None:
        """Clean up existing data by trimming whitespace from string fields (runs in background)"""
        try:
            await asyncio.sleep(2)  # Wait a bit for app to fully start
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if we have data to clean
                cursor.execute("SELECT COUNT(*) FROM qsos")
                count = cursor.fetchone()[0]
                
                if count == 0:
                    return
                
                # Check if cleanup is needed (do any callsigns have whitespace?)
                cursor.execute("SELECT COUNT(*) FROM qsos WHERE callsign != TRIM(callsign)")
                needs_cleanup = cursor.fetchone()[0]
                
                if needs_cleanup > 0:
                    logger.info(f"🧹 Cleaning up {needs_cleanup} QSOs with whitespace in callsigns...")
                    
                    # List of string fields that might have trailing whitespace
                    string_fields = [
                        'callsign', 'mode', 'name', 'qth', 'state', 'country', 
                        'continent', 'band', 'rst_sent', 'rst_rcvd', 'sat_name',
                        'prop_mode', 'ant_path', 'ant', 'email', 'qsl_manager'
                    ]
                    
                    for field in string_fields:
                        cursor.execute(f"UPDATE qsos SET {field} = TRIM({field})")
                    
                    conn.commit()
                    logger.info("✅ Whitespace cleanup complete")
        except Exception as e:
            logger.debug(f"Note: Whitespace cleanup not needed or skipped: {str(e)}")
    
    @staticmethod
    def _parse_adif_field(adif_str: str, field_name: str) -> Optional[str]:
        """
        Parse a single ADIF field value from ADIF string.
        ADIF format: <field:length>value
        """
        import re
        pattern = f"<{field_name}:[0-9]+>([^<]*)"
        match = re.search(pattern, adif_str, re.IGNORECASE)
        return match.group(1) if match else None
    
    @staticmethod
    def _parse_adif_fields(adif_str: str) -> Dict[str, str]:
        """Parse all ADIF fields from an ADIF record"""
        import re
        fields = {}
        pattern = r"<([a-z_]+):[0-9]+>([^<]*)"
        
        for match in re.finditer(pattern, adif_str, re.IGNORECASE):
            field_name = match.group(1).lower()
            field_value = match.group(2).strip()  # Strip whitespace from ADIF field values
            fields[field_name] = field_value
        
        return fields
    
    @staticmethod
    def _frequency_to_band(freq_mhz: float) -> str:
        """Convert frequency in MHz to band designation"""
        try:
            freq = float(freq_mhz)
        except (ValueError, TypeError):
            return ''
        
        # Band definitions (HF, VHF, UHF)
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
        
        return ''
    
    def insert_qso(self, adif_record: str, fields: Dict[str, str]) -> bool:
        """
        Insert or update a QSO record from ADIF data.
        
        Args:
            adif_record: The raw ADIF string for this QSO
            fields: Parsed ADIF fields dict
        
        Returns:
            True if inserted/updated, False otherwise
        """
        try:
            callsign = fields.get('call', '').upper()
            qso_date = fields.get('qso_date', '')
            time_on = fields.get('time_on', '')
            
            if not all([callsign, qso_date, time_on]):
                logger.warning(f"Skipping QSO with missing required fields: {fields}")
                return False
            
            now = datetime.utcnow().isoformat()
            
            # Derive band from frequency if not present
            band = fields.get('band', '')
            if not band:
                freq = fields.get('freq')
                if freq:
                    try:
                        band = self._frequency_to_band(float(freq))
                    except (ValueError, TypeError):
                        band = ''
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Try to insert, update if already exists
                cursor.execute("""
                    INSERT OR REPLACE INTO qsos (
                        callsign, qso_date, time_on, time_off, frequency, mode, band,
                        rst_sent, rst_rcvd, name, qth, state, country, continent,
                        cq_zone, itu_zone, gridsquare, pota_ref, sota_ref, iota, wwff_ref,
                        lotw_qsl_rcvd, lotw_qsl_sent, email, ant, tx_pwr, prop_mode,
                        ant_path, sat_name, sat_mode, freq_rx, mode_rx, comments,
                        qsl_rcvd, qsl_sent, qsl_via, us_county, notes, raw_adif,
                        synced_at, updated_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                """, (
                    callsign,
                    qso_date,
                    time_on,
                    fields.get('time_off'),
                    float(fields.get('freq', 0)) if fields.get('freq') else None,
                    fields.get('mode'),
                    band,  # Derived band (from ADIF or calculated from frequency)
                    int(fields.get('rst_sent', 0)) if fields.get('rst_sent') else None,
                    int(fields.get('rst_rcvd', 0)) if fields.get('rst_rcvd') else None,
                    fields.get('name'),
                    fields.get('qth'),
                    fields.get('state'),
                    fields.get('country'),
                    fields.get('cont'),
                    int(fields.get('cqz', 0)) if fields.get('cqz') else None,
                    int(fields.get('ituz', 0)) if fields.get('ituz') else None,
                    fields.get('gridsquare'),
                    fields.get('pota_ref'),
                    fields.get('sota_ref'),
                    fields.get('iota'),
                    fields.get('wwff_ref'),
                    fields.get('lotw_qsl_rcvd'),
                    fields.get('lotw_qsl_sent'),
                    fields.get('email'),
                    fields.get('ant'),
                    float(fields.get('tx_pwr', 0)) if fields.get('tx_pwr') else None,
                    fields.get('prop_mode'),
                    fields.get('ant_path'),
                    fields.get('sat_name'),
                    fields.get('sat_mode'),
                    float(fields.get('freq_rx', 0)) if fields.get('freq_rx') else None,
                    fields.get('mode_rx'),
                    fields.get('comments'),
                    fields.get('qsl_rcvd'),
                    fields.get('qsl_sent'),
                    fields.get('qsl_via'),
                    fields.get('county'),
                    fields.get('notes'),
                    adif_record,
                    now,
                    now
                ))
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Error inserting QSO: {str(e)}")
            return False
    
    def bulk_insert_qsos(self, qsos: List[Tuple[str, Dict[str, str]]]) -> int:
        """
        Bulk insert multiple QSO records.
        
        Args:
            qsos: List of (adif_record, fields_dict) tuples
        
        Returns:
            Number of successfully inserted QSOs
        """
        inserted = 0
        for adif_record, fields in qsos:
            if self.insert_qso(adif_record, fields):
                inserted += 1
        
        return inserted
    
    def get_qsos_by_callsign(self, callsign: str, limit: int = 5, 
                             offset: int = 0) -> List[Dict[str, Any]]:
        """Get QSOs for a specific callsign, most recent first
        
        Args:
            callsign: The callsign to search for
            limit: Maximum number of QSOs to return (0 = return all)
            offset: Number of records to skip
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Handle limit=0 as "return all QSOs" (use a very large limit)
                actual_limit = limit if limit > 0 else 999999
                
                cursor.execute("""
                    SELECT * FROM qsos 
                    WHERE UPPER(callsign) = UPPER(?)
                    ORDER BY qso_date DESC, time_on DESC
                    LIMIT ? OFFSET ?
                """, (callsign, actual_limit, offset))
                
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error querying QSOs: {str(e)}")
            return []
    
    def get_all_qsos(self, limit: int = 1000, offset: int = 0) -> List[Dict[str, Any]]:
        """Get all QSOs, most recent first"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT * FROM qsos 
                    ORDER BY qso_date DESC, time_on DESC
                    LIMIT ? OFFSET ?
                """, (limit, offset))
                
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error querying all QSOs: {str(e)}")
            return []
    
    def get_qsos_count(self) -> int:
        """Get total count of QSOs in database"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM qsos")
                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Error counting QSOs: {str(e)}")
            return 0
    
    def get_recent_qsos(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get QSOs modified in the last N hours"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            cutoff_iso = cutoff_time.isoformat()
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT * FROM qsos 
                    WHERE updated_at >= ?
                    ORDER BY updated_at DESC
                """, (cutoff_iso,))
                
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error querying recent QSOs: {str(e)}")
            return []
    
    def update_sync_status(self, sync_type: str = 'delta'):
        """Update sync status timestamp"""
        try:
            now = datetime.utcnow().isoformat()
            total = self.get_qsos_count()
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                if sync_type == 'full':
                    cursor.execute("""
                        UPDATE sync_status 
                        SET last_full_sync = ?, total_qsos = ?
                        WHERE id = 1
                    """, (now, total))
                    logger.debug(f"Updated full sync status: {total} QSOs")
                else:  # delta
                    cursor.execute("""
                        UPDATE sync_status 
                        SET last_delta_sync = ?, total_qsos = ?
                        WHERE id = 1
                    """, (now, total))
                    logger.debug(f"Updated delta sync status: {total} QSOs")
                
                conn.commit()
        except Exception as e:
            logger.error(f"Error updating sync status: {str(e)}")
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM sync_status WHERE id = 1")
                row = cursor.fetchone()
                
                if row:
                    return dict(row)
                return {'last_full_sync': None, 'last_delta_sync': None, 'total_qsos': 0}
        except Exception as e:
            logger.error(f"Error getting sync status: {str(e)}")
            return {'last_full_sync': None, 'last_delta_sync': None, 'total_qsos': 0}
    
    def clear_all_qsos(self):
        """Clear all QSOs from database (for full resync)"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM qsos")
                conn.commit()
                logger.info("Cleared all QSOs from database")
        except Exception as e:
            logger.error(f"Error clearing QSOs: {str(e)}")


# Global database instance
_db_instance = None


def get_wavelog_db() -> WavelogDatabase:
    """Get or create the Wavelog database instance"""
    global _db_instance
    if _db_instance is None:
        _db_instance = WavelogDatabase()
    return _db_instance
