# WSJT-Z to OM0RX MSHV feature review

This review compares the locally maintained WSJT-Z automation build with the
OM0RX MSHV build. It is based on the local WSJT-Z patch inventory and source
notes, especially `docs/wsjtx/WSJTZ_AUTOMATION_PORTING.md` and the clean-build
`APPLIED-PATCHES.txt`.

| WSJT-Z capability | OM0RX MSHV status | Recommendation |
|---|---|---|
| Double-click a decoded station to begin a QSO | Fixed: the click now enters MSHV's native selected-decode path and also synchronizes Auto DX | Keep this native path authoritative |
| Six-message QSO sequence with selectable stages and immediate Tx buttons | MSHV already had seven functional stages but the panel could be clipped; it is now explicitly placed and labelled in the lower area | Ported as UI exposure, without duplicating sequence logic |
| Auto Call and Auto CQ fallback | Already covered by Auto DX target selection, CQ fallback, retry policy, and watchdogs | Do not duplicate |
| Direct caller pre-emption / reply lock | Already implemented, including exchange-only reply guards | Do not duplicate |
| DXCC and new-band/new-mode prioritization | Already implemented with richer award policies and compact decode statuses | Do not duplicate |
| Callsign, country, continent, signal and LoTW filters | Already implemented; MSHV also supports per-band country exclusions | Do not duplicate |
| Free-frequency / clear-slot selection | Already implemented by the MSHV slot finder | Do not duplicate |
| Worked-slot veto and log-race protection | Already implemented with Wavelog-backed history, local fallback, cooldown and permanent dedupe | Do not duplicate |
| Band hopping and QSY tracing | Already implemented with scheduled hopping, CAT confirmation and visible band separators | Do not duplicate |
| Automation decision visibility | MSHV exposes status and audit information, but a compact per-QSO event timeline would still improve diagnosis | Good future enhancement |
| Halt after the current transmit period | MSHV has stop/watchdog controls; a clearly labelled graceful-halt action should be evaluated separately | Optional future enhancement |

The main conclusion is that the valuable WSJT-Z interaction model is the
operator-visible QSO sequence and dependable manual decode selection. The
automation and filtering features themselves are already present in the OM0RX
MSHV build, generally with stronger station-specific safeguards.
