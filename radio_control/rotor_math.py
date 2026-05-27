"""
Rotor Auto Control Math Module
Grid square conversion, bearing calculations, and helper functions
"""

import math
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


def _coerce_float(value, name: str) -> float:
    """Return a finite float or raise a clear ValueError."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number, got {value!r}")

    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return number


def validate_coordinates(lat, lon) -> Tuple[float, float]:
    """Validate latitude/longitude and return normalized floats."""
    lat_f = _coerce_float(lat, "Latitude")
    lon_f = _coerce_float(lon, "Longitude")
    if not (-90 <= lat_f <= 90):
        raise ValueError(f"Latitude must be -90 to 90, got {lat_f}")
    if not (-180 <= lon_f <= 180):
        raise ValueError(f"Longitude must be -180 to 180, got {lon_f}")
    return lat_f, lon_f


def grid_to_latlon(grid: str) -> Tuple[float, float]:
    """
    Convert Maidenhead grid square to latitude/longitude (center of square).
    
    Supports 2, 4, 6, or 8 character grids (AA, AA00, AA00aa, AA00aa00)
    
    Args:
        grid: Maidenhead grid square string (e.g., "JN88TQ", "CN87")
    
    Returns:
        Tuple of (latitude, longitude) in decimal degrees
    
    Raises:
        ValueError: If grid format is invalid
    """
    if not isinstance(grid, str):
        raise ValueError(f"Grid must be a string, got {type(grid).__name__}")

    g = grid.strip().upper()
    
    # Validate grid format
    if len(g) not in (2, 4, 6, 8):
        raise ValueError(f"Grid must be 2, 4, 6, or 8 characters, got {len(g)}: {grid}")
    
    if len(g) % 2 != 0:
        raise ValueError(f"Grid must have even number of characters: {grid}")
    
    # Validate character types
    if not g[0:2].isalpha() or not all(c in 'ABCDEFGHIJKLMNOPQR' for c in g[0:2]):
        raise ValueError(f"First two chars must be A-R: {grid}")
    
    # Start at southwest corner of world
    lon = -180.0
    lat = -90.0
    
    # Field (chars 0-1): A-R (20° × 10°)
    lon += (ord(g[0]) - ord('A')) * 20
    lat += (ord(g[1]) - ord('A')) * 10
    
    # Square (chars 2-3): 0-9 (2° × 1°)
    if len(g) >= 4:
        if not g[2:4].isdigit():
            raise ValueError(f"Chars 3-4 must be 0-9: {grid}")
        lon += int(g[2]) * 2
        lat += int(g[3]) * 1
    
    # Subsquare (chars 4-5): a-x (2/24° × 1/24°)
    if len(g) >= 6:
        if not g[4:6].isalpha() or not all(c in 'ABCDEFGHIJKLMNOPQRSTUVWX' for c in g[4:6]):
            raise ValueError(f"Chars 5-6 must be A-X: {grid}")
        lon += (ord(g[4]) - ord('A')) * (2 / 24)
        lat += (ord(g[5]) - ord('A')) * (1 / 24)
    
    # Extended (chars 6-7): 0-9 (2/240° × 1/240°)
    if len(g) >= 8:
        if not g[6:8].isdigit():
            raise ValueError(f"Chars 7-8 must be 0-9: {grid}")
        lon += int(g[6]) * (2 / 240)
        lat += int(g[7]) * (1 / 240)
    
    # Add half cell size to get center of square
    cell_sizes = [(20, 10), (2, 1), (2/24, 1/24), (2/240, 1/240)]
    level = len(g) // 2 - 1  # 0=field, 1=square, 2=subsquare, 3=extended
    cell_width, cell_height = cell_sizes[level]
    
    lat += cell_height / 2.0
    lon += cell_width / 2.0
    
    return (lat, lon)


def latlon_to_grid(lat: float, lon: float, precision: int = 6) -> str:
    """
    Convert latitude/longitude to Maidenhead grid square.
    
    Args:
        lat: Latitude in decimal degrees (-90 to 90)
        lon: Longitude in decimal degrees (-180 to 180)
        precision: Grid precision (2, 4, 6, or 8 characters)
    
    Returns:
        Maidenhead grid square string
    
    Raises:
        ValueError: If coordinates or precision are invalid
    """
    lat, lon = validate_coordinates(lat, lon)
    if precision not in (2, 4, 6, 8):
        raise ValueError(f"Precision must be 2, 4, 6, or 8, got {precision}")

    # Maidenhead cells are half-open at the north/east edges.
    lat = min(lat, 90 - 1e-12)
    lon = min(lon, 180 - 1e-12)
    
    # Normalize coordinates
    lat = lat + 90
    lon = lon + 180
    
    grid = ""
    
    # Field (0-1): A-Z
    field_lat = int(lat / 10)
    field_lon = int(lon / 20)
    grid += chr(ord('A') + field_lon)
    grid += chr(ord('A') + field_lat)
    
    if precision == 2:
        return grid
    
    # Square (2-3): 0-9
    lat = (lat % 10) * 10
    lon = (lon % 20) * 10
    square_lat = int(lat / 10)
    square_lon = int(lon / 20)
    grid += str(square_lon)
    grid += str(square_lat)
    
    if precision == 4:
        return grid
    
    # Subsquare (4-5): A-X
    lat = (lat % 10) * 24
    lon = (lon % 20) * 24
    subsq_lat = int(lat / 10)
    subsq_lon = int(lon / 20)
    grid += chr(ord('A') + subsq_lon)
    grid += chr(ord('A') + subsq_lat)
    
    if precision == 6:
        return grid
    
    # Extended (6-7): 0-9
    lat = (lat % 10) * 10
    lon = (lon % 20) * 10
    ext_lat = int(lat / 10)
    ext_lon = int(lon / 20)
    grid += str(ext_lon)
    grid += str(ext_lat)
    
    return grid


def _spherical_initial_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Robust spherical fallback for edge cases where Vincenty does not converge."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lon = math.radians(lon2 - lon1)
    y = math.sin(delta_lon) * math.cos(phi2)
    x = (
        math.cos(phi1) * math.sin(phi2)
        - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lon)
    )
    if x == 0 and y == 0:
        return 0.0
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def initial_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate initial bearing (azimuth) from point 1 to point 2.
    Uses Vincenty's inverse formula for WGS-84 geodesic (accurate for ham radio).
    
    Args:
        lat1, lon1: Starting point latitude/longitude in decimal degrees
        lat2, lon2: Ending point latitude/longitude in decimal degrees
    
    Returns:
        Bearing in degrees (0-360, where 0=N, 90=E, 180=S, 270=W)
    """
    lat1, lon1 = validate_coordinates(lat1, lon1)
    lat2, lon2 = validate_coordinates(lat2, lon2)

    # WGS-84 ellipsoid parameters
    a = 6378137.0  # Semi-major axis (meters)
    f = 1.0 / 298.257223563  # Flattening
    b = (1.0 - f) * a  # Semi-minor axis
    
    # Convert to radians
    φ1 = math.radians(lat1)
    φ2 = math.radians(lat2)
    L = math.radians(lon2 - lon1)
    
    # Calculate reduced latitudes
    U1 = math.atan((1.0 - f) * math.tan(φ1))
    U2 = math.atan((1.0 - f) * math.tan(φ2))
    
    sinU1 = math.sin(U1)
    cosU1 = math.cos(U1)
    sinU2 = math.sin(U2)
    cosU2 = math.cos(U2)
    
    # Iterative calculation (Vincenty's formula)
    lam = L
    converged = False
    for _ in range(200):  # Max 200 iterations for convergence
        sinlam = math.sin(lam)
        coslam = math.cos(lam)
        
        # Calculate angular distance
        sinsig = math.sqrt(
            (cosU2 * sinlam) ** 2 +
            (cosU1 * sinU2 - sinU1 * cosU2 * coslam) ** 2
        )
        
        if sinsig == 0:
            return 0.0  # Points are the same
        
        cossig = sinU1 * sinU2 + cosU1 * cosU2 * coslam
        sig = math.atan2(sinsig, cossig)
        
        # Calculate azimuth
        sinalpha = cosU1 * cosU2 * sinlam / sinsig
        cos2alpha = 1.0 - sinalpha ** 2
        
        if cos2alpha == 0:
            cos2sigm = 0.0
        else:
            cos2sigm = cossig - 2.0 * sinU1 * sinU2 / cos2alpha
        
        C = (f / 16.0) * cos2alpha * (4.0 + f * (4.0 - 3.0 * cos2alpha))
        
        lam_prev = lam
        lam = L + (1.0 - C) * f * sinalpha * (
            sig + C * sinsig * (
                cos2sigm + C * cossig * (-1.0 + 2.0 * cos2sigm ** 2)
            )
        )
        
        # Check convergence
        if abs(lam - lam_prev) < 1e-12:
            converged = True
            break

    if not converged:
        logger.debug("Vincenty bearing did not converge; using spherical fallback")
        return _spherical_initial_bearing(lat1, lon1, lat2, lon2)
    
    # Calculate initial bearing
    alpha1 = math.atan2(
        cosU2 * sinlam,
        cosU1 * sinU2 - sinU1 * cosU2 * coslam
    )
    
    bearing = math.degrees(alpha1)
    
    # Normalize to 0-360
    return (bearing + 360.0) % 360.0


