# WSJT-Z clean rebuild

This directory records the gated rebuild that starts from a pinned, clean
WSJT-Z source tree. The preserved customized build remains available only as a
behavior and rollback reference.

## Source identity

The pinned source is upstream tag `v2.0.14`, commit
`fa53f635462def9f37b54f63f18e407ecda2ba12`, tree
`2d23c72ddb826f18d21876ac7b6a89642ee0ef34`. It reports WSJT-X core version
`3.0.0` and WSJT-Z version `2.0.14`.

The `v3.0.2` title shown by the preserved customized executable is not an
upstream source identity: the old monolithic patch changed the core patch
number in `Versions.cmake`. The clean rebuild does not repeat that version
change.

## Milestone rules

1. Materialize the exact pinned source into `data/build/wsjt-z-clean/src`.
2. Keep that source pristine until the unmodified configure/build result is
   recorded.
3. If the local toolchain requires a compatibility patch, keep it isolated
   from functional patches and document why it is required.
4. Add one behavior at a time, with tests and a separately pushed milestone
   commit.
5. Never modify or delete `data/build/wsjt-z-om0rx`; it is the rollback and
   behavior reference.

## Prepare the source

```powershell
powershell -ExecutionPolicy Bypass -File scripts\wsjtz\prepare_clean_wsjtz.ps1
```

Use `-Force` only to discard and recreate the exact ignored clean-workspace
directory. The script refuses to remove any other path.

## Initial scope

The first production replacement contains stable band changing, the antenna
policy, display-only CS/DS, current-band DXCC priority, and essential logging
and safety. Cross-band cluster QSY and award-reference exceptions are later
work.

## Build-only compatibility patches

The pinned upstream tree does not configure on this Windows toolchain without
OmniRig COM installed, and it omits the FFTW threaded library while `jt9` calls
the threaded API. The first two patches address only those build conditions:

- `0001-build-allow-omnirig-off.patch`
- `0002-build-link-fftw-threads-on-windows.patch`

They do not change CAT/Hamlib behavior, band logic, decoding, automation, or
the user interface.

## Milestone 0 result

The clean baseline configured and built successfully after only the two
build-only compatibility patches. Artifact and toolchain hashes are recorded
in `build-lock.json`. A runtime smoke launch used the isolated
`OM0RX-WSJTZ-CLEAN` test profile; the launcher started no enrichment service
and rewrote no INI setting.

## Milestone 1 implementation

Patch `0100-band-qsy-transaction-tracing.patch` keeps the upstream band-change
path and adds correlated request/outcome diagnostics at its single CAT write
boundary. Backend automation now defaults to `wsjtz` as the dial-frequency
owner and refuses to issue a competing cross-frequency Flex tune. See
`band-control-acceptance.md` for the diagnostic contract and the deliberately
manual live-radio qualification.
