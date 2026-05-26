# utils.py - Utility functions for band, mode, and frequency handling

import logging
import sys
import re
import socket
import webbrowser
from pathlib import Path
from logging.handlers import RotatingFileHandler


def setup_logging(level: str, log_file: str | None):
    """Setup logging with specified level and optional file output"""
    lvl = getattr(logging, (level or "INFO").upper(), logging.INFO)
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file: handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(level=lvl, format="%(asctime)s | %(levelname)-7s | %(message)s", handlers=handlers)


def setup_flex_logging():
    """
    Configure logging to write to both console and flex_debug.log file.
    Uses RotatingFileHandler to prevent log file from growing too large.
    """
    try:
        from radio_control import config

        log_dir = config.LOGS_DIR
        log_dir.mkdir(exist_ok=True)  # Create logs directory if it doesn't exist
        log_path = log_dir / 'flex_debug.log'
        
        logger = logging.getLogger()
        formatter = logging.Formatter('%(asctime)s | %(levelname)-7s | %(message)s')
        
        # Add rotating file handler (max 2MB, keep 5 backups)
        file_handler = RotatingFileHandler(
            log_path, 
            maxBytes=2*1024*1024,  # 2MB
            backupCount=5, 
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # Ensure logger is at appropriate level
        if logger.level == logging.NOTSET or logger.level > logging.DEBUG:
            logger.setLevel(logging.DEBUG)  # Capture all debug messages
        
        print(f'✅ File logging enabled: {log_path}')
        logging.info('='*80)
        logging.info('OM0RX Radio Control Debug Log')
        logging.info('='*80)
        return True
    except Exception as e:
        print(f'⚠️ File logging setup failed: {e}')
        return False


def _apply_dark_theme(root):
    """Apply dark theme to tkinter window"""
    try:
        import tkinter as tk
        from tkinter import ttk
        style = ttk.Style(root)
        # Use 'clam' which allows color config
        try:
            style.theme_use('clam')
        except Exception:
            pass
        # Palette
        BG = '#1e1f22'
        FG = '#e6e6e6'
        ACCENT = '#3a3f58'
        SEL = '#2a2d35'
        HHL = '#444b6e'
        root.configure(bg=BG)
        # General
        style.configure('.', background=BG, foreground=FG, fieldbackground=SEL)
        style.map('.', background=[('active', SEL), ('disabled', BG)])
        # Buttons
        style.configure('TButton', background=ACCENT, foreground=FG, padding=6, borderwidth=0)
        style.map('TButton', background=[('active', HHL)])
        # Highlighted button (for active selection)
        style.configure('Highlight.TButton', background='#4a7ba7', foreground='#ffffff', padding=6, borderwidth=0)
        style.map('Highlight.TButton', background=[('active', '#5a8bb7')])
        # Labels/Entries
        style.configure('TLabel', background=BG, foreground=FG)
        style.configure('TEntry', fieldbackground=SEL, insertcolor=FG)
        style.configure('TMenubutton', background=ACCENT, foreground=FG)
        # Frames
        style.configure('TFrame', background=BG)
        style.configure('TLabelframe', background=BG, foreground=FG)
        # Treeview
        style.configure('Treeview', background=SEL, foreground=FG, fieldbackground=SEL, bordercolor=BG, borderwidth=0, rowheight=22)
        style.map('Treeview', background=[('selected', HHL)])
        style.configure('Treeview.Heading', background=ACCENT, foreground=FG)
    except Exception:
        pass


def band_from_khz(khz: float) -> str:
    """Determine band from frequency in kHz"""
    if  1800 <= khz < 2000:   return "160m"
    if  3500 <= khz < 4000:   return "80m"
    if  5250 <= khz < 5450:   return "60m"
    if  7000 <= khz < 7300:   return "40m"
    if 10100 <= khz < 10150:  return "30m"
    if 14000 <= khz < 14350:  return "20m"
    if 18068 <= khz < 18168:  return "17m"
    if 21000 <= khz < 21450:  return "15m"
    if 24890 <= khz < 24990:  return "12m"
    if 28000 <= khz < 29700:  return "10m"
    if 50000 <= khz < 54000:  return "6m"
    if 144000 <= khz < 148000: return "2m"
    if 430000 <= khz < 450000: return "70cm"
    return "OTHER"


# Mode detection constants
FT8 = {1840.0, 3573.0, 5357.0, 7074.0, 10136.0, 14074.0, 18100.0, 21074.0, 24915.0, 28074.0, 50313.0}
FT4 = {3575.0, 7047.5, 10140.0, 14080.0, 18104.0, 21140.0, 24919.0, 28180.0}

PHONE_SEG = [("10m",28300.0,29700.0),("12m",24940.0,24990.0),("15m",21200.0,21450.0),
             ("17m",18110.0,18168.0),("20m",14150.0,14350.0),("40m",7090.0,7300.0),
             ("80m",3700.0,4000.0),("6m",50100.0,54000.0)]
CW_SEG    = [("10m",28000.0,28150.0),("12m",24890.0,24910.0),("15m",21000.0,21070.0),
             ("17m",18068.0,18095.0),("20m",14000.0,14060.0),("40m",7000.0,7040.0),
             ("80m",3500.0,3560.0)]


def near_any(freq, table, tol=1.6): 
    """Check if frequency is near any in table"""
    return any(abs(freq-f)<=tol for f in table)


def in_seg(band, khz, segs): 
    """Check if frequency is in band segment"""
    return any((b==band and lo<=khz<=hi) for b,lo,hi in segs)


def infer_mode(comment: str, band: str, khz: float) -> str:
    """Infer operating mode from comment and frequency"""
    c = (comment or "").upper()
    # comment-based first
    if "FT8" in c: return "FT8"
    if "FT4" in c: return "FT4"
    if "RTTY" in c: return "RTTY"
    if "OLIVIA" in c: return "OLIVIA"
    if "PSK" in c: return "PSK"
    if "JT65" in c: return "JT65"
    if "JT9" in c: return "JT9"
    if "HELL" in c: return "HELL"
    if "MFSK" in c: return "MFSK"
    if "SSTV" in c: return "SSTV"
    if "AM " in c or c.endswith(" AM"): return "AM"
    if " FM" in c or c.startswith("FM "): return "FM"
    if "SSB" in c or "USB" in c or "LSB" in c or " PH" in c or c.endswith(" PH"): return "SSB"
    if "CW"  in c or "CWT" in c: return "CW"
    # frequency heuristics
    if near_any(khz, FT8): return "FT8"
    if near_any(khz, FT4): return "FT4"
    if in_seg(band, khz, PHONE_SEG): return "SSB"
    if in_seg(band, khz, CW_SEG): return "CW"
    # CW edge fallback
    cw_edge = None
    for b, lo, hi in CW_SEG:
        if b == band:
            cw_edge = hi; break
    if cw_edge is not None and khz <= cw_edge: return "CW"
    return "SSB"


def extract_special(comment: str) -> str:
    """Extract special tags from comment"""
    from radio_control.config import SPECIAL_PATTERNS
    c = (comment or "")
    for name, pat in SPECIAL_PATTERNS.items():
        try:
            if re.search(pat, c, re.I):
                return name
        except Exception:
            pass
    return ""


def clean_comment(s: str) -> str:
    """Clean comment string for display"""
    s = re.sub(r"[^\x20-\x7E]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def generate_callsign_variants(callsign: str) -> list:
    """
    Generate possible callsign variants for lookup fallback.
    
    Handles callsigns with prefixes/suffixes:
    - IZ4EFP/3 -> [IZ4EFP/3, IZ4EFP]
    - OK/OM0RX -> [OK/OM0RX, OM0RX]
    - F5JDG/M -> [F5JDG/M, F5JDG]
    - MW7MWZ/P -> [MW7MWZ/P, MW7MWZ]
    - PJ4/OM0AAO -> [PJ4/OM0AAO, OM0AAO]
    
    Returns:
        List of callsigns in order of priority (original first, then fallbacks)
    """
    callsign = callsign.upper().strip()
    variants = [callsign]  # Always start with the original
    
    if '/' not in callsign:
        # No slash, return as-is
        return variants
    
    parts = callsign.split('/')
    
    if len(parts) == 2:
        part1, part2 = parts
        
        # Heuristic to detect prefix vs suffix:
        # - Suffix: Usually short (1-3 chars) and contains digits or is a single letter (3, M, P, QRP, etc.)
        # - Prefix: Usually 1-3 country-code chars (OK, PJ4, VK, etc.) before the main callsign
        
        is_suffix = (
            len(part2) <= 3 or  # Suffixes like /3, /M, /P are short
            (len(part2) <= 4 and not part2.startswith('0')) or  # Or short without leading 0
            part2 in ['M', 'P', 'A', 'MM', 'QRP', 'AM', 'QRPP']  # Common suffixes
        )
        
        is_prefix = (
            len(part1) <= 4 and  # Prefixes like OK, PJ4, VK are short
            not part1.startswith('0') and  # Don't start with 0
            len(part2) > len(part1)  # Second part is usually the main callsign, so longer
        )
        
        # If it looks like CALLSIGN/SUFFIX format
        if is_suffix:
            if part1 and part1 != callsign:
                variants.append(part1)
        
        # If it looks like PREFIX/CALLSIGN format
        if is_prefix:
            if part2 and part2 != callsign:
                variants.append(part2)
        
        # Always try both parts as fallback if we're not sure
        if not is_suffix and not is_prefix:
            if part1 and part1 != callsign:
                variants.append(part1)
            if part2 and part2 != callsign:
                variants.append(part2)
    
    # Remove duplicates while preserving order
    seen = set()
    result = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            result.append(v)
    
    return result


def get_dxcc_color(dxcc_status: str) -> str:
    """
    Map DXCC status to SmartSDR panadapter color.
    
    DXCC Status values can be (full or abbreviated format):
    - "ATNO" - Already Taken Number On (priority)
    - "Confirmed" or "C" - Confirmed entity
    - "Confirmed/New Band" or "C/New Band" - Confirmed with new band opportunity
    - "Confirmed/New Mode" or "C/New Mode" - Confirmed with new mode opportunity
    - "Confirmed/New Band+Mode" or "C/New Band+Mode" - Confirmed with both new
    - "Worked" or "W" - Worked but not confirmed
    - "Worked/New Band" or "W/New Band" - Worked with new band
    - "Worked/New Mode" or "W/New Mode" - Worked with new mode
    - "Worked/New Band+Mode" or "W/New Band+Mode" - Worked with both new
    - "Unknown" or others
    
    Color format: #AARRGGBB (with alpha channel)
    
    Args:
        dxcc_status: DXCC status string from classification
    
    Returns:
        Color hex string in #AARRGGBB format
    """
    if not dxcc_status:
        return '#FFFFFFFF'  # White
    
    status = dxcc_status.upper().strip()
    
    # ATNO - orange (priority)
    if status == "ATNO":
        return '#FFFF8C00'  # Orange - HIGHEST PRIORITY
    
    # Confirmed entity - green (full or abbreviated)
    if status == "CONFIRMED" or status == "C":
        return '#FF00D000'  # Bright Green - Already got it confirmed
    
    # Confirmed with new band/mode - light green (handle both C/ and Confirmed/)
    if (status.startswith("C/") or "CONFIRMED/" in status) and ("NEW BAND" in status or "NEW MODE" in status):
        return '#FF32CD32'  # Lime Green - Good + opportunity
    
    # Worked entity - blue (full or abbreviated)
    if status == "WORKED" or status == "W":
        return '#FF0066FF'  # Blue - Have worked it
    
    # Worked with both new band AND mode - magenta (most interesting)
    if (status.startswith("W/") or "WORKED/" in status) and "NEW BAND" in status and "NEW MODE" in status:
        return '#FFFF00FF'  # Magenta - Very interesting
    
    # Worked with new band - cyan (interesting)
    if (status.startswith("W/") or "WORKED/" in status) and "NEW BAND" in status:
        return '#FF00FFFF'  # Cyan - New band opportunity
    
    # Worked with new mode - yellow (interesting)
    if (status.startswith("W/") or "WORKED/" in status) and "NEW MODE" in status:
        return '#FFFFFF00'  # Yellow - New mode opportunity
    
    # Unknown status - gray
    if status == "UNKNOWN":
        return '#FFB0B0B0'  # Gray - Can't determine
    
    # Default - white
    return '#FFFFFFFF'


def get_call_status_abbreviation(call_status: str) -> str:
    """
    Convert call status to abbreviation for display on panadapter callsign.
    
    This takes the CALL STATUS (band+mode specific QSO history classification)
    and converts to a concise label appended to the callsign.
    
    Args:
        call_status: Call status string like "New Band", "New Mode", "Worked", etc.
    
    Returns:
        Status abbreviation like "(NB)", "(NM)", "(NC)", "(C)", "(W)", or empty string
    
    Examples:
        "New Call" → "(NC)"
        "New Band" → "(NB)"
        "New Mode" → "(NM)"
        "New Band+Mode" → "(NB+NM)"
        "Confirmed" → "(C)"
        "Worked" → "(W)"
    """
    if not call_status:
        return ""
    
    status = call_status.upper().strip()
    
    # Check for combined new band + mode first
    if "NEW BAND" in status and "NEW MODE" in status:
        return "(NB+NM)"
    
    # Check for new band only
    if "NEW BAND" in status:
        return "(NB)"
    
    # Check for new mode only
    if "NEW MODE" in status:
        return "(NM)"
    
    # Check for new call (never worked before)
    if "NEW CALL" in status:
        return "(NC)"
    
    # Confirmed on this band+mode
    if "CONFIRMED" in status:
        return "(C)"
    
    # Just worked on this band+mode
    if "WORKED" in status:
        return "(W)"
    
    # Unknown or no special status
    return ""


def flex_probe_info(host: str, port: int, timeout=1.5):
    """Connect to Flex TCP API, read a short burst, and parse common key=value fields.
    Returns (info_dict, raw_text). Safe on failure (returns {}, '')."""
    try:
        sock = socket.create_connection((host, int(port)), timeout=timeout)
        sock.settimeout(0.4)
        chunks=[]
        for _ in range(6):
            try:
                data = sock.recv(4096)
                if not data: break
                chunks.append(data.decode(errors='ignore'))
            except Exception:
                break
        try:
            sock.close()
        except Exception:
            pass
        raw = ''.join(chunks)
        info={}
        # Heuristic: pull model/serial/nickname/version if present as key=value tokens
        import re as _re
        for key in ["model","serial","callsign","nickname","ver","version","region","fpga","name","ip"]:
            m = _re.search(rf"\b{key}=([^\s|]+)", raw)
            if m:
                info[key]=m.group(1)
        return info, raw
    except Exception:
        return {}, ''
