"""
Rotator Control API - TCP/IP Communication with ARCO and other rotators
Supports DCU-1/Rotor-EZ and Yaesu GS-232A protocols
"""

import asyncio
import logging
import re

logger = logging.getLogger(__name__)


class RotorController:
    """Handle TCP communication with rotator controllers"""
    
    def __init__(self, host: str, port: int, protocol: str = "DCU-1", timeout: float = 2.5):
        """
        Initialize rotator controller
        
        Args:
            host: IP address of rotator
            port: TCP port of rotator
            protocol: "DCU-1" or "Yaesu GS-232A"
            timeout: Read timeout in seconds
        """
        self.host = host
        self.port = port
        self.protocol = protocol
        self.timeout = timeout

    async def _read_response(self, reader: asyncio.StreamReader, initial_timeout: float | None = None) -> str:
        """Read one controller reply without waiting for the full timeout after data arrives."""
        buf = bytearray()
        timeout = self.timeout if initial_timeout is None else initial_timeout
        while True:
            try:
                chunk = await asyncio.wait_for(reader.read(256), timeout=timeout)
            except asyncio.TimeoutError:
                break
            if not chunk:
                break
            buf.extend(chunk)
            if b"\r" in chunk or b"\n" in chunk:
                break
            timeout = 0.05

        return buf.decode("ascii", errors="ignore").strip()
    
    async def send_command(self, cmd: str, response_timeout: float | None = None) -> str:
        """
        Send a command to the rotator and receive response
        
        Args:
            cmd: Command string (without terminator)
        
        Returns:
            Response string from rotator
        """
        try:
            # Open connection
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=1.5
            )
        except Exception as e:
            logger.error(f"Rotator TCP connect failed: {e}")
            raise Exception(f"TCP connect failed: {e}")
        
        try:
            # Send command with carriage return
            msg = (cmd + "\r").encode("ascii")
            writer.write(msg)
            await writer.drain()
            
            return await self._read_response(reader, response_timeout)
        
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def send_commands(self, commands: list[str], response_timeout: float | None = None) -> list[str]:
        """Send multiple commands over one TCP session and return each response."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=1.5
            )
        except Exception as e:
            logger.error(f"Rotator TCP connect failed: {e}")
            raise Exception(f"TCP connect failed: {e}")

        responses = []
        try:
            for cmd in commands:
                writer.write((cmd + "\r").encode("ascii"))
                await writer.drain()

                response = await self._read_response(reader, response_timeout)
                self._raise_for_error_response(cmd, response)
                responses.append(response)
            return responses
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    def _raise_for_error_response(self, cmd: str, response: str) -> None:
        """Treat explicit controller errors as failed commands."""
        if not response:
            return
        if re.search(r"\b(ERR|ERROR|NG|BAD|INVALID)\b", response, re.IGNORECASE):
            raise Exception(f"Rotator rejected {cmd}: {response}")
    
    def clamp_azimuth(self, az: int) -> int:
        """Normalize azimuth to 0-359 range."""
        az = int(round(az))
        return az % 360
    
    async def goto_azimuth(self, azimuth: int) -> dict:
        """
        Set rotator to specific azimuth
        
        Args:
            azimuth: Azimuth in degrees (0-359)
        
        Returns:
            dict with 'ok' and 'target' fields
        """
        az = self.clamp_azimuth(azimuth)
        
        if self.protocol == "DCU-1":
            # DCU-1/Rotor-EZ protocol: AP1xxx (set preset), AM1 (move)
            try:
                preset_cmd = f"AP1{str(az).zfill(3)}"
                responses = await self.send_commands([preset_cmd, "AM1"], response_timeout=0.2)
                logger.info(f"Rotor: GOTO {az}°")
                return {"ok": True, "target": az, "responses": responses}
            except Exception as e:
                logger.error(f"Rotor GOTO failed: {e}")
                raise
        
        elif self.protocol == "Yaesu GS-232A":
            # Yaesu GS-232A protocol: MxCCW or MxCW for stepping
            try:
                move_cmd = f"M{str(az).zfill(3)}"
                response = await self.send_command(move_cmd)
                self._raise_for_error_response(move_cmd, response)
                logger.info(f"Rotor: GOTO {az}°")
                return {"ok": True, "target": az, "responses": [response]}
            except Exception as e:
                logger.error(f"Rotor GOTO failed: {e}")
                raise
        
        else:
            raise ValueError(f"Unknown protocol: {self.protocol}")
    
    async def get_azimuth(self) -> dict:
        """
        Query current azimuth
        
        Returns:
            dict with 'az' field (0-359) or error
        """
        try:
            if self.protocol == "DCU-1":
                reply = await self.send_command("AI1")
            elif self.protocol == "Yaesu GS-232A":
                reply = await self.send_command("C")  # Query current position
            else:
                raise ValueError(f"Unknown protocol: {self.protocol}")
            
            candidates = [int(value) for value in re.findall(r"\d{1,3}", reply)]
            candidates = [value for value in candidates if 0 <= value <= 360]
            if candidates:
                az = self.clamp_azimuth(candidates[-1])
                return {"az": az}
            else:
                raise Exception(f"No azimuth in reply: '{reply}'")
        
        except Exception as e:
            logger.error(f"Rotor get azimuth failed: {e}")
            raise
    
    async def stop(self) -> dict:
        """Stop rotator movement"""
        try:
            if self.protocol == "DCU-1":
                response = await self.send_command("AS1")
            elif self.protocol == "Yaesu GS-232A":
                response = await self.send_command("A")  # Stop
            else:
                raise ValueError(f"Unknown protocol: {self.protocol}")
            self._raise_for_error_response("STOP", response)
            logger.info("Rotor: STOP")
            return {"ok": True, "response": response}
        except Exception as e:
            logger.error(f"Rotor stop failed: {e}")
            raise
    
    async def ping(self) -> dict:
        """Check if rotator is responsive"""
        try:
            if self.protocol == "DCU-1":
                response = await self.send_command("AI1")
            elif self.protocol == "Yaesu GS-232A":
                response = await self.send_command("C")
            else:
                raise ValueError(f"Unknown protocol: {self.protocol}")
            self._raise_for_error_response("PING", response)
            return {"ok": True, "response": response}
        except Exception as e:
            logger.error(f"Rotor ping failed: {e}")
            raise
    
    async def goto_direction(self, direction: str) -> dict:
        """
        Set rotator to cardinal direction
        
        Args:
            direction: "N", "S", "E", "W"
        
        Returns:
            dict with 'ok' and 'target' fields
        """
        directions = {
            "N": 0,    # North
            "E": 90,   # East
            "S": 180,  # South
            "W": 270,  # West
        }
        
        if direction not in directions:
            raise ValueError(f"Unknown direction: {direction}")
        
        azimuth = directions[direction]
        return await self.goto_azimuth(azimuth)
