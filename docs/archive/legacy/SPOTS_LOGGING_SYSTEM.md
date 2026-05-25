# DX Spots Logging System

## Overview

The DX Spots Logging System provides persistent, comprehensive logging of all incoming DX cluster spots to a DuckDB file-based database. This ensures no spots are lost when the application is reloaded and enables detailed statistical analysis.

## Database Schema

All spots are logged to `/data/spots.duckdb` with the following comprehensive schema:

### Core Fields
- **id** (BIGINT): Auto-incrementing unique identifier
- **received_at** (TIMESTAMP WITH TIME ZONE): Exact time spot was received from cluster
- **date_utc** (DATE): Date component (for easy daily queries)
- **time_utc** (TIME): Time component (for easy hourly queries)

### Spot Data
- **frequency_khz** (DOUBLE): Frequency in kHz
- **callsign** (VARCHAR): DX station callsign (uppercase)
- **spotter** (VARCHAR): Who spotted it (DX DE callsign)
- **comment** (VARCHAR): Original cluster comment (cleaned)

### Derived Fields (Auto-Computed)
- **band** (VARCHAR): Band name (160m, 80m, 40m, 20m, etc.) - auto-detected from frequency
- **mode** (VARCHAR): Operating mode (FT8, SSB, CW, RTTY, etc.) - inferred from comment & frequency
- **country** (VARCHAR): Spotted station's country name
- **zone_cq** (INTEGER): CQ Zone
- **zone_itu** (INTEGER): ITU Zone
- **continent** (VARCHAR): Continent (NA, EU, AS, etc.)
- **special_tags** (VARCHAR): Special event indicators (POTA, SOTA, IOTA, etc.) - extracted from comment

### Metadata
- **created_at** (TIMESTAMP WITH TIME ZONE): When record was inserted

## Database Indexes

Optimized for common queries:
- `idx_spot_received` - Recent spots queries
- `idx_spot_date` - Daily statistics
- `idx_spot_band` - Band filtering
- `idx_spot_mode` - Mode filtering
- `idx_spot_callsign` - Call history
- `idx_spot_spotter` - Spotter history
- `idx_spot_country` - Country statistics
- `idx_spot_frequency` - Frequency range queries
- `idx_spot_band_mode` - Combined band+mode queries
- `idx_spot_date_band` - Daily band statistics

## Integration Points

### Automatic Logging
Spots are automatically logged when received from the cluster:

```python
# In backend/main.py process_cluster_spot()
log_spot(spot_data)  # Logs immediately when spot received
```

### API Endpoints

#### `/api/spots/count?date=YYYY-MM-DD`
Get total number of logged spots
- **Parameters**: `date` (optional) - Filter by specific date
- **Returns**: Total count

#### `/api/spots/stats/band?date=YYYY-MM-DD`
Statistics grouped by band
- **Returns**: Band stats (total spots, unique calls, spotters, countries, frequency range)

#### `/api/spots/stats/mode?date=YYYY-MM-DD`
Statistics grouped by operating mode
- **Returns**: Mode stats (total spots, unique calls, countries)

#### `/api/spots/stats/country?limit=20&date=YYYY-MM-DD`
Top countries by spot count
- **Parameters**: 
  - `limit` (default: 20) - Number of top countries to return
  - `date` (optional) - Filter by date
- **Returns**: Country stats with spot counts and frequency ranges

#### `/api/spots/recent?limit=100`
Get most recent spots
- **Parameters**: `limit` (default: 100)
- **Returns**: Recent spot data

#### `/api/spots/callsign/{callsign}?limit=100`
Get all spots for a specific callsign
- **Returns**: All spots for that callsign

#### `/api/spots/special?limit=100`
Get spots with special event tags (POTA, SOTA, IOTA, etc.)
- **Returns**: Spots with special tags

#### `/api/spots/export/csv?date=YYYY-MM-DD`
Export spots to CSV file
- **Returns**: Path to generated CSV file and count

## Python API

### Basic Usage

```python
from spots_logger import get_spots_logger

# Get the logger instance
logger = get_spots_logger()

# Log a spot
spot_data = {
    'spotter': 'N0XYZ',
    'freq_khz': 14277.5,
    'freq_khz_str': '14277.5',
    'dxcall': 'JA1XYZ',
    'comment': 'FT8 POTA K-1234',
    'timestamp': datetime.now(UTC)
}
logger.log_spot(spot_data)

# Get statistics
band_stats = logger.get_stats_by_band()
mode_stats = logger.get_stats_by_mode()
country_stats = logger.get_stats_by_country(limit=20)

# Get recent spots
recent = logger.get_recent_spots(limit=100)

# Get spots by callsign
ja_spots = logger.get_spots_by_callsign('JA1XYZ')

# Get special event spots
pota_spots = logger.get_special_event_spots()

# Export to CSV
logger.export_csv('/path/to/export.csv')
```

### Convenience Function

```python
from spots_logger import log_spot

# Quick logging of a single spot
log_spot(spot_data)
```

## Data Flow

```
Cluster Connection
       ↓
cluster_client.py (receives raw spot)
       ↓
process_cluster_spot() in backend/main.py
       ↓
log_spot() → spots_logger.py
       ↓
DuckDB spots.duckdb
       ↓
API endpoints for querying stats
```

## Example Queries

### All spots from today
```python
from datetime import date
logger.get_stats_by_band(date.today().isoformat())
```

### Top countries today
```python
logger.get_stats_by_country(limit=10, date=date.today().isoformat())
```

### All FT8 activity
```python
logger.get_special_event_spots()  # Gets POTA/SOTA/IOTA
```

### Spot history for a station
```python
logger.get_spots_by_callsign('W1AW')
```

## Database Files

- **Main Database**: `/data/spots.duckdb`
- **Exports**: `/data/spots_export_YYYYMMDD_HHMMSS.csv`

## Performance Considerations

- **Automatic Indexes**: Database creates indexes on common query patterns
- **Fast Lookups**: Country/zone data retrieved from CTY resolver at log time
- **Deduplication**: Cluster client already deduplicates spots before logging
- **Efficient Storage**: DuckDB provides column-oriented storage for analytics

## Features

✅ **Persistent Storage**: Spots logged to disk survive app reloads
✅ **Comprehensive Data**: All cluster details plus computed band/mode/country
✅ **Special Events**: Extracts POTA, SOTA, IOTA, and other special tags
✅ **Rich Statistics**: Pre-computed stats by band, mode, country, date
✅ **CSV Export**: Export data for external analysis
✅ **Flexible Queries**: Query by date, band, mode, country, callsign
✅ **Performance**: Optimized indexes for fast queries
✅ **API Access**: RESTful API endpoints for web/mobile integration

## Maintenance

### Database Cleanup
The database grows continuously. For long-term archival:

```python
# Export old data to CSV before archiving
logger.export_csv('/archive/spots_2024_q1.csv', date='2024-01-01')
```

### Monitoring Database Size
```
du -h /data/spots.duckdb
```

## Related Files

- `spots_logger.py` - Main logger implementation
- `backend/main.py` - Integration points and API endpoints
- `cluster_client.py` - Provides raw spot data
- `spot_processor.py` - Derives band, mode, special tags
- `cty_resolvers.py` - Resolves country and zones from callsigns

## Future Enhancements

Possible improvements:
- Automatic archive/compression of old spots
- Real-time dashboard with live statistics
- Alert system for rare countries/bands
- Band-specific frequency allocation tracking
- Spotter reliability metrics
- Time-zone adjusted statistics