# 1. Executive Summary

The project has strong domain coverage and unusually substantial automation regression tests, but its safety boundary does not match its capabilities: unauthenticated browser, HTTP, and WebSocket clients can reach station-control and transmit operations, and the configuration API returns live credentials. The most serious correctness risk is QSO delivery, where races and inconsistent acknowledgement/deduplication rules can discard the only retry copy while still marking a contact as worked. The FlexRadio path also has reproducible parser/locking defects and can report unacknowledged commands as successful, while several UI read paths substitute plausible fake radio data or silently switch to a different data source. Performance risk is concentrated in whole-database spot downloads, synchronous device/database work in async routes, repeated polling, and large multi-purpose modules. The best parts of the codebase are the explicit backend-owned digital state machine, targeted digital race tests, parameterized SQL in maintained query paths, keyset Wavelog pagination, and the escaped rendering pattern already used by `frontend/js/spots-standalone.js`; those patterns should become the standard everywhere.

## Review basis

- Scope: all maintained first-party Python, JavaScript, HTML/CSS, PowerShell, C#, configuration, launch, migration, and test code was inspected, together with vendor/archive boundaries and generated/runtime-file hygiene. Vendored FT8 source was treated as third-party input rather than reviewed for upstream implementation defects.
- Scale: approximately 98,000 first-party lines across 255 code files, excluding `vendor/`, `node_modules/`, generated build output, logs, databases, and archived documentation.
- Verified checks: Python compilation passed; JavaScript syntax checks passed; `tools/Om0rxAgent/Om0rxAgent.csproj` built with 0 warnings and 0 errors; the frontend module contract script passed.
- Static analysis: Ruff reported 456 findings, including three undefined names, 34 unused imports, 16 unused variables, 40 placeholder-free f-strings, and extensive legacy one-line-statement/bare-except debt. `radio_control/flex_radio.py:651` is an undefined name on the active backend path.
- Smoke tests: 330 tests passed. Two non-environmental assertions failed because the DIGITAL button behaviour and ATNO score no longer match their tests; 41 setup errors and four additional failures were caused by this review sandbox denying Python temporary-directory access. The advertised script-mode frontend contract check also fails independently because it calls a `tmp_path` test without the fixture.
- Runtime probes: an invalid `/api/frequency` request reproduced a `TypeError` in the validation exception handler instead of a 422 response; `/api/config` was confirmed to include populated secret-bearing keys. Secret values were not recorded in this report.
- Not exercised: live transmit, tune, rotor movement, external account writes, process shutdown/restart, and live database repair were intentionally excluded to avoid changing station or external state.

# 2. Prioritised Action Items

Priority definitions: **P0** — will cause data loss, security breach, or production crash. **P1** — likely to cause bugs or meaningfully degrade UX/performance under real conditions. **P2** — compounding technical debt, refactors, and pattern inconsistencies. **P3** — polish, consistency, and minor DX improvements.

## P0

### P0-01 — Put an authentication and origin boundary around every control surface

**Affected files / functions:** `bridge/sdc-bridge-server.js:startWebSocketServer`, `sendJson`, and the HTTP command server; `backend/core/__init__.py` CORS setup; `services/radio.py:register_radio_endpoints`; `services/wsjtx.py:register_wsjtx_endpoints`; `backend/api/ft8.py`, `backend/api/rotor.py`, `backend/api/server_control.py`, and `backend/api/spots.py` mutation routes; `services/websocket.py:websocket_endpoint`; `backend/main.py:__main__`.

**Problem:** The Node WebSocket server uses `new WebSocketServer({ port: WS_PORT })`, which listens on all interfaces, accepts every Origin, and lets any client send `wsjtx_command` messages. The loopback HTTP command API sends `Access-Control-Allow-Origin: *`, enabling hostile web pages to command it through the victim's browser. FastAPI has CORS configuration but no authentication, authorization, CSRF protection, Host/Origin enforcement, or WebSocket origin validation; if the documented remote-access setting is enabled, radio TX, FT8 TX, tune, rotor, config, process launch, restart, and shutdown are exposed. Direct execution of `backend/main.py` additionally binds `0.0.0.0` with reload enabled, contradicting the safer launch scripts.

**Fix prompt:**

> Secure all OM0RX control surfaces. In `bridge/sdc-bridge-server.js`, bind both command-capable servers to `127.0.0.1` by default, add an explicit remote opt-in, validate Origin/Host, and require a shared high-entropy capability token for every WSJT command. In FastAPI, add a single dependency/middleware used by every state-changing route in `services/radio.py`, `services/wsjtx.py`, `backend/api/ft8.py`, `backend/api/rotor.py`, `backend/api/server_control.py`, and `backend/api/spots.py`; require authentication for remote access, reject untrusted Origin/Host values, protect WebSocket handshakes, and make read-only versus control permissions explicit. Keep loopback as the default, make `backend/main.py` honor `BACKEND_HOST` and reload settings instead of hard-coding `0.0.0.0`/reload, update launchers to pass the bridge token without logging it, and add tests proving unauthenticated, cross-origin, and non-loopback command attempts fail while the local UI succeeds.

### P0-02 — Stop returning and logging credentials, session keys, and operator logs

**Affected files / functions:** `radio_control/settings_store.py:public_config_from_module`; `backend/api/server_control.py:get_config`; `backend/api/static_files.py:setup_static_files`; `radio_control/qrz_api.py:_get_session_key`; `services/wsjtx.py:get_launch_logs`; frontend configuration loading in `frontend/js/websocket.js` and `frontend/js/config-modal.js`.

**Problem:** `/api/config` serializes every allowed key, including database passwords/DSNs, cluster credentials, Wavelog API keys, and QRZ passwords. The entire logs directory is mounted unauthenticated at `/logs`, exposing ADIF contacts, outbox content, launch diagnostics, and `flex_debug.log`. QRZ authentication logs a URL containing credentials, the first 500 characters of the authentication response, and a session-key prefix. Any browser script that reaches the app—or an XSS finding below—can exfiltrate these values.

**Fix prompt:**

