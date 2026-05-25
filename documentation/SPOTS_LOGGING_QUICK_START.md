# DX Spots Logging - Quick Start Guide

## 🚀 What's New

Your application now automatically logs ALL incoming DX cluster spots to a persistent database at `/data/spots.duckdb`. No spots are lost on reload, and you can query statistics and history!

## 📊 Quick Commands

### View Database Stats (Python)
```python
from spots_logger import get_spots_logger

logger = get_spots_logger()

# How many spots total?
print(logger.get_spot_count())

# Spots by band today?
from datetime import date
print(logger.get_stats_by_band(date.today().isoformat()))

# Top countries?
print(logger.get_stats_by_country(limit=20))

# Recent spots?
for spot in logger.get_recent_spots(limit=10):
    print(f"{spot['callsign']} on {spot['band']}")
```

### API Endpoints (HTTP)
```bash
# Total spot count
curl http://localhost:8000/api/spots/count

# Band statistics
curl http://localhost:8000/api/spots/stats/band

# Mode statistics
curl http://localhost:8000/api/spots/stats/mode

# Top 20 countries
curl http://localhost:8000/api/spots/stats/country?limit=20

# Recent 50 spots
curl http://localhost:8000/api/spots/recent?limit=50

# All spots for a callsign
curl http://localhost:8000/api/spots/callsign/W1AW

# Special event spots (POTA, SOTA, IOTA)
curl http://localhost:8000/api/spots/special

# Export to CSV
curl -X POST http://localhost:8000/api/spots/export/csv
```

## 📁 Files Changed

**New Files:**
- `spots_logger.py` - Main logging system
- `documentation/SPOTS_LOGGING_SYSTEM.md` - Complete documentation
- `documentation/SPOTS_LOGGING_IMPLEMENTATION.md` - Implementation details
- `test_spots_logger_demo.py` - Demo script

**Modified Files:**
- `backend/main.py` - Added logging integration + 8 API endpoints

## 🎯 Key Features

| Feature | Details |
|---------|---------|
| **Persistent** | All spots saved to disk in `/data/spots.duckdb` |
| **Automatic** | Logging happens automatically - no code needed |
| **Rich Data** | Band, mode, country, zones, special tags auto-detected |
| **Fast Queries** | Optimized indexes for quick statistics |
| **CSV Export** | Download data for Excel/analysis |
| **RESTful API** | 8 endpoints for web/mobile integration |

## 📈 Database Contents

Each logged spot includes:
- ✅ Time received (with date/time components)
- ✅ Frequency, band (auto-detected)
- ✅ Callsign, spotter
- ✅ Mode (auto-inferred from comment)
- ✅ Country, CQ zone, ITU zone, continent
- ✅ Special tags (POTA, SOTA, IOTA, etc.)
- ✅ Comment text

## 🔍 Example Queries

### Find all FT8 spots today
```python
from datetime import date
stats = logger.get_stats_by_mode(date.today().isoformat())
for mode_stat in stats:
    if mode_stat['mode'] == 'FT8':
        print(f"Found {mode_stat['total_spots']} FT8 spots today")
```

### Track a station's activity
```python
spots = logger.get_spots_by_callsign('W1AW', limit=100)
print(f"W1AW spotted {len(spots)} times")
for spot in spots:
    print(f"  {spot['time_utc']} on {spot['band']} by {spot['spotter']}")
```

### Find special events today
```python
special = logger.get_special_event_spots(limit=100)
print(f"Found {len(special)} POTA/SOTA/IOTA spots")
for spot in special:
    print(f"  {spot['callsign']}: {spot['special_tags']}")
```

## 🧪 Test It Now

Run the demo script:
```bash
python test_spots_logger_demo.py
```

This will:
1. Log sample spots
2. Show all query types
3. Export to CSV
4. Display results

## 📊 Database File

- **Location**: `c:/Projects/om0rx-radio-control/data/spots.duckdb`
- **Format**: DuckDB (file-based, no server needed)
- **Size**: Grows with spots (typically ~100KB per 1000 spots)

## 🔄 How It Works

```
Cluster receives spot
        ↓
process_cluster_spot() in backend/main.py
        ↓
log_spot(spot_data) - automatically logs to database
        ↓
Spot stored in /data/spots.duckdb with:
  - Band (auto-detected from frequency)
  - Mode (inferred from comment)
  - Country/Zones (looked up from callsign)
  - Special tags (POTA, SOTA, IOTA, etc.)
```

No manual action needed - logging is completely automatic!

## 🛠️ API Endpoints

### GET Endpoints (View Data)

| Endpoint | Query Param | Description |
|----------|------------|-------------|
| `/api/spots/count` | `date=YYYY-MM-DD` | Total spot count |
| `/api/spots/stats/band` | `date=YYYY-MM-DD` | Band statistics |
| `/api/spots/stats/mode` | `date=YYYY-MM-DD` | Mode statistics |
| `/api/spots/stats/country` | `limit=20, date=...` | Top countries |
| `/api/spots/recent` | `limit=100` | Recent spots |
| `/api/spots/callsign/{call}` | `limit=100` | Spots for callsign |
| `/api/spots/special` | `limit=100` | Special event spots |

### POST Endpoints (Export)

| Endpoint | Query Param | Description |
|----------|------------|-------------|
| `/api/spots/export/csv` | `date=YYYY-MM-DD` | Export to CSV |

## 💡 Use Cases

**🎯 Real-time Statistics**
- Show live band activity widget on UI
- Display top countries/modes

**📊 Analysis**
- Export weekly/monthly data to CSV
- Analyze trends over time

**🔍 Lookups**
- Show spot history for a callsign
- Find POTA/SOTA/IOTA activations

**📈 Reports**
- Band openings over time
- Spotter effectiveness
- Country coverage

## ⚙️ Configuration

No configuration needed! The system:
- Auto-creates database on first use
- Auto-creates indexes for performance
- Auto-imports country data from CTY files
- Auto-detects all fields

## 🐛 Troubleshooting

### Database file not found?
✅ It will be created automatically on first spot

### Country/zones showing NULL?
✅ Ensure `/data/cty.dat` and `/data/cty.csv` exist (they should)

### Performance slow?
✅ Check database size: `ls -lh /data/spots.duckdb`
✅ Consider archiving old data to CSV

## 📚 Full Documentation

For detailed information, see:
- `documentation/SPOTS_LOGGING_SYSTEM.md` - Complete reference
- `documentation/SPOTS_LOGGING_IMPLEMENTATION.md` - Technical details
- `spots_logger.py` - Source code with docstrings

## 🎉 You're All Set!

Spots are now being logged automatically. Start using the API endpoints to query your data!

---

**Questions?** Check the detailed documentation files or review the code comments in `spots_logger.py`.