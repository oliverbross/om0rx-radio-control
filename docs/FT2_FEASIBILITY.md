# FT2 feasibility notes

Date: 2026-05-26

## Current conclusion

Do not enable FT2 in the built-in Digital window until a callable FT2 RX decoder is available.

The project can decode FT8/FT4 through the current FT8 service boundary, but FT2 is not the same
drop-in decoder mode. FT2 uses a 3.8 second T/R cycle, 4-GFSK, 167 Hz bandwidth, and a Decodium
Raptor/Shannon-specific decode path.

## What was checked

- Official FT2 documentation describes FT2 as a 77-bit, LDPC(174,91), 4-GFSK mode with a 3.8 second
  cycle and `SUBMODE=FT2` logging.
- `elisir80/decodium3-build-macos` contains the maintained Decodium source and FT2 decoder code,
  including `Detector/FT2DecodeWorker.cpp` and `Detector/FtxFt2Stage7.cpp`.
- The Decodium source also builds a `jt9` command-line decoder. Internally it has an `nmode == 2`
  path for `decode_ft2_mode`.
- The installed local Decodium package at `C:\Program Files\Decodium` includes `jt9.exe`, but
  `jt9.exe --help` exposes FT8, FT4, JT9, JT65, Q65, FST4, FST4W, and MSK144 options only. It does
  not expose `-2` or `--ft2`, and both are rejected.
- `avantol/Otto` is an automation assistant for WSJT-X/Decodium via UDP/control behavior. It does
  not provide a standalone FT2 decoder for embedding in this project.

## Practical paths

1. Build a patched Decodium `jt9.exe` with an explicit `--ft2` CLI mode, then wrap it from
   `services/ft8_rx_decoder.py` through a new neutral digital decoder interface. This is the
   cleanest path if we can install the required Windows build toolchain and produce a redistributable
   executable.
2. Add an external Decodium bridge that consumes Decodium/WSJT-X UDP decode packets and feeds them
   into our Digital UI. This is useful operationally, but it is not a built-in FT2 decoder.
3. Wait for an official Decodium/Raptor CLI or library API that exposes FT2 RX directly.

## Non-goals

- Do not add FT2 to the UI as a selectable mode until RX works.
- Do not fake FT2 by running the FT4 decoder with a shorter cycle.
- Do not start implementing FT2 TX until FT2 RX can be validated with live audio or known-good
  fixture WAVs.