> Redesign configuration and diagnostics exposure in `radio_control/settings_store.py`, `backend/api/server_control.py`, `backend/api/static_files.py`, and `radio_control/qrz_api.py`. Return a typed public configuration DTO that omits all `SECRET_KEYS`; represent configured secrets only as booleans such as `WAVELOG_API_KEY_CONFIGURED`, and support an explicit unchanged-secret sentinel on save so opening the form cannot erase or echo a secret. Remove the `/logs` StaticFiles mount and replace the one frontend dependency on `/logs/qso_log.adif` with a scoped server-side worked-status endpoint. Never log URLs containing passwords/session parameters, XML authentication bodies, API keys, DSNs, or session-key fragments; redact structured errors and add tests that scan config responses and logs for known test secrets.

### P0-03 — Eliminate stored DOM XSS in log, country, and spots views

**Affected files / functions:** `frontend/js/local-log-modal.js:renderTable`; `frontend/js/wavelog-log-modal.js:renderTable`; `frontend/js/country-modal.js:updateInfoDisplay`; `frontend/spots-database.html:populateFilterOptions`, `updateTable`, and `showError`; the DataTables column configuration; security headers in the FastAPI app.

**Problem:** QSO, QRZ/Wavelog, and cluster/RBL fields are interpolated directly into `innerHTML` or passed to DataTables' HTML renderer. Callsigns, names, QTH, countries, comments, spotters, special tags, grids, and server error messages are externally sourced, so a stored payload can execute in the local UI. Because the app currently has unauthenticated transmit/config/process APIs and no restrictive CSP, this becomes a station-control compromise, not merely a visual defect. `frontend/js/spots-standalone.js:escapeStandaloneHtml` demonstrates the safer convention but is not applied consistently.

**Fix prompt:**

> Remove all untrusted HTML interpolation from `frontend/js/local-log-modal.js`, `frontend/js/wavelog-log-modal.js`, `frontend/js/country-modal.js`, and `frontend/spots-database.html`. Build cells with `createElement`/`textContent`, use DataTables text renderers for every external field, bind event listeners instead of inline handlers, and keep HTML only for fixed application-owned markup. Introduce one shared escaping/DOM utility based on the existing `escapeStandaloneHtml` pattern, add a restrictive Content-Security-Policy that disallows inline script, and add browser/DOM tests using payloads such as `<img src=x onerror=...>` in callsign, comment, country, grid, name, QTH, and error fields.

### P0-04 — Make QSO delivery a durable, single-source state machine

**Affected files / functions:** `radio_control/qso_outbox.py:enqueue_adif`, `replay`, and `_rewrite`; `services/qso_logging.py:log_qso`, `_claim_dedupe_keys`, and `_record_dedupe_entries`; `services/wsjtx.py:WSJTXService.log_qso`, `_schedule_wavelog_outbox_replay`, and `_record_logged_qso_in_status_cache`; `bridge/sdc-bridge-server.js:retryLoggedQsoUploadItem`, `uploadLoggedQsoToBackend`, and `loggedQsoResultSucceeded`; related outbox/digital race tests.

**Problem:** `replay()` reads the outbox, awaits uploads, then rewrites the old snapshot; an `enqueue_adif()` during that window is erased. `_rewrite()` truncates the primary file non-atomically. Both backend logging paths record dedupe completion when only the local ADIF write succeeded, so a failed Wavelog upload plus failed outbox write is never retried; the WSJT path also marks the contact worked before any durable Wavelog/outbox success. The bridge removes its retry record on any HTTP 2xx even when the response body says `success:false`, and its UI deliberately treats a durable `outbox_queued` result as failure. A recent-Wavelog duplicate response falsely claims `adif_saved:true` without writing the ADIF file.

**Fix prompt:**

> Replace the split QSO acknowledgement logic in `radio_control/qso_outbox.py`, `services/qso_logging.py`, `services/wsjtx.py`, and `bridge/sdc-bridge-server.js` with one explicit delivery state machine: `received -> durably_queued -> uploaded/duplicate`, with local-archive status tracked separately. Serialize enqueue/replay using one process-wide lock (and file/process locking if multiple processes can write), write queue changes through fsynced temp-file replacement, and never advance dedupe/worked status unless Wavelog accepted the QSO or a durable retry record exists. The bridge must inspect the JSON success/durable-state fields before deleting its queue item; queued-offline should display as a successful durable save with a pending-sync badge. Add deterministic barrier-based tests for enqueue during replay, two replay callers, write failure after Wavelog failure, HTTP 200 with `success:false`, process restart, duplicate Wavelog response, and local ADIF-only outcomes.

## P1

### P1-01 — Return a real 422 response from the validation exception handler

**Affected files / functions:** `backend/core/__init__.py:validation_exception_handler`.

**Problem:** The registered FastAPI exception handler returns a plain dict, which is not an ASGI response in this context. An invalid `/api/frequency` request reproduces `TypeError: 'dict' object is not callable` instead of a 422. The handler also logs the raw request body, which can include credentials from configuration requests.

**Fix prompt:**

> Fix `backend/core/__init__.py:validation_exception_handler` to return `fastapi.responses.JSONResponse(status_code=422, content=...)` with JSON-serializable, stable validation details. Do not log raw bodies; log only method, path, request ID, and sanitized field names. Add TestClient coverage for missing, wrong-type, and out-of-range radio/config payloads and assert a 422 response with no secret values in captured logs.

### P1-02 — Repair Flex snapshot parsing and lock ownership

**Affected files / functions:** `radio_control/flex_radio.py:FlexCtl.get_current_levels`, especially lines around lock acquisition, connection failure, and `_record_antenna_values`; `tests/smoke/test_flex_connection_lifecycle.py`.

**Problem:** `get_current_levels()` passes undefined `state_changed` to `_record_antenna_values`, raising during active slice parsing; a broad receive exception hides the failure and returns stale/partial state. On connection failure it releases `_io_lock` before returning and the `finally` block releases it again, producing a lock ownership error. The 377-line method duplicates parsers already present in the subscription path, making the two state interpretations drift.

**Fix prompt:**

