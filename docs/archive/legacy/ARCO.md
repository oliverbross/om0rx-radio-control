I want you to add rotator control to our application - UI.

The rotator is to rotate antenna and integrate Microham ARCO rotator with our application.

The rotator uses tcp connection. We need to add new configuration parameters  for the rotator to our config, co in configuration button add new tab - Rotor after flex/udp and add there:

1. rotator type: Microham ARCO
2. Ip address of rotator:
3. Port number:
4. protocol used: Yaesu GS-232A or DCU-1/Rotor EZ ... drop down choice

the values will get saved in our config file: config.py

In our UI - 4th line do the following changes - move RIT and XIT between frequency and Step, so to the right side, put them in 2 lines, so rit on the top and xit on the bottom

This will leave a space for the rotator controls on the right had side of the screen from the frequency display.

I want you to add the following parameters to the right hand side of the screen:

in 2 lines: 1st line Az: with filed 0.0 degress so user can type the azimith there and next to it Goto button, so when click, the rotor will turn to the azimuth
Bellow this add the following buttons: QSO SP / QSO LP - this is dropdown menu with those 2 choices, next to it buttons: N, S, W and E ... coresponding to North, South, West and East directions. When clicked they will send command to the rotator to go that direction. the SP and LP choices will send rotator to long path or short path position.

We need to implement the full communication with the rotator using TCP/IP connection and port. For example we have a rotator at IP address 192.168.0.198 and port 4001 then we connect to it via socket.connect(('192.168.0.198', 4001)) and send commands like socket.sendall(b'GOTO AZ=50') to set the azimuth to 50 degrees. 

I'm not 100% sure how it works, you should search the ineternet for examples, but here is one maybe already working example: 

import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ARCO_HOST = "192.168.0.198"
ARCO_PORT = 4001
READ_TIMEOUT_SEC = 2.5

# Allow your Vue dev server + prod domain
origins = [
    "http://localhost:5173",   # Vite dev
    "http://localhost:8080",
    "https://your-domain.tld", # replace with real
]

app = FastAPI(title="Rotor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def send_cmd(cmd: str) -> str:
    """
    Send a single DCU-1/Rotor-EZ command terminated by CR and return any ASCII reply.
    Many commands return nothing until a timeout; we still return whatever we got.
    """
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ARCO_HOST, ARCO_PORT), timeout=1.5
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TCP connect failed: {e}")

    try:
        msg = (cmd + "\r").encode("ascii")
        writer.write(msg)
        await writer.drain()

        # Collect whatever arrives for a short window; some stacks reply immediately,
        # others only on query commands (e.g., AI1).
        buf = bytearray()
        while True:
            try:
                chunk = await asyncio.wait_for(reader.read(256), timeout=READ_TIMEOUT_SEC)
            except asyncio.TimeoutError:
                break
            if not chunk:
                break
            buf.extend(chunk)
        return buf.decode("ascii", errors="ignore").strip()
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

def clamp_deg(v: int) -> int:
    v = int(round(v))
    if v < 0: v = 0
    if v > 359: v = 359
    return v

class GotoReq(BaseModel):
    deg: int

@app.get("/api/rotor/az")
async def get_az():
    """
    Query current azimuth. Common Rotor-EZ/DCU reply is a 0–359 integer (e.g., '123').
    """
    reply = await send_cmd("AI1")
    # Extract first 0–3 digit number
    import re
    m = re.search(r"\b(\d{1,3})\b", reply)
    if not m:
        # Some controllers reply with nothing; treat that as unknown
        raise HTTPException(status_code=502, detail=f"No azimuth in reply: '{reply}'")
    return {"az": int(m.group(1))}

@app.post("/api/rotor/goto")
async def goto(req: GotoReq):
    """
    Set target azimuth and start rotation.
    DCU/Rotor-EZ: AP1xxx (set preset 1), AM1 (move to preset 1).
    """
    az = clamp_deg(req.deg)
    preset = f"AP1{str(az).zfill(3)}"
    # Some stacks accept MGxxx to move directly; we use portable AP1+AM1
    await send_cmd(preset)
    await send_cmd("AM1")
    return {"ok": True, "target": az}

@app.post("/api/rotor/stop")
async def stop():
    await send_cmd("AS1")
    return {"ok": True}

@app.get("/api/rotor/ping")
async def ping():
    # Lightweight liveness check (no motion)
    try:
        await send_cmd("AI1")
        return {"ok": True}
    except HTTPException as e:
        raise e

// src/composables/useRotor.ts
export function useRotor(base = '/api') {
  async function getAz(): Promise<number|null> {
    const r = await fetch(`${base}/rotor/az`);
    if (!r.ok) return null;
    const j = await r.json();
    return typeof j.az === 'number' ? j.az : null;
  }
  async function gotoAz(deg: number) {
    await fetch(`${base}/rotor/goto`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ deg })
    });
  }
  async function stop() {
    await fetch(`${base}/rotor/stop`, { method: 'POST' });
  }
  return { getAz, gotoAz, stop };
}


Notes & gotchas

Command terminator: DCU-1/Rotor-EZ expects CR (\r).

Digits: Bearings are 0–359, usually zero-padded to 3 digits for preset commands (AP1xxx).

Concurrency: ARCO limits concurrent LAN clients—this API opens short-lived sockets per request (safe). Don’t keep long idle connections from multiple tools.

search the internet for how the rotator is being controlled over TCP/IP connection and port.