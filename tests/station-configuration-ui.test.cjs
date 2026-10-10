const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function configurationUi() {
  const window = {};
  const context = { window, console, JSON };
  vm.runInNewContext(fs.readFileSync('frontend/js/station-configuration.js', 'utf8'), context);
  return window.StationConfiguration;
}

test('guarded setup loads and normalizes the active Elecraft integration settings', async () => {
  const requests = [];
  const settings = await configurationUi().requestSettings(async (url, options) => {
    requests.push([url, options]);
    return {
      ok: true,
      status: 200,
      json: async () => ({
        success: true,
        config: {
          KPA500_ENABLED: true,
          KPA500_PORT: 'COM17',
          KPA500_BAUDRATE: 38400,
          DIGITAL_KPA_POLICY: 'standby',
          KAT500_ENABLED: true,
          KAT500_PORT: 'COM15',
          KAT500_BAUDRATE: 38400,
          ELECRAFT_FOLLOW_RADIO: true,
          KAT500_ANTENNA_NAMES: { 1: 'Hexbeam', 2: '40 m dipole', 3: 'Dummy load' },
          KAT500_ANTENNA_POLICY: { '40m': 2 },
          FLEX_ANTENNA_POLICY: { enabled: true, bands: { '40m': 'ANT1' } },
          STATION_AMPLIFIER_ALLOWED_BANDS: ['40m'],
          STATION_AMPLIFIER_DRIVE_W: { '40m': 27 },
          STATION_BAREFOOT_DRIVE_W: { '40m': 80 },
          STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS: ['40m'],
          STATION_DIGITAL_AMPLIFIER_DRIVE_W: { '40m': 15 },
        },
      }),
    };
  });
  assert.equal(requests[0][0], '/api/config');
  assert.equal(requests[0][1].method, 'GET');
  assert.equal(settings.KPA500_PORT, 'COM17');
  assert.equal(settings.KAT500_PORT, 'COM15');
  assert.equal(settings.KAT500_ANTENNA_POLICY['40m'], 2);
  assert.equal(settings.FLEX_ANTENNA_POLICY.bands['40m'], 'ANT1');
  assert.equal(JSON.stringify(settings.STATION_AMPLIFIER_ALLOWED_BANDS), JSON.stringify(['40m']));
  assert.equal(settings.STATION_AMPLIFIER_DRIVE_W['40m'], 27);
  assert.equal(settings.STATION_AMPLIFIER_DRIVE_W['20m'], 25);
  assert.equal(settings.STATION_BAREFOOT_DRIVE_W['40m'], 80);
  assert.equal(settings.STATION_BAREFOOT_DRIVE_W['20m'], 25);
  assert.equal(JSON.stringify(settings.STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS), JSON.stringify(['40m']));
  assert.equal(settings.STATION_DIGITAL_AMPLIFIER_DRIVE_W['40m'], 15);
  assert.equal(settings.STATION_DIGITAL_AMPLIFIER_DRIVE_W['20m'], 25);
});

test('guarded setup saves only a bounded config object through the existing config API', async () => {
  const requests = [];
  const source = {
    KPA500_ENABLED: true,
    KPA500_PORT: 'COM17',
    KAT500_ENABLED: true,
    KAT500_PORT: 'COM15',
  };
  const result = await configurationUi().requestSettingsSave(source, async (url, options) => {
    requests.push([url, options]);
    return { ok: true, status: 200, json: async () => ({ success: true, message: 'saved' }) };
  });
  assert.equal(result.success, true);
  assert.equal(requests[0][0], '/api/config');
  assert.equal(requests[0][1].method, 'POST');
  assert.deepEqual(JSON.parse(requests[0][1].body), { config: source });
});