> Refactor `FlexCtl.get_current_levels` in `radio_control/flex_radio.py` to use `with self._io_lock`, with no manual early release, and route every received line through one shared parser used by both snapshot and subscription updates. Define an explicit snapshot change map or remove that parameter; do not suppress parser programming errors as normal socket timeouts. Add fake-socket tests for connect failure, antenna fields, fragmented/multiple response lines, timeout, and repeated calls, and assert the lock is always reusable and snapshots contain the parsed antenna/state values.

### P1-03 — Never report an unacknowledged radio command as successful

**Affected files / functions:** `radio_control/flex_radio.py:FlexCtl._send_with_response` and `_send`; callers in `services/radio.py`, `backend/api/spots.py`, and antenna enforcement.

**Problem:** If `_send_with_response()` sees unrelated socket traffic but never receives its matching `R{sequence}` response, it logs a warning and returns `(True, "")`. Routes then broadcast the requested state and the UI confirms success even though the radio rejected, lost, or never processed the command.

**Fix prompt:**

> Change `FlexCtl._send_with_response` so only a matching success response returns success. Return a typed result distinguishing accepted, radio-rejected, timed-out, disconnected, and indeterminate outcomes; preserve asynchronous status lines for the shared parser instead of treating them as acknowledgement. Update radio/spot/antenna callers to broadcast only confirmed or subsequently reconciled state, show a concise user error on failure, and add tests with unrelated status traffic, mismatched sequence IDs, radio error codes, empty reads, and delayed matching replies.

### P1-04 — Fail closed when antenna switching may overlap transmission

**Affected files / functions:** `radio_control/flex_radio.py:_tx_active_recently`, `enforce_antenna_policy`, `_record_basic_status_from_line`, and snapshot-triggered policy enforcement; antenna tests in `tests/smoke/test_flex_connection_lifecycle.py`.

**Problem:** A MOX/interlock transmit state older than two seconds is forcibly rewritten to receive/READY. Legitimate FT8/FT4 or voice transmissions can exceed two seconds without a repeated state packet, allowing RX/TX antenna switching while RF is active. This is a dangerous fail-open heuristic.

**Fix prompt:**

> Make antenna switching in `radio_control/flex_radio.py` fail closed. Any explicit MOX, `TRANSMITTING`, or `PTT_REQUESTED` state must block switching until an explicit receive/READY update is parsed; a timeout may mark the state unknown but must not clear it or permit switching. Queue one pending policy application and execute it only after confirmed RX, expose the deferred/unknown state to the UI, and add tests for transmissions longer than two seconds, missing receive updates, reconnect during TX, and multiple queued band changes.

### P1-05 — Remove fake radio defaults and preserve valid zero values

**Affected files / functions:** `services/websocket.py:websocket_endpoint` initial payload; `backend/api/health.py:get_status`; `frontend/js/websocket.js:updateRadioStatus` and initial-state rendering.

**Problem:** Disconnected or failed snapshots are presented as a plausible station at 14.074 MHz/USB with fixed filters and power levels. Python `or` chains also replace valid zero volume, RF power, tune power, mic level, monitor level, filter edge, and AGC threshold values. Operators cannot distinguish authoritative data from fabricated fallback data, and controls can visually jump from fake initial values to the real radio.

**Fix prompt:**

> Replace fallback radio values in `services/websocket.py` and `backend/api/health.py` with a typed snapshot containing `connected`, `known`, `stale`, `observed_at`, and nullable fields. Coalesce only on `is None`, never on falsiness, so zero remains valid. Update `frontend/js/websocket.js` and templates to show disabled controls/skeletons or “Unavailable” until authoritative data exists, retain the last observed snapshot only when explicitly marked stale, and add disconnected, partial, and all-zero snapshot tests.

### P1-06 — Introduce one validated, non-blocking radio command layer

**Affected files / functions:** all request models and handlers in `services/radio.py`; duplicate models in `backend/core/models.py`; synchronous Flex calls in async routes; similar command handling in `backend/api/spots.py:tune_to_spot`.

**Problem:** Radio request models accept arbitrary floats, integers, strings, filter order, DSP names, modes, bands, and steps. Approximately twenty near-identical async handlers call blocking socket methods that may wait 1.5 seconds, serially blocking the event loop. Each raises a 400 inside a broad `except Exception` that converts it to 500 and exposes internal exception text.

**Fix prompt:**

> Refactor `services/radio.py` into one command executor with constrained Pydantic models (`Field` ranges and `Literal`/enums), a serialized worker or `asyncio.to_thread` boundary around Flex I/O, explicit timeouts, and a shared result-to-HTTP mapping. Preserve `HTTPException`, return 400/409 for rejected/unsafe commands, 503 for disconnected hardware, and 504 for timeout; broadcast only reconciled state. Delete duplicate request DTOs from `backend/core/models.py`, reuse the command layer from spot tuning, and add boundary tests for frequency, filter ordering, power/levels, modes, DSP controls, and concurrent requests.

### P1-07 — Do not silently skip Wavelog records or retain deleted QSOs forever

**Affected files / functions:** `radio_control/wavelog_duckdb_sync.py:sync`, `_fetch_changed_records`, `_convert_wavelog_to_duckdb`; `radio_control/postgres_wavelog_sync.py:sync`; sync metadata and tests.

**Problem:** Per-record conversion/upsert exceptions are logged and ignored while later records advance the `(last_modified, id)` watermark. The bad record is permanently skipped on both DuckDB and PostgreSQL backends. Source deletions are never reconciled, so a QSO removed or merged in Wavelog remains in the supposedly authoritative local worked/confirmed cache and can incorrectly block future automation.

**Fix prompt:**

> Make Wavelog cache synchronization lossless in `radio_control/wavelog_duckdb_sync.py` and `radio_control/postgres_wavelog_sync.py`. Process each batch transactionally and advance the watermark only past durably committed records; on a poison record either fail/rollback the batch or persist it in a visible dead-letter table without advancing beyond it. Add periodic deletion reconciliation using a source tombstone/version feed if available, otherwise a bounded ID audit/full reconciliation, and report degraded status until resolved. Test conversion failure in the middle of a batch, retry recovery, equal timestamps, rollback, deletion, and parity between DuckDB and PostgreSQL.

### P1-08 — Refresh Activity Intelligence snapshots atomically

**Affected files / functions:** `activity_intelligence/services.py:_refresh_adapter`; `activity_intelligence/repository.py:delete_current_source_records` and all `upsert_*` methods.

