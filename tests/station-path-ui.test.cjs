// Offline contract tests for the read-only unified station path.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function dashboard() {
  const window = { addEventListener() {} };
  const context = { window, console, setInterval, clearInterval, setTimeout, clearTimeout, AbortController };
  vm.runInNewContext(fs.readFileSync('frontend/js/station-path.js', 'utf8'), context);
  return window.StationPathDashboard;
}

function readyInput(now = 1_800_000_000_000) {
  return {
    now,
    connected: true,
    radioStatus: { frequency: 7.074, mode: 'DIGU', drive: 15, tx_ant: 'ANT1', interlock_state: 'READY' },
    txState: { mox: false, tune: false },
    config: {
      FLEX_ANTENNA_POLICY: { enabled: true, bands: { '40m': 'ANT1' } },
      KAT500_ANTENNA_POLICY: { '40m': 2 },
    },
    status: {
      updated_at: now / 1000,
      radio_band: '40m',
      kpa500: { enabled: true, connected: true, power: true, operate: true, band: '40m', fault: '0', output_power_w: 0, swr: 1.1 },
      kat500: { enabled: true, connected: true, power: true, mode: 'auto', band: '40m', antenna: 2, tuning: false, swr: 1.28, frequency_khz: 7074 },
      path: {
        schema_version: 1,
        state: 'ready',
        alignment: 'confirmed',
        transmit_authorized: false,
        authorization_note: 'Read-only path evidence; not a transmit authorization',
        frequency: 7.074,
        frequency_label: '7.074000 MHz',
        band: '40m',
        mode: 'DIGU',
        route_label: 'FLEX ANT1 → KPA500 → KAT500 → 40 m dipole',
        antenna: { observed: 2, expected: 2, label: '40 m dipole' },
        mismatches: [],
        advisories: [],
        unknown_reasons: [],
        stages: [
          { id: 'flex', state: 'ready', confirmed: true, detail: '7.074000 MHz · 40m · DIGU · ANT1', age_seconds: 0, stale: false },
          { id: 'kpa500', state: 'operate', confirmed: true, detail: '40m · operate', age_seconds: 0, stale: false },
          { id: 'kat500', state: 'auto', confirmed: true, detail: '40m · auto · 40 m dipole', age_seconds: 0, stale: false },
          { id: 'antenna', state: 'selected', confirmed: true, detail: 'KAT500 output 2', age_seconds: 0, stale: false },
        ],
      },
    },
  };
}

test('fresh matching readback produces a ready named end-to-end route', () => {
  const view = dashboard().buildViewModel(readyInput());
  assert.equal(view.state, 'ready');
  assert.equal(view.stateLabel, 'Confirmed');
  assert.equal(view.segments.find(segment => segment.id === 'flex').primary, '7.074.000 MHz');
  assert.equal(view.segments.find(segment => segment.id === 'flex').values['rf-power'], '15 W');
  assert.equal(view.segments.find(segment => segment.id === 'flex').values['tx-port'], 'ANT1');
  assert.equal(view.segments.find(segment => segment.id === 'antenna').primary, '40 m dipole');
  assert.equal(view.segments.find(segment => segment.id === 'antenna').values.route, 'Confirmed');
  assert.match(view.message, /not a transmit authorization/);
});

test('widget shows the effective per-band PA and barefoot drive policy', () => {
  const amplified = readyInput();
  amplified.stationState = {
    route: {
      band: '40m', amplifier_allowed: true, kpa500: 'operate', active_drive_w: 27,
      amplifier_drive_w: 27, barefoot_drive_w: 80,
    },
  };
  let kpa = dashboard().buildViewModel(amplified).segments.find(segment => segment.id === 'kpa500');
  assert.match(kpa.secondary, /Hardware readback: OPERATE/);
  assert.match(kpa.secondary, /Policy: amplified 27 W drive/);

  const barefoot = readyInput();
  barefoot.stationState = {
    route: {
      band: '20m', amplifier_allowed: true, configured_kpa500: 'standby', kpa500: 'standby',
      active_drive_w: 80, amplifier_drive_w: 25, barefoot_drive_w: 80,
    },
  };
  kpa = dashboard().buildViewModel(barefoot).segments.find(segment => segment.id === 'kpa500');
  assert.match(kpa.secondary, /Hardware readback: OPERATE/);
  assert.match(kpa.secondary, /Policy: barefoot 80 W drive/);
});

