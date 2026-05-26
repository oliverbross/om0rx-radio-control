# Logging Organization Rules

## Log Files Location

**All log files MUST be placed in the `/logs` folder.**

### Applies to:
- Application logs (`.log` files)
- Debug logs
- Error logs
- Access logs
- Rotating log backups (`.log.1`, `.log.2`, etc.)
- Any other log files or log-related outputs

### Directory Structure:
```
/logs/
├── flex_debug.log       # Main FlexRadio debug log
├── flex_debug.log.1     # Rotated backup (most recent)
├── flex_debug.log.2     # Rotated backup
├── flex_debug.log.3     # Rotated backup
├── flex_debug.log.4     # Rotated backup
├── flex_debug.log.5     # Rotated backup (oldest)
└── [other-logs].log     # Any other application logs
```

### Configuration Requirements:
1. **Log Directory**: All logging code must use `logs/` folder
2. **Auto-Creation**: Code should create `/logs` directory if it doesn't exist
3. **Rotating Logs**: Use `RotatingFileHandler` with reasonable size limits (e.g., 2MB)
4. **Backup Count**: Keep 5 rotated backups by default
5. **UTF-8 Encoding**: All log files should use UTF-8 encoding

### Code Pattern (Python):
```python
from pathlib import Path
from logging.handlers import RotatingFileHandler

# Use /logs directory for all log files
log_dir = Path(__file__).resolve().parent / 'logs'
log_dir.mkdir(exist_ok=True)  # Create logs directory if it doesn't exist
log_path = log_dir / 'application.log'

file_handler = RotatingFileHandler(
    log_path,
    maxBytes=2*1024*1024,  # 2MB
    backupCount=5,
    encoding='utf-8'
)
```

### Benefits:
✅ Keeps project root clean
✅ Easy to find and manage all log files
✅ Prevents log clutter in the main directory
✅ Simplifies log rotation and cleanup
✅ Easy to add `/logs/` to `.gitignore`

### Git Configuration:
Add to `.gitignore`:
```
# Logs directory
/logs/
*.log
*.log.*
```

### Maintenance:
- Log files in `/logs` can be safely deleted for cleanup
- Rotating file handlers will automatically manage old logs
- Monitor log directory size periodically
- Consider archiving old logs if long-term retention is needed

## Example File Paths:
✅ CORRECT: `C:\Projects\om0rx-radio-control\logs\flex_debug.log`
❌ INCORRECT: `C:\Projects\om0rx-radio-control\flex_debug.log`

✅ CORRECT: `C:\Projects\om0rx-radio-control\logs\backend.log`
❌ INCORRECT: `C:\Projects\om0rx-radio-control\backend.log`