**Problem:** A refresh parses the new payload, deletes the current source records, and then calls several upsert methods that each commit independently. Any failure after deletion leaves a partial or empty new snapshot and destroys the last known-good data, even though the source is then merely marked failed.

**Fix prompt:**

> Add transaction ownership to `activity_intelligence/repository.py` and make `ActivityIntelligenceService._refresh_adapter` publish a source snapshot atomically. Parse and validate fully first, then stage/delete/upsert all entity types and source state in one transaction; rollback must preserve the previous snapshot. Avoid commits inside repository methods when a caller transaction is active, expose the age of the last good snapshot, and add failure injection after each entity type to prove no partial refresh becomes visible.

### P1-09 — Replace whole-database spots downloads with bounded server-side queries

**Affected files / functions:** `backend/api/spots.py:get_recent_spots`; `radio_control/spots_logger.py:get_recent_spots` and filtered queries; `frontend/spots-database.html:loadData`, `autoRefreshSpots`, `refreshDataWithFilters`, `updateTable`, and chart/stat functions.

**Problem:** `/api/spots/recent` defaults to `limit=999999` without a maximum. The database page downloads the entire growing table on initial load and again through three separate refresh paths, copies and filters it in JavaScript, rebuilds charts, and loads it into client-side DataTables every 30 seconds. Memory, database work, JSON serialization, egress, and main-thread rendering all grow without bound; a cache fallback silently changes the data source and semantics.

**Fix prompt:**

> Redesign spots history as bounded server-side search. Cap every limit in `backend/api/spots.py` and `radio_control/spots_logger.py`, add keyset/cursor pagination plus server-side callsign/spotter/band/mode/country/zone/frequency/worked filters and separate aggregate endpoints for charts, and return source/freshness metadata. Configure DataTables for server-side paging, consolidate the three fetch paths into one cancellable request with `AbortController`, render only the current page, and show an explicit database-unavailable state instead of substituting a different cache. Add response-size, pagination-stability, filter, empty-result, and large-table performance tests.

### P1-10 — Stop launchers from killing unrelated processes

**Affected files / functions:** `scripts/start/start_webapp.ps1` global Node cleanup; `start_all.ps1:Stop-KnownRuntimePorts`, `Stop-ProjectProcesses`; `scripts/start/start_services_only.ps1` equivalents; `tools/Om0rxAgent/AgentSupervisor.cs:ProjectProcessQueryScript`, `StopProjectProcessesAsync`, and repair/stop flows.

**Problem:** `start_webapp.ps1` force-stops every Node process. The primary supervisors kill any process owning hard-coded ports 8080, 8081, 8091, 8092, 12166, and 2237, regardless of executable path or project ownership; process queries also match any `backend.main:app` command outside this project. Starting or repairing OM0RX can terminate unrelated development servers and applications.

**Fix prompt:**

> Make process lifecycle ownership explicit in `start_all.ps1`, `scripts/start/start_services_only.ps1`, `scripts/start/start_webapp.ps1`, and `tools/Om0rxAgent/AgentSupervisor.cs`. Persist child PIDs plus creation time/executable/project root in an ignored runtime manifest, stop only verified descendants/owned PIDs, and if a required port belongs to another process, abort with the PID/executable and a user-actionable message rather than killing it. Remove the global Node termination and broad `backend.main:app` matching. Add tests or dry-run helpers using unrelated mock port owners and multiple OM0RX roots.

### P1-11 — Make settings writes atomic, serialized, and schema-validated

**Affected files / functions:** `radio_control/settings_store.py:_read_json`, `_write_json`, and `save_config_updates`; `backend/api/server_control.py:save_config` and `test_postgres_config`; rotor/FT8 settings writers; `tools/Om0rxAgent/AgentSettings.cs:Load` and `Save`.

**Problem:** Settings use read-modify-truncate-write with no lock or atomic replacement. Concurrent config, rotor, and automation updates can lose each other or leave invalid JSON after interruption. Values are allowlisted by key but not validated by type/range/shape, then immediately assigned into the live config module; malformed values can break later services. The tray agent has the same non-atomic write pattern.

**Fix prompt:**

> Build a typed settings service for `radio_control/settings_store.py` and `backend/api/server_control.py`: validate the complete merged configuration with Pydantic before persistence, reject unknown/invalid values with 422, serialize updates through one lock, and use same-directory temp write + flush/fsync + atomic replace with a recoverable backup. Provide patch semantics/versioning so independent sections do not overwrite each other, and update rotor/FT8 callers to use the same service. Apply equivalent atomic JSON handling and corrupt-file recovery to `tools/Om0rxAgent/AgentSettings.cs`; add concurrent-update, interruption, invalid-shape, secret-sentinel, and recovery tests.

### P1-12 — Remove unpinned runtime CDN dependencies from the station UI

**Affected files / functions:** `frontend/index.html`, `frontend/ft8.html`, `frontend/spots.html`, `frontend/visual-map.html`, and `frontend/spots-database.html` external Vue, TopoJSON, Chart.js, jQuery, and DataTables assets.

**Problem:** Core pages load `vue@3` and other libraries from public CDNs at runtime; several are floating/unpinned and none use Subresource Integrity. Internet/DNS/CDN failure can blank a local radio-control interface, and an upstream compromise or unexpected major/minor change runs with access to the station APIs.

**Fix prompt:**

> Vendor exact production builds of Vue, TopoJSON, Chart.js, jQuery, and DataTables under `frontend/vendor/` (or introduce a reproducible local asset build) and load them from the FastAPI origin. Pin versions/hashes in the package lock or an asset manifest, remove floating CDN URLs, add CSP-compatible script loading, and create an offline browser smoke test that blocks all external network access while opening every HTML entry point.

### P1-13 — Fail visibly instead of mounting a partial application

**Affected files / functions:** `frontend/templates-loader.js:resolveTemplateIncludes`, per-template fetch loop, and `insertAllTemplates`; standalone template loaders in `frontend/js/ft8-standalone.js`, `spots-standalone.js`, and `visual-map-standalone.js`.

