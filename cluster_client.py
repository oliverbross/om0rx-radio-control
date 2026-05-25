"""
DX Cluster Client - Async telnet connection to DX cluster
Multi-cluster support with automatic failover
"""
import asyncio
import logging
import re
from datetime import datetime, UTC
from collections import deque
from typing import Optional, Callable, List, Dict
import config

logger = logging.getLogger(__name__)

# DX spot regex pattern
DX_RE = re.compile(
    r"^DX de\s+(?P<spotter>\S+):\s+(?P<freq_khz>\d+\.\d+)\s+(?P<dxcall>[A-Z0-9/]+)\s*(?P<comment>.*)$",
    re.I
)


class ClusterClient:
    """Async DX Cluster (DXSpider/AR-Cluster) telnet client"""
    
    def __init__(self, host: str, port: int, callsign: str, password: str = ""):
        self.host = host
        self.port = port
        self.callsign = callsign
        self.password = password
        self.connected = False
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.on_spot_callback: Optional[Callable] = None
        self.recent_spots = deque(maxlen=5000)  # Deduplication
        
    def set_spot_callback(self, callback: Callable):
        """Set callback function to be called when a spot is received"""
        self.on_spot_callback = callback
        
    async def connect(self) -> bool:
        """Connect to DX cluster"""
        try:
            logger.info(f"Connecting to DX cluster {self.host}:{self.port} as {self.callsign}")
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            
            # Wait for prompt
            await asyncio.sleep(0.5)
            
            # Send callsign
            self.writer.write((self.callsign + "\r\n").encode())
            await self.writer.drain()
            
            # Send password if provided
            if self.password:
                await asyncio.sleep(0.2)
                self.writer.write((self.password + "\r\n").encode())
                await self.writer.drain()
            
            # Send login commands if configured
            if hasattr(config, 'LOGIN_SCRIPT'):
                for line in config.LOGIN_SCRIPT:
                    await asyncio.sleep(0.1)
                    self.writer.write((line + "\r\n").encode())
                    await self.writer.drain()
            
            # Read banner lines flexibly - stop if we timeout or get empty line
            banner_lines = getattr(config, 'BANNER_LOG_LINES', 10)
            for i in range(banner_lines):
                try:
                    line = await asyncio.wait_for(self.reader.readline(), timeout=1.0)
                    if not line:
                        break
                    text = line.decode(errors='ignore').strip()
                    logger.debug(f"Banner[{i}]: {text}")
                    # If we see the prompt, we're ready
                    if '>' in text or 'login:' in text.lower():
                        break
                except asyncio.TimeoutError:
                    # No more banner lines available
                    logger.debug(f"Banner reading complete after {i} lines (timeout)")
                    break
            
            self.connected = True
            logger.info("✅ DX cluster connected successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Cluster connection failed: {e}", exc_info=True)
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from cluster"""
        if self.writer:
            try:
                self.writer.close()
            except Exception:
                pass
        self.connected = False
        logger.info("Disconnected from DX cluster")
    
    def get_status(self) -> Dict:
        """Get current cluster connection status"""
        return {
            'connected': self.connected,
            'active_name': f"{self.host} (Primary)",
            'host': self.host,
            'port': self.port,
        }
    
    async def read_loop(self):
        """Main read loop - parses spots and calls callback"""
        if not self.reader:
            logger.error("Reader not initialized")
            return
        
        logger.info("Starting cluster read loop...")
        
        while self.connected:
            try:
                line = await self.reader.readline()
                if not line:
                    logger.warning("Cluster closed connection")
                    self.connected = False
                    break
                
                text = line.decode(errors='ignore').strip()
                if not text:
                    continue
                
                # Parse DX spot
                match = DX_RE.match(text)
                if not match:
                    continue
                
                # Extract spot data
                spotter = match.group('spotter')
                try:
                    freq_khz = float(match.group('freq_khz'))
                except ValueError:
                    continue
                
                dxcall = match.group('dxcall').upper()
                comment = match.group('comment') or ''
                
                # Deduplication (same call, freq within 0.1 kHz, same mode)
                dedup_key = (dxcall, round(freq_khz, 1))
                if dedup_key in self.recent_spots:
                    logger.debug(f"Duplicate spot filtered: {dxcall} @ {freq_khz}")
                    continue
                
                self.recent_spots.append(dedup_key)
                
                # Call callback with raw spot data
                if self.on_spot_callback:
                    # IMPORTANT: Store both string (for display precision) and float (for calculations)
                    freq_str = match.group('freq_khz')  # Original string from cluster: "14277.0"
                    spot_data = {
                        'spotter': spotter,
                        'freq_khz': freq_khz,             # Float kHz - for calculations
                        'freq_khz_str': freq_str,         # Original string - for display precision
                        'dxcall': dxcall,
                        'comment': comment,
                        'timestamp': datetime.now(UTC)
                    }
                    
                    try:
                        await self.on_spot_callback(spot_data)
                    except Exception as e:
                        logger.error(f"Spot callback error: {e}")
                
            except Exception as e:
                logger.error(f"Read loop error: {e}")
                await asyncio.sleep(1)
    
    async def run(self):
        """Connect and run read loop with auto-reconnect"""
        backoffs = getattr(config, 'RECONNECT_BACKOFF', [2, 5, 10, 20, 30, 60])
        backoff_idx = 0
        
        while True:
            try:
                if await self.connect():
                    backoff_idx = 0  # Reset backoff on successful connect
                    await self.read_loop()
                
                # Connection lost or failed
                if backoff_idx < len(backoffs):
                    delay = backoffs[backoff_idx]
                    backoff_idx += 1
                else:
                    delay = backoffs[-1]
                
                logger.info(f"Reconnecting to cluster in {delay}s...")
                await asyncio.sleep(delay)
                
            except Exception as e:
                logger.error(f"Cluster run error: {e}")
                await asyncio.sleep(5)


class ClusterManager:
    """
    Manages multiple DX Cluster connections with automatic failover.
    Provides a single interface similar to ClusterClient.
    """
    
    def __init__(self, clusters_config: List[Dict] = None):
        """
        Initialize cluster manager with multiple clusters
        
        Args:
            clusters_config: List of cluster configurations, each with:
                - enabled: bool - whether to use this cluster
                - host: str - hostname/IP
                - port: int - port number
                - user: str - login username
                - password: optional login password
                - use_as_failover: bool - whether to use as failover if primary fails
                - name: str - friendly name for logging
        """
        self.clusters_config = clusters_config or getattr(config, 'CLUSTERS', [])
        self.cluster_clients: List[ClusterClient] = []
        self.active_client: Optional[ClusterClient] = None
        self.connected = False
        self.on_spot_callback: Optional[Callable] = None
        self.current_cluster_idx = 0
        self.last_failed_idx = -1
        self.failover_attempts = 0
        self.max_failover_attempts = 3
        
        # Initialize all enabled cluster clients
        self._init_cluster_clients()
    
    def _init_cluster_clients(self):
        """Initialize ClusterClient instances for each enabled cluster"""
        self.cluster_clients = []
        
        for idx, cluster_cfg in enumerate(self.clusters_config):
            if cluster_cfg.get('enabled', False):
                client = ClusterClient(
                    host=cluster_cfg.get('host', 'localhost'),
                    port=cluster_cfg.get('port', 7373),
                    callsign=cluster_cfg.get('user', 'N0CALL'),
                    password=cluster_cfg.get('password', '')
                )
                self.cluster_clients.append({
                    'client': client,
                    'config': cluster_cfg,
                    'index': idx,
                    'status': 'disconnected'
                })
                logger.info(f"📡 Initialized cluster {idx+1}: {cluster_cfg.get('name', f'Cluster {idx+1}')}")
        
        if not self.cluster_clients:
            logger.warning("⚠️  No clusters are enabled in configuration")
    
    def set_spot_callback(self, callback: Callable):
        """Set callback function to be called when a spot is received"""
        self.on_spot_callback = callback
        
        # Set callback on all cluster clients
        for cluster_info in self.cluster_clients:
            cluster_info['client'].set_spot_callback(callback)
    
    async def _try_connect_cluster(self, cluster_info: Dict) -> bool:
        """Try to connect to a specific cluster"""
        try:
            client = cluster_info['client']
            cluster_cfg = cluster_info['config']
            
            logger.info(f"🔗 Attempting to connect to {cluster_cfg.get('name', 'cluster')}...")
            
            if await client.connect():
                self.active_client = client
                cluster_info['status'] = 'connected'
                self.connected = True
                self.current_cluster_idx = cluster_info['index']
                logger.info(f"✅ Connected to cluster: {cluster_cfg.get('name', 'cluster')}")
                return True
            else:
                cluster_info['status'] = 'failed'
                return False
        except Exception as e:
            logger.error(f"❌ Cluster connection error: {e}")
            cluster_info['status'] = 'failed'
            return False
    
    async def connect(self) -> bool:
        """Connect to primary cluster or failover cluster if primary is unavailable"""
        if not self.cluster_clients:
            logger.error("❌ No clusters configured")
            return False
        
        # Try primary cluster first (the one with enabled=True and use_as_failover=False)
        # If multiple primaries, use the first enabled one
        for cluster_info in self.cluster_clients:
            # Check if this is a primary cluster (use_as_failover=False)
            if not cluster_info['config'].get('use_as_failover', False):
                logger.info(f"🔌 Trying primary cluster: {cluster_info['config'].get('name', 'cluster')}")
                if await self._try_connect_cluster(cluster_info):
                    return True
                # Primary failed, continue to try failover clusters
                logger.warning(f"⚠️  Primary cluster failed, trying failover...")
                break
        
        # If primary failed or no primary defined, try failover clusters in order
        for cluster_info in self.cluster_clients:
            # Skip if already connected
            if cluster_info['status'] == 'connected':
                continue
            
            # Try failover clusters (use_as_failover=True)
            if cluster_info['config'].get('use_as_failover', False):
                logger.info(f"🔌 Trying failover cluster: {cluster_info['config'].get('name', 'cluster')}")
                if await self._try_connect_cluster(cluster_info):
                    logger.warning(f"⚠️  Using failover cluster: {cluster_info['config'].get('name', 'cluster')}")
                    return True
        
        logger.error("❌ All clusters failed to connect")
        self.connected = False
        return False
    
    def disconnect(self):
        """Disconnect all cluster clients"""
        for cluster_info in self.cluster_clients:
            cluster_info['client'].disconnect()
            cluster_info['status'] = 'disconnected'
        self.connected = False
        self.active_client = None
        logger.info("Disconnected from all clusters")
    
    async def read_loop(self):
        """Main read loop from active cluster"""
        if not self.active_client:
            logger.error("No active cluster client")
            return
        
        # Monitor the active client's read loop
        await self.active_client.read_loop()
        
        # When read_loop returns, connection was lost
        self.connected = False
        logger.warning("⚠️  Active cluster connection lost")
    
    async def run(self):
        """Connect and run read loop with auto-reconnect and failover"""
        backoffs = getattr(config, 'RECONNECT_BACKOFF', [2, 5, 10, 20, 30, 60])
        backoff_idx = 0
        connection_failures = 0
        
        while True:
            try:
                # Try to connect (will try primary first, then failovers)
                if await self.connect():
                    backoff_idx = 0  # Reset backoff on successful connect
                    connection_failures = 0  # Reset failure count
                    
                    try:
                        # Run the read loop for the active cluster
                        await self.read_loop()
                    except Exception as e:
                        logger.error(f"Read loop error: {e}")
                        self.connected = False
                
                # Connection lost or failed
                connection_failures += 1
                
                # Mark current cluster as failed and disconnect
                if self.active_client:
                    # Mark as failed first
                    for cluster_info in self.cluster_clients:
                        if cluster_info['client'] == self.active_client:
                            cluster_info['status'] = 'failed'
                            logger.warning(f"❌ Cluster {cluster_info['config'].get('name')} marked as failed")
                            break
                    
                    # Then disconnect and clear
                    self.active_client.disconnect()
                    self.active_client = None
                
                # If we haven't exhausted all clusters, try immediate failover
                available_clusters = sum(1 for c in self.cluster_clients if c['status'] != 'connected')
                if connection_failures <= len(self.cluster_clients):
                    logger.warning(f"🔄 Attempting failover (attempt {connection_failures}/{len(self.cluster_clients)})")
                    await asyncio.sleep(2)  # Brief delay before failover attempt
                    continue
                
                # All clusters exhausted, reset status and use backoff
                logger.warning("⚠️  All clusters failed, resetting status and retrying with backoff...")
                for cluster_info in self.cluster_clients:
                    cluster_info['status'] = 'disconnected'  # Reset for retry
                
                connection_failures = 0
                
                if backoff_idx < len(backoffs):
                    delay = backoffs[backoff_idx]
                    backoff_idx += 1
                else:
                    delay = backoffs[-1]
                
                logger.info(f"⏳ Reconnecting to clusters in {delay}s...")
                await asyncio.sleep(delay)
                
            except Exception as e:
                logger.error(f"Cluster manager error: {e}")
                await asyncio.sleep(5)
    
    def get_status(self) -> Dict:
        """Get current cluster status"""
        # Get active cluster info
        active_name = ''
        active_host = ''
        active_port = ''
        
        if self.active_client and self.current_cluster_idx < len(self.cluster_clients):
            active_config = self.cluster_clients[self.current_cluster_idx]['config']
            active_name = active_config.get('name', 'Unknown')
            active_host = active_config.get('host', '')
            active_port = active_config.get('port', '')
        
        return {
            'connected': self.connected,
            'active_name': active_name,  # For frontend compatibility
            'host': active_host,          # For frontend compatibility
            'port': active_port,          # For frontend compatibility
            'active_cluster': {
                'name': active_name,
                'host': active_host,
                'port': active_port
            } if self.active_client else None,
            'clusters': [
                {
                    'name': info['config'].get('name', f"Cluster {i+1}"),
                    'host': info['config'].get('host'),
                    'port': info['config'].get('port'),
                    'status': info['status'],
                    'is_primary': not info['config'].get('use_as_failover', True)
                }
                for i, info in enumerate(self.cluster_clients)
            ]
        }
