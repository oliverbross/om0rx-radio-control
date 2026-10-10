// Offline safety-contract tests for the coordinator workflow UI.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function workflow() {
  const window = { addEventListener() {} };
  const context = { window, console, setInterval, clearInterval, setTimeout, clearTimeout, AbortController };
  vm.runInNewContext(fs.readFileSync('frontend/js/station-workflow.js', 'utf8'), context);
  return window.StationWorkflow;
}

test('commissioning lock wins even when backend lists an action', async () => {
  const api = workflow();
  const state = api.normalizeState({ commissioned: false, allowed_actions: ['tune'] });
  let requests = 0;
  const result = await api.postAction('tune', state, async () => { requests += 1; });
  assert.equal(api.actionAllowed(state, 'tune'), false);
  assert.equal(result.sent, false);
  assert.equal(result.reason, 'commissioning-lock');
  assert.equal(requests, 0);
});

test('backend-authorized standby remains available as a de-escalation action while locked', async () => {
  const api = workflow();
  const state = api.normalizeState({ commissioned: false, allowed_actions: ['standby'] });
  const requests = [];
  const result = await api.postAction('standby', state, async (url, options) => {
    requests.push([url, options]);
    return { ok: true, status: 200, json: async () => ({ commissioned: false }) };
  });
  assert.equal(result.sent, true);
  assert.equal(requests[0][0], '/api/station/actions/standby');
});

test('commissioned state still blocks actions missing from allowed_actions', async () => {
  const api = workflow();
  const state = api.normalizeState({ commissioned: true, allowed_actions: ['standby'] });
  let requests = 0;
  const result = await api.postAction('operate', state, async () => { requests += 1; });
  assert.equal(result.sent, false);
  assert.equal(result.reason, 'action-not-allowed');
  assert.equal(requests, 0);
});

test('authorized action posts only to the station coordinator endpoint', async () => {
  const api = workflow();
  const state = api.normalizeState({ commissioned: true, allowed_actions: ['prepare-route'] });
  const requests = [];
  const result = await api.postAction('prepare-route', state, async (url, options) => {
    requests.push([url, options]);
    return { ok: true, status: 200, json: async () => ({ state: { commissioned: true } }) };
  });
  assert.equal(result.sent, true);
  assert.equal(requests[0][0], '/api/station/actions/prepare-route');
  assert.equal(requests[0][1].method, 'POST');
  assert.doesNotMatch(requests[0][0], /elecraft/);
});

test('state and transaction payloads normalize for compact progress display', () => {
  const api = workflow();
  const state = api.normalizeState({
    success: true,
    station_state: {
      commissioned: true,
      coordinator_state: 'tuning',
      selected_route: { id: '40m-ant2', label: '40 m dipole' },
      allowed_actions: ['cancel'],
      issues: [{ code: 'carrier', message: 'Tune carrier active' }],
      active_transaction: { transaction_id: 'tx-12', action: 'tune', status: 'running', progress: 0.45, step: 'Measuring SWR' },
    },
  });
  const view = api.buildViewModel(state, { endpointAvailable: true });
  assert.equal(view.state, 'active');
  assert.equal(view.routeLabel, '40 m dipole');
  assert.equal(view.transaction.progress, 45);
  assert.equal(view.actionEnabled.cancel, true);
  assert.equal(view.actionEnabled.tune, false);
  assert.deepEqual([...view.issues], ['Tune carrier active']);
});

test('missing endpoint renders an explicit read-only unavailable state', () => {
  const view = workflow().buildViewModel(null, { endpointAvailable: false });
  assert.equal(view.state, 'unavailable');
  assert.equal(view.commissioned, false);
  assert.ok(Object.values(view.actionEnabled).every(enabled => enabled === false));
  assert.match(view.issues[0], /read-only/);
});

test('active normalized alarms feed the compact badge and issue list', () => {
  const api = workflow();
  const state = api.normalizeState({
    station_state: {
      commissioned: true,
      alarms: {
        active_count: 2,
        items: [
          { code: 'kpa500-fault', severity: 'critical', active: true, message: 'KPA500 fault 04' },
          { code: 'old', status: 'cleared', active: false, message: 'Old alarm' },
          { code: 'kat500-stale', severity: 'warning', active: true, message: 'KAT500 telemetry is stale' },
        ],
      },
    },
  });
  const view = api.buildViewModel(state, { endpointAvailable: true });
  assert.equal(view.alarmCount, 2);
  assert.deepEqual([...view.issues], ['KPA500 fault 04', 'KAT500 telemetry is stale']);
});

test('maintenance controls use only the coordinator lifecycle endpoints', async () => {
  const api = workflow();
  const enterState = api.normalizeState({
    commissioned: false,
    maintenance: false,
    maintenance_enter_available: true,
  });
  const requests = [];
  const entered = await api.postMaintenance('enter', enterState, async (url, options) => {
    requests.push([url, options]);
    return { ok: true, status: 200, json: async () => ({ station_state: { maintenance: true } }) };
  });
  const exitState = api.normalizeState({ commissioned: true, maintenance: true });
  const exited = await api.postMaintenance('exit', exitState, async (url, options) => {
    requests.push([url, options]);
    return { ok: true, status: 200, json: async () => ({ station_state: { maintenance: false } }) };
  });
  assert.equal(entered.sent, true);
  assert.equal(exited.sent, true);
  assert.deepEqual(requests.map(item => item[0]), [
    '/api/station/maintenance/enter',
    '/api/station/maintenance/exit',
  ]);
  assert.ok(requests.every(item => item[1].method === 'POST'));
});

test('maintenance state locks normal controls and enables only exit', () => {
  const api = workflow();
  const state = api.normalizeState({
    commissioned: true,
    maintenance: true,
    allowed_actions: ['exit-maintenance'],
  });
  const view = api.buildViewModel(state, { endpointAvailable: true });
  assert.equal(view.state, 'maintenance');
  assert.equal(view.maintenanceActionEnabled.enter, false);
  assert.equal(view.maintenanceActionEnabled.exit, true);
  assert.ok(Object.values(view.actionEnabled).every(enabled => enabled === false));
});

test('template starts locked and exposes only coordinator action names', () => {
  const template = fs.readFileSync('frontend/templates/partials/station-workflow.html', 'utf8');
  const source = fs.readFileSync('frontend/js/station-workflow.js', 'utf8');
  const shell = fs.readFileSync('frontend/js/station-shell.js', 'utf8');
  const page = fs.readFileSync('frontend/station.html', 'utf8');
  const actions = [...template.matchAll(/data-station-action="([^"]+)" disabled/g)].map(match => match[1]);
  assert.deepEqual(actions, ['prepare-route', 'standby', 'operate', 'tune', 'cancel']);
  assert.deepEqual(
    [...template.matchAll(/data-station-maintenance="([^"]+)" disabled/g)].map(match => match[1]),
    ['enter', 'exit'],
  );
  assert.match(shell, /templates\/partials\/station-workflow\.html/);
  assert.doesNotMatch(source, /\/api\/elecraft\//);
  assert.match(source, /`\/api\/station\/actions\/\$\{action\}`/);
  assert.match(page, /js\/station-workflow\.js/);
});