**Problem:** A required template or nested partial can fail, be stored as empty, and still trigger `templates-loaded`; Vue then mounts an incomplete UI with missing controls and only a console error. There is no timeout, retry, integrity check, or visible fatal state, so the operator can believe the control surface is complete when safety/feedback elements are absent.

**Fix prompt:**

> Refactor `frontend/templates-loader.js` around one `Promise.all`/`Promise.allSettled` manifest with required versus optional fragments, request timeouts, and a small bounded retry. Do not dispatch `templates-loaded` or mount Vue when any required fragment/partial is absent; render a fixed app-shell error listing the failed asset with a Retry button. Reuse the loader in standalone pages, add a manifest/DOM contract test for required target IDs, and browser-test a 404, timeout, and malformed include.

### P1-14 — Bound and harden external XML/feed parsing

**Affected files / functions:** `radio_control/qrz_api.py` XML parsing; `activity_intelligence/adapters.py` XML/feed adapters; `backend/api/solar.py` remote XML parsing; `scripts/maintenance/update_zone_overlays.py` KML parsing; HTTP client response handling.

**Problem:** Externally supplied XML/KML is read into memory and parsed with `xml.etree.ElementTree` without a response-size limit. Malformed or adversarial feeds can consume excessive memory/CPU and stall the event loop; error paths sometimes include raw remote content or exception detail.

**Fix prompt:**

> Harden all external XML/feed ingestion in `radio_control/qrz_api.py`, `activity_intelligence/adapters.py`, `backend/api/solar.py`, and `scripts/maintenance/update_zone_overlays.py`. Enforce content-length and streamed byte caps, use `defusedxml` (or an equivalently hardened parser), parse off the event loop where appropriate, validate expected root/schema/cardinality, and log only source/status/hash plus sanitized errors. Add oversized, entity-expansion, deeply nested, malformed, wrong-content-type, timeout, and redirect tests.

## P2

### P2-01 — Register routes once and make the quality gate inspect the real app

**Affected files / functions:** `backend/main.py:register_all_services`, `initialize_services`, and lifespan; `scripts/maintenance/check_project.ps1`; `tests/smoke/test_frontend_contracts.py`; `pyproject.toml` Ruff/pytest configuration; missing CI workflow.

**Problem:** Routes are registered during lifespan after device/database initialization, so importing the app yields an incomplete route table and repeated lifespans can duplicate routes. The duplicate-route gate therefore passes without scanning the real routes. The advertised safe smoke script runs pytest tests as plain Python; `test_frontend_contracts.py` now calls a `tmp_path` function without its fixture. Ruff is not run despite active undefined names, and two maintained FT8 assertions currently disagree with implementation.

**Fix prompt:**

> Introduce a FastAPI app factory in `backend/main.py` that registers routers/static routes exactly once during construction and uses lifespan only to create/stop dependencies. Update `scripts/maintenance/check_project.ps1` to instantiate that app for route scans, run `python -m pytest tests/smoke -q` rather than invoking pytest files as scripts, and run Ruff with at least `F`, `E9`, and selected bug/security rules. Resolve the current DIGITAL-button and ATNO-score contract drift by documenting the intended behaviour and updating implementation/tests together. Add a Windows CI workflow that runs Python/JS syntax, Ruff, smoke tests, route duplication, and the .NET build.

### P2-02 — Make reads side-effect free and serve radio/spot state from shared snapshots

**Affected files / functions:** `backend/api/spots.py:get_spots` and `search_filtered_spots`; `activity_intelligence/services.py:enrich_spot`; `backend/api/health.py:get_status`; `services/websocket.py` initial status; `services/background_tasks.py:poll_radio_status`; `frontend/js/websocket.js:startRadioStatusReconciliation`.

**Problem:** A GET of `/api/spots` mutates the shared cache and runs uncertain classification, CTY, local-heard, and Activity Intelligence enrichment per row; some enrichment persists samples. Spot search and status routes perform synchronous DB/device work inside async handlers. Each browser also asks the radio for a fresh snapshot every ten seconds while the backend already polls it, multiplying serialized radio commands as clients increase.

**Fix prompt:**

> Make background ingestion the sole owner of radio I/O and spot enrichment. In `services/background_tasks.py`, maintain immutable/versioned radio and spot snapshots with freshness metadata; ingest/enrich each spot once before caching/persistence. Change `backend/api/health.py`, `services/websocket.py`, and `backend/api/spots.py` reads to return copies/slices of those snapshots without writes or device queries, and move unavoidable DB work to bounded worker threads. Let the frontend reconcile from a cheap cached endpoint only after a stale/missed-WebSocket threshold. Add tests that GETs do not mutate repositories, N clients do not increase radio command rate, and stale snapshots are labelled.

### P2-03 — Use one authoritative spots state and one detached-window transport

**Affected files / functions:** `frontend/js/dx-spots.js:getVisualCandidateSpots`, `getVisualBaseSpots`, `loadVisualFallbackSpots`, `saveSpotsPopoutState`, `startSpotsCommandListener`; `frontend/js/spots-standalone.js`; `backend/api/spots.py:popout-command` endpoints.

**Problem:** An empty filtered result is treated as missing data, causing the visual map to switch to database or live-cache fallback rows; timestamp-less rows bypass the selected time window. Detached spots simultaneously use localStorage snapshots every second (at least 500 rows), BroadcastChannel, storage events, backend WebSocket, and 750 ms HTTP polling. This creates inconsistent provenance, redundant serialization/disk writes, unnecessary requests, and a map that changes data sources without telling the user.

**Fix prompt:**

> Define one spots query state (`loading | ready | empty | error`) with source, filters, cursor, and freshness, shared by table and visual map. In `frontend/js/dx-spots.js`, never interpret an empty authoritative result as a reason to show other data, and exclude missing timestamps when a time window is active. For the detached window, choose BroadcastChannel for same-origin browser windows and one WebSocket/native bridge fallback; send versioned deltas/query state rather than full localStorage snapshots, remove storage-event and 750 ms polling duplication, and show source/freshness in both windows. Add empty-filter, source-failure, stale-command, detach/reattach, and out-of-order version tests.

### P2-04 — Add Activity Intelligence retention, indexes, and resilient PostgreSQL connections

