# Milestone 1: band-control acceptance

## Ownership rule

For the clean rebuild, WSJT-Z is the sole automation owner of the Flex dial
frequency. The backend may select and rank targets, but it must not retune the
radio before engaging one. A target on a different dial frequency is released
with the reason `dial-frequency-owner-blocked`.

The operator's explicit spot-click tune endpoint remains available. A legacy
backend-owned automation tune path can be selected only by explicitly setting
`operatorSettings.automation.dialFrequencyOwner` to `backend`; `wsjtz` is the
default and the fail-safe value for an invalid setting.

## Diagnostic contract

Each frequency-changing CAT request emitted by WSJT-Z writes an `OM0RX_QSY`
record containing a monotonically increasing sequence number, origin, CAT path,
and requested frequency. It must end with exactly one of:

- `ack`: the rig reports the requested frequency within one hertz;
- `timeout`: no matching rig report arrives within five seconds;
- `superseded`: another request replaces it before completion; or
- `failed`: the transceiver reports a control failure.

No-change CAT refreshes are deliberately not recorded as QSY transactions.

## Isolated verification completed

- Functional patch applies cleanly on top of the two build-only patches.
- The native WSJT-Z executable builds successfully.
- The executable starts under the isolated `OM0RX-WSJTZ-CLEAN` test profile.
- Backend tests prove that the default owner blocks direct automation tuning
  and that the explicit legacy owner still permits it.

## Live Flex qualification required

Run this only when the station is available for deliberate radio testing. Do
not enable Auto Call, Auto CQ, antenna automation, or the amplifier.

1. Start the clean executable with the isolated profile and configure its CAT
   connection to the Flex.
2. Select 20 m, 40 m, 15 m, 80 m, and 10 m manually, one at a time.
3. After every selection, confirm the Flex reaches the standard FT8 dial once
   and stays there for at least 30 seconds.
4. Confirm the log contains one request and one matching acknowledgement for
   each change, with origin `operator-band-selector`.
5. Enable only the native WSJT-Z band hopper and observe at least five hops.
6. Confirm every hop has origin `native-band-hopper`, one acknowledgement, and
   no immediate return to the previous band.
7. Start backend automation in a dry/no-TX state with a target on another band.
   Confirm it reports `dial-frequency-owner-blocked` and the Flex does not move.
8. Fail the milestone if any transaction times out, is unexpectedly
   superseded, oscillates, or lacks a matching acknowledgement.

POTA, SOTA, IOTA, WWFF, WWBOTA, ARLHS, and other award-reference exceptions
are explicitly outside this milestone.
