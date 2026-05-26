"""
ADIF Service Module

Extracted ADIF operations from main.py for modularization.
Includes ADIF file operations, DuckDB QSO queries, and ADIF sync management.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Optional, List, Dict, Any
import concurrent.futures
from pathlib import Path
from radio_control import config

# Import required modules
from radio_control.adif_sync import get_adif_sync, init_adif_sync
from radio_control.adif_handler import ADIFHandler
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class ADIFService:
    """
    Service class for ADIF operations, DuckDB queries, and sync management.
    Encapsulates all ADIF-related functionality extracted from main.py.
    """

    def __init__(self):
        self.sync_manager = None
        self.sync_task: Optional[asyncio.Task] = None
        self.sync_status = {
            "syncing": False,
            "last_sync": None,
            "total_records": 0,
            "new_records_this_sync": 0,
            "records_skipped": 0,
            "next_sync_in": 0,
            "adif_file_path": None,
            "adif_file_size": 0,
            "adif_file_modified": None,
            "adif_qso_count": 0,
        }

    async def initialize(self):
        """Initialize the ADIF service"""
        try:
            self.sync_manager = init_adif_sync()
            logger.info("✅ ADIF DuckDB sync initialized")

            # Start periodic ADIF sync task (handles both initial and ongoing syncs)
            self.sync_task = asyncio.create_task(self.periodic_adif_sync())
            logger.info("✅ ADIF periodic sync task started (runs first immediately, then every 30 seconds)")
            return True
        except Exception as e:
            logger.error(f"❌ ADIF sync initialization failed: {e}")
            self.sync_manager = None
            return False

    async def shutdown(self):
        """Shutdown the ADIF service"""
        if self.sync_task and not self.sync_task.done():
            self.sync_task.cancel()
            try:
                await self.sync_task
            except asyncio.CancelledError:
                pass
        logger.info("✅ ADIF service shutdown complete")

    def count_adif_records(self, file_path: str) -> int:
        """Count the number of QSO records in an ADIF file"""
        try:
            if not Path(file_path).exists():
                return 0

            count = 0
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    # Count EOR (End Of Record) markers - each represents one QSO
                    if '<eor>' in line.lower():
                        count += 1
            return count
        except Exception as e:
            logger.error(f"❌ Error counting ADIF records: {str(e)}")
            return 0

    async def periodic_adif_sync(self):
        """Periodically sync ADIF file to DuckDB (every 30 seconds)"""
        logger.info("🔄 Starting periodic ADIF sync task (30 second interval)")

        loop = asyncio.get_event_loop()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        # Run sync immediately on startup (in background thread to not block event loop)
        logger.info("⏳ Running initial ADIF sync in background...")

        sync_interval = 30
        last_sync_time = 0

        while True:
            try:
                current_time = time.time()

                if self.sync_manager:
                    self.sync_status["syncing"] = True

                    # Update ADIF file info
                    adif_path = Path(self.sync_manager.adif_path)
                    if adif_path.exists():
                        self.sync_status["adif_file_path"] = str(adif_path)
                        self.sync_status["adif_file_size"] = adif_path.stat().st_size
                        self.sync_status["adif_file_modified"] = datetime.fromtimestamp(
                            adif_path.stat().st_mtime
                        ).isoformat()

                        # Count QSO records in ADIF file
                        self.sync_status["adif_qso_count"] = self.count_adif_records(str(adif_path))

                    # Run sync in thread pool to avoid blocking event loop
                    result = await loop.run_in_executor(executor, self.sync_manager.sync)

                    # Update sync status
                    self.sync_status["total_records"] = result.get('total_records', 0)
                    self.sync_status["new_records_this_sync"] = result.get('records_synced', 0)
                    self.sync_status["records_skipped"] = result.get('records_skipped', 0)
                    self.sync_status["last_sync"] = datetime.now().isoformat()

                    if result.get('synced', False):
                        if result.get('records_synced', 0) > 0:
                            logger.info(f"✅ ADIF sync: {result['records_synced']} new records, "
                                       f"total: {result.get('total_records', 0)}")
                    # Silent on unchanged file to reduce log noise

                self.sync_status["syncing"] = False
                last_sync_time = current_time

                # Calculate next sync time
                time_until_next = sync_interval - (time.time() - current_time)
                self.sync_status["next_sync_in"] = max(0, int(time_until_next))

                await asyncio.sleep(30.0)  # Wait 30 seconds before next sync

            except Exception as e:
                logger.error(f"❌ Periodic ADIF sync error: {str(e)}", exc_info=True)
                self.sync_status["syncing"] = False
                await asyncio.sleep(30.0)

    # === Sync Status ===

    def get_sync_status(self):
        """Get ADIF sync status"""
        return self.sync_status

    # === ADIF Operations ===

    async def trigger_sync(self):
        """Manually trigger ADIF to DuckDB sync"""
        if not self.sync_manager:
            raise HTTPException(status_code=503, detail="ADIF sync not initialized")

        try:
            result = self.sync_manager.sync()
            return result
        except Exception as e:
            logger.error(f"ADIF sync error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")

    async def get_stats(self):
        """Get ADIF database statistics"""
        if not self.sync_manager:
            raise HTTPException(status_code=503, detail="ADIF sync not initialized")

        try:
            stats = self.sync_manager.get_stats()
            return stats
        except Exception as e:
            logger.error(f"ADIF stats error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")

    async def get_all_qsos(self, limit: int = 100, offset: int = 0):
        """Get all QSOs from ADIF database with pagination"""
        if not self.sync_manager:
            raise HTTPException(status_code=503, detail="ADIF sync not initialized")

        try:
            qsos = self.sync_manager.get_all_qsos(limit=limit, offset=offset)
            return {"count": len(qsos), "qsos": qsos}
        except Exception as e:
            logger.error(f"ADIF query error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

    async def get_qsos_by_callsign(self, callsign: str, limit: int = None):
        """Get all QSOs for a specific callsign"""
        if not self.sync_manager:
            raise HTTPException(status_code=503, detail="ADIF sync not initialized")

        try:
            qsos = self.sync_manager.get_qsos_by_callsign(callsign, limit=limit)
            return {
                "callsign": callsign,
                "count": len(qsos),
                "qsos": qsos
            }
        except Exception as e:
            logger.error(f"ADIF callsign query error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

    async def get_qsos_by_band(self, band: str, limit: int = None):
        """Get all QSOs for a specific band"""
        if not self.sync_manager:
            raise HTTPException(status_code=503, detail="ADIF sync not initialized")

        try:
            qsos = self.sync_manager.get_qsos_by_band(band, limit=limit)
            return {
                "band": band,
                "count": len(qsos),
                "qsos": qsos
            }
        except Exception as e:
            logger.error(f"ADIF band query error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

    async def get_qsos_by_mode(self, mode: str, limit: int = None):
        """Get all QSOs for a specific mode"""
        if not self.sync_manager:
            raise HTTPException(status_code=503, detail="ADIF sync not initialized")

        try:
            qsos = self.sync_manager.get_qsos_by_mode(mode, limit=limit)
            return {
                "mode": mode,
                "count": len(qsos),
                "qsos": qsos
            }
        except Exception as e:
            logger.error(f"ADIF mode query error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

    async def get_qsos_by_date_range(self, start_date: str, end_date: str):
        """Get QSOs within a date range (format: YYYYMMDD)"""
        if not self.sync_manager:
            raise HTTPException(status_code=503, detail="ADIF sync not initialized")

        try:
            qsos = self.sync_manager.get_qsos_by_date_range(start_date, end_date)
            return {
                "start_date": start_date,
                "end_date": end_date,
                "count": len(qsos),
                "qsos": qsos
            }
        except Exception as e:
            logger.error(f"ADIF date range query error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

    async def check_worked_before(self, callsign: str, band: str = None, mode: str = None):
        """Check if a callsign was worked before (optionally on specific band/mode)"""
        if not self.sync_manager:
            raise HTTPException(status_code=503, detail="ADIF sync not initialized")

        try:
            worked = self.sync_manager.worked_before(callsign, band=band, mode=mode)
            return {
                "callsign": callsign,
                "band": band,
                "mode": mode,
                "worked_before": worked
            }
        except Exception as e:
            logger.error(f"ADIF worked-before check error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

    # === DuckDB Query Endpoints ===

    async def get_all_qsos_from_duckdb(self):
        """
        Get all QSOs from DuckDB database (most recent first)
        MUCH FASTER than ADIF parsing - returns ~40k records in milliseconds
        """
        try:
            import duckdb
            from pathlib import Path
            import time

            start_time = time.time()

            db_path = config.DATA_DIR / "qso_log.duckdb"

            if not db_path.exists():
                logger.error(f"❌ DuckDB file not found: {db_path}")
                return {'success': False, 'count': 0, 'data': [], 'error': 'Database not found'}

            # Connect and query (read-only for performance)
            conn = duckdb.connect(str(db_path), read_only=True)

            # Query all QSOs with required fields, ordered by date/time DESC (most recent first)
            query = """
                SELECT
                    COALESCE(call, '') as call,
                    COALESCE(qso_date, '') as qso_date,
                    COALESCE(time_on, '') as time_on,
                    COALESCE(mode, '') as mode,
                    COALESCE(frequency, 0) as frequency,
                    COALESCE(rst_sent, '') as rst_sent,
                    COALESCE(rst_rcvd, '') as rst_rcvd,
                    COALESCE(band, '') as band,
                    COALESCE(name, '') as name,
                    COALESCE(qth, '') as qth,
                    COALESCE(gridsquare, '') as gridsquare,
                    COALESCE(pota_ref, '') as pota_ref,
                    COALESCE(sota_ref, '') as sota_ref,
                    COALESCE(iota, '') as iota,
                    COALESCE(wwff_ref, '') as wwff_ref,
                    COALESCE(comment, '') as comment,
                    COALESCE(country, '') as country
                FROM qso_records
                ORDER BY qso_date DESC, time_on DESC
            """

            result = conn.execute(query).fetchall()

            # Convert tuples to dictionaries
            qsos = []
            for row in result:
                qsos.append({
                    'call': row[0],
                    'qso_date': row[1],
                    'time_on': row[2],
                    'mode': row[3],
                    'frequency': float(row[4]) if row[4] else 0,
                    'rst_sent': row[5],
                    'rst_rcvd': row[6],
                    'band': row[7],
                    'name': row[8],
                    'qth': row[9],
                    'gridsquare': row[10],
                    'pota_ref': row[11],
                    'sota_ref': row[12],
                    'iota': row[13],
                    'wwff_ref': row[14],
                    'comment': row[15],
                    'country': row[16]
                })

            conn.close()

            elapsed = time.time() - start_time
            logger.info(f"⚡ DuckDB query returned {len(qsos)} QSOs in {elapsed*1000:.2f}ms")

            return {
                'success': True,
                'count': len(qsos),
                'data': qsos,
                'query_time_ms': round(elapsed * 1000, 2),
                'source': 'duckdb'
            }

        except Exception as e:
            logger.error(f"❌ DuckDB query error: {str(e)}", exc_info=True)
            return {'success': False, 'count': 0, 'data': [], 'error': str(e)}

    async def get_qsos_by_call_duckdb(self, call: str = ""):
        """
        Get QSOs for a specific callsign from DuckDB database (most recent first)
        Used by "Prev QSO's" local log modal - replaces slow ADIF parsing

        Args:
            call: Callsign to filter by (case-insensitive)

        Returns:
            List of matching QSOs in same format as ADIF handler
        """
        try:
            import duckdb
            from pathlib import Path
            import time

            if not call or not call.strip():
                return {'success': True, 'count': 0, 'data': []}

            start_time = time.time()
            callsign = call.strip().upper()

            db_path = config.DATA_DIR / "qso_log.duckdb"

            if not db_path.exists():
                logger.error(f"❌ DuckDB file not found: {db_path}")
                return {'success': False, 'count': 0, 'data': [], 'error': 'Database not found'}

            # Connect and query (read-only for performance)
            conn = duckdb.connect(str(db_path), read_only=True)

            # Query for matching callsign, ordered by date/time DESC (most recent first)
            query = """
                SELECT
                    COALESCE(call, '') as call,
                    COALESCE(qso_date, '') as qso_date,
                    COALESCE(time_on, '') as time_on,
                    COALESCE(mode, '') as mode,
                    COALESCE(frequency, 0) as frequency,
                    COALESCE(rst_sent, '') as rst_sent,
                    COALESCE(rst_rcvd, '') as rst_rcvd,
                    COALESCE(band, '') as band,
                    COALESCE(name, '') as name,
                    COALESCE(qth, '') as qth,
                    COALESCE(gridsquare, '') as gridsquare,
                    COALESCE(pota_ref, '') as pota_ref,
                    COALESCE(sota_ref, '') as sota_ref,
                    COALESCE(iota, '') as iota,
                    COALESCE(wwff_ref, '') as wwff_ref,
                    COALESCE(comment, '') as comment,
                    COALESCE(country, '') as country,
                    COALESCE(lotw_qsl_rcvd, '') as lotw_qsl_rcvd
                FROM qso_records
                WHERE UPPER(call) = ?
                ORDER BY qso_date DESC, time_on DESC
            """

            result = conn.execute(query, [callsign]).fetchall()

            # Convert tuples to dictionaries matching ADIF handler format
            qsos = []
            for row in result:
                # Map lotw_qsl_rcvd to lotw_qsl (Y/N format)
                lotw_rcvd = row[17] if row[17] else ''
                lotw_qsl = 'Y' if str(lotw_rcvd).upper() in ('Y', 'YES', '1', 'TRUE') else ('N' if lotw_rcvd else '')

                qsos.append({
                    'call': row[0],
                    'qso_date': row[1],
                    'time_on': row[2],
                    'mode': row[3],
                    'frequency': float(row[4]) if row[4] else 0,
                    'rst_sent': row[5],
                    'rst_rcvd': row[6],
                    'band': row[7],
                    'name': row[8],
                    'qth': row[9],
                    'gridsquare': row[10],
                    'pota_ref': row[11],
                    'sota_ref': row[12],
                    'iota': row[13],
                    'wwff_ref': row[14],
                    'comment': row[15],
                    'country': row[16],
                    'lotw_qsl': lotw_qsl
                })

            conn.close()

            elapsed = time.time() - start_time
            logger.info(f"⚡ DuckDB query for {callsign} returned {len(qsos)} QSOs in {elapsed*1000:.2f}ms")

            return {
                'success': True,
                'count': len(qsos),
                'data': qsos,
                'query_time_ms': round(elapsed * 1000, 2),
                'callsign': callsign,
                'source': 'duckdb'
            }

        except Exception as e:
            logger.error(f"❌ DuckDB by-call query error: {str(e)}", exc_info=True)
            return {'success': False, 'count': 0, 'data': [], 'error': str(e)}


# Global service instance
_adif_service: Optional[ADIFService] = None


def get_adif_service() -> ADIFService:
    """Get the global ADIF service instance"""
    global _adif_service
    if _adif_service is None:
        _adif_service = ADIFService()
    return _adif_service


async def init_adif_service() -> bool:
    """Initialize the global ADIF service"""
    global _adif_service
    if _adif_service is None:
        _adif_service = ADIFService()
    return await _adif_service.initialize()


async def shutdown_adif_service():
    """Shutdown the global ADIF service"""
    global _adif_service
    if _adif_service:
        await _adif_service.shutdown()
        _adif_service = None
def register_adif_endpoints(app):
    """
    Register ADIF-related endpoints with the FastAPI app.
    This function can be called from main.py to register all ADIF endpoints.
    """

    # === ADIF DuckDB Query Endpoints ===

    @app.get("/api/adif/sync")
    async def trigger_adif_sync():
        """Manually trigger ADIF to DuckDB sync"""
        service = get_adif_service()
        return await service.trigger_sync()

    @app.get("/api/adif/stats")
    async def get_adif_stats():
        """Get ADIF database statistics"""
        service = get_adif_service()
        return await service.get_stats()

    @app.get("/api/adif/qsos")
    async def get_all_adif_qsos(limit: int = 100, offset: int = 0):
        """Get all QSOs from ADIF database with pagination"""
        service = get_adif_service()
        return await service.get_all_qsos(limit=limit, offset=offset)

    @app.get("/api/adif/callsign/{callsign}")
    async def get_adif_qsos_by_callsign(callsign: str, limit: int = None):
        """Get all QSOs for a specific callsign"""
        service = get_adif_service()
        return await service.get_qsos_by_callsign(callsign, limit=limit)

    @app.get("/api/adif/band/{band}")
    async def get_adif_qsos_by_band(band: str, limit: int = None):
        """Get all QSOs for a specific band"""
        service = get_adif_service()
        return await service.get_qsos_by_band(band, limit=limit)

    @app.get("/api/adif/mode/{mode}")
    async def get_adif_qsos_by_mode(mode: str, limit: int = None):
        """Get all QSOs for a specific mode"""
        service = get_adif_service()
        return await service.get_qsos_by_mode(mode, limit=limit)

    @app.get("/api/adif/date-range/{start_date}/{end_date}")
    async def get_adif_qsos_by_date_range(start_date: str, end_date: str):
        """Get QSOs within a date range (format: YYYYMMDD)"""
        service = get_adif_service()
        return await service.get_qsos_by_date_range(start_date, end_date)

    @app.get("/api/adif/worked-before/{callsign}")
    async def check_worked_before(callsign: str, band: str = None, mode: str = None):
        """Check if a callsign was worked before (optionally on specific band/mode)"""
        service = get_adif_service()
        return await service.check_worked_before(callsign, band=band, mode=mode)

    # === DuckDB Query Endpoints ===

    @app.get("/api/qsos/duckdb")
    async def get_all_qsos_from_duckdb():
        """
        Get all QSOs from DuckDB database (most recent first)
        MUCH FASTER than ADIF parsing - returns ~40k records in milliseconds
        """
        service = get_adif_service()
        return await service.get_all_qsos_from_duckdb()

    @app.get("/api/qsos/duckdb/by-call")
    async def get_qsos_by_call(call: str = ""):
        """
        Get QSOs for a specific callsign from DuckDB database (most recent first)
        Used by "Prev QSO's" local log modal - replaces slow ADIF parsing

        Args:
            call: Callsign to filter by (case-insensitive)

        Returns:
            List of matching QSOs in same format as ADIF handler
        """
        service = get_adif_service()
        return await service.get_qsos_by_call_duckdb(call)

    # === ADIF File Operations ===

    @app.get("/api/adif/count")
    async def get_adif_count():
        """Get number of QSOs in local ADIF file"""
        try:
            adif_handler = ADIFHandler()
            count = adif_handler.read_qso_count()
            return {'success': True, 'count': count}
        except Exception as e:
            logger.error(f"ADIF count error: {str(e)}")
            return {'success': False, 'count': 0}

    @app.get("/api/adif/all")
    async def get_all_local_qsos():
        """Get all QSOs from local ADIF file (most recent first)"""
        try:
            adif_handler = ADIFHandler()
            qsos = adif_handler.read_all_qsos()
            logger.info(f"📋 Returning {len(qsos)} QSOs from local ADIF log")
            return {'success': True, 'count': len(qsos), 'data': qsos}
        except Exception as e:
            logger.error(f"ADIF all QSOs error: {str(e)}")
            return {'success': False, 'count': 0, 'data': []}