**Affected files / functions:** `activity_intelligence/repository.py:_initialize_schema`, `upsert_rbn_spot`, `upsert_station_state_sample`, lookup queries, and `_PostgresActivityConnection`; `activity_intelligence/services.py` pruning.

**Problem:** Only raw payloads are pruned. RBN spots and station-state samples grow indefinitely, and no indexes support timestamp/callsign/band, alias, activation, contest, or source queries. PostgreSQL mode keeps one process-long connection rather than using a pool/reconnect boundary. Query latency and storage will compound with uptime, and a dropped connection can disable the feature until restart.

**Fix prompt:**

> Add configurable retention and batched pruning for `ai_rbn_spots`, `ai_station_state_samples`, expired activations, old space-weather snapshots, and obsolete source rows. Create indexes matching actual predicates/orderings (timestamp, spotted call + band + timestamp, alias call, source ID, activation last-seen/expiry, contest dates) for both DuckDB and PostgreSQL. Replace the single PostgreSQL connection wrapper with a small pool or per-operation reconnect/retry transaction boundary, expose row counts/prune diagnostics, and add migration plus large-table query-plan/performance tests.

### P2-05 — Broadcast WebSocket messages concurrently with backpressure

**Affected files / functions:** `services/websocket.py:ConnectionManager.broadcast` and `close_all`.

**Problem:** Clients are awaited sequentially with a 0.5-second timeout. Several slow or suspended clients delay every later client and the caller by `N * 0.5s`, affecting status and spot delivery. There is no per-client queue, coalescing, or backpressure policy for high-frequency state.

**Fix prompt:**

> Refactor `services/websocket.py:ConnectionManager` to fan out concurrently with `asyncio.gather`/TaskGroup and one overall deadline, disconnect failed clients after collection, and avoid holding locks during network I/O. For status/spots, use a bounded per-client latest-value queue or coalescing so a slow client cannot accumulate stale frames. Add tests with fast, slow, failing, and disconnecting fake clients and assert broadcast latency is bounded independently of client count.

### P2-06 — Standardize API success/error contracts and hide internal exception text

**Affected files / functions:** `backend/api/server_control.py`, `backend/api/spots.py`, `backend/api/cluster.py`, `backend/api/rotor.py`; `services/qso_logging.py`, `services/wsjtx.py`, and `services/radio.py`; frontend fetch handlers across `frontend/js/`.

**Problem:** Some failures return HTTP 200 with `{success:false}`, others raise 400/500, and payloads alternate among `ok`, `success`, `error`, `message`, and `detail`. Several routes return `str(e)` to the browser. Frontend callers inconsistently check `response.ok`, a payload flag, both, or neither—the bridge QSO-loss issue is one consequence.

**Fix prompt:**

> Define one API envelope and error taxonomy for OM0RX: use HTTP status for transport/outcome, a stable machine code, safe user message, request ID, and optional typed data; never expose raw exception strings. Add shared FastAPI exception handlers and a small frontend `apiClient` that validates JSON, checks both protocol and schema, applies timeout/abort, and maps errors consistently. Migrate server-control, spots, cluster, rotor, radio, QSO, and WSJT endpoints first, then update every frontend/bridge caller and add contract tests for success, validation, disconnected hardware, conflict, timeout, and internal failure.

### P2-07 — Split the largest modules by domain and ownership

**Affected files / functions:** `frontend/js/dx-spots.js` (~5,800 lines), `frontend/js/ft8-modal.js` (~4,400), `frontend/js/app-main.js` (~2,400), `frontend/main-styles.css` (~5,600); `services/digital_automation.py` (~3,300), `services/wsjtx.py` (~3,100), `services/ft8_service.py` (~2,300); `radio_control/flex_radio.py`; `tools/Om0rxAgent/AgentSupervisor.cs` (~1,500). Large functions include `register_wsjtx_endpoints`, `WSJTXService.log_qso`, `FlexCtl.get_current_levels`, `refresh_radio_state`, and automation target selection.

**Problem:** UI state, network transport, persistence, rendering, policy, process launch, and hardware parsing are co-located. This drives duplicate logic (for example two near-identical standalone table renderers), broad exception handling, circular imports, and contract tests that assert source strings rather than behaviour. Small changes have a large regression surface.

**Fix prompt:**

> Decompose the listed modules without changing behaviour. Extract typed domain services/state machines first (radio protocol parser/transport, QSO delivery, WSJT bridge client/launcher, automation policy/store, spots query/render/visual state, tray process ownership), then thin FastAPI routes and Vue mixins around them. Keep public DTOs and pure selectors in small modules, co-locate unit tests with each boundary, replace source-text assertions with behaviour/DOM/API tests, and enforce pragmatic size/complexity limits only after the split.

### P2-08 — Remove the legacy Tk bridge dependency from backend startup

**Affected files / functions:** `backend/main.py` import of `FlexCtl`; `radio_control/dxbridge.py`; `radio_control/bridge_runtime.py`; `radio_control/spot_ui.py`; `radio_control/ui_dialogs.py`; `radio_control/ui_components.py`; `radio_control/classifier.py`; `radio_control/flex_radio.py:FlexSpots`.

**Problem:** The backend imports `FlexCtl` through the legacy `dxbridge.py` entry point. That import performs a MySQL dependency check, configures logging, and loads the Tk UI/runtime/classifier tree solely to re-export a class already defined in `radio_control/flex_radio.py`. It creates startup side effects, hides dead code, and leaves two undefined `COLOR_DEFAULT` references in a nominally supported module.

**Fix prompt:**

> Change `backend/main.py` to import `FlexCtl` directly from `radio_control.flex_radio`. Confirm no documented launcher invokes `python -m radio_control.dxbridge`; then retire the legacy Tk bridge modules (`dxbridge.py`, `bridge_runtime.py`, `spot_ui.py`, `ui_dialogs.py`, `ui_components.py`, `classifier.py`) and `FlexSpots`, preserving any still-used pure helpers in appropriately named modules. Remove their tests/config hooks and verify backend import no longer initializes logging, MySQL, or Tk.

### P2-09 — Separate portable defaults, operator preferences, and transient runtime state

