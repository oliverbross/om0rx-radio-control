const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function commissioningUi() {
  const window = {};
  const context = { window, console, JSON, Object };
  vm.runInNewContext(fs.readFileSync('frontend/js/station-commissioning.js', 'utf8'), context);
  return window.StationCommissioning;
}

test('readiness fetch uses the single read-only commissioning endpoint', async () => {
  const requests = [];
  const report = await commissioningUi().requestReadiness(async (url, options) => {
    requests.push([url, options]);
    return {
      ok: true,
      status: 200,
      json: async () => ({ readiness: { ready: false, blockers: ['key interrupt'] } }),
    };
  });
  assert.equal(requests[0][0], '/api/station/commissioning/readiness');
  assert.equal(requests[0][1].method, 'GET');
  assert.deepEqual(report.blockers, ['key interrupt']);
});

test('evidence evaluation posts exactly five bounded boolean fields to the same endpoint', async () => {
  const requests = [];
  const source = {
    physical_key_interrupt_verified: true,
    antenna_routes_names_verified: 1,
    vendor_backups_captured: true,
    dummy_load_or_approved_antenna_connected: 'yes',
    digital_engine_inhibit_verified: true,
    unexpected_apply_request: true,
  };
  await commissioningUi().evaluateEvidence(source, async (url, options) => {
    requests.push([url, options]);
    return { ok: true, status: 200, json: async () => ({ ready: false, preview_only: true }) };
  });
  assert.equal(requests[0][0], '/api/station/commissioning/readiness');
  assert.equal(requests[0][1].method, 'POST');
  assert.deepEqual(JSON.parse(requests[0][1].body), {
    physical_key_interrupt_verified: true,
    antenna_routes_names_verified: false,
    vendor_backups_captured: true,
    dummy_load_or_approved_antenna_connected: false,
    digital_engine_inhibit_verified: true,
  });
});

test('readiness normalization bounds hostile or malformed response data', () => {
  const huge = Array.from({ length: 70 }, (_, index) => ({ message: `check-${index}-${'x'.repeat(300)}` }));
  const result = commissioningUi().normalizeReadiness({
    ready: 'true',
    preview_only: false,
    blockers: huge,
    warnings: 'not-an-array',
    checks: [null, { label: 'relay identity checked' }],
  });
  assert.equal(result.ready, false);
  assert.equal(result.previewOnly, false);
  assert.equal(result.blockers.length, 50);
  assert.equal(result.blockers[0].length, 240);
  assert.deepEqual(Array.from(result.warnings), []);
  assert.deepEqual(Array.from(result.checks), ['Unspecified check', 'relay identity checked']);
});

test('readiness normalization keeps receive-only and low-power stages separate', () => {
  const result = commissioningUi().normalizeReadiness({
    readiness: {
      read_only: true,
      commissioning_enabled: false,
      disposition: 'receive-only',
      ready_for_receive_only: true,
      ready_for_low_power_test: false,
      blockers: [{ message: 'Vendor backups still required' }],
    },
  });
  assert.equal(result.readyForReceiveOnly, true);
  assert.equal(result.readyForLowPowerTest, false);
  assert.equal(result.commissioningEnabled, false);
  assert.equal(result.disposition, 'receive-only');
  assert.deepEqual(Array.from(result.blockers), ['Vendor backups still required']);
});

test('partial exposes all evidence controls and no commissioning or transmit action', () => {
  const html = fs.readFileSync('frontend/templates/partials/station-commissioning.html', 'utf8');
  const source = fs.readFileSync('frontend/js/station-commissioning.js', 'utf8');
  for (const key of commissioningUi().EVIDENCE_KEYS) assert.match(html, new RegExp(`data-evidence-key="${key}"`));
  assert.match(html, /does not commission, apply changes, key, or transmit/i);
  assert.match(html, />Evaluate evidence</);
  assert.doesNotMatch(html, /<button[^>]*>\s*(Commission|Apply|Transmit)/i);
  assert.doesNotMatch(source, /fetchImpl\([^)]*(apply|commission|transmit)/i);
  const row = fs.readFileSync('frontend/templates/controls-row1.html', 'utf8');
  const shell = fs.readFileSync('frontend/js/station-shell.js', 'utf8');
  assert.doesNotMatch(row, /@include templates\/partials\/station-commissioning\.html/);
  assert.match(shell, /templates\/partials\/station-commissioning\.html/);
});

test('commissioning decision text uses readable typography and full-width checks', () => {
  const css = fs.readFileSync('frontend/station-commissioning.css', 'utf8');
  assert.match(css, /\.station-commissioning-results ul[^}]*font-size:\s*12px/s);
  assert.match(css, /\.station-commissioning-panel label[^}]*font-size:\s*12px/s);
  assert.match(css, /section:last-child\s*\{\s*grid-column:\s*1 \/ -1/);
});
