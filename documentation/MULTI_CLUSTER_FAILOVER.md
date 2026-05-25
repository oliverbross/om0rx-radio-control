# Multi-Cluster Failover Implementation

## Overview
The Wave-Flex-Spots application now supports **multiple DX cluster connections with automatic failover**. This allows you to define up to 5 clusters and have the system automatically switch to the next available cluster if the primary one becomes unavailable.

## Feature Highlights

### Key Capabilities
- **Up to 5 Clusters**: Configure up to 5 different DX clusters
- **Automatic Failover**: If the primary cluster fails to connect, the system automatically tries the next enabled cluster
- **Primary/Failover Toggle**: Easily designate one cluster as primary and others as failover
- **Enable/Disable**: Turn individual clusters on/off without removing their configuration
- **Per-Cluster Settings**: Each cluster can have its own:
  - Host/IP address
  - Port number
  - Login credentials (user/password)
  - Friendly name

### How It Works

1. **Startup**: The ClusterManager initializes all enabled clusters
2. **Primary Connection**: First, it attempts to connect to the configured primary cluster
3. **Failover**: If the primary fails, it automatically tries enabled failover clusters in order
4. **Fallback**: If all clusters fail, the system uses exponential backoff and retries

## Configuration

### Via Web UI
1. Click the **"⚙️ Config"** button in the header
2. Go to the **"Station & Cluster"** tab
3. You'll see 5 cluster configuration sections:
   - Each has an **Enable checkbox** to turn it on/off
   - **Host** and **Port** fields for the cluster address
   - **User** and **Password** for login credentials
   - **Primary Cluster** checkbox to set it as the primary (only one can be primary)
   - **Use as Failover** checkbox to enable failover attempts

### Via config.py

The configuration is stored in a `CLUSTERS` list:

```python
CLUSTERS = [
    {
        "enabled": True,
        "host": "localhost",
        "port": 7373,
        "user": "OM0RX-11",
        "password": "",
        "use_as_failover": False,  # Primary cluster
        "name": "Cluster 1 (Primary)"
    },
    {
        "enabled": True,
        "host": "dxc.ww2dx.club",
        "port": 7373,
        "user": "OM0RX-11",
        "password": "",
        "use_as_failover": True,   # Failover cluster
        "name": "Cluster 2 (WW2DX)"
    },
    # ... up to 5 clusters total
]
```

## Architecture Changes

### Backend Changes

#### 1. **ClusterManager** (new class in `cluster_client.py`)
- Manages multiple ClusterClient instances
- Handles failover logic
- Provides unified interface compatible with existing code
- Tracks connection status for each cluster

#### 2. **Updated `backend/main.py`**
- Initializes ClusterManager instead of single ClusterClient
- Falls back to ClusterClient if CLUSTERS config is not available
- All existing cluster monitoring code works unchanged

#### 3. **Updated `config.py`**
- New `CLUSTERS` list with up to 5 cluster definitions
- Backward compatible: legacy `CLUSTER_HOST`, `CLUSTER_PORT` etc. still present

### Frontend Changes

#### 1. **Configuration Modal** (`frontend/templates/modal-config.html`)
- New multi-cluster UI in "Station & Cluster" tab
- Visual cluster cards showing enabled/disabled status
- Grid layout for efficient space usage
- Help text explaining failover behavior

#### 2. **Vue Methods** (`frontend/js/app-main.js`)
- `toggleClusterPrimary(idx)`: Set a cluster as primary
- Loads/saves `CLUSTERS` configuration from backend

## Usage Scenarios

### Scenario 1: Simple Failover
```
Primary:  localhost:7373 (OM0RX-11)
Failover: dxc.ww2dx.club:7373 (OM0RX-11)
Failover: ar-cluster.de:7373 (OM0RX-11)
```
If your local cluster goes down, the system automatically connects to WW2DX, then to AR-Cluster if needed.

### Scenario 2: Redundancy Setup
```
Primary:  Main cluster in your country
Failover: Backup cluster in your region
Failover: International cluster (always active)
Failover: Regional cluster
Failover: Spare cluster (emergency only)
```