test('standby and mismatched antenna are warnings, not ready', () => {
  const input = readyInput();
  input.status.kpa500.operate = false;
  input.status.kat500.antenna = 1;
  input.status.path.state = 'fault';
  input.status.path.alignment = 'mismatch';
  input.status.path.stages.find(stage => stage.id === 'kpa500').state = 'standby';
  input.status.path.stages.find(stage => stage.id === 'kat500').state = 'mismatch';
  input.status.path.mismatches = [{ code: 'kat-antenna-mismatch', message: 'KAT500 reports ANT1; policy expects ANT2 on 40m' }];
  const view = dashboard().buildViewModel(input);
  assert.equal(view.state, 'warning');
  assert.match(view.message, /expects ANT2/);
});

test('healthy KPA500 standby is a normal confirmed state, not an attention condition', () => {
  const input = readyInput();
  input.status.kpa500.operate = false;
  input.status.kpa500.output_power_w = 40;
  input.status.kpa500.swr = 1.23;
  input.status.path.state = 'standby';
  input.status.path.stages.find(stage => stage.id === 'kpa500').state = 'standby';
  const view = dashboard().buildViewModel(input);
  const kpa = view.segments.find(segment => segment.id === 'kpa500');
  assert.equal(view.state, 'ready');
  assert.equal(kpa.state, 'ready');
  assert.equal(kpa.stateLabel, 'STANDBY MODE');
  assert.equal(kpa.primary, 'STANDBY');
  assert.match(kpa.secondary, /Hardware readback: STANDBY/);
  assert.equal(kpa.amplifierState, 'standby');
  assert.equal(kpa.values.output, '40 W');
  assert.equal(kpa.values.swr, '1.23');
  const antenna = view.segments.find(segment => segment.id === 'antenna');
  assert.equal(antenna.txPower, 'TX 40 W');
  assert.equal(antenna.txActive, true);
  assert.equal(view.ageText, 'Live telemetry');
});

test('active KPA500 output keeps the large state label while transmit details stay in the metrics', () => {
  const input = readyInput();
  input.radioStatus.mox = true;
  input.radioStatus.interlock_state = 'TRANSMITTING';
  input.status.path.mox = true;
  input.status.path.interlock_state = 'TRANSMITTING';
  input.status.kpa500.output_power_w = 378;
  input.status.kpa500.current = 9.7;

  const view = dashboard().buildViewModel(input);
  const kpa = view.segments.find(segment => segment.id === 'kpa500');

  assert.equal(kpa.stateLabel, 'TX ACTIVE');
  assert.equal(kpa.primary, 'OPERATE');
  assert.equal(kpa.values.output, '378 W');
  assert.equal(kpa.amplifierState, 'tx');
  assert.equal(kpa.txActive, true);
});

test('active KAT RF with zero KPA output is shown as operate but not keyed', () => {
  const input = readyInput();
  input.radioStatus.mox = true;
  input.radioStatus.interlock_state = 'TRANSMITTING';
  input.status.path.mox = true;
  input.status.path.interlock_state = 'TRANSMITTING';
  input.status.path.state = 'unknown';
  input.status.path.stages.find(stage => stage.id === 'flex').state = 'transmitting';
  input.status.kpa500.output_power_w = 0;
  input.status.kpa500.current = 0;
  input.status.kat500.forward_adc = 325;
  input.status.kat500.swr_live = true;

  const view = dashboard().buildViewModel(input);
  const kpa = view.segments.find(segment => segment.id === 'kpa500');
  const antenna = view.segments.find(segment => segment.id === 'antenna');

  assert.equal(kpa.state, 'warning');
  assert.equal(kpa.stateLabel, 'NOT KEYED');
  assert.equal(kpa.primary, 'OPERATE');
  assert.equal(kpa.amplifierState, 'warning');
  assert.equal(kpa.values.output, '0 W');
  assert.equal(antenna.txPower, 'TX 0 W');
  assert.equal(antenna.txActive, false);
  assert.match(view.message, /not keyed and is adding no power/);
});

test('frequency and antenna transmit power use operator-friendly formatting', () => {
  const api = dashboard();
  assert.equal(api.formatFrequency(14.074), '14.074.000 MHz');
  assert.equal(api.formatFrequency(7.02), '7.020.000 MHz');
  assert.equal(api.formatTxPower(234), 'TX 234 W');
  assert.equal(api.formatTxPower(null), 'TX — W');
});