**Affected files / functions:** tracked `settings/app_settings.json`; `radio_control/config.py`; settings save paths in `frontend/js/config-modal.js`, `frontend/js/ft8-modal.js`, `services/digital_automation.py`; `settings/window_layout.json` and `.gitignore`.

**Problem:** The tracked settings file contains machine-specific absolute paths, LAN IPs, callsign/grid, database choice, and transient automation counters/timestamps such as `autoCQRemaining`, `autoCallRemaining`, `lastHopAt`, and `lastHopKey`. Runtime use continually dirties the repository, stale session state can affect the next startup, and defaults are not portable to another checkout. Window layout is also runtime state but is currently untracked without a clear ignore/default split.

**Fix prompt:**

> Split configuration into a tracked portable defaults/schema file, ignored station-local preferences, ignored secrets, and a dedicated ignored runtime-state store for counters, active attempts, hop timestamps, and window geometry. Remove absolute project paths in favour of project-relative defaults resolved at runtime, provide a one-time migration from `settings/app_settings.json`, and document precedence. Ensure reset-to-default never touches secrets and runtime state is crash-safe but not treated as configuration.

### P2-10 — Make dependency resolution and continuous checks reproducible

**Affected files / functions:** `requirements.txt`, `pyproject.toml`, `package.json`, `package-lock.json`, `scripts/maintenance/check_project.ps1`, repository CI configuration.

**Problem:** Python dependencies are duplicated between two manifests with only lower bounds and no lock/constraints hashes, so installs can change underneath the application. There is no checked-in CI workflow, no automated audit by default, and the local gate scans recursively rather than from tracked files, making generated/unreadable directories capable of breaking checks.

**Fix prompt:**

> Choose `pyproject.toml` as the Python source of truth, generate a platform-appropriate locked constraints file with hashes, and make `requirements.txt` generated or remove it. Keep Node installs on `npm ci`, add scheduled/opt-in dependency audits, and update `check_project.ps1` to enumerate tracked files (`git ls-files`/explicit roots) instead of arbitrary caches/build output. Add CI for supported Python/Windows versions and a documented lock-update workflow with offline smoke validation.

### P2-11 — Make frontend bootstrap parallel, cancellable, and fully disposable

**Affected files / functions:** `frontend/js/app-main.js:initializeApp`, `mounted`, and `beforeUnmount`; timer setup in `frontend/js/websocket.js`, `solar-data.js`, `solar-overlay.js`, `wavelog-stats.js`, `dx-spots.js`, and `ft8-modal.js`.

**Problem:** App startup serially awaits solar data, Wavelog statistics, radio status, worked calls, a filtered search, outbox status, rotor calls, and WinKeyer initialization. One slow optional service delays the entire ready state. Several anonymous intervals and a document click listener are never retained/removed; `beforeUnmount` clears only selected timers, so remounts/tests can duplicate polling and event handling.

**Fix prompt:**

> Split frontend initialization into a minimal critical render and independent feature loaders using `Promise.allSettled`, per-request timeouts/AbortControllers, and explicit loading/error/empty states per panel. Do not block radio controls on solar, Wavelog stats, spots history, rotor, or WinKeyer. Store every timer/listener/subscription handle in one disposable registry and clear it in `beforeUnmount`/standalone teardown, including clock, rotor, sync countdown/status, outbox, document click, reconnect, and overlay timers. Add a mount/unmount/remount test and slow/unavailable optional-service browser tests.

### P2-12 — Use one atomic local-file persistence primitive

**Affected files / functions:** `radio_control/adif_handler.py`, `radio_control/qrz_api.py:_save_profile_cache`, `radio_control/wavelog_api.py` ADIF cache/meta writes, `radio_control/digital_target_store.py`, `radio_control/lifecycle.py`, and other JSON/ADIF file writers.

**Problem:** Beyond the P0 outbox and settings paths, several caches/stores write directly or perform read-check-append without shared locking. Concurrent QSO requests can duplicate archive records, interrupted QRZ/cache writes are silently treated as empty, and persistence/recovery behaviour differs by module.

**Fix prompt:**

> Add a small `radio_control/persistence.py` with locked atomic JSON/text replacement, append-with-fsync, optional backup, and corrupt-file quarantine/recovery. Migrate ADIF archive, QRZ cache, Wavelog cache metadata, digital target state, and lifecycle request writers to it, using per-file locks and explicit durability requirements. Keep append-only QSO archive semantics separate from replaceable caches, and add concurrent writer plus interrupted-write tests.

## P3

### P3-01 — Replace “coming soon” controls with working actions or remove them

**Affected files / functions:** `frontend/js/app-main.js:viewQSODetails` and `refreshSummaryField`; buttons in `frontend/templates/modal-prev-qsos.html` and `frontend/templates/modal-callsign-search.html`.

**Problem:** “View details” logs the object and opens a basic `alert`; each summary refresh button displays “Feature coming soon.” These controls look production-ready but do not meet user expectations and add paths that must be maintained/tested.

**Fix prompt:**

> Decide whether QSO details and per-field refresh are supported now. If yes, implement an accessible details panel and one real refresh endpoint/action with loading/error state; if not, remove `viewQSODetails`, `refreshSummaryField`, and their buttons from both modal templates. Do not ship placeholder alerts, and add a DOM test for the chosen behaviour.

### P3-02 — Fix small correctness and path-containment edge cases

**Affected files / functions:** `frontend/js/country-modal.js:updateInfoDisplay`; `backend/api/static_files.py:serve_frontend_files`; associated tests.

**Problem:** Latitude or longitude equal to zero renders as an em dash due to truthiness checks. Static path containment uses string-prefix comparison, so a sibling directory whose name begins with `frontend` can pass the check; current lack of uploads limits exploitability, but the pattern is brittle.

**Fix prompt:**

> In `frontend/js/country-modal.js`, test latitude/longitude with `Number.isFinite`/null checks so `0.00°` renders correctly. In `backend/api/static_files.py`, replace string-prefix containment with `Path.resolve().is_relative_to(frontend_path.resolve())`, catch only expected path errors, and test zero coordinates plus traversal/sibling-prefix paths.

### P3-03 — Use structured process arguments and improve tray-agent settings recovery

