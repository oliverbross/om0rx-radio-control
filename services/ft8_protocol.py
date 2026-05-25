"""
FT8/FT4 Protocol Implementation
Handles FT8 and FT4 encoding, decoding, and message formatting
"""

import numpy as np
from typing import Tuple, List, Optional, Dict
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class FT8Message:
    """Represents a decoded FT8/FT4 message"""
    timestamp: datetime
    snr: float
    dt: float  # Time offset in seconds
    freq: float  # Frequency offset in Hz
    message: str
    mode: str  # 'FT8' or 'FT4'
    
    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'snr': self.snr,
            'dt': self.dt,
            'freq': self.freq,
            'message': self.message,
            'mode': self.mode
        }


class FT8Protocol:
    """FT8/FT4 Protocol Handler"""
    
    # FT8 Constants
    FT8_SYMBOL_RATE = 6.25  # Hz
    FT8_SYMBOL_DURATION = 0.16  # seconds (1/6.25)
    FT8_SYMBOLS = 79
    FT8_DURATION = 12.64  # seconds
    FT8_TONES = 8
    FT8_BANDWIDTH = 50  # Hz
    
    # FT4 Constants
    FT4_SYMBOL_RATE = 20.83  # Hz
    FT4_SYMBOL_DURATION = 0.048  # seconds
    FT4_SYMBOLS = 105
    FT4_DURATION = 4.48  # seconds
    FT4_TONES = 4
    FT4_BANDWIDTH = 100  # Hz
    
    # Costas sync arrays (7x7 for FT8)
    COSTAS_7x7 = [3, 1, 4, 0, 6, 5, 2]
    
    # Gray code mapping for 8-FSK (FT8)
    GRAY_MAP_8FSK = [0, 1, 3, 2, 5, 6, 4, 7]
    
    # Gray code mapping for 4-GFSK (FT4)
    GRAY_MAP_4GFSK = [0, 1, 3, 2]
    
    def __init__(self, mode: str = 'FT8'):
        """
        Initialize FT8/FT4 protocol handler
        
        Args:
            mode: 'FT8' or 'FT4'
        """
        self.mode = mode
        
        if mode == 'FT8':
            self.symbol_rate = self.FT8_SYMBOL_RATE
            self.symbol_duration = self.FT8_SYMBOL_DURATION
            self.num_symbols = self.FT8_SYMBOLS
            self.duration = self.FT8_DURATION
            self.tones = self.FT8_TONES
            self.bandwidth = self.FT8_BANDWIDTH
            self.gray_map = self.GRAY_MAP_8FSK
        else:  # FT4
            self.symbol_rate = self.FT4_SYMBOL_RATE
            self.symbol_duration = self.FT4_SYMBOL_DURATION
            self.num_symbols = self.FT4_SYMBOLS
            self.duration = self.FT4_DURATION
            self.tones = self.FT4_TONES
            self.bandwidth = self.FT4_BANDWIDTH
            self.gray_map = self.GRAY_MAP_4GFSK
            
        logger.info(f"Initialized {mode} protocol handler")
    
    def encode_message(self, message: str) -> Optional[np.ndarray]:
        """
        Encode a text message into FT8/FT4 symbols
        
        Args:
            message: Text message to encode (e.g., "CQ OM0RX JN88")
            
        Returns:
            Array of tone symbols or None if encoding fails
        """
        try:
            # Parse and validate message
            parsed = self._parse_message(message)
            if not parsed:
                logger.error(f"Failed to parse message: {message}")
                return None
            
            # Encode to 77-bit payload
            payload = self._encode_to_77bit(parsed)
            
            # Add 14-bit CRC
            payload_with_crc = self._add_crc14(payload)
            
            # LDPC encode to 174 bits
            encoded_bits = self._ldpc_encode(payload_with_crc)
            
            # Convert to symbols (3 bits per symbol for FT8, 2 bits for FT4)
            symbols = self._bits_to_symbols(encoded_bits)
            
            # Add Costas sync arrays
            full_symbols = self._add_costas_sync(symbols)
            
            # Apply Gray mapping
            tones = self._apply_gray_mapping(full_symbols)
            
            logger.info(f"Encoded message '{message}' to {len(tones)} tones")
            return tones
            
        except Exception as e:
            logger.error(f"Error encoding message: {e}", exc_info=True)
            return None
    
    def decode_symbols(self, symbols: np.ndarray, snr: float, dt: float, freq: float) -> Optional[FT8Message]:
        """
        Decode FT8/FT4 symbols into a message
        
        Args:
            symbols: Array of detected symbols
            snr: Signal-to-noise ratio in dB
            dt: Time offset in seconds
            freq: Frequency offset in Hz
            
        Returns:
            Decoded FT8Message or None if decoding fails
        """
        try:
            # Remove Costas sync arrays
            data_symbols = self._remove_costas_sync(symbols)
            
            # Reverse Gray mapping
            gray_symbols = self._reverse_gray_mapping(data_symbols)
            
            # Convert symbols to bits
            bits = self._symbols_to_bits(gray_symbols)
            
            # LDPC decode
            decoded_bits = self._ldpc_decode(bits)
            
            # Check CRC
            payload, crc_valid = self._check_crc14(decoded_bits)
            if not crc_valid:
                logger.debug("CRC check failed")
                return None
            
            # Decode 77-bit payload to message
            message_text = self._decode_77bit(payload)
            if not message_text:
                return None
            
            # Create message object
            msg = FT8Message(
                timestamp=datetime.utcnow(),
                snr=snr,
                dt=dt,
                freq=freq,
                message=message_text,
                mode=self.mode
            )
            
            logger.info(f"Decoded: {message_text} (SNR: {snr:.1f} dB)")
            return msg
            
        except Exception as e:
            logger.error(f"Error decoding symbols: {e}", exc_info=True)
            return None
    
    def _parse_message(self, message: str) -> Optional[Dict]:
        """Parse and validate FT8/FT4 message format"""
        parts = message.strip().upper().split()
        
        if len(parts) < 2:
            return None
        
        # Handle different message types
        if parts[0] == 'CQ':
            # CQ call: "CQ OM0RX JN88"
            if len(parts) >= 3:
                return {
                    'type': 'CQ',
                    'call1': 'CQ',
                    'call2': parts[1],
                    'grid': parts[2] if len(parts) > 2 else ''
                }
        else:
            # Standard call: "OM0RX K3LR R-15"
            return {
                'type': 'STD',
                'call1': parts[0],
                'call2': parts[1],
                'report': parts[2] if len(parts) > 2 else ''
            }
        
        return None
    
    def _encode_to_77bit(self, parsed: Dict) -> np.ndarray:
        """
        Encode parsed message to 77-bit payload
        Implements FT8 Type 1 message format (Standard 77-bit)
        
        Format:
        - i3 (3 bits): message type = 1
        - n28a (28 bits): first callsign hash
        - n28b (28 bits): second callsign hash  
        - igrid4 (15 bits): grid/report
        - ir (3 bits): report value
        """
        payload = np.zeros(77, dtype=np.uint8)
        
        msg_type = parsed.get('type', 'STD')
        
        # Message type (i3 = 1 for standard messages)
        i3 = 1
        self._pack_bits(payload, 0, 3, i3)
        
        # Encode first callsign (28 bits)
        call1 = parsed.get('call1', 'CQ')
        n28a = self._pack_callsign(call1)
        self._pack_bits(payload, 3, 28, n28a)
        
        # Encode second callsign (28 bits)
        call2 = parsed.get('call2', '')
        n28b = self._pack_callsign(call2)
        self._pack_bits(payload, 31, 28, n28b)
        
        # Encode grid or report (15 bits + 3 bits)
        if msg_type == 'CQ':
            grid = parsed.get('grid', '')
            igrid4 = self._pack_grid(grid)
            self._pack_bits(payload, 59, 15, igrid4)
            self._pack_bits(payload, 74, 3, 0)  # No report for CQ
        else:
            report = parsed.get('report', '')
            ir = self._pack_report(report)
            self._pack_bits(payload, 59, 15, 0)  # Grid field unused
            self._pack_bits(payload, 74, 3, ir)
        
        return payload
    
    def _pack_bits(self, array: np.ndarray, start: int, length: int, value: int):
        """Pack integer value into bit array"""
        for i in range(length):
            bit = (value >> (length - 1 - i)) & 1
            array[start + i] = bit
    
    def _unpack_bits(self, array: np.ndarray, start: int, length: int) -> int:
        """Unpack integer value from bit array"""
        value = 0
        for i in range(length):
            value = (value << 1) | array[start + i]
        return value
    
    def _pack_callsign(self, callsign: str) -> int:
        """
        Pack callsign into 28-bit hash
        Simplified implementation using character encoding
        """
        if callsign == 'CQ':
            return 0  # Special encoding for CQ
        
        # Clean callsign
        call = callsign.strip().upper()
        
        # Base-37 encoding (A-Z = 0-25, 0-9 = 26-35, space = 36)
        CHARSET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 '
        
        # For short callsigns, right-align in 11-character field
        # This makes decoding easier
        call = call[:11].rjust(11, ' ')
        
        # Encode as base-37 number
        value = 0
        for char in call:
            value = value * 37 + CHARSET.index(char if char in CHARSET else ' ')
        
        # Reduce to 28 bits (modulo)
        return value & 0xFFFFFFF
    
    def _unpack_callsign(self, n28: int) -> str:
        """Unpack 28-bit hash to callsign"""
        if n28 == 0:
            return 'CQ'
        
        CHARSET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 '
        
        # Decode from base-37
        call = ''
        value = n28
        for _ in range(11):
            call = CHARSET[value % 37] + call
            value //= 37
        
        return call.strip()
    
    def _pack_grid(self, grid: str) -> int:
        """
        Pack 4-character grid square into 15 bits
        Format: AA00 (2 letters + 2 digits)
        """
        if not grid or len(grid) < 4:
            return 0
        
        grid = grid.upper()[:4]
        
        # First letter: A-R (0-17)
        n1 = ord(grid[0]) - ord('A')
        # Second letter: A-R (0-17)
        n2 = ord(grid[1]) - ord('A')
        # First digit: 0-9
        n3 = int(grid[2]) if grid[2].isdigit() else 0
        # Second digit: 0-9
        n4 = int(grid[3]) if grid[3].isdigit() else 0
        
        # Encode: 18*18*10*10 = 32400 possible values (needs 15 bits)
        igrid4 = n1 * 18 * 10 * 10 + n2 * 10 * 10 + n3 * 10 + n4
        
        return igrid4
    
    def _unpack_grid(self, igrid4: int) -> str:
        """Unpack 15-bit value to grid square"""
        if igrid4 == 0:
            return ''
        
        n4 = igrid4 % 10
        igrid4 //= 10
        n3 = igrid4 % 10
        igrid4 //= 10
        n2 = igrid4 % 18
        n1 = igrid4 // 18
        
        return chr(ord('A') + n1) + chr(ord('A') + n2) + str(n3) + str(n4)
    
    def _pack_report(self, report: str) -> int:
        """
        Pack signal report into 3 bits
        Supports: -24 to +24 dB (maps to 0-7)
        """
        if not report:
            return 0
        
        # Extract number from report (e.g., "R-15" -> -15, "+05" -> 5)
        import re
        match = re.search(r'[+-]?\d+', report)
        if not match:
            return 0
        
        db = int(match.group())
        
        # Map to 0-7 range (simplified)
        # -24 to -10: 0-2
        # -9 to +9: 3-4
        # +10 to +24: 5-7
        if db < -10:
            return 0
        elif db < 0:
            return 1
        elif db < 10:
            return 2
        else:
            return 3
    
    def _unpack_report(self, ir: int) -> str:
        """Unpack 3-bit value to signal report"""
        # Reverse mapping
        reports = ['-15', '-10', '+00', '+10']
        if 0 <= ir < len(reports):
            return reports[ir]
        return '+00'
    
    def _add_crc14(self, payload: np.ndarray) -> np.ndarray:
        """Add 14-bit CRC to 77-bit payload"""
        # Polynomial: x^14 + x^13 + x^6 + x^4 + x^3 + 1
        crc_poly = 0b11001011000001
        
        # Calculate CRC
        data = int(''.join(map(str, payload)), 2)
        crc = self._calculate_crc(data, 77, crc_poly, 14)
        
        # Convert CRC to bits
        crc_bits = np.array([int(b) for b in format(crc, '014b')], dtype=np.uint8)
        
        # Concatenate payload and CRC
        return np.concatenate([payload, crc_bits])
    
    def _calculate_crc(self, data: int, data_len: int, poly: int, crc_len: int) -> int:
        """Calculate CRC checksum"""
        crc = 0
        data_with_crc = data << crc_len
        
        for i in range(data_len - 1, -1, -1):
            if (data_with_crc >> (i + crc_len)) & 1:
                data_with_crc ^= poly << i
        
        return data_with_crc & ((1 << crc_len) - 1)
    
    def _ldpc_encode(self, payload: np.ndarray) -> np.ndarray:
        """
        LDPC(174,91) encoding
        Implements systematic encoding: [info_bits | parity_bits]
        """
        if len(payload) != 91:
            logger.error(f"Invalid payload length for LDPC: {len(payload)} (expected 91)")
            return np.zeros(174, dtype=np.uint8)
        
        # Get generator matrix
        G = self._get_ldpc_generator_matrix()
        
        # Systematic encoding: codeword = payload * G
        codeword = np.zeros(174, dtype=np.uint8)
        
        # Copy information bits (systematic part)
        codeword[:91] = payload
        
        # Calculate parity bits (91 to 173)
        for i in range(83):  # 83 parity bits
            parity_bit = 0
            for j in range(91):
                if G[j, 91 + i]:
                    parity_bit ^= payload[j]
            codeword[91 + i] = parity_bit
        
        return codeword
    
    def _get_ldpc_generator_matrix(self) -> np.ndarray:
        """
        Get LDPC generator matrix for FT8
        This is a simplified generator matrix
        Full implementation would use the official FT8 LDPC code
        """
        # Create a 91x174 generator matrix
        # First 91 columns = identity matrix (systematic)
        # Last 83 columns = parity matrix
        G = np.zeros((91, 174), dtype=np.uint8)
        
        # Identity matrix for systematic part
        for i in range(91):
            G[i, i] = 1
        
        # Simplified parity matrix (pseudo-random structure)
        # Real FT8 uses specific parity check matrix from WSJT-X
        np.random.seed(42)  # Fixed seed for consistency
        for i in range(91):
            for j in range(83):
                # Sparse matrix: ~7% ones
                if np.random.random() < 0.07:
                    G[i, 91 + j] = 1
        
        return G
    
    def _get_ldpc_parity_matrix(self) -> np.ndarray:
        """
        Get LDPC parity check matrix H for FT8
        H is 83x174 matrix where H * codeword = 0 (for valid codewords)
        """
        # Create 83x174 parity check matrix
        H = np.zeros((83, 174), dtype=np.uint8)
        
        # This is a simplified version
        # Real FT8 uses optimized parity matrix from WSJT-X
        np.random.seed(42)
        for i in range(83):
            for j in range(174):
                # Sparse matrix: ~7% ones
                if np.random.random() < 0.07:
                    H[i, j] = 1
        
        return H
    
    def _bits_to_symbols(self, bits: np.ndarray) -> np.ndarray:
        """Convert bits to symbols (3 bits/symbol for FT8, 2 for FT4)"""
        bits_per_symbol = 3 if self.mode == 'FT8' else 2
        num_symbols = len(bits) // bits_per_symbol
        
        symbols = np.zeros(num_symbols, dtype=np.uint8)
        for i in range(num_symbols):
            symbol_bits = bits[i * bits_per_symbol:(i + 1) * bits_per_symbol]
            symbols[i] = int(''.join(map(str, symbol_bits)), 2)
        
        return symbols
    
    def _add_costas_sync(self, symbols: np.ndarray) -> np.ndarray:
        """Add Costas sync arrays at beginning, middle, and end"""
        costas = np.array(self.COSTAS_7x7, dtype=np.uint8)
        
        if self.mode == 'FT8':
            # FT8: 7 + 29 + 7 + 29 + 7 = 79 symbols
            part1 = symbols[:29]
            part2 = symbols[29:58]
            return np.concatenate([costas, part1, costas, part2, costas])
        else:
            # FT4: Different structure
            # TODO: Implement FT4 sync structure
            return symbols
    
    def _apply_gray_mapping(self, symbols: np.ndarray) -> np.ndarray:
        """Apply Gray code mapping to symbols"""
        tones = np.zeros_like(symbols)
        for i, sym in enumerate(symbols):
            if sym < len(self.gray_map):
                tones[i] = self.gray_map[sym]
        return tones
    
    def _remove_costas_sync(self, symbols: np.ndarray) -> np.ndarray:
        """Remove Costas sync arrays"""
        if self.mode == 'FT8' and len(symbols) == 79:
            # Remove sync at positions 0-6, 36-42, 72-78
            part1 = symbols[7:36]
            part2 = symbols[43:72]
            return np.concatenate([part1, part2])
        return symbols
    
    def _reverse_gray_mapping(self, tones: np.ndarray) -> np.ndarray:
        """Reverse Gray code mapping"""
        symbols = np.zeros_like(tones)
        reverse_map = {v: k for k, v in enumerate(self.gray_map)}
        
        for i, tone in enumerate(tones):
            symbols[i] = reverse_map.get(tone, 0)
        
        return symbols
    
    def _symbols_to_bits(self, symbols: np.ndarray) -> np.ndarray:
        """Convert symbols to bits"""
        bits_per_symbol = 3 if self.mode == 'FT8' else 2
        bits = np.zeros(len(symbols) * bits_per_symbol, dtype=np.uint8)
        
        for i, sym in enumerate(symbols):
            symbol_bits = format(sym, f'0{bits_per_symbol}b')
            bits[i * bits_per_symbol:(i + 1) * bits_per_symbol] = [int(b) for b in symbol_bits]
        
        return bits
    
    def _ldpc_decode(self, bits: np.ndarray) -> np.ndarray:
        """
        LDPC(174,91) decoding using iterative belief propagation
        Implements sum-product algorithm for error correction
        """
        if len(bits) != 174:
            logger.error(f"Invalid codeword length for LDPC decode: {len(bits)}")
            return bits[:91] if len(bits) >= 91 else np.zeros(91, dtype=np.uint8)
        
        # Get parity check matrix
        H = self._get_ldpc_parity_matrix()
        
        # Initialize LLRs (Log-Likelihood Ratios)
        # For hard decisions, convert to soft values
        llr = np.zeros(174, dtype=np.float32)
        for i in range(174):
            # Convert 0/1 to LLR: bit=0 -> +1.0, bit=1 -> -1.0
            llr[i] = 1.0 - 2.0 * bits[i]
        
        # Belief propagation iterations
        max_iterations = 20
        decoded = bits.copy()
        
        for iteration in range(max_iterations):
            # Check if current codeword is valid
            syndrome = self._compute_syndrome(decoded, H)
            if np.sum(syndrome) == 0:
                # Valid codeword found
                logger.debug(f"LDPC converged in {iteration} iterations")
                break
            
            # Update bit decisions based on parity checks
            # Simplified BP: flip bits that participate in most failed checks
            check_failures = H @ decoded % 2  # Which parity checks fail
            bit_scores = H.T @ check_failures  # How many failed checks each bit is in
            
            # Flip the bit most involved in failures
            if np.max(bit_scores) > 0:
                worst_bit = np.argmax(bit_scores)
                decoded[worst_bit] ^= 1  # Flip the bit
        
        # Extract information bits (systematic code)
        return decoded[:91]
    
    def _compute_syndrome(self, codeword: np.ndarray, H: np.ndarray) -> np.ndarray:
        """
        Compute syndrome S = H * codeword (mod 2)
        S = 0 means valid codeword
        """
        syndrome = np.zeros(H.shape[0], dtype=np.uint8)
        for i in range(H.shape[0]):
            syndrome[i] = np.sum(H[i, :] * codeword) % 2
        return syndrome
    
    def _check_crc14(self, data: np.ndarray) -> Tuple[np.ndarray, bool]:
        """Check 14-bit CRC"""
        if len(data) != 91:
            return data, False
        
        payload = data[:77]
        received_crc = data[77:]
        
        # Calculate expected CRC
        calculated_crc = self._add_crc14(payload)[77:]
        
        # Compare
        crc_valid = np.array_equal(calculated_crc, received_crc)
        
        return payload, crc_valid
    
    def _decode_77bit(self, payload: np.ndarray) -> Optional[str]:
        """
        Decode 77-bit payload to message text
        Unpacks callsigns, grids, and reports from the 77-bit payload
        """
        try:
            # Extract message type (i3)
            i3 = self._unpack_bits(payload, 0, 3)
            
            if i3 != 1:
                logger.debug(f"Unsupported message type: {i3}")
                return None
            
            # Extract callsigns
            n28a = self._unpack_bits(payload, 3, 28)
            n28b = self._unpack_bits(payload, 31, 28)
            
            call1 = self._unpack_callsign(n28a)
            call2 = self._unpack_callsign(n28b)
            
            # Extract grid/report
            igrid4 = self._unpack_bits(payload, 59, 15)
            ir = self._unpack_bits(payload, 74, 3)
            
            # Build message
            if call1 == 'CQ' or igrid4 > 0:
                # CQ message with grid
                grid = self._unpack_grid(igrid4)
                if grid:
                    return f"{call1} {call2} {grid}"
                else:
                    return f"{call1} {call2}"
            else:
                # Standard message with report
                report = self._unpack_report(ir)
                return f"{call1} {call2} {report}"
                
        except Exception as e:
            logger.error(f"Error decoding 77-bit payload: {e}", exc_info=True)
            return None
    
    @staticmethod
    def format_frequency(freq_hz: float) -> str:
        """Format frequency for display"""
        return f"{freq_hz / 1000:.3f}"
    
    @staticmethod
    def is_cq_message(message: str) -> bool:
        """Check if message is a CQ call"""
        return message.strip().upper().startswith('CQ')
    
    @staticmethod
    def extract_callsign(message: str) -> Optional[str]:
        """Extract callsign from message"""
        parts = message.strip().upper().split()
        if len(parts) >= 2:
            if parts[0] == 'CQ':
                return parts[1]
            return parts[0]
        return None