test('widget actions accept only coordinator-authorized guarded transitions', () => {
  const api = dashboard();
  const state = api.normalizeCoordinatorState({
    station_state: { commissioned: true, maintenance: false, allowed_actions: ['prepare-route', 'operate'] },
  });
  assert.equal(api.actionAllowed('operate', state), true);
  assert.equal(api.actionAllowed('standby', state), false);
  assert.equal(api.actionAllowed('raw-write', state), false);
  assert.equal(api.actionAllowed('operate', { ...state, commissioned: false }), false);
});

test('same-band KAT memory frequency is shown as an advisory without degrading the route', () => {
  const input = readyInput();
  input.status.kat500.frequency_khz = 7016;
  input.status.path.advisories = [{
    code: 'kat-frequency-selection-different',
    message: 'KAT500 memory selection reports 7016 kHz while FLEX is at 7074 kHz; route preparation must update and verify it before transmit',
  }];
  const view = dashboard().buildViewModel(input);
  assert.equal(view.state, 'ready');
  assert.match(view.message, /memory selection reports 7016 kHz/);
});

test('standalone backend path supplies FLEX port and interlock without the main Vue app', () => {
  const input = readyInput();
  input.radioStatus = {};
  input.status.path.tx_ant = 'ANT1';
  input.status.path.interlock_state = 'READY';
  const view = dashboard().buildViewModel(input);
  const flex = view.segments.find(segment => segment.id === 'flex');
  assert.equal(flex.values['tx-port'], 'ANT1');
  assert.equal(flex.values.interlock, 'READY');
});

test('explicit device loss wins over unknown and warning states', () => {
  const input = readyInput();
  input.status.kpa500.connected = false;
  input.status.kat500.mode = null;
  input.status.path.state = 'unknown';
  input.status.path.stages.find(stage => stage.id === 'kpa500').state = 'disconnected';
  input.status.path.stages.find(stage => stage.id === 'kpa500').confirmed = false;
  input.status.path.unknown_reasons = ['KPA500 is disconnected'];
  const view = dashboard().buildViewModel(input);
  assert.equal(view.state, 'disconnected');
  assert.equal(view.segments.find(segment => segment.id === 'kpa500').state, 'disconnected');
});

test('stale telemetry and missing Flex antenna readback fail visibly unknown', () => {
  const input = readyInput();
  input.status.updated_at -= 60;
  input.radioStatus.tx_ant = null;
  input.status.path.state = 'unknown';
  input.status.path.stages.forEach(stage => {
    stage.age_seconds = 60;
    stage.stale = true;
  });
  input.status.path.stages.find(stage => stage.id === 'flex').state = 'stale';
  input.status.path.unknown_reasons = ['FLEX state is not fresh and confirmed'];
  const view = dashboard().buildViewModel(input);
  assert.equal(view.state, 'unknown');
  assert.equal(view.ageText, 'Stale · 60s oldest');
  assert.match(view.message, /not fresh and confirmed/);
});

test('dashboard template exposes four ordered read-only path segments', () => {
  const template = fs.readFileSync('frontend/templates/partials/station-path.html', 'utf8');
  const shell = fs.readFileSync('frontend/js/station-shell.js', 'utf8');
  const page = fs.readFileSync('frontend/station.html', 'utf8');
  const ids = [...template.matchAll(/data-path-segment="([^"]+)"/g)].map(match => match[1]);
  assert.deepEqual(ids, ['flex', 'kpa500', 'kat500', 'antenna']);
  assert.doesNotMatch(template, /@click|<button|<input|<select/);
  assert.match(shell, /templates\/partials\/station-path\.html/);
  assert.match(page, /js\/station-path\.js/);
  assert.match(page, /station-path\.css/);
});

test('path monitor uses change-stream updates with low-rate reconciliation', () => {
  const source = fs.readFileSync('frontend/js/station-path.js', 'utf8');
  assert.match(source, /new EventSource\(STREAM_ENDPOINT\)/);
  assert.match(source, /\/api\/station\/stream/);
  assert.match(source, /RECONCILE_MS\s*=\s*30000/);
  assert.match(source, /new WebSocket\(`\$\{protocol\}\/\/\$\{host\}\/ws\/radio`\)/);
  assert.doesNotMatch(source, /setInterval\(renderCurrent,\s*1000\)/);
});

test('radio websocket aliases expose the current FLEX RF power immediately', () => {
  const api = dashboard();
  const update = api.normalizeRadioUpdate({ freq: 10.136, mode: 'DIGU', rfpower: 25 });
  assert.equal(update.frequency, 10.136);
  assert.equal(update.mode, 'DIGU');
  assert.equal(update.drive, 25);
});