**Affected files / functions:** `tools/Om0rxAgent/AgentSupervisor.cs:StartAllAsync`, `StartAllWithoutLockAsync`, `RunProcessAsync`, and `Quote`; `tools/Om0rxAgent/AgentSettings.cs:Load`.

**Problem:** The tray agent constructs Windows command lines manually and escapes quotes with backslashes, which is not a universal Windows/PowerShell argument rule. A malformed agent settings JSON throws during startup instead of falling back to a quarantined/default file.

**Fix prompt:**

> Replace manually concatenated `ProcessStartInfo.Arguments` in `tools/Om0rxAgent/AgentSupervisor.cs` with `ProcessStartInfo.ArgumentList` for scripts, Docker, and PowerShell commands wherever possible; isolate the few `-Command` scripts behind one tested PowerShell quoting helper. In `AgentSettings.Load`, catch JSON/I/O errors, move the corrupt file aside, load defaults, and surface a tray warning. Add paths-with-spaces/quotes and corrupt-settings tests.

# 3. Quick Wins

These are safe to batch after the P0/P1 fixes are protected by tests:

- Remove the 34 Ruff-reported unused imports and 16 unused local variables, including the unused `data` receive value in `services/websocket.py`, stale CTY temporaries, and unused digital-status values.
- Replace the 40 Ruff F541 placeholder-free f-strings with ordinary strings; expand or remove one-line semicolon statements only where touched rather than mass-formatting unrelated code.
- Fix or delete the two legacy `COLOR_DEFAULT` references; do not hide undefined names through broad exception handling.
- Delete the unused `renderStandaloneTableRows` method; `renderStandaloneFallbackUi` already contains the active escaped renderer.
- Change `backend/main.py` to import `FlexCtl` directly from `radio_control.flex_radio` even before the larger legacy deletion.
- Delete the no-op `poll_dx_spots` task and use metrics/logging at the actual cache mutation point.
- Remove the dead `/app.js` endpoint and redundant explicit `/logging-panel.css` endpoint; the generic frontend static handler already serves the real CSS and `frontend/app.js` does not exist.
- Correct the script-mode test harness in `tests/smoke/test_frontend_contracts.py` or remove its `__main__` block once the quality gate uses pytest.
- Consolidate duplicate `filteredSpots.map(...)` row-building code in `frontend/spots-database.html` into one pure function while the server-side pagination work is prepared.
- Rename ambiguous booleans/results (`ok`, `result`, `data`) at hardware/persistence boundaries to outcome-specific names when touching those functions.

**Batch fix prompt:**

> Apply the low-risk cleanup batch in OM0RX without changing runtime behaviour: run Ruff autofix only for F401/F541-safe edits, manually remove the listed unused variables, delete `frontend/js/spots-standalone.js:renderStandaloneTableRows`, delete `services/background_tasks.py:poll_dx_spots` and its registration, import `FlexCtl` directly in `backend/main.py`, remove the dead `/app.js` and redundant `/logging-panel.css` routes, fix/remove the script-mode `__main__` calls in `tests/smoke/test_frontend_contracts.py`, and extract one spot-database row builder. Do not autoformat the whole repository or modify unrelated user changes. Run Python/JS syntax, Ruff F/E9, the smoke suite, route scan, and the .NET build afterward.

# 4. Redundancy Removal Log

- `frontend/js/wsjtx-widget.js` — no HTML/template/script references; superseded by `wsjtx-handler.js`, the FT8 UI, and current WSJT status controls.
- `frontend/js/spots-standalone.js:renderStandaloneTableRows` — has no callers and duplicates the active table renderer in `renderStandaloneFallbackUi`.
- `services/background_tasks.py:poll_dx_spots` plus its `start_background_tasks` task — wakes every 30 seconds only to write debug counts; no data is polled or changed.
- `backend/main.py:init_wavelog_sync_manager` — unused synchronous initializer; only `init_wavelog_sync_manager_background` is called.
- `backend/core/config.py` — unregistered legacy config API with stale FT8 function names; active configuration lives in `backend/api/server_control.py` and `radio_control/settings_store.py`.
- `backend/core/models.py` and its import/re-export block in `backend/core/__init__.py` — no external consumers; active routes define separate DTOs. Delete after the P1 shared-model migration rather than maintaining two model sets.
- `backend/api/static_files.py:serve_app_js` — always 404 because `frontend/app.js` does not exist.
- `backend/api/static_files.py:serve_logging_panel_css` — redundant because the catch-all frontend handler serves `frontend/logging-panel.css`.
- `frontend/controls-section.html` — runtime uses `frontend/templates/controls-row*.html` and partials; this is a stale duplicate retained only by source-text tests.
- `frontend/logging-panel-section.html` — runtime uses `frontend/templates/logging-panel.html`; no maintained runtime references.
- `frontend/modals-section.html` — runtime uses individual `frontend/templates/modal-*.html`; remaining references are source-text tests.
- `frontend/dx-spots-section.html` — runtime uses `frontend/templates/dx-spots.html`; remaining references are documentation/source-text tests.
- Tests that assert duplicated legacy section files (`tests/smoke/test_frontend_contracts.py`, `test_frontend_module_contracts.py`, and `test_ft8_implementation.py` legacy-section assertions) — delete/update with the four duplicate templates and test the loaded DOM/manifest instead.
- `radio_control/wavelog_sync.py` and the `stop_wavelog_sync` import in `backend/api/server_control.py` — legacy HTTP/SQLite-era sync manager; the running manager is `wavelog_duckdb_sync`/`postgres_wavelog_sync` and background task cancellation already owns its lifecycle.
- `radio_control/dxbridge.py`, `bridge_runtime.py`, `spot_ui.py`, `ui_dialogs.py`, `ui_components.py`, and `classifier.py` — legacy Tk bridge tree with no documented/current launcher; backend reaches it only through an unnecessary `FlexCtl` re-export. Remove after the direct import change.
- `radio_control/flex_radio.py:FlexSpots` — used only by the removable legacy Tk bridge runtime; current backend uses `FlexCtl`.
- Ruff-listed unused imports and locals — delete outright; they carry no side effects except `dxbridge.py`'s unused MySQL import, whose startup dependency check disappears with the legacy entry point.
