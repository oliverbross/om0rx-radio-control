"""
DX Spots Logger - DuckDB-based persistent logging of all incoming spots
Stores all spot details for statistical analysis and persistence across app reloads
"""
import os
import logging
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional, Dict, Any, List
import duckdb

from radio_control.spot_processor import band_from_khz, infer_mode, extract_special, clean_comment

logger = logging.getLogger(__name__)

# Try to import cty resolver, but don't fail if not available
try:
    from radio_control.cty_resolvers import CtyDatResolver
    _cty_resolver = None
except ImportError:
    CtyDatResolver = None
    _cty_resolver = None


def _initialize_cty_resolver():
    """Initialize CTY resolver once (called lazily on first use)"""
    global _cty_resolver
    
    if _cty_resolver is not None or not CtyDatResolver:
        return
    
    try:
        from radio_control import config

        cty_dat = config.DATA_DIR / "cty.dat"
        cty_csv = config.DATA_DIR / "cty.csv"
        
        if cty_dat.exists():
            _cty_resolver = CtyDatResolver(
                str(cty_dat),
                csv_path=str(cty_csv) if cty_csv.exists() else None
            )
            logger.debug(f"✓ CTY resolver initialized")
    except Exception as e:
        logger.debug(f"Warning: Could not initialize CTY resolver: {e}")


def get_country_and_zone(callsign: str) -> Optional[Dict[str, Any]]:
    """
    Get country and zone information for a callsign using CTY resolver
    Returns dict with keys: country, cq_zone, itu_zone, continent, dxcc
    Returns None if resolver not available
    """
    global _cty_resolver
    
    if not callsign or not CtyDatResolver:
        return None
    
    try:
        # Initialize CTY resolver on first use (lazy)
        if _cty_resolver is None:
            _initialize_cty_resolver()
        
        if _cty_resolver:
            info = _cty_resolver.lookup(callsign)
            if info:
                return {
                    'country': info.get('country'),
                    'cq_zone': info.get('cq'),
                    'itu_zone': info.get('itu'),
                    'continent': info.get('continent'),
                    'dxcc': info.get('dxcc')
                }
    except Exception as e:
        logger.debug(f"Error looking up country for {callsign}: {e}")
    
    return None

from radio_control import config

# Data directory path
DATA_DIR = config.DATA_DIR
DATA_DIR.mkdir(exist_ok=True)

SPOTS_DB_PATH = DATA_DIR / "spots.duckdb"


