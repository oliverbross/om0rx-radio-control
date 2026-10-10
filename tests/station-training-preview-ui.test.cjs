const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function moduleApi() {
  const window = {};
  const document = { addEventListener() {}, getElementById() { return null; } };
  const context = { window, document, console, AbortController, fetch: async () => null };
  vm.runInNewContext(fs.readFileSync('frontend/js/station-training-preview.js', 'utf8'), context);
  return window.StationTrainingPreview;
}

test('normalizes an eligible and prohibited-band preview', () => {
  const view = moduleApi().normalize({ training_preview: {
    preview_only: true,
    eligible_count: 1,
    blocked_count: 1,
    total_worst_case_seconds: 76,
    tune_power_w: 20,
    validation_errors: [],
    points: [
      { band: '20m', frequency_mhz: 14.074, flex_tx_ant: 'ANT1', kat_antenna: 1, antenna_name: 'Beam', eligible: true },
      { band: '60m', frequency_mhz: 5.357, flex_tx_ant: 'ANT1', kat_antenna: 2, antenna_name: 'Wire', eligible: false, blocked_reasons: ['Amplifier prohibited'] },
    ],
  }});
  assert.equal(view.state, 'ready');
  assert.equal(view.duration, '1m 16s');
  assert.equal(view.points[0].status, 'Eligible preview');
  assert.match(view.points[1].status, /prohibited/i);
  assert.equal(view.executionAvailable, false);
  assert.match(view.executionBlockers[0], /not enabled/i);
});

test('requires server-provided execution preflight without a typed phrase', () => {
  const view = moduleApi().normalize({ training_preview: {
    preview_only: true,
    execution_available: true,
    execution_blockers: [],
    required_confirmation: 'TRAIN 20M ANT1',
    points: [{ band: '20m', frequency_mhz: 14.074, eligible: true }],
  }});
  assert.equal(view.executionAvailable, true);
  assert.equal(view.requiredConfirmation, 'TRAIN 20M ANT1');

  const noPhraseRequired = moduleApi().normalize({ training_preview: {
    preview_only: true, execution_available: true, points: [],
  }});
  assert.equal(noPhraseRequired.executionAvailable, true);
  assert.equal(noPhraseRequired.requiredConfirmation, '');

  const digitalBlocked = moduleApi().normalize({ training_preview: {
    preview_only: true,
    execution_available: false,
    execution_blockers: [{ code: 'digital-engine-owns-radio', message: 'External engine owns radio' }],
    required_confirmation: 'TRAIN 40M ANT2',
    points: [{ band: '40m', frequency_mhz: 7.074, eligible: true }],
  }});
  assert.deepEqual(Array.from(digitalBlocked.executionBlockerCodes), ['digital-engine-owns-radio']);
});

test('keeps policy-blocked points visible while allowing the eligible subset', () => {
  const view = moduleApi().normalize({ training_preview: {
    preview_only: true,
    execution_available: true,
    eligible_count: 26,
    blocked_count: 2,
    point_count: 28,
    points: [
      { band: '40m', frequency_mhz: 7.02, eligible: true },
      { band: '60m', frequency_mhz: 5.357, eligible: false, blocked_reasons: ['Amplifier operation is prohibited by band policy'] },
    ],
  }});
  assert.equal(view.executionAvailable, true);
  assert.equal(view.eligible, 26);
  assert.equal(view.blocked, 2);
  assert.match(view.message, /26 runnable/i);
  assert.match(view.message, /will be skipped/i);
});

test('fails visibly closed for missing or invalid payloads', () => {
  assert.equal(moduleApi().normalize(null).state, 'unavailable');
  const invalid = moduleApi().normalize({ training_preview: {
    preview_only: true, points: [], validation_errors: [{ code: 'bad', message: 'Bad route' }],
  }});
  assert.equal(invalid.state, 'invalid');
  assert.equal(invalid.message, 'Bad route');
});

test('builds bounded CW, data, and SSB requests for selected bands', () => {
  const api = moduleApi();
  const request = api.buildRequest(['20m', '40m', '20m', 'bogus'], ['cw', 'data', 'ssb']);
  assert.deepEqual(Array.from(request.bands), ['20m', '40m']);
  assert.deepEqual(Array.from(request.portions), ['cw', 'data', 'ssb']);
  assert.equal(request.coverage, 'representative');
  assert.equal(request.erase_selected_memories, false);
  assert.deepEqual(Object.keys(request.frequency_points_mhz), []);
});

