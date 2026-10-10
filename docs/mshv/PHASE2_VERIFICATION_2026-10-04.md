# Phase 2 frozen-candidate verification (2026-10-04)

## Candidate

- Runtime: `data/build/mshv-auto-dx/phase2-runtime`
- Upstream commit: `d960ae22de78940c6be9d95bd4817d233d02ee39`
- Maintained Phase 2 patch SHA-256: `010B76D628354951A7DCBB9ADFBD929A29425872C915B7FBDF5BB734B40EC3ED`
- Source-attestation SHA-256: `BEC888E6A013FEF5BB02B481C71558257889C57875445D8F06722CDA4262971E`
- `MSHV_OM0RX.exe` SHA-256: `5BC806BB45E93D83421FDF19DBCB4D96EF92FA13E4272CC3E68AF0C110E8A2AC`
- `om0rx-build.json` SHA-256: `EE4F0DB063EFDD3CBA3CBD07844FE80FEE0BDDB23F538E71F07AB00635B26BD9`
- `compiled-source.json` SHA-256: `F7CFA4FE955865378D7C6354BC6EAA947469DF2196C47E3F046F35BC8BFB9E75`
- Clean-build transcript: `data/build/mshv-auto-dx/phase2-native-build-final.log`
- Clean-build transcript SHA-256: `FB698DA29E8F4BA21FA7562FB1A7F9E8A96530F29953B7804EE961E8F3DAEFBF`

## Verification

- `scripts/mshv/assert_release.ps1`: passed.
- `scripts/mshv/test_mshv.ps1`: passed before and after linked native fixtures.
- Native fixtures passed: runtime configuration, target priority, scorer/tracker
  integration, delayed station gate, three fake-hardware PTT cycles, permit
  rejection/replay/halt/timeout/Stop/QSY/frequency races, history authority and
  pending-call band-change races, and tracker transaction/idempotency behavior.
- Packaged native-offline pytest: 1 passed.
- Expanded Phase 2 Python/API suite: 236 passed in 140.81 seconds.
- Full smoke suite: 711 passed in 194.02 seconds; two pre-existing
  `datetime.utcnow()` deprecation warnings.
- JavaScript syntax checks: passed for `sdc-bridge-server.js`,
  `digital-provider.js`, and `wsjtx-parser.js`.
- Python compile-all checks: passed for backend, services, radio control, and
  activity intelligence.
- `git diff --check`: passed (line-ending conversion warnings only).

The candidate was packaged only to the non-live Phase 2 staging runtime. It was
not promoted or launched. The running WSJT-Z fallback, services, and radio were
not stopped, restarted, or reconfigured during this verification.
