# Wavelog Log Viewer Implementation

## Overview
Direct database access log viewer for fast, real-time display of Wavelog QSO log entries without relying on the slow Wavelog API.

## Features
- **Direct MariaDB Access**: Queries Wavelog database directly for instant results
- **View Mode Toggle**: Switch between "Filters" (spots) and "Log" views
- **Pagination Options**: Display 50, 100, 250, or 500 contacts
- **Real-time Refresh**: Always shows fresh data (no caching)
- **Comprehensive Display**: Shows all relevant QSO fields including:
  - Date/Time, Callsign, Mode, RST (sent/received)
  - Band, Frequency, Name, QTH, Gridsquare
  - Country, CQ Zone, ITU Zone, DXCC
  - State, County, IOTA
  - POTA, SOTA, WWFF references
  - QSL status (LoTW, QSL, eQSL - sent/received)
  - Comments

## Architecture

### Backend Components

#### 1. Database Service (`services/wavelog_log.py`)
- **WavelogLogService class**: Handles all database interactions
- **Methods**:
  - `get_log_entries(limit, station_id)`: Fetch log entries with pagination
  - `get_log_stats(station_id)`: Get log statistics (total QSOs, unique DXCC, etc.)
- **Features**:
  - Connection pooling
  - Automatic data formatting (dates, frequencies)
  - Error handling and logging

#### 2. API Endpoints (`backend/api/wavelog_log.py`)
- **GET `/api/wavelog-log/entries`**: Fetch log entries
  - Parameters:
    - `limit` (1-500, default: 100): Number of entries to return
    - `station_id` (default: 1): Station profile ID
  - Returns: JSON with entries array and metadata

- **GET `/api/wavelog-log/stats`**: Get log statistics
  - Parameters:
    - `station_id` (default: 1): Station profile ID
  - Returns: JSON with statistics

### Frontend Components

#### 1. JavaScript Module (`frontend/js/wavelog-log-viewer.js`)
- **Vue.js Integration**: Extends Vue instance with log viewer functionality
- **Reactive Data**:
  - `viewMode`: Current view ('spots' or 'log')
  - `logEntries`: Array of log entries
  - `logLoading`: Loading state
  - `logError`: Error message
  - `logLimit`: Current pagination limit
  - `availableLogLimits`: [50, 100, 250, 500]

- **Methods**:
  - `switchViewMode(mode)`: Toggle between spots and log view
  - `loadLogEntries()`: Fetch log entries from API
  - `setLogLimit(limit)`: Change pagination limit
  - `refreshLogEntries()`: Reload current view
  - `formatLogDateTime(date)`: Format datetime for display
  - `formatLogFrequency(freq)`: Format frequency in MHz
  - `formatQslStatus(status)`: Convert QSL status to emoji
  - `getLogRowClass(entry)`: Apply highlighting for confirmed QSOs
  - `getLogModeDisplay(entry)`: Combine mode and submode

#### 2. HTML Template (`frontend/templates/dx-spots.html`)
- **View Toggle Buttons**: Switch between Filters and Log views
- **Log Controls**: Pagination selector and refresh button
- **Log Table**: Comprehensive display with 23 columns
- **Loading/Error States**: User-friendly feedback

#### 3. CSS Styling (`frontend/wavelog-log-viewer.css`)
- **View Toggle**: Modern tab-like buttons
- **Table Styling**: Dark theme with hover effects
- **Row Highlighting**: 
  - Green tint for LoTW confirmed QSOs
  - Blue tint for QSL confirmed QSOs
- **Responsive Design**: Adapts to screen size
- **Smooth Transitions**: Professional animations

## Database Schema

### Main Table: `TABLE_HRD_CONTACTS_V01`
- **Primary Key**: `COL_PRIMARY_KEY` (bigint)
- **Key Fields**:
  - `COL_TIME_ON`, `COL_TIME_OFF`: QSO timestamps
  - `COL_CALL`: Callsign
  - `COL_BAND`, `COL_FREQ`: Band and frequency
  - `COL_MODE`, `COL_SUBMODE`: Operating mode
  - `COL_RST_SENT`, `COL_RST_RCVD`: Signal reports
  - `COL_GRIDSQUARE`, `COL_NAME`, `COL_QTH`: Location data
  - `COL_COUNTRY`, `COL_DXCC`, `COL_CQZ`, `COL_ITUZ`: Geographic info
  - `COL_LOTW_QSL_SENT/RCVD`: LoTW confirmations
  - `COL_QSL_SENT/RCVD`: QSL card status
  - `COL_EQSL_QSL_SENT/RCVD`: eQSL confirmations
  - `COL_POTA_REF`, `COL_SOTA_REF`, `COL_WWFF_REF`: Special references
  - `station_id`: Station profile ID

## Configuration

