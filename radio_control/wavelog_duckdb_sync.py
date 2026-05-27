"""
Wavelog to DuckDB read-cache synchronization.

Wavelog remains the source of truth. This module builds a local DuckDB cache for
fast UI reads and live DX spot classification, and the cache can be rebuilt from
Wavelog when needed.
"""

import logging
import duckdb
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
import pymysql
from pymysql.cursors import DictCursor

from radio_control import config
logger = logging.getLogger(__name__)


class WavelogDuckDBSync:
    """Manage synchronization from Wavelog MySQL to the local read cache."""
    
    def __init__(self, db_path: str = None):
        """
        Initialize Wavelog to DuckDB synchronizer
        
        Args:
            db_path: Path to DuckDB database (default: data/qso_log.duckdb)
        """
        self.db_path = Path(db_path) if db_path else config.DATA_DIR / "qso_log.duckdb"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Wavelog MySQL connection config
        self.wavelog_config = {
            'host': config.DB_HOST,
            'port': config.DB_PORT,
            'user': config.DB_USER,
            'password': config.DB_PASS,
            'database': config.DB_NAME,
            'charset': 'utf8mb4',
            'cursorclass': DictCursor
        }
        
        # Station ID from config
        self.station_id = int(getattr(config, 'WAVELOG_STATION_ID', 1))
        self.last_sync_error: Optional[str] = None
        self._db_lock = threading.RLock()
        self._sync_active = False
        self._cached_status: Dict[str, Any] = {
            'initialized': False,
            'status': 'not_initialized',
            'last_sync_error': None,
            'total_records': 0,
            'message': 'Sync not yet initialized',
        }
        
        # Initialize database
        self._init_database()
        
        logger.info(f"✅ Wavelog→DuckDB Sync initialized - DB: {self.db_path}, Station ID: {self.station_id}")
    
    def _init_database(self):
        """Initialize DuckDB schema and metadata tables"""
        conn = None
        try:
            with self._db_lock:
                conn = duckdb.connect(str(self.db_path))
            
                # Create sequence FIRST (must exist before table references it)
                conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_qso_id START 1")

                # Create QSO records table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS qso_records (
                    id INTEGER PRIMARY KEY DEFAULT nextval('seq_qso_id'),
                    wavelog_id BIGINT UNIQUE,
                    call VARCHAR,
                    qso_date VARCHAR,
                    time_on TIMESTAMP,
                    time_off TIMESTAMP,
                    qso_datetime TIMESTAMP,
                    mode VARCHAR,
                    submode VARCHAR,
                    frequency DOUBLE,
                    band VARCHAR,
                    rst_sent VARCHAR,
                    rst_rcvd VARCHAR,
                    name VARCHAR,
                    qth VARCHAR,
                    state VARCHAR,
                    county VARCHAR,
                    gridsquare VARCHAR,
                    pota_ref VARCHAR,
                    sota_ref VARCHAR,
                    iota VARCHAR,
                    wwff_ref VARCHAR,
                    sig VARCHAR,
                    sig_info VARCHAR,
                    comment VARCHAR,
                    country VARCHAR,
                    dxcc INTEGER,
                    cqz INTEGER,
                    ituz INTEGER,
                    continent VARCHAR,
                    lotw_qsl_sent VARCHAR,
                    lotw_qsl_rcvd VARCHAR,
                    eqsl_qsl_sent VARCHAR,
                    eqsl_qsl_rcvd VARCHAR,
                    qsl_sent VARCHAR,
                    qsl_rcvd VARCHAR,
                    tx_pwr DOUBLE,
                    operator VARCHAR,
                    station_callsign VARCHAR,
                    station_id INTEGER,
                    creation_date TIMESTAMP,
                    last_modified TIMESTAMP,
                    sync_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Create sync metadata table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sync_metadata (
                    id INTEGER PRIMARY KEY,
                    last_sync_timestamp TIMESTAMP,
                    last_wavelog_modified TIMESTAMP,
                    last_wavelog_id BIGINT,
                    total_records_synced INTEGER,
                    last_sync_added INTEGER,
                    last_sync_updated INTEGER
                    )
                """)

                # Create indexes for fast queries
                conn.execute("CREATE INDEX IF NOT EXISTS idx_wavelog_id ON qso_records(wavelog_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_call ON qso_records(call)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_qso_date ON qso_records(qso_date)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_band ON qso_records(band)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_mode ON qso_records(mode)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_dxcc ON qso_records(dxcc)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_dxcc_band_mode ON qso_records(dxcc, band, mode)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_qso_datetime ON qso_records(qso_datetime)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_frequency ON qso_records(frequency)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_time_on ON qso_records(time_on)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_last_modified ON qso_records(last_modified)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_call_band_mode ON qso_records(call, band, mode)")

            logger.info("✅ DuckDB schema initialized for Wavelog sync")
        except Exception as e:
            logger.error(f"❌ Failed to initialize DuckDB: {str(e)}", exc_info=True)
            raise
        finally:
            if conn is not None:
                conn.close()
    
    def _get_wavelog_connection(self):
        """Create a new Wavelog database connection"""
        try:
            return pymysql.connect(**self.wavelog_config)
        except Exception as e:
            logger.error(f"❌ Failed to connect to Wavelog database: {e}")
            raise
    
    def _get_sync_metadata(self, conn) -> Optional[Dict[str, Any]]:
        """Retrieve current sync metadata"""
        try:
            result = conn.execute(
                "SELECT * FROM sync_metadata WHERE id = 1"
            ).fetchall()
            
            if result:
                row = result[0]
                return {
                    'last_sync_timestamp': row[1],
                    'last_wavelog_modified': row[2],
                    'last_wavelog_id': row[3],
                    'total_records_synced': row[4],
                    'last_sync_added': row[5],
                    'last_sync_updated': row[6]
                }
            return None
        except Exception as e:
            logger.warning(f"⚠️ Could not retrieve sync metadata: {str(e)}")
            return None
    
    def _update_sync_metadata(self, conn, last_modified: datetime, last_id: int, 
                             total_records: int, added: int, updated: int):
        """Update sync metadata after successful sync"""
        try:
            metadata = self._get_sync_metadata(conn)
            
            if metadata:
                conn.execute("""
                    UPDATE sync_metadata
                    SET last_sync_timestamp = CURRENT_TIMESTAMP,
                        last_wavelog_modified = ?,
                        last_wavelog_id = ?,
                        total_records_synced = ?,
                        last_sync_added = ?,
                        last_sync_updated = ?
                    WHERE id = 1
                """, (last_modified, last_id, total_records, added, updated))
            else:
                conn.execute("""
                    INSERT INTO sync_metadata (id, last_sync_timestamp, last_wavelog_modified, 
                                              last_wavelog_id, total_records_synced, 
                                              last_sync_added, last_sync_updated)
                    VALUES (1, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?)
                """, (last_modified, last_id, total_records, added, updated))
            
            conn.commit()
        except Exception as e:
            logger.error(f"❌ Failed to update sync metadata: {str(e)}")
    
    def _fetch_changed_records(self, last_modified: Optional[datetime] = None, 
                               last_id: Optional[int] = None, 
                               batch_size: int = 1000) -> List[Dict]:
        """
        Fetch records from Wavelog that have been added or modified since last sync
        
        Args:
            last_modified: Last modification timestamp from previous sync
            last_id: Last Wavelog COL_PRIMARY_KEY from previous sync
            batch_size: Number of records to fetch in one batch (default: 1000)
            
        Returns:
            List of QSO records from Wavelog
        """
        try:
            conn = self._get_wavelog_connection()
            
            # Build query based on what we're tracking
            if last_modified:
                # Smart sync: fetch only records modified since last sync
                query = """
                    SELECT 
                        COL_PRIMARY_KEY,
                        COL_CALL,
                        COL_QSO_DATE,
                        COL_TIME_ON,
                        COL_TIME_OFF,
                        COL_BAND,
                        COL_FREQ,
                        COL_MODE,
                        COL_SUBMODE,
                        COL_RST_SENT,
                        COL_RST_RCVD,
                        COL_NAME,
                        COL_QTH,
                        COL_STATE,
                        COL_CNTY,
                        COL_GRIDSQUARE,
                        COL_COUNTRY,
                        COL_DXCC,
                        COL_CQZ,
                        COL_ITUZ,
                        COL_CONT,
                        COL_IOTA,
                        COL_POTA_REF,
                        COL_SOTA_REF,
                        COL_WWFF_REF,
                        COL_SIG,
                        COL_SIG_INFO,
                        COL_COMMENT,
                        COL_TX_PWR,
                        COL_LOTW_QSL_SENT,
                        COL_LOTW_QSL_RCVD,
                        COL_EQSL_QSL_SENT,
                        COL_EQSL_QSL_RCVD,
                        COL_QSL_SENT,
                        COL_QSL_RCVD,
                        COL_OPERATOR,
                        COL_STATION_CALLSIGN,
                        station_id,
                        creation_date,
                        last_modified
                    FROM TABLE_HRD_CONTACTS_V01
                    WHERE station_id = %s 
                    AND (last_modified > %s OR (last_modified = %s AND COL_PRIMARY_KEY > %s))
                    ORDER BY last_modified ASC, COL_PRIMARY_KEY ASC
                    LIMIT %s
                """
                params = (self.station_id, last_modified, last_modified, last_id or 0, batch_size)
            else:
                # Initial sync: keyset pagination by primary key avoids slow OFFSET scans.
                query = """
                    SELECT 
                        COL_PRIMARY_KEY,
                        COL_CALL,
                        COL_QSO_DATE,
                        COL_TIME_ON,
                        COL_TIME_OFF,
                        COL_BAND,
                        COL_FREQ,
                        COL_MODE,
                        COL_SUBMODE,
                        COL_RST_SENT,
                        COL_RST_RCVD,
                        COL_NAME,
                        COL_QTH,
                        COL_STATE,
                        COL_CNTY,
                        COL_GRIDSQUARE,
                        COL_COUNTRY,
                        COL_DXCC,
                        COL_CQZ,
                        COL_ITUZ,
                        COL_CONT,
                        COL_IOTA,
                        COL_POTA_REF,
                        COL_SOTA_REF,
                        COL_WWFF_REF,
                        COL_SIG,
                        COL_SIG_INFO,
                        COL_COMMENT,
                        COL_TX_PWR,
                        COL_LOTW_QSL_SENT,
                        COL_LOTW_QSL_RCVD,
                        COL_EQSL_QSL_SENT,
                        COL_EQSL_QSL_RCVD,
                        COL_QSL_SENT,
                        COL_QSL_RCVD,
                        COL_OPERATOR,
                        COL_STATION_CALLSIGN,
                        station_id,
                        creation_date,
                        last_modified
                    FROM TABLE_HRD_CONTACTS_V01
                    WHERE station_id = %s
                    AND COL_PRIMARY_KEY > %s
                    ORDER BY COL_PRIMARY_KEY ASC
                    LIMIT %s
                """
                params = (self.station_id, last_id or 0, batch_size)
            
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()
                
                logger.info(
                    "📥 Fetched %s records from Wavelog database (after id: %s)",
                    len(results),
                    last_id or 0,
                )
                return results
                
        except Exception as e:
            logger.error(f"❌ Error fetching records from Wavelog: {e}", exc_info=True)
            raise
        finally:
            if conn:
                conn.close()
    
    def _convert_wavelog_to_duckdb(self, wavelog_record: Dict) -> Dict[str, Any]:
        """
        Convert Wavelog record format to DuckDB format
        
        Args:
            wavelog_record: Record from Wavelog database
            
        Returns:
            Dictionary formatted for DuckDB insertion
        """
        try:
            # Extract values with proper type conversions
            wavelog_id = wavelog_record.get('COL_PRIMARY_KEY')
            
            # Convert frequency from Hz to MHz if needed
            frequency = wavelog_record.get('COL_FREQ')
            if frequency:
                frequency = float(frequency) / 1000000 if frequency > 1000 else float(frequency)
            else:
                frequency = None
            
            # Format datetime fields
            time_on = wavelog_record.get('COL_TIME_ON')
            time_off = wavelog_record.get('COL_TIME_OFF')
            creation_date = wavelog_record.get('creation_date')
            last_modified = wavelog_record.get('last_modified')
            
            # Create qso_datetime from date and time_on
            qso_date = wavelog_record.get('COL_QSO_DATE')
            if qso_date and time_on:
                if isinstance(qso_date, str):
                    qso_datetime = datetime.strptime(f"{qso_date} {time_on.strftime('%H:%M:%S')}", 
                                                    "%Y-%m-%d %H:%M:%S")
                else:
                    qso_datetime = datetime.combine(qso_date, time_on.time() if isinstance(time_on, datetime) else time_on)
            else:
                qso_datetime = time_on
            
            # Build DuckDB record
            return {
                'wavelog_id': wavelog_id,
                'call': wavelog_record.get('COL_CALL', '').strip() if wavelog_record.get('COL_CALL') else None,
                'qso_date': qso_date.strftime('%Y-%m-%d') if isinstance(qso_date, datetime) else str(qso_date) if qso_date else None,
                'time_on': time_on,
                'time_off': time_off,
                'qso_datetime': qso_datetime,
                'mode': wavelog_record.get('COL_MODE', '').strip() if wavelog_record.get('COL_MODE') else None,
                'submode': wavelog_record.get('COL_SUBMODE', '').strip() if wavelog_record.get('COL_SUBMODE') else None,
                'frequency': frequency,
                'band': wavelog_record.get('COL_BAND', '').strip() if wavelog_record.get('COL_BAND') else None,
                'rst_sent': wavelog_record.get('COL_RST_SENT', '').strip() if wavelog_record.get('COL_RST_SENT') else None,
                'rst_rcvd': wavelog_record.get('COL_RST_RCVD', '').strip() if wavelog_record.get('COL_RST_RCVD') else None,
                'name': wavelog_record.get('COL_NAME', '').strip() if wavelog_record.get('COL_NAME') else None,
                'qth': wavelog_record.get('COL_QTH', '').strip() if wavelog_record.get('COL_QTH') else None,
                'state': wavelog_record.get('COL_STATE', '').strip() if wavelog_record.get('COL_STATE') else None,
                'county': wavelog_record.get('COL_CNTY', '').strip() if wavelog_record.get('COL_CNTY') else None,
                'gridsquare': wavelog_record.get('COL_GRIDSQUARE', '').strip() if wavelog_record.get('COL_GRIDSQUARE') else None,
                'pota_ref': wavelog_record.get('COL_POTA_REF', '').strip() if wavelog_record.get('COL_POTA_REF') else None,
                'sota_ref': wavelog_record.get('COL_SOTA_REF', '').strip() if wavelog_record.get('COL_SOTA_REF') else None,
                'iota': wavelog_record.get('COL_IOTA', '').strip() if wavelog_record.get('COL_IOTA') else None,
                'wwff_ref': wavelog_record.get('COL_WWFF_REF', '').strip() if wavelog_record.get('COL_WWFF_REF') else None,
                'sig': wavelog_record.get('COL_SIG', '').strip() if wavelog_record.get('COL_SIG') else None,
                'sig_info': wavelog_record.get('COL_SIG_INFO', '').strip() if wavelog_record.get('COL_SIG_INFO') else None,
                'comment': wavelog_record.get('COL_COMMENT', '').strip() if wavelog_record.get('COL_COMMENT') else None,
                'country': wavelog_record.get('COL_COUNTRY', '').strip() if wavelog_record.get('COL_COUNTRY') else None,
                'dxcc': int(wavelog_record.get('COL_DXCC')) if wavelog_record.get('COL_DXCC') else None,
                'cqz': int(wavelog_record.get('COL_CQZ')) if wavelog_record.get('COL_CQZ') else None,
                'ituz': int(wavelog_record.get('COL_ITUZ')) if wavelog_record.get('COL_ITUZ') else None,
                'continent': wavelog_record.get('COL_CONT', '').strip() if wavelog_record.get('COL_CONT') else None,
                'lotw_qsl_sent': wavelog_record.get('COL_LOTW_QSL_SENT', '').strip() if wavelog_record.get('COL_LOTW_QSL_SENT') else None,
                'lotw_qsl_rcvd': wavelog_record.get('COL_LOTW_QSL_RCVD', '').strip() if wavelog_record.get('COL_LOTW_QSL_RCVD') else None,
                'eqsl_qsl_sent': wavelog_record.get('COL_EQSL_QSL_SENT', '').strip() if wavelog_record.get('COL_EQSL_QSL_SENT') else None,
                'eqsl_qsl_rcvd': wavelog_record.get('COL_EQSL_QSL_RCVD', '').strip() if wavelog_record.get('COL_EQSL_QSL_RCVD') else None,
                'qsl_sent': wavelog_record.get('COL_QSL_SENT', '').strip() if wavelog_record.get('COL_QSL_SENT') else None,
                'qsl_rcvd': wavelog_record.get('COL_QSL_RCVD', '').strip() if wavelog_record.get('COL_QSL_RCVD') else None,
                'tx_pwr': float(wavelog_record.get('COL_TX_PWR')) if wavelog_record.get('COL_TX_PWR') else None,
                'operator': wavelog_record.get('COL_OPERATOR', '').strip() if wavelog_record.get('COL_OPERATOR') else None,
                'station_callsign': wavelog_record.get('COL_STATION_CALLSIGN', '').strip() if wavelog_record.get('COL_STATION_CALLSIGN') else None,
                'station_id': int(wavelog_record.get('station_id')) if wavelog_record.get('station_id') else self.station_id,
                'creation_date': creation_date,
                'last_modified': last_modified
            }
        except Exception as e:
            logger.error(f"❌ Error converting Wavelog record: {e}", exc_info=True)
            raise
    
    def _upsert_record(self, conn, record: Dict[str, Any]) -> str:
        """
        Insert or update a single record in DuckDB
        
        Args:
            conn: DuckDB connection
            record: Record to upsert
            
        Returns:
            'added' or 'updated'
        """
        try:
            # Check if record exists
            existing = conn.execute(
                "SELECT id FROM qso_records WHERE wavelog_id = ?",
                (record['wavelog_id'],)
            ).fetchone()
            
            if existing:
                # Update existing record
                conn.execute("""
                    UPDATE qso_records
                    SET call = ?, qso_date = ?, time_on = ?, time_off = ?, qso_datetime = ?,
                        mode = ?, submode = ?, frequency = ?, band = ?, rst_sent = ?, rst_rcvd = ?,
                        name = ?, qth = ?, state = ?, county = ?, gridsquare = ?,
                        pota_ref = ?, sota_ref = ?, iota = ?, wwff_ref = ?,
                        sig = ?, sig_info = ?, comment = ?, country = ?, dxcc = ?,
                        cqz = ?, ituz = ?, continent = ?,
                        lotw_qsl_sent = ?, lotw_qsl_rcvd = ?,
                        eqsl_qsl_sent = ?, eqsl_qsl_rcvd = ?,
                        qsl_sent = ?, qsl_rcvd = ?, tx_pwr = ?,
                        operator = ?, station_callsign = ?, station_id = ?,
                        creation_date = ?, last_modified = ?,
                        sync_timestamp = CURRENT_TIMESTAMP
                    WHERE wavelog_id = ?
                """, (
                    record['call'], record['qso_date'], record['time_on'], record['time_off'],
                    record['qso_datetime'], record['mode'], record['submode'], record['frequency'],
                    record['band'], record['rst_sent'], record['rst_rcvd'], record['name'],
                    record['qth'], record['state'], record['county'], record['gridsquare'],
                    record['pota_ref'], record['sota_ref'], record['iota'], record['wwff_ref'],
                    record['sig'], record['sig_info'], record['comment'], record['country'],
                    record['dxcc'], record['cqz'], record['ituz'], record['continent'],
                    record['lotw_qsl_sent'], record['lotw_qsl_rcvd'],
                    record['eqsl_qsl_sent'], record['eqsl_qsl_rcvd'],
                    record['qsl_sent'], record['qsl_rcvd'], record['tx_pwr'],
                    record['operator'], record['station_callsign'], record['station_id'],
                    record['creation_date'], record['last_modified'],
                    record['wavelog_id']
                ))
                return 'updated'
            else:
                # Insert new record
                conn.execute("""
                    INSERT INTO qso_records (
                        wavelog_id, call, qso_date, time_on, time_off, qso_datetime,
                        mode, submode, frequency, band, rst_sent, rst_rcvd,
                        name, qth, state, county, gridsquare,
                        pota_ref, sota_ref, iota, wwff_ref, sig, sig_info, comment,
                        country, dxcc, cqz, ituz, continent,
                        lotw_qsl_sent, lotw_qsl_rcvd, eqsl_qsl_sent, eqsl_qsl_rcvd,
                        qsl_sent, qsl_rcvd, tx_pwr, operator, station_callsign, station_id,
                        creation_date, last_modified
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                             ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record['wavelog_id'], record['call'], record['qso_date'], record['time_on'],
                    record['time_off'], record['qso_datetime'], record['mode'], record['submode'],
                    record['frequency'], record['band'], record['rst_sent'], record['rst_rcvd'],
                    record['name'], record['qth'], record['state'], record['county'],
                    record['gridsquare'], record['pota_ref'], record['sota_ref'], record['iota'],
                    record['wwff_ref'], record['sig'], record['sig_info'], record['comment'],
                    record['country'], record['dxcc'], record['cqz'], record['ituz'],
                    record['continent'], record['lotw_qsl_sent'], record['lotw_qsl_rcvd'],
                    record['eqsl_qsl_sent'], record['eqsl_qsl_rcvd'], record['qsl_sent'],
                    record['qsl_rcvd'], record['tx_pwr'], record['operator'],
                    record['station_callsign'], record['station_id'], record['creation_date'],
                    record['last_modified']
                ))
                return 'added'
                
        except Exception as e:
            logger.error(f"❌ Error upserting record {record.get('wavelog_id')}: {e}", exc_info=True)
            raise
    
    def sync(self, batch_size: int = 1000) -> Dict[str, Any]:
        """
        Perform smart sync from Wavelog to DuckDB
        Uses batched fetching for initial sync to handle large databases
        
        Args:
            batch_size: Number of records to process per batch (default: 1000)
        
        Returns:
            Dictionary with sync results
        """
        conn = None
        self._sync_active = True
        try:
            with self._db_lock:
                conn = duckdb.connect(str(self.db_path))

            # Get last sync metadata
                metadata = self._get_sync_metadata(conn)
                last_modified = metadata['last_wavelog_modified'] if metadata else None
                last_id = metadata['last_wavelog_id'] if metadata else None

                is_initial_sync = (last_modified is None)

                # Process records
                added_count = 0
                updated_count = 0
                latest_modified = last_modified
                latest_id = last_id or 0
                initial_cursor_id = last_id or 0
                batch_num = 0

                if is_initial_sync:
                    logger.info(f"🔄 Starting INITIAL sync (batched: {batch_size} records per batch)")

                while True:
                    # Fetch a batch of records from Wavelog
                    if is_initial_sync:
                        wavelog_records = self._fetch_changed_records(None, initial_cursor_id, batch_size)
                    else:
                        wavelog_records = self._fetch_changed_records(last_modified, last_id, batch_size)

                    # If no more records, we're done
                    if not wavelog_records:
                        break

                    batch_num += 1
                    batch_added = 0
                    batch_updated = 0

                    # Process this batch
                    for wavelog_record in wavelog_records:
                        try:
                            # Convert to DuckDB format
                            duckdb_record = self._convert_wavelog_to_duckdb(wavelog_record)

                            # Upsert record
                            action = self._upsert_record(conn, duckdb_record)

                            if action == 'added':
                                added_count += 1
                                batch_added += 1
                            else:
                                updated_count += 1
                                batch_updated += 1

                            # Track latest modified timestamp and ID
                            record_modified = wavelog_record.get('last_modified')
                            record_id = wavelog_record.get('COL_PRIMARY_KEY')

                            if is_initial_sync and record_id and record_id > initial_cursor_id:
                                initial_cursor_id = record_id

                            if record_modified and (latest_modified is None or record_modified > latest_modified):
                                latest_modified = record_modified
                                latest_id = record_id
                            elif record_modified == latest_modified and record_id > latest_id:
                                latest_id = record_id
                            elif is_initial_sync and latest_modified is None and record_id > latest_id:
                                latest_id = record_id

                        except Exception as e:
                            logger.error(f"❌ Error processing Wavelog record {wavelog_record.get('COL_PRIMARY_KEY')}: {e}")
                            continue

                    # Commit this batch
                    conn.commit()

                    # Get current total
                    total_records = conn.execute("SELECT COUNT(*) FROM qso_records").fetchone()[0]

                    # Log progress for initial sync
                    if is_initial_sync:
                        logger.info(f"✅ Batch {batch_num}: +{batch_added} new, ~{batch_updated} updated | "
                                   f"Total: {total_records} QSOs synced")

                    # For incremental sync, we only fetch one batch
                    if not is_initial_sync:
                        break

                    # For initial sync, if we got fewer records than batch_size, we're done
                    if len(wavelog_records) < batch_size:
                        break

                # Final commit
                conn.commit()

                # Get final total record count
                total_records = conn.execute("SELECT COUNT(*) FROM qso_records").fetchone()[0]

                # Update sync metadata
                self._update_sync_metadata(conn, latest_modified, latest_id, total_records,
                                          added_count, updated_count)
                self.last_sync_error = None

                if added_count > 0 or updated_count > 0:
                    logger.info(f"✅ Wavelog sync complete: {added_count} added, {updated_count} updated, "
                               f"total: {total_records}")

                self._cached_status = {
                    'initialized': True,
                    'last_sync': datetime.now(),
                    'last_wavelog_modified': latest_modified,
                    'last_wavelog_id': latest_id,
                    'total_records': total_records,
                    'last_sync_added': added_count,
                    'last_sync_updated': updated_count,
                    'last_sync_error': None,
                    'status': 'ok',
                }

                return {
                    'synced': True,
                    'records_added': added_count,
                    'records_updated': updated_count,
                    'total_records': total_records,
                    'message': f'Synced {added_count + updated_count} records from Wavelog'
                }

        except Exception as e:
            logger.error(f"❌ Wavelog sync failed: {e}", exc_info=True)
            self.last_sync_error = str(e)
            self._cached_status = {
                **self._cached_status,
                'status': 'failed',
                'last_sync_error': self.last_sync_error,
                'error': str(e),
            }
            return {
                'synced': False,
                'error': str(e),
                'message': f'Sync failed: {str(e)}'
            }
        finally:
            if conn is not None:
                conn.close()
            self._sync_active = False
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status and statistics"""
        if self._sync_active or not self._db_lock.acquire(blocking=False):
            return {
                **self._cached_status,
                'syncing': self._sync_active,
            }

        conn = None
        try:
            conn = duckdb.connect(str(self.db_path))
            metadata = self._get_sync_metadata(conn)
            
            if not metadata:
                self._cached_status = {
                    'initialized': False,
                    'status': 'failed' if self.last_sync_error else 'not_initialized',
                    'last_sync_error': self.last_sync_error,
                    'total_records': 0,
                    'message': 'Sync not yet initialized'
                }
                return self._cached_status
            
            total_records = conn.execute("SELECT COUNT(*) FROM qso_records").fetchone()[0]
            
            self._cached_status = {
                'initialized': True,
                'last_sync': metadata['last_sync_timestamp'],
                'last_wavelog_modified': metadata['last_wavelog_modified'],
                'last_wavelog_id': metadata['last_wavelog_id'],
                'total_records': total_records,
                'last_sync_added': metadata['last_sync_added'],
                'last_sync_updated': metadata['last_sync_updated'],
                'last_sync_error': self.last_sync_error,
                'status': 'failed' if self.last_sync_error else 'ok',
            }
            return self._cached_status
        except Exception as e:
            logger.debug(f"Could not read sync status from DuckDB, returning cached status: {e}")
            self.last_sync_error = str(e)
            return {
                **self._cached_status,
                'status': 'failed',
                'error': str(e),
                'last_sync_error': self.last_sync_error,
            }
        finally:
            if conn is not None:
                conn.close()
            self._db_lock.release()
    
    def reset_sync(self, clear_data: bool = False) -> Dict[str, Any]:
        """
        Reset sync metadata to force a fresh initial sync
        
        Args:
            clear_data: If True, also clear all synced QSO records (default: False)
        
        Returns:
            Dictionary with reset status
        """
        try:
            conn = duckdb.connect(str(self.db_path))
            
            # Delete sync metadata to trigger fresh initial sync
            conn.execute("DELETE FROM sync_metadata WHERE id = 1")
            
            if clear_data:
                # Also clear all QSO records
                conn.execute("DELETE FROM qso_records")
                logger.info("🔄 Cleared all QSO records from DuckDB")
            
            conn.commit()
            conn.close()
            
            logger.info("✅ Sync metadata reset - next sync will be a full initial sync")
            
            return {
                'success': True,
                'message': 'Sync reset successfully',
                'data_cleared': clear_data
            }
        except Exception as e:
            logger.error(f"❌ Failed to reset sync: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }


# Module-level instance
_sync_instance: Optional[WavelogDuckDBSync] = None


def get_wavelog_sync() -> WavelogDuckDBSync:
    """Get or create the Wavelog sync instance"""
    global _sync_instance
    if _sync_instance is None:
        _sync_instance = WavelogDuckDBSync()
    return _sync_instance


def init_wavelog_sync():
    """Initialize Wavelog sync"""
    global _sync_instance
    _sync_instance = WavelogDuckDBSync()
    return _sync_instance


async def periodic_wavelog_sync():
    """
    Periodic Wavelog sync task
    Runs immediately on first call, then at configured interval to check for Wavelog changes
    """
    import asyncio
    
    # Get sync interval from config (default 60 seconds)
    sync_interval = getattr(config, 'WAVELOG_SYNC_INTERVAL', 60)
    
    first_run = True
    while True:
        try:
            # Do immediate first sync, then wait configured interval between subsequent syncs
            if first_run:
                await asyncio.sleep(0)
            else:
                await asyncio.sleep(sync_interval)
            first_run = False
            
            if _sync_instance is not None:
                result = await asyncio.to_thread(_sync_instance.sync)
                if result['synced']:
                    logger.info(f"✅ Wavelog sync: +{result['records_added']} new, "
                               f"~{result['records_updated']} updated, "
                               f"total: {result.get('total_records', 0)}")
                # If not synced, no changes - skip logging
        except Exception as e:
            logger.error(f"❌ Error in periodic Wavelog sync: {e}")
            await asyncio.sleep(5)  # Brief pause before retry on error