### Scenario 3: Testing
```
Primary:  Test cluster (localhost)
Failover: Production cluster (dxc.ww2dx.club)
```
Test locally first, automatically fall back to production if needed.

## Connection Status

The ClusterManager tracks connection status with the `get_status()` method:

```javascript
{
  "connected": true/false,
  "active_cluster": {
    "name": "Cluster 1 (Primary)",
    "host": "localhost"
  },
  "clusters": [
    {
      "name": "Cluster 1 (Primary)",
      "host": "localhost",
      "port": 7373,
      "status": "connected|failed|disconnected",
      "is_primary": true/false
    },
    // ... other clusters
  ]
}
```

## Logging

The system provides detailed logging for cluster operations:

```
📡 Initialized cluster 1: Cluster 1 (Primary)
📡 Initialized cluster 2: Cluster 2 (Failover)
🔗 Attempting to connect to Cluster 1 (Primary)...
✅ Connected to cluster: Cluster 1 (Primary)
🔗 Cluster status: ✅ Connected
```

On failover:
```
Read loop error: Connection lost
🔄 Trying failover clusters...
🔗 Attempting to connect to Cluster 2 (Failover)...
✅ Connected to cluster: Cluster 2 (Failover)
⚠️  Using failover cluster: Cluster 2 (Failover)
```

## Key Differences from Original Implementation

| Feature | Original | Multi-Cluster |
|---------|----------|----------------|
| Clusters Supported | 1 | Up to 5 |
| Failover | Manual restart | Automatic |
| Config Format | Simple variables | List structure |
| UI | Single cluster config | Multi-cluster cards |
| Status Tracking | Simple connected flag | Per-cluster status |

## Migration from Single Cluster

If you're upgrading from a single cluster setup:

1. Your existing `CLUSTER_HOST`, `CLUSTER_PORT`, etc. are preserved
2. The backend automatically creates the new `CLUSTERS` config on next startup
3. Your primary cluster settings are used as the first cluster
4. You can customize additional clusters via the UI

## Backward Compatibility

- The old `CLUSTER_HOST`, `CLUSTER_PORT`, `CLUSTER_USER`, `CLUSTER_PASS` config variables are maintained
- If `CLUSTERS` is not defined, the system attempts to use the old single-cluster configuration
- Existing code that references `cluster_client` continues to work

## Performance Considerations

- **Connection Timeout**: Each cluster connection attempt has a 1-second timeout per banner line (max 10 lines)
- **Failover Delay**: 2-second delay between failover attempts to avoid rapid connection cycling
- **Backoff Strategy**: Uses exponential backoff [2s, 5s, 10s, 20s, 30s, 60s] after all clusters fail
- **Memory**: Minimal overhead - one ClusterClient instance per enabled cluster

## Troubleshooting

### All clusters fail to connect
1. Check that at least one cluster is enabled in config
2. Verify host/port are correct
3. Check network connectivity
4. Review logs for specific error messages

### Failover not working
1. Ensure multiple clusters are enabled
2. Check that failover clusters have `use_as_failover: true`
3. Verify credentials are correct for failover clusters
4. Check logs for connection errors

### Performance issues
1. Reduce number of enabled clusters if not needed
2. Verify network connectivity is stable
3. Check for DNS resolution delays (use IP instead of hostname)

## Future Enhancements

Potential improvements for future versions:
- Weighted failover (prefer certain clusters)
- Health checks between clusters
- Cluster status dashboard
- Per-cluster statistics and monitoring
- Geographic cluster selection
- Cluster load balancing

## Files Modified

- `config.py` - Added CLUSTERS configuration list
- `cluster_client.py` - Added ClusterManager class
- `backend/main.py` - Updated to use ClusterManager
- `frontend/templates/modal-config.html` - Multi-cluster UI
- `frontend/js/app-main.js` - Configuration handling

---

**Implementation Date**: November 2024  
**Status**: Production Ready  
**Version**: 1.0