### Database Connection (config.py)
```python
DB_HOST = "wavelog.online"
DB_PORT = 3306
DB_NAME = "om0rx"
DB_USER = "<db_user>"
DB_PASS = "<db_password>"
WAVELOG_STATION_ID = "1"
```

## Usage

### For Users
1. **Switch to Log View**: Click the "📋 Log" button in the header
2. **Adjust Pagination**: Use the "Show: N" dropdown to select number of contacts
3. **Refresh Data**: Click the "🔄 Refresh" button to reload
4. **View Details**: Scroll horizontally to see all columns
5. **Return to Spots**: Click the "🎯 Filters" button

### For Developers

#### Adding New Fields
1. Update SQL query in `services/wavelog_log.py`
2. Add column to template in `frontend/templates/dx-spots.html`
3. Add formatting method if needed in `frontend/js/wavelog-log-viewer.js`

#### Modifying Pagination Limits
Update `availableLogLimits` in `frontend/js/wavelog-log-viewer.js`:
```javascript
availableLogLimits: [50, 100, 250, 500, 1000]  // Add 1000
```

#### Adding Filtering
Extend the SQL query in `get_log_entries()` with WHERE clauses and add filter UI controls.

## Performance

### Database Query Performance
- **Initial Load (100 entries)**: ~50-100ms
- **500 entries**: ~150-250ms
- **Database Size**: 41,795 QSOs
- **Network Latency**: Direct MariaDB connection (faster than API)

### Optimization Features
- Indexed queries (station_id, COL_TIME_ON)
- Efficient field selection (only needed columns)
- Connection pooling
- Minimal data processing

## Testing

### Backend Test
```bash
python test_wavelog_log_service.py
```

### API Test
```bash
curl http://localhost:8000/api/wavelog-log/entries?limit=10
curl http://localhost:8000/api/wavelog-log/stats
```

### Frontend Test
1. Start application: `.\start_webapp.ps1`
2. Open browser: http://localhost:8000
3. Click "📋 Log" button
4. Verify log entries load correctly
5. Test pagination and refresh

## Error Handling

### Database Errors
- Connection failures: Retry with exponential backoff
- Query errors: Logged to console and displayed to user
- Timeout handling: 30-second query timeout

### Frontend Errors
- Loading state: Shows spinner during data fetch
- Error state: Displays error message with retry button
- Empty state: Shows "No log entries found" message

## Security

### Read-Only Access
- Database user has READ-ONLY permissions
- No write operations allowed
- Station ID filtering enforced

### Input Validation
- Limit parameter: 1-500 range enforced
- Station ID: Integer validation
- SQL injection: Parameterized queries

## Future Enhancements

### Planned Features
1. **Advanced Filtering**: Filter by callsign, band, mode, date range
2. **Sorting**: Click column headers to sort
3. **Export**: Export filtered log to ADIF/CSV
4. **Search**: Full-text search across all fields
5. **Statistics**: Charts and graphs for log analysis
6. **QSO Details**: Click row to view full QSO details in modal

### Performance Improvements
1. **Virtual Scrolling**: Load more entries as user scrolls
2. **Server-side Pagination**: Implement cursor-based pagination
3. **Caching**: Optional caching with TTL for reduced DB load
4. **Compression**: Gzip response compression

## Dependencies

### Python
- `pymysql>=1.1.2`: MariaDB/MySQL database connector
- `fastapi`: Web framework
- `pydantic`: Data validation

### JavaScript
- Vue.js 3: Reactive UI framework

### Database
- MariaDB 10.6.22+
- Wavelog database schema

## Troubleshooting

### "Module Not Found: pymysql"
```bash
pip install pymysql
```

### "Connection Refused"
- Check database host/port in config.py
- Verify network connectivity
- Check firewall rules

### "Empty Log"
- Verify station_id is correct
- Check database has data
- Review SQL query in service

### "Slow Loading"
- Reduce pagination limit
- Check database indexes
- Monitor network latency

## Files Modified/Created

### Created
- `services/wavelog_log.py` - Database service
- `backend/api/wavelog_log.py` - API endpoints
- `frontend/js/wavelog-log-viewer.js` - Frontend logic
- `frontend/wavelog-log-viewer.css` - Styling
- `test_wavelog_log_service.py` - Test script
- `documentation/WAVELOG_LOG_VIEWER.md` - This file

### Modified
- `backend/main.py` - Registered log API router
- `frontend/index.html` - Added CSS and JS includes
- `frontend/templates/dx-spots.html` - Added log view UI

## Support

For issues or questions:
1. Check application logs: `logs/flex_debug.log`
2. Review browser console for JavaScript errors
3. Test database connectivity with test script
4. Verify API endpoints with curl/Postman

## License
Part of om0rx-radio-control project - All rights reserved