test('marks a destructive erase selection only in the calculation payload', () => {
  const request = moduleApi().buildRequest(['20m'], ['data'], {
    coverage: 'full_bins', eraseSelectedMemories: true,
  });
  assert.equal(request.coverage, 'full_bins');
  assert.equal(request.erase_selected_memories, true);
});

test('normalizes optional SWR results for the dependency-free plot', () => {
  const api = moduleApi();
  const view = api.normalize({ training_preview: {
    preview_only: true, eligible_count: 1, blocked_count: 0, points: [
      { band: '20m', frequency_mhz: 14.074, eligible: true, swr_before: 2.8, swr_after: 1.3, status: 'complete' },
    ],
  }});
  assert.equal(view.points[0].swrBefore, 2.8);
  assert.equal(view.points[0].swrAfter, 1.3);
  assert.equal(view.points[0].status, 'complete');
  assert.deepEqual(Array.from(api.buildPlotSeries(view.points), item => ({ kind: item.kind, swr: item.swr })), [
    { kind: 'before', swr: 2.8 }, { kind: 'after', swr: 1.3 },
  ]);
});

test('builds guarded start payload and normalizes the preferred job envelope', () => {
  const api = moduleApi();
  const request = api.buildRequest(['40m'], ['cw'], { eraseSelectedMemories: true });
  const payload = api.buildStartPayload(request, {
    operation: 'survey',
    operatorConfirmed: true,
    approvedLoadConfirmed: true,
    digitalEngineInhibitConfirmed: true,
    legalOperationConfirmed: true,
    vendorBackupConfirmed: true,
  });
  assert.equal(payload.operation, 'survey');
  assert.equal(payload.operator_confirmed, true);
  assert.equal(payload.typed_confirmation, undefined);
  assert.equal(payload.approved_load_confirmed, true);
  assert.equal(payload.digital_engine_inhibit_confirmed, true);
  assert.equal(payload.legal_operation_confirmed, true);
  assert.equal(payload.vendor_backup_confirmed, true);
  assert.equal(payload.erase_selected_memories, true);

  const job = api.normalizeJob({ success: true, training_job: {
    id: 'atu-7', operation: 'survey', status: 'running', total_points: 2, completed_points: 1,
    current_frequency_mhz: 7.02,
    results: [{ band: '40m', frequency_mhz: 7.02, swr_before: 2.7, swr_after: 1.4, status: 'complete' }],
  }});
  assert.equal(job.id, 'atu-7');
  assert.equal(job.operation, 'survey');
  assert.equal(job.terminal, false);
  assert.equal(job.results[0].swrAfter, 1.4);
  assert.equal(api.normalizeJob({ training_job: { id: 'atu-7', status: 'cancelled' } }).terminal, true);

  const filteredJob = api.normalizeJob({ training_job: {
    id: 'atu-filtered', status: 'queued', point_count: 26,
    requested_point_count: 28, skipped_point_count: 2,
  }});
  assert.equal(filteredJob.total, 26);
  assert.equal(filteredJob.requestedTotal, 28);
  assert.equal(filteredJob.skipped, 2);

  const partialJob = api.normalizeJob({ training_job: {
    id: 'atu-partial', state: 'completed_with_failures', point_count: 4,
    processed_count: 4, completed_count: 3, failed_point_count: 1,
    message: 'Training completed: 3 point(s) succeeded and 1 point(s) did not meet the target.',
  }});
  assert.equal(partialJob.terminal, true);
  assert.equal(partialJob.processed, 4);
  assert.equal(partialJob.completed, 3);
  assert.equal(partialJob.failedPoints, 1);
});

test('groups persisted tune and survey records into selectable SWR profiles', () => {
  const profiles = moduleApi().normalizeHistoryProfiles({ records: [
    {
      completed_at: '2026-10-04T10:00:00Z', route_id: '40m-flex-ant1-kat-ant2',
      frequency_hz: 7020000, swr_before: 1.8, swr_after: null,
      details: { operation: 'survey', training_job_id: 'survey-1' },
    },
    {
      completed_at: '2026-10-04T10:00:10Z', route_id: '40m-flex-ant1-kat-ant2',
      frequency_hz: 7050000, swr_before: 1.4, swr_after: null,
      details: { operation: 'survey', training_job_id: 'survey-1' },
    },
    {
      completed_at: '2026-10-04T11:00:00Z', route_id: '20m-flex-ant1-kat-ant2',
      frequency_hz: 14074000, swr_before: 2.2, swr_after: 1.2,
      details: { operation: 'train', training_job_id: 'train-1' },
    },
  ] });
  assert.equal(profiles.length, 2);
  assert.equal(profiles[0].operation, 'train');
  assert.equal(profiles[1].operation, 'survey');
  assert.equal(profiles[1].points.length, 2);
  assert.equal(profiles[1].points[0].swrBefore, 1.8);
});

