"""
Spot Processor - Band detection, mode inference, special tag extraction
"""
import re
from radio_control import config
# Band detection
def band_from_khz(khz: float) -> str:
    """Convert frequency in kHz to band name"""
    # HF Bands
    if 1800 <= khz < 2000: return "160m"
    if 3500 <= khz < 4000: return "80m"
    if 5250 <= khz < 5450: return "60m"
    if 7000 <= khz < 7300: return "40m"
    if 10100 <= khz < 10150: return "30m"
    if 14000 <= khz < 14350: return "20m"
    if 18068 <= khz < 18168: return "17m"
    if 21000 <= khz < 21450: return "15m"
    if 24890 <= khz < 24990: return "12m"
    if 28000 <= khz < 29700: return "10m"
    
    # VHF Bands
    if 50000 <= khz < 54000: return "6m"
    if 144000 <= khz < 148000: return "2m"
    if 220000 <= khz < 225000: return "1.25m"
    
    # UHF/Microwave Bands
    if 430000 <= khz < 450000: return "70cm"
    if 902000 <= khz < 928000: return "33cm"
    if 1240000 <= khz < 1300000: return "23cm"
    if 2300000 <= khz < 2450000: return "13cm"
    if 3400000 <= khz < 3475000: return "9cm"
    if 5650000 <= khz < 5925000: return "5cm"
    if 10368000 <= khz < 10550000: return "3cm"
    if 24000000 <= khz < 24250000: return "1.25cm"
    
    return "OTHER"

# Known frequencies
FT8_FREQS = {1840.0, 3573.0, 5357.0, 7074.0, 10136.0, 14074.0, 18100.0, 21074.0, 24915.0, 28074.0, 50313.0}
FT4_FREQS = {3575.0, 7047.5, 10140.0, 14080.0, 18104.0, 21140.0, 24919.0, 28180.0}
FT2_FREQS = {50320.0}
DIGITAL_MODES = {"FT8", "FT4", "FT2", "RTTY", "PSK", "DIGI", "JT65", "JT9", "OLIVIA", "MFSK", "HELL", "SSTV"}
PHONE_MODES = {"SSB", "AM", "FM"}

PHONE_SEGMENTS = [
    ("10m", 28300.0, 29700.0), ("12m", 24940.0, 24990.0), ("15m", 21200.0, 21450.0),
    ("17m", 18110.0, 18168.0), ("20m", 14150.0, 14350.0), ("40m", 7090.0, 7300.0),
    ("80m", 3700.0, 4000.0), ("6m", 50100.0, 54000.0)
]

CW_SEGMENTS = [
    ("10m", 28000.0, 28150.0), ("12m", 24890.0, 24910.0), ("15m", 21000.0, 21070.0),
    ("17m", 18068.0, 18095.0), ("20m", 14000.0, 14060.0), ("40m", 7000.0, 7040.0),
    ("80m", 3500.0, 3560.0)
]

def near_any(freq, table, tol=1.6):
    """Check if frequency is near any in table"""
    return any(abs(freq - f) <= tol for f in table)

def in_segment(band, khz, segments):
    """Check if frequency is in specific band segment"""
    return any((b == band and lo <= khz <= hi) for b, lo, hi in segments)

def infer_mode(comment: str, band: str, khz: float) -> str:
    """Infer operating mode from comment, band, and frequency"""
    c = (comment or "").upper()
    
    # Comment-based detection first
    if "FT8" in c: return "FT8"
    if "FT4" in c: return "FT4"
    if "FT2" in c: return "FT2"
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
    if "CW" in c or "CWT" in c: return "CW"
    
    # Frequency heuristics
    if near_any(khz, FT8_FREQS): return "FT8"
    if near_any(khz, FT4_FREQS): return "FT4"
    if near_any(khz, FT2_FREQS): return "FT2"
    if in_segment(band, khz, PHONE_SEGMENTS): return "SSB"
    if in_segment(band, khz, CW_SEGMENTS): return "CW"
    
    # CW edge fallback
    cw_edge = None
    for b, lo, hi in CW_SEGMENTS:
        if b == band:
            cw_edge = hi
            break
    
    if cw_edge is not None and khz <= cw_edge:
        return "CW"
    
    return "SSB"


def rbl_mode_group(mode: str) -> str:
    """Map a spot mode to the broad RBL filter group."""
    normalized = (mode or "").upper()
    if normalized == "CW":
        return "CW"
    if normalized in PHONE_MODES:
        return "SSB"
    if normalized in DIGITAL_MODES:
        return "DIGI"
    return "OTHER"


def classify_spot_source(spotter: str, comment: str, mode: str) -> tuple[str, str]:
    """Return source type and broad RBL mode group for a cluster spot."""
    spotter_text = (spotter or "").upper()
    comment_text = (comment or "").upper()
    is_rbl = spotter_text.endswith("-#") or bool(
        re.search(r"\b(?:RBL|RBN|SKIMMER)\b", comment_text)
    )
    return ("rbl" if is_rbl else "cluster", rbl_mode_group(mode) if is_rbl else "")

def extract_special(comment: str) -> str:
    """Extract special tags from comment (POTA, SOTA, IOTA, etc.)
    Returns comma-separated list of all matching special types"""
    if not hasattr(config, 'SPECIAL_PATTERNS'):
        return ""
    
    c = (comment or "")
    matched_specials = []
    
    # Check all patterns and collect ALL matches
    for name, pattern in config.SPECIAL_PATTERNS.items():
        try:
            if re.search(pattern, c, re.I):
                matched_specials.append(name)
        except Exception:
            pass
    
    # Return comma-separated list of matches, or empty string if none
    return ", ".join(matched_specials) if matched_specials else ""

def clean_comment(s: str) -> str:
    """Clean comment text - remove non-printable characters"""
    s = re.sub(r"[^\x20-\x7E]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s