def bearing_from_grids(grid_from: str, grid_to: str) -> float:
    """
    Calculate bearing from one grid square to another.
    
    Args:
        grid_from: Starting grid square (e.g., "JN88TQ")
        grid_to: Ending grid square (e.g., "CN87")
    
    Returns:
        Bearing in degrees (0-360)
    
    Raises:
        ValueError: If grid format is invalid
    """
    try:
        lat1, lon1 = grid_to_latlon(grid_from)
        lat2, lon2 = grid_to_latlon(grid_to)
        return initial_bearing(lat1, lon1, lat2, lon2)
    except ValueError as e:
        logger.error(f"Invalid grid conversion: {e}")
        raise


def bearing_from_coordinates(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate bearing from one set of coordinates to another.
    
    Args:
        lat1, lon1: Starting point (decimal degrees)
        lat2, lon2: Ending point (decimal degrees)
    
    Returns:
        Bearing in degrees (0-360)
    """
    return initial_bearing(lat1, lon1, lat2, lon2)


def calculate_bearing_for_station(
    my_lat: float,
    my_lon: float,
    station_grid: Optional[str] = None,
    station_lat: Optional[float] = None,
    station_lon: Optional[float] = None
) -> Optional[float]:
    """
    Calculate bearing to a station using available data.
    Prefers grid square over lat/lon if both provided.
    
    Args:
        my_lat, my_lon: Your QTH in decimal degrees
        station_grid: Station grid square (e.g., "CN87")
        station_lat, station_lon: Station coordinates (fallback)
    
    Returns:
        Bearing in degrees (0-360) or None if insufficient data
    
    Raises:
        ValueError: If coordinates are invalid
    """
    # Try grid square first (more accurate)
    if station_grid:
        try:
            station_grid = station_grid.strip().upper()
            target_lat, target_lon = grid_to_latlon(station_grid)
            return initial_bearing(my_lat, my_lon, target_lat, target_lon)
        except ValueError as e:
            logger.debug(f"Grid conversion failed: {e}, trying lat/lon fallback")
    
    # Fall back to lat/lon
    if station_lat is not None and station_lon is not None:
        station_lat, station_lon = validate_coordinates(station_lat, station_lon)
        return initial_bearing(my_lat, my_lon, station_lat, station_lon)
    
    logger.warning("Insufficient data to calculate bearing")
    return None


def get_band_from_frequency(freq_khz: float) -> Optional[str]:
    """
    Get band name from frequency in kHz.
    
    Args:
        freq_khz: Frequency in kilohertz
    
    Returns:
        Band name (e.g., "20m", "10m") or None if not in amateur bands
    """
    bands = {
        (135.7, 137.8): "2200m",
        (472, 479): "630m",
        (1800, 2000): "160m",
        (3500, 4000): "80m",
        (5248, 5368): "60m",
        (7000, 7300): "40m",
        (10100, 10150): "30m",
        (14000, 14350): "20m",
        (18068, 18168): "17m",
        (21000, 21450): "15m",
        (24890, 24990): "12m",
        (28000, 29700): "10m",
        (50000, 54000): "6m",
        (144000, 148000): "2m",
        (220000, 225000): "1.25m",
        (430000, 450000): "70cm",
        (902000, 928000): "33cm",
        (1240000, 1300000): "23cm",
    }
    
    for (low, high), band in bands.items():
        if low <= freq_khz <= high:
            return band
    
    return None


def validate_band_config(bands_config: dict) -> bool:
    """
    Validate rotor band configuration.
    
    Args:
        bands_config: Dictionary with band names as keys and bool values
    
    Returns:
        True if valid band configuration
    """
    valid_bands = {"160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m", "2m"}
    
    if not isinstance(bands_config, dict):
        return False
    
    for band, enabled in bands_config.items():
        if band not in valid_bands or not isinstance(enabled, bool):
            return False
    
    return True


# Example usage and tests
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test grid conversion
    print("=== Grid Conversion Tests ===")
    grid = "JN88TQ"
    lat, lon = grid_to_latlon(grid)
    print(f"{grid} -> {lat:.4f}°, {lon:.4f}°")
    
    grid2 = "CN87"
    lat2, lon2 = grid_to_latlon(grid2)
    print(f"{grid2} -> {lat2:.4f}°, {lon2:.4f}°")
    
    # Test bearing calculation
    print("\n=== Bearing Calculation ===")
    bearing = bearing_from_grids(grid, grid2)
    print(f"Bearing from {grid} to {grid2}: {bearing:.1f}°")
    
    # Test reverse bearing
    bearing_rev = bearing_from_grids(grid2, grid)
    print(f"Bearing from {grid2} to {grid} (reverse): {bearing_rev:.1f}°")
    
    # Test coordinate conversion
    print("\n=== Coordinate Conversion ===")
    grid_back = latlon_to_grid(lat, lon, 6)
    print(f"({lat:.4f}°, {lon:.4f}°) -> {grid_back}")
    
    # Test band detection
    print("\n=== Band Detection ===")
    test_freqs = [7100, 14200, 28500, 50100, 145000]
    for freq in test_freqs:
        band = get_band_from_frequency(freq)
        print(f"{freq} kHz -> {band}")