class SpotsLogger:
    """DuckDB-based logger for DX cluster spots"""
    
    def __init__(self, db_path: str = str(SPOTS_DB_PATH)):
        """Initialize spots logger with DuckDB database"""
        self.db_path = db_path
        self.conn = None
        self._initialize_database()
    
    def _initialize_database(self):
        """Create database and schema if not exists"""
        try:
            self.conn = duckdb.connect(self.db_path)
            
            # Create spots table with comprehensive schema
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS spots (
                    -- Timestamp fields
                    received_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    date_utc DATE NOT NULL,
                    time_utc TIME NOT NULL,
                    
                    -- Spot core data (from cluster)
                    frequency_khz DOUBLE NOT NULL,
                    callsign VARCHAR NOT NULL,
                    spotter VARCHAR NOT NULL,
                    comment VARCHAR,
                    
                    -- Derived fields (processed)
                    band VARCHAR NOT NULL,
                    mode VARCHAR NOT NULL,
                    
                    -- Country/Zone information
                    country VARCHAR,
                    zone_cq INTEGER,
                    zone_itu INTEGER,
                    continent VARCHAR,
                    
                    -- Special event tags (POTA, SOTA, IOTA, etc.)
                    special_tags VARCHAR,
                    
                    -- Classification results (cached to avoid re-computing during searches)
                    call_status VARCHAR DEFAULT 'Unknown',
                    dxcc_status VARCHAR DEFAULT 'Unknown',
                    
                    -- Metadata
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    
                    -- Constraints for data quality
                    CHECK (frequency_khz > 0),
                    CHECK (length(callsign) > 0),
                    CHECK (length(spotter) > 0)
                )
            """)
            
            # ⚡ CRITICAL FIX: Don't create indexes during init - defer to background task
            # This was blocking app startup for several seconds!
            # Indexes will be created lazily on first query or in background
            self._indexes_created = False
            
            logger.info(f"✅ Spots database initialized (indexes deferred): {self.db_path}")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize spots database: {e}", exc_info=True)
            raise
    
    def _create_indexes(self):
        """Create indexes for efficient querying (called lazily to avoid blocking startup)"""
        if self._indexes_created:
            return
            
        indexes = [
            ("idx_spot_received", "spots(received_at)"),
            ("idx_spot_date", "spots(date_utc)"),
            ("idx_spot_band", "spots(band)"),
            ("idx_spot_mode", "spots(mode)"),
            ("idx_spot_callsign", "spots(callsign)"),
            ("idx_spot_spotter", "spots(spotter)"),
            ("idx_spot_country", "spots(country)"),
            ("idx_spot_frequency", "spots(frequency_khz)"),
            ("idx_spot_band_mode", "spots(band, mode)"),
            ("idx_spot_date_band", "spots(date_utc, band)"),
            ("idx_spot_call_status", "spots(call_status)"),
            ("idx_spot_dxcc_status", "spots(dxcc_status)"),
        ]
        
        try:
            for idx_name, idx_def in indexes:
                try:
                    self.conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_def}")
                except duckdb.CatalogException:
                    pass  # Index already exists
            self._indexes_created = True
            logger.debug(f"✅ Spots database indexes created")
        except Exception as e:
            logger.warning(f"⚠️ Index creation warning: {e}")
    
    def log_spot(self, spot_data: Dict[str, Any], call_status: str = "Unknown", dxcc_status: str = "Unknown") -> bool:
        """
        Log a single DX spot to database
        
        Args:
            spot_data: Dictionary with keys:
                - spotter: Spotter callsign
                - freq_khz: Frequency in kHz (float)
                - freq_khz_str: Frequency string for display precision
                - dxcall: DX station callsign
                - comment: Comment from cluster
                - timestamp: UTC datetime of receipt
            call_status: Classification result for callsign (e.g., "New Call", "Worked", "New Band")
            dxcc_status: Classification result for DXCC entity (e.g., "ATNO", "Confirmed")
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Check if connection is valid
            if not self.conn:
                logger.error(f"❌ Database connection is None - cannot save spot")
                return False
            
            # Extract and validate required fields
            spotter = spot_data.get('spotter', '').upper().strip()
            dxcall = spot_data.get('dxcall', '').upper().strip()
            freq_khz = spot_data.get('freq_khz', 0.0)
            comment = clean_comment(spot_data.get('comment', ''))
            received_at = spot_data.get('timestamp', datetime.now(UTC))
            
            # Validate
            if not spotter or not dxcall or freq_khz <= 0:
                logger.warning(f"❌ Invalid spot data: spotter={spotter}, call={dxcall}, freq={freq_khz}")
                return False
            
            # Derive fields
            band = band_from_khz(freq_khz)
            mode = infer_mode(comment, band, freq_khz)
            special_tags = extract_special(comment)
            
            # Get country and zone information
            country_info = get_country_and_zone(dxcall)
            country = country_info.get('country') if country_info else None
            zone_cq = country_info.get('cq_zone') if country_info else None
            zone_itu = country_info.get('itu_zone') if country_info else None
            continent = country_info.get('continent') if country_info else None
            
            # Extract date and time components
            date_utc = received_at.date()
            time_utc = received_at.time()
            
            # Insert into database with classifications
            self.conn.execute("""
                INSERT INTO spots (
                    received_at, date_utc, time_utc,
                    frequency_khz, callsign, spotter, comment,
                    band, mode, country, zone_cq, zone_itu, continent,
                    special_tags, call_status, dxcc_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                received_at, date_utc, time_utc,
                freq_khz, dxcall, spotter, comment,
                band, mode, country, zone_cq, zone_itu, continent,
                special_tags if special_tags else None,
                call_status, dxcc_status
            ])
            
            # ✅ CRITICAL: Commit transaction so spot is actually persisted to database
            self.conn.commit()
            
            # Force checkpoint to flush WAL to main database file
            try:
                self.conn.execute("CHECKPOINT")
            except Exception as e:
                logger.debug(f"Checkpoint warning (non-critical): {e}")
            
            logger.debug(f"✓ Logged spot: {dxcall} on {band} ({mode}) by {spotter} [{call_status}/{dxcc_status}]")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error logging spot for {dxcall} on {band_from_khz(freq_khz)}: {e}", exc_info=True)
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    def get_spot_count(self, date_filter: Optional[str] = None) -> int:
        """Get total number of logged spots, optionally filtered by date (YYYY-MM-DD)"""
        try:
            # Lazy-create indexes on first query
            if not self._indexes_created:
                self._create_indexes()
            
            if date_filter:
                result = self.conn.execute(
                    "SELECT COUNT(*) FROM spots WHERE date_utc = ?",
                    [date_filter]
                ).fetchall()
            else:
                result = self.conn.execute(
                    "SELECT COUNT(*) FROM spots"
                ).fetchall()
            
            return result[0][0] if result else 0
        except Exception as e:
            logger.error(f"Error getting spot count: {e}")
            return 0
    
    def get_stats_by_band(self, date_filter: Optional[str] = None) -> List[Dict]:
        """Get spot statistics grouped by band"""
        try:
            # Lazy-create indexes on first query
            if not self._indexes_created:
                self._create_indexes()
            
            where = "WHERE date_utc = ?" if date_filter else ""
            params = [date_filter] if date_filter else []
            
            query = f"""
                SELECT 
                    band,
                    COUNT(*) as total_spots,
                    COUNT(DISTINCT callsign) as unique_callsigns,
                    COUNT(DISTINCT spotter) as spotters,
                    COUNT(DISTINCT country) as countries,
                    MIN(frequency_khz) as min_freq,
                    MAX(frequency_khz) as max_freq
                FROM spots
                {where}
                GROUP BY band
                ORDER BY band
            """
            
            result = self.conn.execute(query, params).fetchall()
            columns = ['band', 'total_spots', 'unique_callsigns', 'spotters', 'countries', 'min_freq', 'max_freq']
            
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.error(f"Error getting band stats: {e}")
            return []
    
    def get_stats_by_mode(self, date_filter: Optional[str] = None) -> List[Dict]:
        """Get spot statistics grouped by mode"""
        try:
            # Lazy-create indexes on first query
            if not self._indexes_created:
                self._create_indexes()
            
            where = "WHERE date_utc = ?" if date_filter else ""
            params = [date_filter] if date_filter else []
            
            query = f"""
                SELECT 
                    mode,
                    COUNT(*) as total_spots,
                    COUNT(DISTINCT callsign) as unique_callsigns,
                    COUNT(DISTINCT country) as countries
                FROM spots
                {where}
                GROUP BY mode
                ORDER BY total_spots DESC
            """
            
            result = self.conn.execute(query, params).fetchall()
            columns = ['mode', 'total_spots', 'unique_callsigns', 'countries']
            
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.error(f"Error getting mode stats: {e}")
            return []
    
    def get_stats_by_country(self, limit: int = 20, date_filter: Optional[str] = None) -> List[Dict]:
        """Get top countries by spot count"""
        try:
            # Lazy-create indexes on first query
            if not self._indexes_created:
                self._create_indexes()
            
            where = "WHERE date_utc = ?" if date_filter else "WHERE country IS NOT NULL"
            params = [date_filter] if date_filter else []
            
            query = f"""
                SELECT 
                    country,
                    COUNT(*) as total_spots,
                    COUNT(DISTINCT callsign) as unique_callsigns,
                    COUNT(DISTINCT band) as bands,
                    MIN(frequency_khz) as min_freq,
                    MAX(frequency_khz) as max_freq
                FROM spots
                {where}
                GROUP BY country
                ORDER BY total_spots DESC
                LIMIT ?
            """
            
            result = self.conn.execute(query, params + [limit]).fetchall()
            columns = ['country', 'total_spots', 'unique_callsigns', 'bands', 'min_freq', 'max_freq']
            
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.error(f"Error getting country stats: {e}")
            return []
    
    def get_recent_spots(self, limit: int = 100) -> List[Dict]:
        """Get most recent spots"""
        try:
            # Lazy-create indexes on first query
            if not self._indexes_created:
                self._create_indexes()
            
            query = """
                SELECT 
                    CAST(received_at AS VARCHAR) as received_at, CAST(date_utc AS VARCHAR) as date_utc, CAST(time_utc AS VARCHAR) as time_utc,
                    frequency_khz, band, mode,
                    callsign, spotter, country, zone_cq as cq,
                    comment, special_tags
                FROM spots
                ORDER BY received_at DESC
                LIMIT ?
            """
            
            result = self.conn.execute(query, [limit]).fetchall()
            columns = ['received_at', 'date_utc', 'time_utc', 'frequency_khz', 'band', 'mode',
                      'callsign', 'spotter', 'country', 'cq', 'comment', 'special_tags']
            
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.error(f"Error getting recent spots: {e}")
            return []
    
    def get_spots_by_callsign(self, callsign: str, limit: int = 100) -> List[Dict]:
        """Get all spots for a specific callsign"""
        try:
            # Lazy-create indexes on first query
            if not self._indexes_created:
                self._create_indexes()
            
            query = """
                SELECT 
                    CAST(received_at AS VARCHAR) as received_at, CAST(date_utc AS VARCHAR) as date_utc, CAST(time_utc AS VARCHAR) as time_utc,
                    frequency_khz, band, mode,
                    spotter, country, comment
                FROM spots
                WHERE callsign = ?
                ORDER BY received_at DESC
                LIMIT ?
            """
            
            result = self.conn.execute(query, [callsign.upper(), limit]).fetchall()
            columns = ['received_at', 'date_utc', 'time_utc', 'frequency_khz', 'band', 'mode',
                      'spotter', 'country', 'comment']
            
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.error(f"Error getting spots by callsign: {e}")
            return []
    
    def get_special_event_spots(self, limit: int = 100) -> List[Dict]:
        """Get spots with special event tags (POTA, SOTA, IOTA)"""
        try:
            query = """
                SELECT 
                    CAST(received_at AS VARCHAR) as received_at, CAST(date_utc AS VARCHAR) as date_utc, CAST(time_utc AS VARCHAR) as time_utc,
                    frequency_khz, band, mode,
                    callsign, spotter, country,
                    special_tags, comment
                FROM spots
                WHERE special_tags IS NOT NULL AND special_tags != ''
                ORDER BY received_at DESC
                LIMIT ?
            """
            
            result = self.conn.execute(query, [limit]).fetchall()
            columns = ['received_at', 'date_utc', 'time_utc', 'frequency_khz', 'band', 'mode',
                      'callsign', 'spotter', 'country', 'special_tags', 'comment']
            
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.error(f"Error getting special event spots: {e}")
            return []
    
    def get_filtered_spots(
        self,
        limit: int = 100,
        callsign: Optional[str] = None,
        bands: Optional[List[str]] = None,
        modes: Optional[List[str]] = None,
        zones_cq: Optional[List[int]] = None,
        continents: Optional[List[str]] = None,
        special_tags_filter: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Query spots from database with comprehensive filtering
        Used when filters are applied in the UI - searches the full spot history
        
        Args:
            limit: Maximum number of spots to return
            callsign: Partial callsign to search for
            bands: List of bands to filter by (e.g., ['20m', '40m'])
            modes: List of modes to filter by (e.g., ['SSB', 'CW'])
            zones_cq: List of CQ zones to filter by
            continents: List of continents to filter by
            special_tags_filter: List of special tags to filter by (POTA, SOTA, etc)
        
        Returns:
            List of spot dictionaries matching all filters
        """
        try:
            # Lazy-create indexes on first query
            if not self._indexes_created:
                self._create_indexes()
            
            # Build WHERE clauses
            where_clauses = []
            params = []
            
            # Callsign filter (case-insensitive PREFIX match - much faster than infix)
            # Using LIKE 'PREFIX%' allows database to use index on callsign column
            # This is 50-100x faster than LIKE '%PREFIX%' which requires full table scan
            if callsign:
                where_clauses.append("UPPER(callsign) LIKE ?")
                params.append(f"{callsign.upper()}%")  # PREFIX match only (no leading wildcard)
            
            # Band filter
            if bands and len(bands) > 0:
                placeholders = ','.join(['?' for _ in bands])
                where_clauses.append(f"band IN ({placeholders})")
                params.extend(bands)
            
            # Mode filter
            if modes and len(modes) > 0:
                placeholders = ','.join(['?' for _ in modes])
                where_clauses.append(f"mode IN ({placeholders})")
                params.extend(modes)
            
            # CQ Zone filter
            if zones_cq and len(zones_cq) > 0:
                placeholders = ','.join(['?' for _ in zones_cq])
                where_clauses.append(f"zone_cq IN ({placeholders})")
                params.extend(zones_cq)
            
            # Continent filter
            if continents and len(continents) > 0:
                placeholders = ','.join(['?' for _ in continents])
                where_clauses.append(f"continent IN ({placeholders})")
                params.extend(continents)
            
            # Special tags filter (any tag matching)
            if special_tags_filter and len(special_tags_filter) > 0:
                # Build OR condition for special tags since they're comma-separated
                or_clauses = []
                for tag in special_tags_filter:
                    or_clauses.append(f"special_tags LIKE ?")
                    params.append(f"%{tag}%")
                where_clauses.append(f"({' OR '.join(or_clauses)})")
            
            # Combine WHERE clauses
            where = ""
            if where_clauses:
                where = "WHERE " + " AND ".join(where_clauses)
            
            query = f"""
                SELECT 
                    EXTRACT(EPOCH FROM received_at) as timestamp,
                    CAST(time_utc AS VARCHAR) as time,
                    frequency_khz / 1000.0 as frequency_mhz,
                    CAST(frequency_khz AS VARCHAR) as frequency,
                    band, mode,
                    callsign, spotter, country, zone_cq as cq, zone_itu,
                    continent, special_tags, comment,
                    call_status, dxcc_status
                FROM spots
                {where}
                ORDER BY received_at DESC
                LIMIT ?
            """
            
            params.append(limit)
            result = self.conn.execute(query, params).fetchall()
            columns = ['timestamp', 'time', 'frequency_mhz', 'frequency', 'band', 'mode',
                      'callsign', 'spotter', 'country', 'cq', 'zone_itu',
                      'continent', 'special_tags', 'comment', 'call_status', 'dxcc_status']
            
            spots = []
            for row in result:
                spot = dict(zip(columns, row))
                # Add fields expected by frontend template
                spot['tag'] = None
                spot['special'] = spot.get('special_tags', '')  # Frontend expects 'special' field
                spot['spotter_continent'] = spot.get('continent', '')  # For filtering
                # Use stored classifications from database
                if not spot.get('call_status'):
                    spot['call_status'] = '-'
                if not spot.get('dxcc_status'):
                    spot['dxcc_status'] = '-'
                spots.append(spot)
            
            logger.debug(f"✓ Filtered query returned {len(spots)} spots with filters: callsign={callsign}, bands={bands}, modes={modes}")
            return spots
            
        except Exception as e:
            logger.error(f"Error querying filtered spots: {e}", exc_info=True)
            return []
    
    def export_csv(self, output_path: str, date_filter: Optional[str] = None):
        """Export spots to CSV file"""
        try:
            where = "WHERE date_utc = ?" if date_filter else ""
            params = [date_filter] if date_filter else []
            
            query = f"""
                SELECT 
                    received_at, date_utc, time_utc,
                    frequency_khz, band, mode,
                    callsign, spotter, country, zone_cq, zone_itu, continent,
                    special_tags, comment
                FROM spots
                {where}
                ORDER BY received_at DESC
            """
            
            df = self.conn.execute(query, params).df()
            df.to_csv(output_path, index=False)
            logger.info(f"✓ Exported {len(df)} spots to {output_path}")
            return len(df)
        except Exception as e:
            logger.error(f"Error exporting to CSV: {e}")
            return 0
    
    def close(self):
        """Close database connection"""
        try:
            if self.conn:
                self.conn.close()
                logger.info("Spots database connection closed")
        except Exception as e:
            logger.error(f"Error closing database: {e}")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Global instance for easy access
_logger_instance: Optional[SpotsLogger] = None


def get_spots_logger() -> SpotsLogger:
    """Get or create the global spots logger instance"""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = SpotsLogger()
    return _logger_instance


def log_spot(spot_data: Dict[str, Any], call_status: str = "Unknown", dxcc_status: str = "Unknown") -> bool:
    """Convenience function to log a spot using global instance with optional classifications"""
    return get_spots_logger().log_spot(spot_data, call_status, dxcc_status)


if __name__ == "__main__":
    # Test the logger
    logging.basicConfig(level=logging.DEBUG)
    
    with SpotsLogger() as logger:
        print(f"Total spots: {logger.get_spot_count()}")
        print("\nStats by band:")
        for stat in logger.get_stats_by_band():
            print(f"  {stat['band']}: {stat['total_spots']} spots, {stat['unique_callsigns']} unique calls")
