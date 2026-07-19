# Milestone 2: basic antenna policy

The clean rebuild retains the station's existing SmartSDR antenna routing as
an external station policy. It is deliberately not copied into the WSJT-Z
binary. This keeps CAT frequency ownership and physical antenna routing as two
separate responsibilities:

1. WSJT-Z requests the dial frequency and waits for the rig acknowledgement.
2. The OM0RX backend observes SmartSDR's reported slice frequency.
3. While receive state is explicitly confirmed, the backend applies the
   configured RX/TX antenna for that reported band.

## Basic mapping

| Bands | RX antenna | TX antenna |
| --- | --- | --- |
| 160 m, 80 m, 60 m, 40 m, 30 m | ANT2 | ANT2 |
| 20 m, 17 m, 15 m, 12 m, 10 m | ANT1 | ANT1 |

The mapping remains editable in Config > Flex & UDP through
`FLEX_ANTENNA_POLICY`. Per-band objects with distinct `rx` and `tx` values are
supported by the backend even though the current UI presents the basic
same-antenna selection.

## Safety behavior

- Explicit MOX, `TRANSMITTING`, and `PTT_REQUESTED` states block switching.
- Unknown transmit state also blocks switching; it does not time out into an
  assumed receive state.
- If several band reports arrive while TX is active, only the latest reported
  frequency is retained, and it is applied after an explicit receive/READY
  update.
- A failed antenna command does not update the successful-policy cache and is
  retried when state is polled or reported again.

The production gate still requires a positive TX-inhibit path if antenna
routing cannot be confirmed. Because clean WSJT-Z owns CAT/PTT directly, the
backend cannot honestly guarantee that interlock yet; it is tracked for the
final safety milestone and must not be represented as complete here.

POTA, SOTA, IOTA, WWFF, WWBOTA, ARLHS, and all other award-reference
exceptions are deferred. They do not alter this mapping or its trigger rules.

## Live acceptance

With the amplifier disabled, perform one confirmed QSY into each antenna group
and verify SmartSDR reports the expected RX and TX antenna. Then key a test
transmission, request a band in the other group, confirm no antenna command is
sent during TX, return explicitly to RX, and confirm the queued latest policy
is applied once.
