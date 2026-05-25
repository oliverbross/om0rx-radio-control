"""
Wavelog Sync Manager
Handles automatic syncing of Wavelog data every 5 minutes
"""

import asyncio
import logging
import aiohttp
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from radio_control import config
from radio_control.wavelog_db import get_wavelog_db

logger = logging.getLogger(__name__)

# Thread pool for blocking database operations
_thread_pool = ThreadPoolExecutor(max_workers=1)


class WavelogSyncManager:
    """Manages automatic sync of Wavelog data to local database"""
    
    def __init__(self, api_url: str, api_key: str, station_id: str):
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.station_id = station_id
        self.db = get_wavelog_db()
        self._sync_task = None
        self._is_syncing = False
    
    async def start(self):
        """Start the background sync task"""
        if self._sync_task is None or self._sync_task.done():
            logger.info("🔄 Starting Wavelog sync manager (5-minute intervals)")
            self._sync_task = asyncio.create_task(self._sync_loop())
    
    async def stop(self):
        """Stop the background sync task"""
        if self._sync_task and not self._sync_task.done():
            logger.info("⏹️ Stopping Wavelog sync manager")
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
    
    async def _process_adif_reverse(self, adif_string: str) -> int:
        """
        Process ADIF records in REVERSE order (newest first).
        Stops inserting when we hit a duplicate (record already in DB).
        This handles the fact that the Wavelog API returns records oldest-first.
        
        Args:
            adif_string: Raw ADIF formatted string
        
        Returns:
            Number of NEW QSOs inserted (stops at first duplicate)
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_thread_pool, self._process_adif_reverse_sync, adif_string)
    
    def _process_adif_reverse_sync(self, adif_string: str) -> int:
        """
        Synchronous ADIF reverse processing (runs in thread pool).
        Process records from NEWEST to OLDEST, stopping at first duplicate.
        """
        try:
            import re
            
            # Split ADIF into individual records
            records = re.split(r'<(?:eor|eoh)>\s*', adif_string, flags=re.IGNORECASE)
            
            # Remove empty records and header
            valid_records = []
            for record in records:
                record = record.strip()
                if record and not record.startswith('Wavelog ADIF'):  # Skip header
                    valid_records.append(record)
            
            # REVERSE the list so we process NEWEST records first
            # The API returns oldest-first, so reversing gives us newest-first
            valid_records.reverse()
            
            qsos_inserted = 0
            
            for record in valid_records:
                # Parse fields from this record
                fields = self.db._parse_adif_fields(record)
                
                if fields:
                    # Try to insert; if it already exists (duplicate), stop processing
                    # We use a modified insert that returns 'duplicate' if the record exists
                    result = self._try_insert_qso(record, fields)
                    
                    if result == 'duplicate':
                        # We've reached old records we've already synced
                        logger.debug(f"  Reached duplicate record ({fields.get('callsign', '?')}), stopping delta sync")
                        break
                    elif result == 'inserted':
                        qsos_inserted += 1
                        # Log every 100 inserts for visibility
                        if qsos_inserted % 100 == 0:
                            logger.debug(f"  ... inserted {qsos_inserted} new QSOs so far")
            
            return qsos_inserted
        
        except Exception as e:
            logger.error(f"Error processing ADIF reverse: {str(e)}")
            return 0
    
    def _try_insert_qso(self, adif_record: str, fields: Dict[str, str]) -> str:
        """
        Try to insert a QSO record.
        Returns: 'inserted', 'duplicate', or 'error'
        """
        try:
            # Check if record already exists (by callsign, date, time)
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id FROM qsos 
                    WHERE callsign = ? AND qso_date = ? AND time_on = ?
                    LIMIT 1
                """, (
                    fields.get('callsign', ''),
                    fields.get('qso_date', ''),
                    fields.get('time_on', '')
                ))
                
                if cursor.fetchone():
                    # Record already exists
                    return 'duplicate'
        
        except Exception as e:
            logger.warning(f"Error checking for duplicate: {str(e)}")
        
        # Try to insert the new record
        try:
            if self.db.insert_qso(adif_record, fields):
                return 'inserted'
            else:
                return 'error'
        except Exception as e:
            logger.warning(f"Error inserting QSO: {str(e)}")
            return 'error'
    
    async def _sync_loop(self):
        """Main sync loop that runs every 5 minutes"""
        # Check if we need a full sync (empty database)
        status = self.db.get_sync_status()
        if status.get('total_qsos', 0) == 0:
            logger.info("📥 Database is empty, starting full Wavelog sync...")
            await self.full_sync()
        else:
            logger.info(f"📥 Database has {status.get('total_qsos', 0)} QSOs, skipping full sync (will use delta sync)")
        
        # Run delta syncs every 1 minute (was 5 minutes - made more frequent for "almost on the fly" syncing)
        while True:
            try:
                await asyncio.sleep(60)  # 1 minute (changed from 5 minutes)
                logger.info("🔄 Running scheduled delta sync...")
                await self.delta_sync()
            except asyncio.CancelledError:
                logger.debug("Sync loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in sync loop: {str(e)}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying
    
    async def full_sync(self) -> bool:
        """
        Perform a full sync of all Wavelog QSOs.
        Downloads ALL ADIF data in batches (pagination) and stores in local database.
        """
        if self._is_syncing:
            logger.debug("Sync already in progress, skipping")
            return False
        
        self._is_syncing = True
        try:
            logger.info("📥 Starting full Wavelog sync (with pagination for all QSOs)...")
            
            endpoint = f"{self.api_url}/api/get_contacts_adif"
            total_qsos_inserted = 0
            fetch_from_id = 0
            batch_num = 0
            
            async with aiohttp.ClientSession() as session:
                while True:
                    batch_num += 1
                    logger.debug(f"  Fetching batch {batch_num} from ID {fetch_from_id}...")
                    
                    payload = {
                        'key': self.api_key,
                        'station_id': self.station_id,
                        'fetchfromid': fetch_from_id  # Pagination: start from last ID
                    }
                    
                    try:
                        async with session.post(
                            endpoint,
                            json=payload,
                            timeout=aiohttp.ClientTimeout(total=60),
                            headers={'Content-Type': 'application/json', 'Accept': 'application/json'}
                        ) as resp:
                            if resp.status == 200:
                                result = await resp.json()
                                adif_string = result.get('adif')
                                
                                if adif_string and len(adif_string.strip()) > 0:
                                    # Parse and insert QSOs (runs in thread pool)
                                    qsos_in_batch = await self._process_adif(adif_string)
                                    total_qsos_inserted += qsos_in_batch
                                    
                                    logger.debug(f"  ✓ Batch {batch_num}: {qsos_in_batch} QSOs processed")
                                    
                                    # Check if we got a partial response (means there's more data)
                                    # If batch returned 0 records, we're done
                                    if qsos_in_batch == 0:
                                        logger.debug("  Batch returned 0 records - sync complete")
                                        break
                                    
                                    # Update fetch_from_id for next batch
                                    # The API likely expects the next ID after the last one we processed
                                    fetch_from_id += qsos_in_batch
                                else:
                                    # No ADIF data in this batch - we've reached the end
                                    logger.debug("  No ADIF data in batch response - sync complete")
                                    break
                            else:
                                error_text = await resp.text()
                                logger.warning(f"Batch {batch_num} API error ({resp.status}): {error_text[:200]}")
                                if batch_num == 1:
                                    # First batch failed completely
                                    logger.error("❌ First sync batch failed, aborting")
                                    return False
                                else:
                                    # Subsequent batches failed, but we got some data
                                    logger.info(f"Stopping pagination at batch {batch_num}, got {total_qsos_inserted} total QSOs")
                                    break
                    
                    except asyncio.TimeoutError:
                        logger.warning(f"Batch {batch_num} timeout")
                        if batch_num == 1:
                            logger.error("❌ First sync batch timed out")
                            return False
                        else:
                            logger.info(f"Pagination timeout at batch {batch_num}, got {total_qsos_inserted} total QSOs")
                            break
                    except Exception as e:
                        logger.warning(f"Batch {batch_num} error: {str(e)}")
                        if batch_num == 1:
                            logger.error(f"❌ First sync batch failed: {str(e)}")
                            return False
                        else:
                            logger.info(f"Pagination stopped at batch {batch_num}, got {total_qsos_inserted} total QSOs")
                            break
            
            # Update sync status after all batches
            self.db.update_sync_status('full')
            status = self.db.get_sync_status()
            
            logger.info(
                f"✅ Full sync complete: {total_qsos_inserted} QSOs processed "
                f"(in {batch_num} batches), total in DB: {status['total_qsos']}"
            )
            return True
        
        except Exception as e:
            logger.error(f"❌ Wavelog sync error: {str(e)}")
            return False
        finally:
            self._is_syncing = False
    
    async def delta_sync(self) -> bool:
        """
        Perform a delta sync to get new/updated QSOs.
        The Wavelog API returns records in OLDEST-first order (oldest records first).
        We reverse the order to process NEWEST records first, stopping when we hit duplicates.
        """
        if self._is_syncing:
            logger.debug("Sync already in progress, skipping delta")
            return False
        
        self._is_syncing = True
        try:
            logger.debug("🔄 Starting delta Wavelog sync (processing newest records first)...")
            
            endpoint = f"{self.api_url}/api/get_contacts_adif"
            
            # Always fetch from ID 0 to get all available records (API returns oldest first, limited to 20000)
            payload = {
                'key': self.api_key,
                'station_id': self.station_id,
                'fetchfromid': 0  # Always start from beginning - API has limited window anyway
            }
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        endpoint,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=60),
                        headers={'Content-Type': 'application/json', 'Accept': 'application/json'}
                    ) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            adif_string = result.get('adif')
                            
                            if adif_string and len(adif_string.strip()) > 0:
                                # Parse ADIF in REVERSE order (newest first)
                                # This is critical because the API returns oldest records first!
                                qsos_processed = await self._process_adif_reverse(adif_string)
                                
                                logger.info(f"✅ Delta sync complete: {qsos_processed} new QSOs found and inserted")
                                
                                # Update sync status
                                self.db.update_sync_status('delta')
                                status = self.db.get_sync_status()
                                logger.info(f"   Total QSOs in database: {status['total_qsos']}")
                                
                                return True
                            else:
                                logger.debug("  No ADIF data in API response")
                                return False
                        else:
                            error_text = await resp.text()
                            logger.error(f"❌ API error ({resp.status}): {error_text[:200]}")
                            return False
            
            except asyncio.TimeoutError:
                logger.error("❌ Delta sync timeout")
                return False
            except Exception as e:
                logger.error(f"❌ Delta sync error: {str(e)}")
                return False
        
        except Exception as e:
            logger.error(f"Delta sync error: {str(e)}")
            return False
        finally:
            self._is_syncing = False
    
    def _process_adif_sync(self, adif_string: str) -> int:
        """
        Synchronous ADIF processing (runs in thread pool).
        This does the heavy database work without blocking the event loop.
        
        Args:
            adif_string: Raw ADIF formatted string
        
        Returns:
            Number of QSOs processed
        """
        try:
            import re
            
            # Split ADIF into individual records (split by <eor> or <eoh>)
            # Handle case-insensitive matching
            records = re.split(r'<(?:eor|eoh)>\s*', adif_string, flags=re.IGNORECASE)
            
            qsos_processed = 0
            
            for record in records:
                record = record.strip()
                if not record:
                    continue
                
                # Parse fields from this record
                fields = self.db._parse_adif_fields(record)
                
                if fields:
                    if self.db.insert_qso(record, fields):
                        qsos_processed += 1
            
            return qsos_processed
        
        except Exception as e:
            logger.error(f"Error processing ADIF: {str(e)}")
            return 0
    
    async def _process_adif(self, adif_string: str) -> int:
        """
        Async wrapper for ADIF processing.
        Runs the heavy database work in a thread pool to avoid blocking the event loop.
        
        Args:
            adif_string: Raw ADIF formatted string
        
        Returns:
            Number of QSOs processed
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_thread_pool, self._process_adif_sync, adif_string)


# Global sync manager instance
_sync_manager = None


async def get_wavelog_sync_manager() -> WavelogSyncManager:
    """Get or create the Wavelog sync manager"""
    global _sync_manager
    if _sync_manager is None:
        _sync_manager = WavelogSyncManager(
            config.WAVELOG_API_URL,
            config.WAVELOG_API_KEY,
            config.WAVELOG_STATION_ID
        )
    return _sync_manager


async def start_wavelog_sync():
    """Start the Wavelog sync manager"""
    try:
        manager = await get_wavelog_sync_manager()
        await manager.start()
        logger.info("✅ Wavelog sync manager started")
    except Exception as e:
        logger.error(f"Failed to start Wavelog sync manager: {str(e)}")


async def stop_wavelog_sync():
    """Stop the Wavelog sync manager"""
    global _sync_manager
    if _sync_manager:
        await _sync_manager.stop()
        logger.info("✅ Wavelog sync manager stopped")