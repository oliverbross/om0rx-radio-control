# Multi-Cluster Failover - Quick Start Guide

## 30-Second Setup

### Step 1: Open Configuration
Click the **⚙️ Config** button in the header

### Step 2: Go to Station & Cluster Tab
You'll see 5 cluster configuration sections

### Step 3: Configure Your Clusters

**Example Setup:**
```
✅ CLUSTER 1 (PRIMARY)
   Host: localhost
   Port: 7373
   User: OM0RX-11
   Password: (leave blank)
   [✓] Primary Cluster
   [ ] Use as Failover

✅ CLUSTER 2 (FAILOVER)
   Host: dxc.ww2dx.club
   Port: 7373
   User: OM0RX-11
   Password: (leave blank)
   [ ] Primary Cluster
   [✓] Use as Failover

⬜ CLUSTER 3-5 (DISABLED)
   [Leave as disabled for now]
```

### Step 4: Save Configuration
Click **"Save Configuration"** button

### Step 5: Done! ✅
Your system now has automatic failover protection!

---

## Common Configurations

### Minimal Setup (Basic Failover)
```
Cluster 1: Your local DX cluster (Primary)
Cluster 2: WW2DX or similar (Failover)
Cluster 3-5: Disabled
```

### Redundant Setup (Maximum Protection)
```
Cluster 1: Primary DX cluster
Cluster 2: Backup in same region
Cluster 3: National backup cluster
Cluster 4: International cluster
Cluster 5: Emergency backup
```

### Testing Setup
```
Cluster 1: Local test cluster (Primary)
Cluster 2: Production cluster (Failover)
Cluster 3-5: Disabled
```

---

## How to Use

### Setting a Cluster as Primary
1. Find the cluster you want to be primary
2. Check the **"Primary Cluster"** checkbox
3. This automatically unchecks all other primary checkboxes
4. Save configuration

### Enabling/Disabling Clusters
1. Check the main checkbox next to cluster name to **Enable**
2. Uncheck to **Disable**
3. Disabled clusters won't be tried even if others fail
4. Save configuration

### Testing Failover
1. Stop your primary cluster
2. Watch the logs in the browser console (F12 → Console tab)
3. You should see failover messages like:
   ```
   🔄 Attempting failover to next cluster
   ✅ Connected to cluster: Cluster 2 (Failover)
   ⚠️ Using failover cluster: Cluster 2 (Failover)
   ```

---

## Finding Popular Cluster Addresses

### World-Wide
- **WW2DX**: `dxc.ww2dx.club:7373` (USA)
- **N0AR**: `ar-cluster.de:7373` (Germany)
- **RBN**: Various locations

### Europe
- **AR-Cluster**: `ar-cluster.de:7373`
- **M0DXE**: Various UK clusters
- **EA**: Spanish clusters

### Americas
- **K4**: Various US clusters
- **VE**: Canadian clusters

*Note: Check your local DX cluster documentation for current addresses*

---

## Checking Cluster Status

### Via Web Browser Console
Open Developer Tools (F12) and look at the Network tab or Console:

```javascript
// Successful connection
✅ Connected to cluster: Cluster 1 (Primary)

// Failover activated
⚠️ Using failover cluster: Cluster 2 (Failover)

// Connection lost
❌ Cluster connection failed
```

### Via Backend Logs
Check the application logs (if running with debug logging):
```
INFO: ✅ Cluster client started
INFO: 🔗 Cluster status: ✅ Connected
INFO: 🔄 Trying failover clusters...
```

---

## Troubleshooting

### "Connection Failed" Messages
**Problem**: Can't connect to any cluster
**Solution**:
1. Check internet connectivity
2. Verify host/port are correct (try with telnet)
3. Verify username/password are correct
4. Check firewall isn't blocking port 7373

### Failover Not Working
**Problem**: System doesn't switch to failover cluster
**Solution**:
1. Verify failover cluster is **Enabled**
2. Verify **"Use as Failover"** checkbox is checked
3. Verify failover cluster credentials are correct
4. Manually stop primary cluster to test failover

### All Clusters Disabled
**Problem**: See "No clusters are enabled in configuration"
**Solution**:
1. Open Configuration
2. Check at least one cluster's Enable checkbox
3. Save configuration

### Cluster Connects Then Disconnects
**Problem**: Can't stay connected
**Solution**:
1. Check cluster login credentials
2. Look for rate limiting or connection limits
3. Verify network is stable
4. Check cluster isn't full or experiencing issues

---

## Advanced Tips

### Using Different Credentials Per Cluster
Some clusters require different credentials:
```
Cluster 1: User: OM0RX-11
Cluster 2: User: OM0RX@WW2DX (different cluster login)
```

### Geographic Failover
```
Cluster 1: Local cluster (Primary)
Cluster 2: Regional cluster 500km away
Cluster 3: National cluster 1000km away
Cluster 4: European cluster 2000km away
```

### Testing in Production
```
Cluster 1: Test/Development (Primary)
Cluster 2: Live production (Failover)
```
This lets you test new configurations without affecting production.

---

## What Happens During Failover

1. **Detection**: Primary cluster connection drops
2. **Notification**: System detects disconnection
3. **Attempt**: Tries to reconnect to primary
4. **Backoff**: Waits 2-5 seconds
5. **Failover**: Tries next enabled failover cluster
6. **Success**: Connects to failover cluster
7. **Notification**: Spot reception resumes from failover cluster

**Total Time**: Usually 5-15 seconds from primary failure to failover connection

---

## Best Practices

✅ **DO:**
- Keep at least one backup cluster enabled
- Use cluster addresses from reliable sources
- Test your failover setup periodically
- Document which clusters you're using (comment in config)
- Monitor connection status in logs

❌ **DON'T:**
- Enable too many clusters (causes slower failover)
- Use clusters without permission
- Change cluster configs while running
- Forget to save configuration changes
- Leave old cluster configs in place if you're not using them

---

## Questions?

For more detailed information, see `MULTI_CLUSTER_FAILOVER.md`

---

**Quick Reference**:
- 📡 Configure up to 5 clusters
- 🔄 Automatic failover between clusters
- 💾 Changes saved to config.py
- 🔌 No application restart needed
- ✅ Easy enable/disable toggle