test('snapshot export uses the cached semantic station endpoint', async () => {
  const requests = [];
  const snapshot = await configurationUi().requestSnapshot(async (url, options) => {
    requests.push([url, options]);
    return {
      ok: true,
      status: 200,
      json: async () => ({ configuration_snapshot: { schema_version: 1, snapshot_id: 'abc' } }),
    };
  });
  assert.equal(snapshot.snapshot_id, 'abc');
  assert.equal(requests[0][0], '/api/station/configuration/snapshot');
  assert.equal(requests[0][1].method, 'GET');
});

test('restore preview posts the snapshot and never calls an apply endpoint', async () => {
  const requests = [];
  const source = { schema_version: 1, settings: { KPA500_PORT: 'COM17' } };
  const preview = await configurationUi().requestRestorePreview(source, async (url, options) => {
    requests.push([url, options]);
    return {
      ok: true,
      status: 200,
      json: async () => ({ restore_preview: { valid: true, preview_only: true, apply_available: false, changes: [] } }),
    };
  });
  assert.equal(preview.apply_available, false);
  assert.equal(requests[0][0], '/api/station/configuration/restore-preview');
  assert.deepEqual(JSON.parse(requests[0][1].body), { snapshot: source });
  assert.doesNotMatch(fs.readFileSync('frontend/js/station-configuration.js', 'utf8'), /configuration\/restore['"`]/);
});

test('preview normalization preserves maintenance classification', () => {
  const result = configurationUi().normalizePreview({
    valid: true,
    preview_only: true,
    apply_available: false,
    change_count: 1,
    requires_maintenance: true,
    changes: [{ key: 'KAT500_PORT', class: 'connection', before: 'COM14', after: 'COM15' }],
  });
  assert.equal(result.previewOnly, true);
  assert.equal(result.applyAvailable, false);
  assert.equal(result.requiresMaintenance, true);
  assert.equal(result.changes[0].category, 'connection');
});

test('management partial is loaded after the station workflow and training preview', () => {
  const shell = fs.readFileSync('frontend/js/station-shell.js', 'utf8');
  const page = fs.readFileSync('frontend/station.html', 'utf8');
  assert.ok(shell.indexOf('station-workflow.html') < shell.indexOf('station-configuration.html'));
  assert.ok(shell.indexOf('station-training-preview.html') < shell.indexOf('station-configuration.html'));
  assert.match(page, /station-configuration\.css/);
  assert.match(page, /station-configuration\.js/);
});

test('station configuration exposes connection, routing, antenna naming and tune safeguards', () => {
  const partial = fs.readFileSync('frontend/templates/partials/station-configuration.html', 'utf8');
  const script = fs.readFileSync('frontend/js/station-configuration.js', 'utf8');
  for (const key of [
    'KPA500_ENABLED', 'KPA500_PORT', 'KPA500_BAUDRATE',
    'KAT500_ENABLED', 'KAT500_PORT', 'KAT500_BAUDRATE',
    'ELECRAFT_FOLLOW_RADIO', 'DIGITAL_KPA_POLICY',
    'STATION_TUNE_POWER_W', 'STATION_TUNE_TARGET_SWR',
    'STATION_TUNE_ABORT_SWR', 'STATION_TUNE_TIMEOUT_SECONDS',
  ]) assert.match(partial, new RegExp(key));
  assert.match(partial, /data-station-config-antenna-name="1"/);
  assert.match(partial, /data-station-configuration="band-rows"/);
  assert.match(script, /data-station-config-amp-drive-band/);
  assert.match(script, /data-station-config-barefoot-drive-band/);
  assert.match(script, /data-station-config-digital-amp-band/);
  assert.match(script, /data-station-config-digital-drive-band/);
  assert.match(partial, /PA drive \(W\)/);
  assert.match(partial, /Barefoot drive \(W\)/);
  assert.match(partial, /Digital PA/);
  assert.match(partial, /Digital PA drive \(W\)/);
  assert.match(partial, /never enables commissioning or starts a tune\/transmission/);
  assert.doesNotMatch(script, /\/api\/elecraft\/(?:raw|command|write|tune|operate|antenna)/i);
});
