# MSHV Phase 2: Wavelog history authority

## Authority boundary

Wavelog is the only authoritative QSO history. The MSHV `mshvlog.adi`,
`mshvlog.edim`, and `worked.db` files are derived stores. They are never used
to promote an unacknowledged QSO into canonical history and are not recovery
sources when Wavelog delivery is pending or ambiguous.

The initial tracker is built only from the attested Wavelog-canonical ADIF
snapshot. A runtime with the `wavelog_history_delta_v2` capability is required;
older `offline_history_v1` packages cannot accept live Wavelog deltas safely.

## QSO lifecycle

The durable lifecycle is:

1. `type5_received`: the bridge forwards MSHV's provisional event immediately.
2. `type12_paired`: the authoritative ADIF event is paired using `TIME_OFF`
   tolerance, while its canonical identity continues to use `TIME_ON`.
3. `submitted`: the event is sent through the normal Wavelog logging path.
4. `pending`: Wavelog is unavailable or the result is not authoritative. The
   event remains in the outbox and provisional journal and is exposed to MSHV
   only as a negative target-inhibition identity.
5. `acknowledged` or `readback_verified`: Wavelog accepted the QSO, a prior
   dedupe record proves Wavelog success, or an exact structured readback proves
   the canonical record exists.
6. `native_applied`: MSHV has transactionally applied the acknowledged delta to
   `worked.db` and its SQLite idempotency ledger.

`outbox_queued`, a duplicate-looking message string, or a dedupe entry whose
prior outcome was only pending is never an acknowledgement. Pending events are
not written into the authoritative Postgres QSO read cache and cannot appear in
a canonical Wavelog export.

## Snapshot and delta integrity

Acknowledged deltas have a unique monotonically increasing sequence and a
SHA-256 hash chain. MSHV applies only the exact next sequence and records the
delta key in `wavelog_applied_deltas` in the same SQLite transaction as the
worked-status update. It then atomically commits
`settings/database/wavelog_delta_state.json`.

If MSHV stops after the SQLite commit but before the JSON cursor commit, the
backend repairs the cursor only when the SQLite ledger is an exact contiguous
prefix of the active acknowledged journal. Missing, malformed, reordered, or
unsupported rows fail closed.

The initial snapshot marker defines a generation. Derived native and ADIF logs
may evolve after import and are reported as non-authoritative warnings rather
than compared as immutable recovery images. The tracker is validated against
the baseline when no deltas are applied, or against the exact SQLite ledger and
cursor state after deltas.

## Availability states

- `healthy`: the attested Wavelog snapshot, provenance, tracker state, journal,
  and currently available source all validate.
- `offline-attested`: the source is temporarily unavailable, but the last
  attested snapshot plus acknowledged deltas remain valid.
- `blocked-diverged`: identity, provenance, sequence, hash, tracker, or cursor
  validation failed. Historical novelty is disabled.

Native history polling has a bounded four-second request deadline. A timeout,
invalid response, or a transition to `blocked-diverged` immediately revokes
historical-novelty target selection and revalidates queued, deferred,
cross-band, and nonstandard-frequency actions. Only an explicit station-directed
`calling-me` event remains exempt. Pending Wavelog calls are separately inhibited
so an outage cannot cause the same unacknowledged station to be selected again.

## Packaging and rollback

The Phase 2 maintained patch is
`docs/mshv/om0rx-wavelog-history-phase2.patch`. Packaging must use the
transactional installer and an approved `phase2-runtime` staging destination.
The immutable executable and patches are SHA-256 inventoried; mutable operator
state includes the tracker, its WAL/SHM files, and the Wavelog delta cursor.
Previous bundles are preserved for rollback. A staged package is not a live
deployment and does not authorize a provider switch or RF operation.

## Verified offline candidate (2026-10-04)

- Maintained Phase 2 patch SHA-256:
  `010B76D628354951A7DCBB9ADFBD929A29425872C915B7FBDF5BB734B40EC3ED`
- Source-diff attestation SHA-256:
  `BEC888E6A013FEF5BB02B481C71558257889C57875445D8F06722CDA4262971E`
- Staged executable SHA-256:
  `5BC806BB45E93D83421FDF19DBCB4D96EF92FA13E4272CC3E68AF0C110E8A2AC`
- Fresh single-job clean-build transcript:
  `data/build/mshv-auto-dx/phase2-native-build-final.log`
  (SHA-256 `FB698DA29E8F4BA21FA7562FB1A7F9E8A96530F29953B7804EE961E8F3DAEFBF`)
- Offline stage:
  `data/build/mshv-auto-dx/phase2-runtime`
- Release assertion and all 21 digital-engine preflight checks passed.
- Native package fixtures passed: runtime configuration, target scorer/tracker,
  station gate, linked PTT race/fake-hardware paths, tracker delta ledger, and
  release attestation.
- Expanded Phase 2/focused Python regression: 236 passed.
- Full smoke regression: 711 passed, with two unrelated `datetime.utcnow()`
  deprecation warnings.

The candidate was not promoted to the live runtime during this verification.
The running WSJT-Z fallback and radio state were not changed.