test('keeps structured terminal failure details and safe diagnostic events', () => {
  const job = moduleApi().normalizeJob({ training_job: {
    id: 'atu-failed', state: 'failed', point_count: 3, completed_count: 1,
    error: { code: 'flex-tx-proof-timeout', message: 'Fresh FLEX TX state timed out' },
    results: [
      { sequence: 1, band: '40m', frequency_mhz: 7.02, status: 'succeeded', swr_after: 1.27 },
      { sequence: 2, band: '40m', frequency_mhz: 7.05, status: 'failed', error: { code: 'flex-tx-proof-timeout', message: 'Fresh FLEX TX state timed out' } },
    ],
    events: [
      { sequence: 1, event: 'point.completed', point_sequence: 1, frequency_mhz: 7.02, duration_ms: 900 },
      { sequence: 2, event: 'point.failed', point_sequence: 2, frequency_mhz: 7.05, error: { code: 'flex-tx-proof-timeout', message: 'Fresh FLEX TX state timed out' } },
    ],
  }});
  assert.equal(job.terminal, true);
  assert.equal(job.error.code, 'flex-tx-proof-timeout');
  assert.equal(job.message, 'Fresh FLEX TX state timed out');
  assert.match(job.results[1].status, /Fresh FLEX TX state timed out/);
  assert.equal(job.events.length, 2);
  assert.equal(job.events[1].pointSequence, 2);
});

test('accepts optional plot results and memory-bin frequencies', () => {
  const view = moduleApi().normalize({ training_preview: {
    preview_only: true, points: [], plot: { points: [
      { band: '40m', portion: 'cw', memory_bin_khz: 7030, swr_before: 2.1, status: 'historic' },
    ] },
  }});
  assert.equal(view.plotPoints[0].frequency, '7.030 MHz');
  assert.equal(view.plotPoints[0].portion, 'cw');
  assert.equal(view.plotPoints[0].status, 'historic');
});

test('panel keeps plan preview separate from guarded RF job controls and loads before the app', () => {
  const source = fs.readFileSync('frontend/js/station-training-preview.js', 'utf8');
  const partial = fs.readFileSync('frontend/templates/partials/station-training-preview.html', 'utf8');
  const shell = fs.readFileSync('frontend/js/station-shell.js', 'utf8');
  const page = fs.readFileSync('frontend/station.html', 'utf8');
  assert.match(source, /method:\s*'GET'/);
  assert.match(source, /requestPreview\('POST'/);
  assert.match(source, /\/api\/station\/training\/jobs/);
  assert.match(source, /approved_load_confirmed/);
  assert.match(source, /digital_engine_inhibit_confirmed/);
  assert.match(source, /legal_operation_confirmed/);
  assert.match(source, /operator_confirmed/);
  assert.match(source, /vendor_backup_confirmed/);
  assert.match(source, /\/api\/digital\/stop/);
  assert.match(source, /refreshSafetyStatus/);
  assert.doesNotMatch(source, /\/actions\/|\/maintenance\//);
  assert.match(partial, /ATU Auto Setup/);
  assert.match(partial, /data-training-role="swr-plot"/);
  assert.match(partial, /Start training — produces RF/);
  assert.match(partial, /Run SWR survey — produces RF/);
  assert.match(partial, /data-training-role="cancel"/);
  assert.match(partial, /This action produces RF/);
  assert.doesNotMatch(partial, /Type the exact confirmation/);
  assert.match(partial, /data-training-role="rf-confirm-dialog"/);
  assert.match(partial, /Yes, start RF/);
  assert.match(partial, /No, go back/);
  assert.match(partial, /data-training-role="history-profile"/);
  assert.match(partial, /data-training-role="train-recommended"/);
  assert.match(partial, /Stop digital engine &amp; release radio/);
  assert.match(partial, /Recheck safety status/);
  assert.match(partial, /data-training-role="diagnostics"/);
  assert.match(shell, /templates\/partials\/station-training-preview\.html/);
  assert.match(page, /js\/station-training-preview\.js/);
  assert.match(page, /station-training-preview\.css/);
});
