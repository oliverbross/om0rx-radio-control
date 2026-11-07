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
