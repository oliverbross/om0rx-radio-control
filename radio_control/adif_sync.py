"""
ADIF DuckDB Synchronization Module
Incrementally syncs ADIF log file to DuckDB for faster queries
"""

import logging
import duckdb
from pathlib import Path
from datetime import datetime
import hashlib
from typing import Optional, List, Dict, Any

from radio_control.adif_handler import ADIFHandler
from radio_control import config
logger = logging.getLogger(__name__)

class ADIFDuckDBSync:
    """Manages synchronization of ADIF file to DuckDB database"""
    
    def __init__(self, adif_path: str = None, db_path: str = None):
        """
        Initialize ADIF to DuckDB synchronizer
        
        Args:
            adif_path: Path to ADIF file (default: config.ADIF_LOG_PATH)
            db_path: Path to DuckDB database (default: data/qso_log.duckdb)
        """
        self.adif_path = Path(adif_path or config.ADIF_LOG_PATH)
        self.db_path = Path(db_path) if db_path else config.DATA_DIR / "qso_log.duckdb"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize ADIF handler
        self.adif_handler = ADIFHandler(str(self.adif_path))
        
        # Initialize database
        self._init_database()
        
        logger.info(f"✅ ADIF DuckDB Sync initialized - DB: {self.db_path}, ADIF: {self.adif_path}")
    
    def _init_database(self):
        """Initialize DuckDB schema and metadata tables"""
        try:
            conn = duckdb.connect(str(self.db_path))
            
            # Create sequence FIRST (must exist before table references it)
            conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_qso_id START 1")
            
            # Create QSO records table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS qso_records (
                    id INTEGER PRIMARY KEY DEFAULT nextval('seq_qso_id'),
                    call VARCHAR,
                    qso_date VARCHAR,
                    time_on VARCHAR,
                    qso_datetime TIMESTAMP,
                    mode VARCHAR,
                    frequency DOUBLE,
                    band VARCHAR,
                    rst_sent VARCHAR,
                    rst_rcvd VARCHAR,
                    name VARCHAR,
                    qth VARCHAR,
                    gridsquare VARCHAR,
                    pota_ref VARCHAR,
                    sota_ref VARCHAR,
                    iota VARCHAR,
                    wwff_ref VARCHAR,
                    comment VARCHAR,
                    country VARCHAR,
                    dxcc INTEGER,
                    cqz INTEGER,
                    ituz INTEGER,
                    lotw_qsl_sent VARCHAR,
                    lotw_qsl_rcvd VARCHAR,
                    eqsl_qsl_sent VARCHAR,
                    eqsl_qsl_rcvd VARCHAR,
                    qsl_sent VARCHAR,
                    qsl_rcvd VARCHAR,
                    clublog_status VARCHAR,
                    hrdlog_status VARCHAR,
                    qrzcom_status VARCHAR,
                    operator VARCHAR,
                    station_callsign VARCHAR,
                    my_country VARCHAR,
                    my_dxcc INTEGER,
                    my_gridsquare VARCHAR,
                    my_city VARCHAR,
                    my_cq_zone INTEGER,
                    my_itu_zone INTEGER,
                    contest_id VARCHAR,
                    cont VARCHAR,
                    stx INTEGER,
                    raw_adif_record TEXT,
                    sync_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    adif_file_hash VARCHAR,
                    adif_record_number INTEGER
                )
            """)
            
            # Create sync metadata table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_metadata (
                    id INTEGER PRIMARY KEY,
                    last_sync_timestamp TIMESTAMP,
                    adif_file_hash VARCHAR,
                    total_records_synced INTEGER,
                    last_record_count INTEGER
                )
            """)
            
            # Create indexes for fast queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_call ON qso_records(call)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_qso_date ON qso_records(qso_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_band ON qso_records(band)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mode ON qso_records(mode)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_qso_datetime ON qso_records(qso_datetime)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_frequency ON qso_records(frequency)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_call_band_mode ON qso_records(call, band, mode)")
            
            conn.close()
            logger.info("✅ DuckDB schema initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize DuckDB: {str(e)}", exc_info=True)
            raise
    
    def _get_adif_file_hash(self) -> str:
        """Get SHA256 hash of ADIF file to detect changes"""
        try:
            if not self.adif_path.exists():
                return ""
            
            sha256_hash = hashlib.sha256()
            with open(self.adif_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            logger.warning(f"⚠️ Could not compute ADIF file hash: {str(e)}")
            return ""
    
    def _get_sync_metadata(self, conn) -> Dict[str, Any]:
        """Retrieve current sync metadata"""
        try:
            result = conn.execute(
                "SELECT * FROM sync_metadata WHERE id = 1"
            ).fetchall()
            
            if result:
                row = result[0]
                return {
                    'last_sync_timestamp': row[1],
                    'adif_file_hash': row[2],
                    'total_records_synced': row[3],
                    'last_record_count': row[4]
                }
            return None
        except Exception as e:
            logger.warning(f"⚠️ Could not retrieve sync metadata: {str(e)}")
            return None
    
    def _update_sync_metadata(self, conn, file_hash: str, record_count: int):
        """Update sync metadata after successful sync"""
        try:
            metadata = self._get_sync_metadata(conn)
            
            if metadata:
                conn.execute("""
                    UPDATE sync_metadata
                    SET last_sync_timestamp = CURRENT_TIMESTAMP,
                        adif_file_hash = ?,
                        total_records_synced = ?,
                        last_record_count = ?
                    WHERE id = 1
                """, (file_hash, record_count, record_count))
            else:
                conn.execute("""
                    INSERT INTO sync_metadata (id, last_sync_timestamp, adif_file_hash, total_records_synced, last_record_count)
                    VALUES (1, CURRENT_TIMESTAMP, ?, ?, ?)
                """, (file_hash, record_count, record_count))
            
            conn.commit()
        except Exception as e:
            logger.error(f"❌ Failed to update sync metadata: {str(e)}")
    
    def _batch_insert_records(self, conn, records: List[Dict[str, Any]]):
        """
        Insert multiple records in a single batch operation for better performance
        """
        if not records:
            return
        
        try:
            # Prepare values for batch insert
            values_list = []
            for db_record in records:
                values_list.append((
                    db_record['call'], db_record['qso_date'], db_record['time_on'],
                    db_record['qso_datetime'], db_record['mode'], db_record['frequency'],
                    db_record['band'], db_record['rst_sent'], db_record['rst_rcvd'],
                    db_record['name'], db_record['qth'], db_record['gridsquare'],
                    db_record['pota_ref'], db_record['sota_ref'], db_record['iota'],
                    db_record['wwff_ref'], db_record['comment'], db_record['country'],
                    db_record['dxcc'], db_record['cqz'], db_record['ituz'],
                    db_record['lotw_qsl_sent'], db_record['lotw_qsl_rcvd'],
                    db_record['eqsl_qsl_sent'], db_record['eqsl_qsl_rcvd'],
                    db_record['qsl_sent'], db_record['qsl_rcvd'],
                    db_record['clublog_status'], db_record['hrdlog_status'],
                    db_record['qrzcom_status'], db_record['operator'],
                    db_record['station_callsign'], db_record['my_country'],
                    db_record['my_dxcc'], db_record['my_gridsquare'],
                    db_record['my_city'], db_record['my_cq_zone'],
                    db_record['my_itu_zone'], db_record['contest_id'],
                    db_record['cont'], db_record['stx'],
                    db_record['raw_adif_record'], db_record['adif_file_hash'],
                    db_record['adif_record_number']
                ))
            
            # Execute batch insert
            conn.executemany("""
                INSERT INTO qso_records (
                    call, qso_date, time_on, qso_datetime, mode, frequency, band,
                    rst_sent, rst_rcvd, name, qth, gridsquare, pota_ref, sota_ref,
                    iota, wwff_ref, comment, country, dxcc, cqz, ituz,
                    lotw_qsl_sent, lotw_qsl_rcvd, eqsl_qsl_sent, eqsl_qsl_rcvd,
                    qsl_sent, qsl_rcvd, clublog_status, hrdlog_status, qrzcom_status,
                    operator, station_callsign, my_country, my_dxcc, my_gridsquare,
                    my_city, my_cq_zone, my_itu_zone, contest_id, cont, stx,
                    raw_adif_record, adif_file_hash, adif_record_number
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                         ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, values_list)
            
            conn.commit()
        except Exception as e:
            logger.error(f"❌ Batch insert failed: {str(e)}")
            conn.rollback()
    
    def _parse_adif_record_full(self, record: str) -> Dict[str, Any]:
        """
        Parse ADIF record and extract ALL fields
        """
        import re
        
        result = {}
        pattern = r'<([A-Z_]+):(\d+)>'
        
        for match in re.finditer(pattern, record):
            field_name = match.group(1).lower()
            field_length = int(match.group(2))
            
            # Extract exactly field_length characters after the >
            value_start = match.end()
            field_value = record[value_start:value_start + field_length].strip()
            
            # Skip empty fields
            if not field_value:
                continue
            
            result[field_name] = field_value
        
        return result
    
    def _convert_to_db_record(self, adif_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert parsed ADIF data to database record format
        """
        try:
            # Parse date and time
            qso_date_str = adif_data.get('qso_date', '')
            time_on_str = adif_data.get('time_on', '000000')
            
            qso_datetime = None
            if qso_date_str and len(qso_date_str) == 8:
                try:
                    dt = datetime.strptime(f"{qso_date_str}{time_on_str}", "%Y%m%d%H%M%S")
                    qso_datetime = dt
                except:
                    pass
            
            # Parse frequency
            freq = 0.0
            try:
                freq = float(adif_data.get('freq', 0))
            except:
                pass
            
            # Parse integer fields
            def safe_int(val):
                try:
                    return int(val) if val else None
                except:
                    return None
            
            record = {
                'call': adif_data.get('call', ''),
                'qso_date': qso_date_str,
                'time_on': time_on_str,
                'qso_datetime': qso_datetime,
                'mode': adif_data.get('mode', ''),
                'frequency': freq,
                'band': adif_data.get('band', ''),
                'rst_sent': adif_data.get('rst_sent', ''),
                'rst_rcvd': adif_data.get('rst_rcvd', '') or adif_data.get('rst_received', ''),
                'name': adif_data.get('name', ''),
                'qth': adif_data.get('qth', ''),
                'gridsquare': adif_data.get('gridsquare', ''),
                'pota_ref': adif_data.get('pota_ref', ''),
                'sota_ref': adif_data.get('sota_ref', ''),
                'iota': adif_data.get('iota', ''),
                'wwff_ref': adif_data.get('wwff_ref', ''),
                'comment': adif_data.get('comment', ''),
                'country': adif_data.get('country', ''),
                'dxcc': safe_int(adif_data.get('dxcc')),
                'cqz': safe_int(adif_data.get('cqz')),
                'ituz': safe_int(adif_data.get('ituz')),
                'lotw_qsl_sent': adif_data.get('lotw_qsl_sent', ''),
                'lotw_qsl_rcvd': adif_data.get('lotw_qsl_rcvd', ''),
                'eqsl_qsl_sent': adif_data.get('eqsl_qsl_sent', ''),
                'eqsl_qsl_rcvd': adif_data.get('eqsl_qsl_rcvd', ''),
                'qsl_sent': adif_data.get('qsl_sent', ''),
                'qsl_rcvd': adif_data.get('qsl_rcvd', ''),
                'clublog_status': adif_data.get('clublog_qso_upload_status', ''),
                'hrdlog_status': adif_data.get('hrdlog_qso_upload_status', ''),
                'qrzcom_status': adif_data.get('qrzcom_qso_upload_status', ''),
                'operator': adif_data.get('operator', ''),
                'station_callsign': adif_data.get('station_callsign', ''),
                'my_country': adif_data.get('my_country', ''),
                'my_dxcc': safe_int(adif_data.get('my_dxcc')),
                'my_gridsquare': adif_data.get('my_gridsquare', ''),
                'my_city': adif_data.get('my_city', ''),
                'my_cq_zone': safe_int(adif_data.get('my_cq_zone')),
                'my_itu_zone': safe_int(adif_data.get('my_itu_zone')),
                'contest_id': adif_data.get('contest_id', ''),
                'cont': adif_data.get('cont', ''),
                'stx': safe_int(adif_data.get('stx')),
                'raw_adif_record': '',
                'adif_file_hash': '',
                'adif_record_number': 0
            }
            
            return record
        except Exception as e:
            logger.error(f"❌ Error converting ADIF record: {str(e)}")
            return None
    
    def sync(self) -> Dict[str, Any]:
        """
        Perform INCREMENTAL sync from ADIF file to DuckDB
        Only adds new records, doesn't delete existing ones
        
        Returns:
            Dictionary with sync statistics
        """
        try:
            if not self.adif_path.exists():
                logger.warning(f"⚠️ ADIF file not found: {self.adif_path}")
                return {'synced': False, 'message': 'ADIF file not found', 'records_synced': 0}
            
            conn = duckdb.connect(str(self.db_path))
            
            # Get current file hash
            current_hash = self._get_adif_file_hash()
            
            # Get previous metadata
            metadata = self._get_sync_metadata(conn)
            previous_hash = metadata.get('adif_file_hash') if metadata else None
            last_record_count = metadata.get('total_records_synced', 0) if metadata else 0
            
            # If file hasn't changed, skip sync
            if previous_hash and current_hash == previous_hash:
                logger.debug(f"✅ ADIF file unchanged since last sync")
                current_count = conn.execute("SELECT COUNT(*) FROM qso_records").fetchone()[0]
                conn.close()
                return {
                    'synced': False,
                    'message': 'File unchanged - no sync needed',
                    'records_synced': 0,
                    'total_records': current_count
                }
            
            # Stream read ADIF file (efficient for large files)
            logger.info(f"🔄 Reading ADIF file (incremental sync, last: {last_record_count} records)...")
            
            # Get existing record signatures to avoid duplicates
            # A signature is call+qso_date+time_on - this uniquely identifies a QSO
            existing_signatures = set()
            try:
                existing_records = conn.execute(
                    "SELECT call, qso_date, time_on FROM qso_records WHERE call IS NOT NULL"
                ).fetchall()
                for call, date, time_on in existing_records:
                    sig = f"{call}|{date}|{time_on or ''}"
                    existing_signatures.add(sig)
                logger.debug(f"📊 Found {len(existing_signatures)} existing QSO signatures in database")
            except Exception as e:
                logger.warning(f"⚠️ Could not check existing records: {e}")
            
            synced_count = 0
            new_count = 0
            skipped_count = 0
            errors = 0
            record_num = 0
            current_record = []
            batch_records = []  # Collect records for batch insert
            batch_size = 1000  # Batch insert every 1000 records
            
            try:
                with open(self.adif_path, 'r', encoding='utf-8', errors='replace') as f:
                    for line in f:
                        line = line.rstrip('\n\r')
                        current_record.append(line)
                        
                        # Check if this line ends a record
                        if line.strip() == '<EOR>':
                            record_text = '\n'.join(current_record)
                            
                            # Skip header and empty records
                            if record_text.strip() and '<EOH>' not in record_text:
                                try:
                                    # Parse the ADIF record
                                    adif_data = self._parse_adif_record_full(record_text)
                                    
                                    # Convert to database record
                                    db_record = self._convert_to_db_record(adif_data)
                                    if db_record:
                                        # Check if record already exists (incremental sync)
                                        call = db_record.get('call', '')
                                        qso_date = db_record.get('qso_date', '')
                                        time_on = db_record.get('time_on', '')
                                        sig = f"{call}|{qso_date}|{time_on or ''}"
                                        
                                        if sig not in existing_signatures:
                                            # New record - add it
                                            db_record['adif_file_hash'] = current_hash
                                            db_record['adif_record_number'] = record_num
                                            db_record['raw_adif_record'] = record_text.strip()
                                            batch_records.append(db_record)
                                            existing_signatures.add(sig)  # Track this new one
                                            new_count += 1
                                            
                                            # Batch insert when we reach batch_size
                                            if len(batch_records) >= batch_size:
                                                self._batch_insert_records(conn, batch_records)
                                                synced_count += len(batch_records)
                                                logger.debug(f"📊 Synced {synced_count} new records ({skipped_count} existing)...")
                                                batch_records = []
                                        else:
                                            skipped_count += 1
                                    else:
                                        errors += 1
                                
                                except Exception as e:
                                    logger.debug(f"⚠️ Error processing record {record_num}: {str(e)}")
                                    errors += 1
                                
                                record_num += 1
                            
                            # Reset for next record
                            current_record = []
                
                # Insert any remaining records
                if batch_records:
                    self._batch_insert_records(conn, batch_records)
                    synced_count += len(batch_records)
                    logger.debug(f"📊 Final batch: {len(batch_records)} records")
            
            except Exception as e:
                logger.error(f"❌ Error reading ADIF file: {str(e)}", exc_info=True)
                errors += 1
            
            # Final commit
            conn.commit()
            
            # Get final record count
            final_count = conn.execute("SELECT COUNT(*) FROM qso_records").fetchone()[0]
            
            # Update sync metadata with TOTAL count, not just new records
            self._update_sync_metadata(conn, current_hash, final_count)
            
            conn.close()
            
            logger.info(f"✅ ADIF incremental sync complete: {new_count} NEW records, "
                       f"{skipped_count} existing, {final_count} total ({errors} errors)")
            
            return {
                'synced': new_count > 0,  # True if any new records were added
                'message': f'Incremental sync: {new_count} new records, {skipped_count} existing',
                'records_synced': new_count,
                'records_skipped': skipped_count,
                'errors': errors,
                'total_records': final_count,
                'timestamp': datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"❌ ADIF sync failed: {str(e)}", exc_info=True)
            return {
                'synced': False,
                'message': f'Sync failed: {str(e)}',
                'records_synced': 0,
                'total_records': 0
            }
    
    # Query Methods
    
    def get_all_qsos(self, limit: int = None, offset: int = 0) -> List[Dict[str, Any]]:
        """Get all QSOs from database"""
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)
            
            query = "SELECT * FROM qso_records ORDER BY qso_datetime DESC"
            if limit:
                query += f" LIMIT {limit} OFFSET {offset}"
            
            results = conn.execute(query).fetchall()
            columns = [desc[0] for desc in conn.description]
            
            conn.close()
            
            return [dict(zip(columns, row)) for row in results]
        except Exception as e:
            logger.error(f"❌ Error querying all QSOs: {str(e)}")
            return []
    
    def get_qsos_by_callsign(self, callsign: str, limit: int = None) -> List[Dict[str, Any]]:
        """Get QSOs for a specific callsign"""
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)
            
            query = "SELECT * FROM qso_records WHERE UPPER(call) = ? ORDER BY qso_datetime DESC"
            if limit:
                query += f" LIMIT {limit}"
            
            results = conn.execute(query, (callsign.upper(),)).fetchall()
            columns = [desc[0] for desc in conn.description]
            
            conn.close()
            
            return [dict(zip(columns, row)) for row in results]
        except Exception as e:
            logger.error(f"❌ Error querying QSOs for {callsign}: {str(e)}")
            return []
    
    def get_qsos_by_band(self, band: str, limit: int = None) -> List[Dict[str, Any]]:
        """Get QSOs for a specific band"""
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)
            
            query = "SELECT * FROM qso_records WHERE band = ? ORDER BY qso_datetime DESC"
            if limit:
                query += f" LIMIT {limit}"
            
            results = conn.execute(query, (band,)).fetchall()
            columns = [desc[0] for desc in conn.description]
            
            conn.close()
            
            return [dict(zip(columns, row)) for row in results]
        except Exception as e:
            logger.error(f"❌ Error querying QSOs for band {band}: {str(e)}")
            return []
    
    def get_qsos_by_date_range(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Get QSOs within a date range (YYYYMMDD format)"""
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)
            
            query = """
                SELECT * FROM qso_records 
                WHERE qso_date >= ? AND qso_date <= ?
                ORDER BY qso_datetime DESC
            """
            
            results = conn.execute(query, (start_date, end_date)).fetchall()
            columns = [desc[0] for desc in conn.description]
            
            conn.close()
            
            return [dict(zip(columns, row)) for row in results]
        except Exception as e:
            logger.error(f"❌ Error querying QSOs by date range: {str(e)}")
            return []
    
    def get_qsos_by_mode(self, mode: str, limit: int = None) -> List[Dict[str, Any]]:
        """Get QSOs for a specific mode"""
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)
            
            query = "SELECT * FROM qso_records WHERE mode = ? ORDER BY qso_datetime DESC"
            if limit:
                query += f" LIMIT {limit}"
            
            results = conn.execute(query, (mode,)).fetchall()
            columns = [desc[0] for desc in conn.description]
            
            conn.close()
            
            return [dict(zip(columns, row)) for row in results]
        except Exception as e:
            logger.error(f"❌ Error querying QSOs for mode {mode}: {str(e)}")
            return []
    
    def worked_before(self, callsign: str, band: str = None, mode: str = None) -> bool:
        """Check if a callsign was worked before (optionally on specific band/mode)"""
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)
            
            query = "SELECT COUNT(*) FROM qso_records WHERE UPPER(call) = ?"
            params = [callsign.upper()]
            
            if band:
                query += " AND band = ?"
                params.append(band)
            
            if mode:
                query += " AND mode = ?"
                params.append(mode)
            
            count = conn.execute(query, params).fetchone()[0]
            conn.close()
            
            return count > 0
        except Exception as e:
            logger.error(f"❌ Error checking if worked before: {str(e)}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        try:
            conn = duckdb.connect(str(self.db_path), read_only=True)
            
            total_qsos = conn.execute("SELECT COUNT(*) FROM qso_records").fetchone()[0]
            unique_calls = conn.execute("SELECT COUNT(DISTINCT call) FROM qso_records").fetchone()[0]
            
            bands = conn.execute("""
                SELECT band, COUNT(*) as count FROM qso_records 
                GROUP BY band ORDER BY count DESC
            """).fetchall()
            
            modes = conn.execute("""
                SELECT mode, COUNT(*) as count FROM qso_records 
                GROUP BY mode ORDER BY count DESC
            """).fetchall()
            
            countries = conn.execute("""
                SELECT country, COUNT(*) as count FROM qso_records 
                WHERE country IS NOT NULL AND country != ''
                GROUP BY country ORDER BY count DESC LIMIT 10
            """).fetchall()
            
            conn.close()
            
            return {
                'total_qsos': total_qsos,
                'unique_calls': unique_calls,
                'bands': [{'band': b[0], 'count': b[1]} for b in bands],
                'modes': [{'mode': m[0], 'count': m[1]} for m in modes],
                'top_countries': [{'country': c[0], 'count': c[1]} for c in countries],
                'last_updated': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ Error getting stats: {str(e)}")
            return {}


# Module-level instance
_sync_instance: Optional[ADIFDuckDBSync] = None

def get_adif_sync() -> ADIFDuckDBSync:
    """Get or create the ADIF sync instance"""
    global _sync_instance
    if _sync_instance is None:
        _sync_instance = ADIFDuckDBSync()
    return _sync_instance

def init_adif_sync():
    """Initialize ADIF sync"""
    global _sync_instance
    _sync_instance = ADIFDuckDBSync()
    return _sync_instance

async def periodic_adif_sync():
    """
    Periodic ADIF sync task
    Runs immediately on first call, then every 30 seconds to check for ADIF file changes
    """
    import asyncio
    
    first_run = True
    while True:
        try:
            # Do immediate first sync, then wait 30 seconds between subsequent syncs
            if not first_run:
                await asyncio.sleep(30)
            first_run = False
            
            if _sync_instance is not None:
                result = _sync_instance.sync()
                if result['synced']:
                    logger.info(f"✅ ADIF sync: {result['records_synced']} records synced, "
                               f"total: {result.get('total_records', 0)}")
                # If not synced, file unchanged - skip logging
        except Exception as e:
            logger.error(f"❌ Error in periodic ADIF sync: {e}")
            await asyncio.sleep(5)  # Brief pause before retry on error
