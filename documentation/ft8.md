 build native FT8 TX/RX into your app without WSJT-X. The protocol is fully documented and there are usable reference libraries. Here’s the practical path.

What “direct FT8” entails (condensed)

Protocol facts you must match

77-bit payload + 14-bit CRC → LDPC(174,91) FEC → 174 coded bits → 58 symbols of 8-tone CPFSK (3 bits/symbol). Three 7×7 Costas arrays are embedded for time/frequency sync. 
wsjt.sourceforge.io

Tone spacing = symbol rate ≈ 6.25 Hz → 160 ms/symbol; a transmission is ~12.64 s inside a 15 s T/R cycle. 
files.tapr.org
+1

The official paper (QEX) is the gold-standard spec and includes public-domain snippets (source-encoding, generator/parity matrices filenames, etc.). 
wsjt.sourceforge.io

DSP/decoder pipeline (receive)

Audio in (e.g., 12 kHz or 48 kHz) → windowed FFT over the full 15 s capture → candidate detection across the passband.

Coarse time/freq sync using the Costas sequences → soft metrics for each symbol → LDPC(174,91) decode → CRC check → 77-bit payload → render message. (WSJT-X’s paper explains block detection, hybrid BP+OSD decoding, and AP-assisted retries; you don’t need all of that to get first decodes, but it boosts sensitivity a lot.) 
wsjt.sourceforge.io

Encoder (transmit)

Map your message → 77-bit payload → add CRC → LDPC encode to 174 bits → Gray-map to 8-FSK symbols → insert Costas arrays (begin/middle/end) → generate CPFSK baseband with gentle rise/fall and constant envelope → send to your radio’s audio path with tight time sync at 00/15/30/45 s. 
wsjt.sourceforge.io

Time & frequency discipline

Clock must be within ~±1 s (better: ±250 ms). Use NTP and guard against drift.

Frequency accuracy matters because the tone spacing is only ~6.25 Hz; keep audio chain and LO error low (or search over small Δf during sync). 
wsjt.sourceforge.io

Legal/interoperability notes

The authors explicitly allow independent implementations but require that anything called “FT8” adheres to the protocol and disallows robotic/unattended QSOs; GPLv3 applies if you reuse WSJT-X code. If you implement from the paper (or use a permissive library), you’re fine. 
wsjt.sourceforge.io

Build options

A) Use a permissive FT8 library (fastest way to working TX/RX)

kgoba/ft8_lib (MIT): C code for both encoding and decoding; comes with console examples and expects you to wire up live audio (e.g., PortAudio) and rig control. Great starting point and not GPL-encumbered. 
GitHub

Others exist (RTL-SDR oriented decoders, forks, etc.), but the above is the cleanest permissive base. 
GitHub

B) Roll your own from the spec (maximum control)

Use the QEX paper’s public-domain source-encoding and matrices; implement your own LDPC decode (belief propagation) and CPFSK modem. Expect substantial DSP work if you also want WSJT-X-class sensitivity (block detection, AP-aided decoding, signal subtraction for second-pass decodes). 
wsjt.sourceforge.io
+1

How this plugs into your existing stack

Audio I/O: your current app already handles spots/logging; add a small audio engine (PortAudio/Wasapi) for an input ring buffer (15 s) and an output buffer for TX baseband.

Rig control/PTT: use your existing CAT/SmartSDR hooks to set the TX audio path and key PTT cleanly at the 0.5 s mark of the slot.

Sequencer: implement the 6-message FT8 state machine (CQ → report → RRR/RR73/73) with “Call 1st” and AP-assisted heuristics so you interoperate smoothly. The QEX paper even diagrams the auto-sequencing logic. 
wsjt.sourceforge.io

Time sync: ensure periodic NTP disciplining and show a UI warning when offset >500 ms.

Message formatting: follow the 77-bit message types (standard, non-std calls, telemetry, DXpedition, etc.) so your decodes/encodes match everyone else. 
wsjt.sourceforge.io

Levels/AGC: keep TX audio low enough to avoid ALC action; keep RX AGC slow/off if possible (operator guidance mirrors WSJT-X best practices). 
europeanft8club.wordpress.com