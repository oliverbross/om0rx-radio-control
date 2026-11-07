# 10 m KPA standby investigation and KAT tune

Live evidence showed KPA500 fault 09, amplifier standby, FLEX in receive, and
10 m permitted by policy. Agent route attempts repeatedly failed with
`KPA500 fault is '09', expected '00'` from 13:25:09 through 13:26:32 local.
The route failure path requests verified standby. This was a fault-driven
standby, rather than a policy prohibition of 10 m. No contemporaneous high-power
SWR trace was available to prove the physical cause of the reflected-power trip.

The operator explicitly authorized KAT500 tuning. The guarded standby and
fault-clear commands succeeded, with KPA fault 00 and KAT fault 0. Tuning was
initially blocked because route proof was invalidated by fault clearing and
the remote API did not expose the coordinator's existing prepare-route action.

Added `station_prepare_route` to advertised commands and dispatch, delegating
to the existing `perform("prepare-route")` safety checks. No coordinator
interlocks changed. Regression gate: 152 Remote Agent/coordinator tests passed.
Canonical Windows Agent deployment commit:
`e3b973095ac5204d595327e77faa8b1b46404cd8`.

The Agent alone was gracefully restarted. At 13:31:15–13:31:30 Europe/Bratislava,
one guarded KAT500 tune succeeded at the then-current 28.397 MHz, FLEX ANT1,
KAT ANT1, with configured 25 W tune power, 1.5 target SWR and 30-second limit.
Tune transaction `a3a9cc7197254b32bcdb80c93aedce67` stored memory after proving
carrier off. Transaction SWR before/after was 1.2/1.2; final meter sample 1.18.
Final evidence: MOX false, interlock READY, KPA standby/fault00/output0W,
KAT not tuning/fault0, zero alarms, no Agent error. The authorized tune emitted
low-power RF; no amplified transmission was performed. A good low-power match
does not establish that high-power operation will not trip again.

## Supervised 5 W drive comparison, 13:52 local

The operator authorized and keyed one reduced-drive test. The configured
10 m amplifier drive was temporarily changed from 25 W to 5 W through the
authenticated config API; guarded Operate freshly confirmed 5 W before keying.
Frequency was 28.4314 MHz, FLEX ANT1/KAT ANT1. Live MOX was observed from
13:52:26.916 until 13:52:34.935 (approximately 8 seconds).

Concurrent live samples showed KPA output 90–102 W, KPA SWR 2.3–2.4, and KAT
SWR 1.25–1.27. Typical paired meter receipt timestamps were within 20–60 ms;
one later pair was approximately 384 ms apart. Both live flags were true.
KAT forward/reflected ADC counts during RF were approximately 673–774/30–38;
these are raw ADC counts, not watts. KPA stayed in Operate during this test,
fault 00; KAT fault 0. No fault trip occurred at 5 W drive.

The driver reads KPA power/SWR through ^WS and KAT SWR through VSWR, rather
than calculating these two SWR values from a shared source. The discrepancy
does not identify which meter is correct. Inspect the KPA-output to KAT-input
jumper/connectors with RF off, and compare against a suitable dummy load and/or
independent wattmeter before resuming higher-power tests.

After the test, PTT off and guarded standby were confirmed. The original
25 W 10 m setting was restored and the Agent restarted. The original active
configuration fingerprint was restored exactly:
`4ac89b36b8f2bec42fb28f745d656a1c713411b293736083373b9642a4918743`.
Settled evidence: MOX false, interlock READY, KPA standby/fault00, KAT fault0,
both accessory quality good, zero alarms and no Agent error. No safety policy
was weakened and no software logic was changed for this comparison.
