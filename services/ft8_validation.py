"""
FT8 Input Validation Module
Provides validation functions for callsigns, grid squares, and network configuration
"""

import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class FT8Validator:
    """Validator for FT8/FT4 parameters"""
    
    # Callsign pattern: 1-3 letter prefix, digit, 0-3 alphanumerics, letter suffix
    # Examples: W5XYZ, K0ABC, VE3ABC, GM0XYZ
    CALLSIGN_PATTERN = re.compile(r'^[A-Z0-9]{1,3}[0-9][A-Z0-9]{0,3}[A-Z]$', re.IGNORECASE)
    
    # Grid square pattern: 2 letters, 2 digits, optionally 2 more letters
    # Examples: JN88, JN88ab, AA00
    GRID_SQUARE_PATTERN = re.compile(r'^[A-R]{2}[0-9]{2}([A-X]{2})?$', re.IGNORECASE)
    
    # Hostname/IP pattern (simplified)
    HOSTNAME_PATTERN = re.compile(r'^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$')
    IP_PATTERN = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
    
    # Valid network modes
    VALID_MODES = {'FT8', 'FT4'}
    
    # Valid PTT methods
    VALID_PTT_METHODS = {'CAT', 'VOX'}
    
    # Port range
    MIN_PORT = 1024
    MAX_PORT = 65535
    
    @staticmethod
    def validate_callsign(callsign: str) -> Tuple[bool, str]:
        """
        Validate amateur radio callsign format
        
        Args:
            callsign: Callsign to validate (e.g., 'OM0RX')
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not callsign:
            return False, "Callsign cannot be empty"
        
        callsign = callsign.strip().upper()
        
        if len(callsign) < 3 or len(callsign) > 6:
            return False, f"Callsign must be 3-6 characters, got {len(callsign)}"
        
        if not FT8Validator.CALLSIGN_PATTERN.match(callsign):
            return False, f"Invalid callsign format: {callsign}. Expected format: prefix+digit+suffix (e.g., W5XYZ, K0ABC)"
        
        return True, ""
    
    @staticmethod
    def validate_grid_square(grid: str) -> Tuple[bool, str]:
        """
        Validate Maidenhead grid square format
        
        Args:
            grid: Grid square to validate (e.g., 'JN88' or 'JN88ab')
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not grid:
            return False, "Grid square cannot be empty"
        
        grid = grid.strip().upper()
        
        if not FT8Validator.GRID_SQUARE_PATTERN.match(grid):
            return False, (
                f"Invalid grid square format: {grid}. "
                f"Expected format: 2 letters + 2 digits + optional 2 letters (e.g., JN88, JN88AB, AA00)"
            )
        
        # Validate first pair (A-R)
        if not ('A' <= grid[0] <= 'R' and 'A' <= grid[1] <= 'R'):
            return False, f"Grid letters must be in range A-R, got {grid[:2]}"
        
        # Validate digits (0-9)
        if not (grid[2].isdigit() and grid[3].isdigit()):
            return False, f"Grid digits must be 0-9, got {grid[2:4]}"
        
        return True, ""
    
    @staticmethod
    def validate_network_server(server_addr: str) -> Tuple[bool, str]:
        """
        Validate network server address (hostname:port or IP:port)
        
        Args:
            server_addr: Server address (e.g., '192.168.0.199:4992' or 'radioserver.local:4992')
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not server_addr:
            return False, "Server address cannot be empty"
        
        server_addr = server_addr.strip()
        
        # Split host and port
        if ':' not in server_addr:
            return False, "Server address must include port (e.g., 'hostname:4992')"
        
        try:
            parts = server_addr.rsplit(':', 1)
            if len(parts) != 2:
                return False, "Invalid server address format"
            
            host, port_str = parts
            
            if not host:
                return False, "Hostname/IP cannot be empty"
            
            # Validate hostname or IP
            is_valid_ip = FT8Validator.IP_PATTERN.match(host)
            is_valid_hostname = FT8Validator.HOSTNAME_PATTERN.match(host) or host.lower() in ('localhost',)
            
            if not (is_valid_ip or is_valid_hostname):
                return False, f"Invalid hostname or IP address: {host}"
            
            # Validate IP octets if it's an IP address
            if is_valid_ip:
                octets = host.split('.')
                for octet in octets:
                    num = int(octet)
                    if not (0 <= num <= 255):
                        return False, f"Invalid IP address: {host} (octets must be 0-255)"
            
            # Validate port
            try:
                port = int(port_str)
            except ValueError:
                return False, f"Port must be a number, got '{port_str}'"
            
            if not (FT8Validator.MIN_PORT <= port <= FT8Validator.MAX_PORT):
                return False, (
                    f"Port must be between {FT8Validator.MIN_PORT} and {FT8Validator.MAX_PORT}, "
                    f"got {port}"
                )
            
            return True, ""
            
        except Exception as e:
            return False, f"Error validating server address: {str(e)}"
    
    @staticmethod
    def validate_mode(mode: str) -> Tuple[bool, str]:
        """
        Validate FT8/FT4 mode
        
        Args:
            mode: Mode to validate ('FT8' or 'FT4')
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not mode:
            return False, "Mode cannot be empty"
        
        mode = mode.upper()
        
        if mode not in FT8Validator.VALID_MODES:
            return False, f"Invalid mode: {mode}. Must be one of: {', '.join(FT8Validator.VALID_MODES)}"
        
        return True, ""
    
    @staticmethod
    def validate_ptt_method(ptt_method: str) -> Tuple[bool, str]:
        """
        Validate PTT method
        
        Args:
            ptt_method: PTT method to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not ptt_method:
            return False, "PTT method cannot be empty"
        
        ptt_method = ptt_method.upper()
        
        if ptt_method not in FT8Validator.VALID_PTT_METHODS:
            return False, (
                f"Invalid PTT method: {ptt_method}. "
                f"Must be one of: {', '.join(FT8Validator.VALID_PTT_METHODS)}"
            )
        
        return True, ""
    
    @staticmethod
    def validate_sample_rate(sample_rate: int) -> Tuple[bool, str]:
        """
        Validate audio sample rate
        
        Args:
            sample_rate: Sample rate in Hz
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not isinstance(sample_rate, int):
            return False, f"Sample rate must be an integer, got {type(sample_rate).__name__}"
        
        valid_rates = [8000, 11025, 12000, 16000, 22050, 44100, 48000]
        
        if sample_rate not in valid_rates:
            return False, (
                f"Sample rate {sample_rate} Hz not supported. "
                f"Valid rates: {', '.join(map(str, valid_rates))}"
            )
        
        return True, ""
    
    @staticmethod
    def validate_all_config(config: dict) -> Tuple[bool, dict]:
        """
        Validate complete FT8 configuration dictionary
        
        Args:
            config: Configuration dictionary
            
        Returns:
            Tuple of (is_valid, error_dict) where error_dict contains field->error_message mappings
        """
        errors = {}
        
        # Validate mode
        if 'mode' in config:
            valid, msg = FT8Validator.validate_mode(config['mode'])
            if not valid:
                errors['mode'] = msg
        
        # Validate callsign
        if 'mycall' in config:
            valid, msg = FT8Validator.validate_callsign(config['mycall'])
            if not valid:
                errors['mycall'] = msg
        
        # Validate grid
        if 'mygrid' in config:
            valid, msg = FT8Validator.validate_grid_square(config['mygrid'])
            if not valid:
                errors['mygrid'] = msg
        
        # Validate network server
        if 'networkServer' in config:
            valid, msg = FT8Validator.validate_network_server(config['networkServer'])
            if not valid:
                errors['networkServer'] = msg
        
        # Validate PTT method
        if 'pttMethod' in config:
            valid, msg = FT8Validator.validate_ptt_method(config['pttMethod'])
            if not valid:
                errors['pttMethod'] = msg
        
        # Validate sample rate
        if 'sampleRate' in config:
            valid, msg = FT8Validator.validate_sample_rate(config['sampleRate'])
            if not valid:
                errors['sampleRate'] = msg
        
        return len(errors) == 0, errors
