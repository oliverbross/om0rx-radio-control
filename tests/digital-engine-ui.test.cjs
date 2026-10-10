// Offline provider UI behavior tests: no browser, backend, or radio required.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function fixture(fetch) {
  const events = [];
  const window = { dispatchEvent(event) { events.push(event); } };
  const context = { window, fetch, setTimeout, clearTimeout, console: { log() {} }, CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } } };
  vm.runInNewContext(fs.readFileSync('frontend/js/config-modal.js', 'utf8'), context);
  const config = window.RadioControlConfig;
  const instance = { ...config.data, ...config.methods };
  Object.defineProperty(instance, 'mshvOwnsDigitalPlanner', { get: () => config.computed.mshvOwnsDigitalPlanner.call(instance) });
  Object.defineProperty(instance, 'digitalEngineDisabled', { get: () => config.computed.digitalEngineDisabled.call(instance) });
  Object.defineProperty(instance, 'digitalEngineBlocksOm0rx', { get: () => config.computed.digitalEngineBlocksOm0rx.call(instance) });
  Object.defineProperty(instance, 'wsjtzOwnsDigitalPlanner', { get: () => config.computed.wsjtzOwnsDigitalPlanner.call(instance) });
  return { instance, window, events };
}

test('MSHV selection broadcasts ownership and stops legacy health requests', async () => {
  const urls = [];
  const { instance, window, events } = fixture(async url => {
    urls.push(url);
    return { ok: true, json: async () => ({ selected_engine: 'mshv_auto_dx', planner_owner: 'mshv', running: true }) };
  });
  await instance.loadWsjtxHealth();
  assert.deepEqual(urls, ['/api/digital/status']);
  assert.equal(instance.mshvOwnsDigitalPlanner, true);
  assert.equal(window.om0rxDigitalEngine, 'mshv_auto_dx');
  assert.equal(events[0].type, 'digital-engine-status');
});

test('lifecycle actions use provider API and recover selected state after a refusal', async () => {
  const requests = [];
  const { instance } = fixture(async (url, options) => {
    requests.push([url, options]);
    if (url.endsWith('/start')) return { ok: false, json: async () => ({ detail: 'TX active' }) };
    return { ok: true, json: async () => ({ selected_engine: 'wsjtz' }) };
  });
  instance.digitalEngineChoice = 'mshv_auto_dx';
  await instance.digitalEngineAction('start');
  assert.equal(requests[0][0], '/api/digital/start');
  assert.equal(JSON.parse(requests[0][1].body).engine, 'mshv_auto_dx');
  assert.equal(instance.digitalEngineMessage, 'TX active');
  assert.equal(instance.digitalEngineChoice, 'wsjtz');
  assert.equal(instance.digitalEngineBusy, false);
});

test('slow owned startup is shown as pending readiness rather than failure', async () => {
  const { instance } = fixture(async (url) => {
    if (url.endsWith('/start')) return {
      ok: true,
      status: 202,
      json: async () => ({
        success: true,
        selected_engine: 'mshv_auto_dx',
        startup: { ready: false, accepted: true, starting: true },
      }),
    };
    return { ok: true, json: async () => ({ selected_engine: 'mshv_auto_dx' }) };
  });
  instance.digitalEngineChoice = 'mshv_auto_dx';
  await instance.digitalEngineAction('start');
  assert.match(instance.digitalEngineMessage, /still starting/);
});

test('main-screen launch action starts the explicitly requested provider', async () => {
  const requests = [];
  let selected = 'none';
  const { instance } = fixture(async (url, options = {}) => {
    requests.push([url, options]);
    if (url === '/api/digital/start') {
      selected = JSON.parse(options.body).engine;
      return { ok: true, json: async () => ({ success: true, selected_engine: selected }) };
    }
    return { ok: true, json: async () => ({ selected_engine: selected, running: true }) };
  });

  await instance.launchDigitalEngine('mshv_auto_dx');
  await instance.launchDigitalEngine('wsjtz');

  assert.deepEqual(requests.map(([url]) => url), [
    '/api/digital/start', '/api/digital/status',
    '/api/digital/start', '/api/digital/status',
  ]);
  assert.equal(JSON.parse(requests[0][1].body).engine, 'mshv_auto_dx');
  assert.equal(JSON.parse(requests[2][1].body).engine, 'wsjtz');
  assert.equal(instance.digitalEngineChoice, 'wsjtz');
});

test('main screen shows adjacent WSJT-Z and MSHV launch controls in both layouts', () => {
  const full = fs.readFileSync('frontend/templates/controls-row1.html', 'utf8');
  const compact = fs.readFileSync('frontend/templates/partials/compact-radio-controls.html', 'utf8');
  for (const template of [full, compact]) {
    const wsjtz = template.indexOf("launchDigitalEngine('wsjtz')");
    const mshv = template.indexOf("launchDigitalEngine('mshv_auto_dx')");
    assert.ok(wsjtz >= 0, 'WSJT-Z launch control is missing');
    assert.ok(mshv > wsjtz, 'MSHV launch control must follow WSJT-Z');
    assert.ok(template.includes('digitalEngineBusy'));
  }
});

test('MSHV priority editor loads and saves composable scorer values', async () => {
  const requests = [];
  const settings = {
    success: true,
    editable: true,
    desired: { enabled: true },
    callsign: 'OM0RX',
    grid: 'JN88',
    min_snr: -20,
    spot_sources_us_only: false,
    grid_chase_us_only: false,
    band_switching_enabled: false,
    enabled_bands: [3, 4, 6, 7, 8, 9, 10, 11, 12],
    auto_dx_modes: ['FT8'],
    atno_chase_type: 3,
    scarce_threshold: 5,
    filter_matrix_enabled: true,
    filter_new: { call: true, dxcc: true, continent: false, grid: true, cq_zone: false, itu_zone: false },
    filter_new_on_band: { call: true, dxcc: false, continent: false, grid: true, cq_zone: false, itu_zone: false },
    filter_continents: ['EU', 'AF', 'OC', 'AS', 'SA', 'NA', 'AN'],
    allow_band_dxcc_outside_continent: true,
    filter_lotw_only: false,
    engaged_completion_grace_seconds: 120,
    recent_qso_cooldown_seconds: 3600,
    automation_timing: {
      normal_call_seconds: 120, quiet_band_seconds: 300,
      target_heard_fresh_seconds: 60, cross_band_verify_seconds: 60,
      band_switch_cooldown_seconds: 120,
      persist_new_dxcc_while_heard: true, persist_new_band_slot_while_heard: true,
    },
    band_schedules: {
      3: { restricted: true, start: '18:00', end: '06:00' },
      4: { restricted: true, start: '18:00', end: '06:00' },
      8: { restricted: false, start: '18:00', end: '06:00' },
    },
    spot_sources: {
      us_only: false,
      rbn: { enabled: true, host: 'telnet.reversebeacon.net', port: 7001 },
      psk_reporter: { enabled: true, poll_interval_seconds: 120 },
      dx_cluster: { enabled: true, use_default_servers: true, servers: [] },
    },
    target_priority: {
      new_dxcc: 10000, new_band_slot: 1000, new_grid: 500,
      calling_me: 400, cq: 200, snr_per_db: 10,
    },
  };
  const { instance } = fixture(async (url, options = {}) => {
    requests.push([url, options]);
    return { ok: true, json: async () => ({ ...settings, saved: options.method === 'POST' }) };
  });
  await instance.loadMshvAutoDxSettings();
  instance.mshvAutoDxSettings.target_priority.new_grid = 650;
  await instance.saveMshvAutoDxSettings();
  assert.equal(requests[0][0], '/api/digital/mshv-settings');
  assert.equal(requests[1][0], '/api/digital/mshv-settings');
  const body = JSON.parse(requests[1][1].body);
  assert.equal(body.enabled, true);
  assert.equal(body.target_priority.new_grid, 650);
  assert.equal(body.spot_sources.us_only, false);
  assert.equal(Object.hasOwn(body, 'spot_sources_us_only'), false);
  assert.deepEqual(body.auto_dx_modes, ['FT8']);
  assert.deepEqual(body.enabled_bands, [3, 4, 6, 7, 8, 9, 10, 11, 12]);
  assert.equal(body.spot_sources.rbn.port, 7001);
  assert.equal(Object.hasOwn(body.automation_timing, 'normal_call_seconds'), false);
  assert.equal(body.filter_matrix_enabled, true);
  assert.equal(body.engaged_completion_grace_seconds, 120);
  assert.equal(body.recent_qso_cooldown_seconds, 3600);
  assert.equal(body.allow_band_dxcc_outside_continent, true);
  assert.deepEqual(body.band_schedules['3'], { restricted: true, start: '18:00', end: '06:00' });
  assert.equal(body.award_hunting.stack_scores, true);
  assert.equal(body.award_hunting.new_dxcc_weight, 10000);
  assert.equal(body.reference_hunting.pota_enabled, true);
  assert.equal(body.reference_hunting.sota_enabled, true);
  assert.equal(body.reference_hunting.wwff_enabled, true);
  assert.equal(body.reference_hunting.pota_weight, 1800);
  assert.equal(body.propagation_adaptation.window_seconds, 900);
  assert.deepEqual(body.pileup_strategy.audio_offsets_hz, [0, -120, 120, -240, 240]);
  assert.equal(body.directed_callers.inbox_size, 8);
  assert.equal(body.campaign.profile, 'balanced');
  assert.equal(body.outcome_learning.enabled, true);
});

test('MSHV award settings normalize additively and auto-save through the existing endpoint', async () => {
  const requests = [];
  const responseSettings = {
    success: true, editable: true, desired: { enabled: true },
    callsign: 'OM0RX', grid: 'JN88', min_snr: -20,
    grid_chase_us_only: false, band_switching_enabled: false,
    automation_timing: {}, band_schedules: {}, enabled_bands: [8], auto_dx_modes: ['FT8'],
    filter_new: {}, filter_new_on_band: {}, filter_continents: [], spot_sources: {}, target_priority: {},
  };
  const { instance } = fixture(async (url, options = {}) => {
    requests.push([url, options]);
    return { ok: true, json: async () => ({ ...responseSettings }) };
  });
  await instance.loadMshvAutoDxSettings();
  instance.mshvAutoDxSettings.reference_hunting.pota_enabled = true;
  instance.mshvAutoDxSettings.reference_hunting.sota_enabled = true;
  instance.mshvAutoDxSettings.reference_hunting.wwff_enabled = true;
  instance.mshvAutoDxSettings.campaign.reference_weight_percent = 140;
  instance.queueMshvAutoDxSave();
  await new Promise(resolve => setTimeout(resolve, 525));
  const posts = requests.filter(([, options]) => options.method === 'POST');
  assert.equal(posts.length, 1);
  const body = JSON.parse(posts[0][1].body);
  assert.equal(body.reference_hunting.pota_enabled, true);
  assert.equal(body.reference_hunting.sota_enabled, true);
  assert.equal(body.reference_hunting.wwff_enabled, true);
  assert.equal(body.award_hunting.enabled, true);
  assert.equal(body.campaign.reference_weight_percent, 140);
  assert.equal(instance.mshvAutoDxDirty, false);
});

test('MSHV pileup audio offsets accept a bounded sequence and reject unsafe input', () => {
  const { instance } = fixture(async () => ({ ok: true, json: async () => ({}) }));
  instance.mshvAutoDxSettings = instance.normalizeMshvAwardSettings({ editable: true });
  assert.equal(instance.updateMshvAudioOffsets('0, -120, 120, -120'), true);
  assert.deepEqual(Array.from(instance.mshvAutoDxSettings.pileup_strategy.audio_offsets_hz), [0, -120, 120]);
  assert.equal(instance.updateMshvAudioOffsets('0, 2500'), false);
  assert.deepEqual(Array.from(instance.mshvAutoDxSettings.pileup_strategy.audio_offsets_hz), [0, -120, 120]);
  assert.match(instance.mshvAutoDxMessage, /−2400 to 2400 Hz/);
});

test('MSHV campaign profiles populate canonical multipliers and custom preserves them', () => {
  const { instance } = fixture(async () => ({ ok: true, json: async () => ({}) }));
  instance.mshvAutoDxSettings = instance.normalizeMshvAwardSettings({ editable: true });
  const values = () => {
    const campaign = instance.mshvAutoDxSettings.campaign;
    return [
      campaign.dxcc_weight_percent,
      campaign.state_weight_percent,
      campaign.zone_weight_percent,
      campaign.grid_weight_percent,
      campaign.reference_weight_percent,
    ];
  };
  for (const [profile, expected] of Object.entries({
    balanced: [100, 100, 100, 100, 100],
    'dxcc-challenge': [175, 75, 100, 75, 75],
    'five-band-dxcc': [200, 50, 75, 50, 50],
    'worked-all-states': [75, 200, 75, 75, 50],
    waz: [75, 50, 200, 50, 50],
    'itu-zones': [75, 50, 200, 50, 50],
    grids: [75, 50, 50, 200, 50],
    references: [75, 50, 50, 50, 200],
  })) {
    instance.applyMshvCampaignProfile(profile);
    assert.equal(instance.mshvAutoDxSettings.campaign.profile, profile);
    assert.deepEqual(values(), expected);
  }
  const beforeCustom = values();
  instance.applyMshvCampaignProfile('custom');
  assert.equal(instance.mshvAutoDxSettings.campaign.profile, 'custom');
  assert.deepEqual(values(), beforeCustom);
  clearTimeout(instance.mshvAutoDxSaveTimer);
  instance.mshvAutoDxSaveTimer = null;
});

test('status refresh does not overwrite dirty MSHV priority edits', async () => {
  let settingsFetches = 0;
  const { instance } = fixture(async (url) => {
    if (url === '/api/digital/status') return {
      ok: true,
      json: async () => ({ selected_engine: 'mshv_auto_dx' }),
    };
    settingsFetches += 1;
    return {
      ok: true,
      json: async () => ({ success: true, editable: true, target_priority: { new_grid: 500 } }),
    };
  });
  instance.configDialogVisible = true;
  instance.activeConfigTab = 'wsjtx';
  await instance.loadMshvAutoDxSettings();
  instance.mshvAutoDxSettings.target_priority.new_grid = 777;
  instance.mshvAutoDxDirty = true;
  await instance.loadDigitalEngineStatus();
  assert.equal(settingsFetches, 1);
  assert.equal(instance.mshvAutoDxSettings.target_priority.new_grid, 777);
});

test('emergency halt displays command acceptance separately from idle confirmation', async () => {
  const { instance } = fixture(async () => ({
    ok: true,
    json: async () => ({ selected_engine: 'mshv_auto_dx', command_accepted: true, idle_confirmed: false }),
  }));
  instance.digitalEngineChoice = 'mshv_auto_dx';
  await instance.digitalEngineAction('halt-tx');
  assert.equal(instance.digitalEngineMessage, 'halt command accepted; RF idle confirmation pending.');
});

test('missing telemetry is displayed as unknown rather than healthy', () => {
  const { instance } = fixture(async () => {});
  assert.equal(instance.digitalEngineHealthText('dax'), 'not reported');
  instance.digitalEngineStatus = { health: { udp: { status: 'stale' } } };
  assert.equal(instance.digitalEngineHealthText('udp'), 'stale');
});

test('MSHV blocks every OM0RX transmit action but keeps provider emergency halt', async () => {
  const requests = [];
  const context = {
    window: { om0rxDigitalEngine: 'mshv_auto_dx' },
    fetch: async (url) => {
      requests.push(url);
      return { ok: true, json: async () => ({ success: true, command_accepted: true, idle_confirmed: false }) };
    },
    console: { log() {}, warn() {}, error() {} },
    setInterval, clearInterval, setTimeout, clearTimeout, URLSearchParams, Date,
  };
  vm.runInNewContext(fs.readFileSync('frontend/js/ft8-modal.js', 'utf8'), context);
  const methods = context.window.ft8ModalMixin.methods;
  const instance = {
    ...methods,
    mshvOwnsDigitalPlanner: true,
    ft8: {
      connected: true,
      engine: { transmit: true },
      autoCQ: true,
      autoCall: true,
      automation: { enabled: true, spotHuntEnabled: true },
      txMessages: [{ id: 1, text: 'EA1AA OM0RX JN88' }],
      selectedTxMessage: 1,
      txOffset: 1500,
    },
    async ft8PollStatus() {},
  };
  await instance.ft8EnableTx();
  await instance.ft8TuneTone();
  await instance.ft8TuneRadioFrequency(14.074, 'FT8');
  await instance.ft8QueueSelectedTxMessage(1, { immediate: true });
  assert.deepEqual(requests, []);
  assert.equal(instance.ft8.autoCQ, false);
  assert.match(instance.ft8.errorMessage, /blocked by MSHV/);
  await instance.ft8HaltTx();
  assert.deepEqual(requests, ['/api/digital/halt-tx']);
  assert.match(instance.ft8.radioSyncMessage, /confirmation pending/);
});

test('None selection blocks all digital TX controls and exposes no start action', async () => {
  const { instance, window } = fixture(async () => ({
    ok: true,
    json: async () => ({ selected_engine: 'none', planner_owner: 'none', running: false }),
  }));
  await instance.loadDigitalEngineStatus();
  assert.equal(instance.digitalEngineChoice, 'none');
  assert.equal(instance.digitalEngineDisabled, true);
  assert.equal(instance.digitalEngineBlocksOm0rx, true);
  assert.equal(window.om0rxDigitalEngine, 'none');
  const template = fs.readFileSync('frontend/templates/modal-config.html', 'utf8');
  assert.match(template, /option value="none"/);
  assert.match(template, /digitalEngineChoice === 'none'/);
});

test('MSHV template disables legacy TX controls and leaves Emergency Halt enabled', () => {
  const template = fs.readFileSync('frontend/templates/modal-ft8.html', 'utf8');
  assert.match(template, /:disabled="mshvOwnsDigitalPlanner \|\| !ft8\.engine\.transmit"/);
  assert.match(template, /<fieldset :disabled="mshvOwnsDigitalPlanner"/);
  assert.match(template, /mshvOwnsDigitalPlanner \? ft8HaltTx\(\) : ft8StopTransmitOnly\(\)/);
  assert.match(template, /'Emergency Halt TX'/);
});

test('MSHV priority template keeps grid enabled and documents bonus-only behavior', () => {
  const template = fs.readFileSync('frontend/templates/modal-config.html', 'utf8');
  assert.match(template, /mshvAutoDxSettings\.target_priority\.new_grid/);
  assert.match(template, /min="1" max="100000"/);
  assert.match(template, /Minimum SNR<input type="number" min="-30" max="0"/);
  assert.match(template, /CQ and SNR only rank eligible stations/);
  assert.match(template, /!mshvAutoDxSettings\.editable/);
  assert.match(template, /mshvAutoDxSettings\.band_switching_enabled/);
  assert.match(template, /mshvAutoDxSettings\.enabled_bands/);
  assert.match(template, /mshvAutoDxSettings\.spot_sources\.rbn\.enabled/);
  assert.match(template, /Phase 1 automation mode is fixed to FT8/);
  assert.doesNotMatch(template, /Scarce-target threshold/);
  assert.doesNotMatch(template, /v-model\.number="mshvAutoDxSettings\.scarce_threshold"/);
});

test('MSHV template exposes native automation timing and local band schedules', () => {
  const template = fs.readFileSync('frontend/templates/modal-config.html', 'utf8');
  assert.match(template, /Automation Timing &amp; Band Schedules/);
  assert.match(template, /Total attempt budget:/);
  assert.match(template, /automation_timing\.quiet_band_seconds/);
  assert.match(template, /persist_new_dxcc_while_heard/);
  assert.match(template, /band_schedules\[band\.i\]\.restricted/);
  assert.match(template, /type="time"/);
  assert.match(template, /computer's local time/);
  assert.match(template, /Changes apply and persist automatically/);
});

test('MSHV template exposes independent award, reference, adaptation, and learning campaigns', () => {
  const template = fs.readFileSync('frontend/templates/modal-config.html', 'utf8');
  for (const contract of [
    'award_hunting.stack_scores',
    'award_hunting.new_dxcc_weight',
    'award_hunting.new_dxcc_band_weight',
    'award_hunting.unconfirmed_dxcc_weight',
    'award_hunting.new_continent_weight',
    'award_hunting.new_cq_zone_weight',
    'award_hunting.new_itu_zone_weight',
    'award_hunting.new_grid_weight',
    'reference_hunting.pota_enabled',
    'reference_hunting.sota_enabled',
    'reference_hunting.wwff_enabled',
    'reference_hunting.new_reference_band_mode_weight',
    'propagation_adaptation.window_seconds',
    'mshvAudioOffsetsText()',
    'directed_callers.inbox_size',
    'campaign.reference_weight_percent',
    'outcome_learning.enabled',
  ]) assert.ok(template.includes(contract), contract);
  assert.match(template, /enabling one campaign never disables another/i);
  assert.match(template, /POTA, SOTA, and WWFF switches are independent/);
  assert.match(template, /@input="queueMshvAutoDxSave"/);
  assert.match(template, /DXCC Challenge 175\/75\/100\/75\/75/);
  assert.match(template, /newest 2 MiB/);
  assert.match(template, /\+75 per completed outcome and −25 per non-completed outcome/);
  assert.match(template, /never overrides duplicate or safety rules/);
});

test('MSHV hunting has a dedicated operator settings tab', () => {
  const template = fs.readFileSync('frontend/templates/modal-config.html', 'utf8');
  const script = fs.readFileSync('frontend/js/config-modal.js', 'utf8');
  assert.match(script, /\{ id: 'mshv', name: 'MSHV hunting' \}/);
  assert.match(template, /activeConfigTab === 'wsjtx' \|\| activeConfigTab === 'mshv'/);
  assert.match(template, /activeConfigTab === 'mshv' \|\| digitalEngineChoice === 'mshv_auto_dx'/);
  assert.match(script, /tabId === 'mshv'/);
  assert.match(script, /loadMshvAutoDxSettings\(true\)/);
});

test('MSHV award UI uses the canonical backend bounds', () => {
  const template = fs.readFileSync('frontend/templates/modal-config.html', 'utf8');
  for (const pattern of [
    /min="60" max="86400" v-model\.number="mshvAutoDxSettings\.reference_hunting\.max_activation_age_seconds"/,
    /min="60" max="86400" v-model\.number="mshvAutoDxSettings\.propagation_adaptation\.window_seconds"/,
    /min="0" max="100000" v-model\.number="mshvAutoDxSettings\.propagation_adaptation\.unique_decode_weight"/,
    /min="0" max="100000" v-model\.number="mshvAutoDxSettings\.propagation_adaptation\.distant_decode_weight"/,
    /min="0" max="100000" v-model\.number="mshvAutoDxSettings\.propagation_adaptation\.successful_qso_weight"/,
    /min="1" max="20" v-model\.number="mshvAutoDxSettings\.pileup_strategy\.rotate_after_attempts"/,
    /min="0" max="86400" v-model\.number="mshvAutoDxSettings\.pileup_strategy\.revisit_delay_seconds"/,
    /min="1" max="100" v-model\.number="mshvAutoDxSettings\.directed_callers\.inbox_size"/,
    /min="15" max="3600" v-model\.number="mshvAutoDxSettings\.directed_callers\.max_age_seconds"/,
    /min="0" max="500" v-model\.number="mshvAutoDxSettings\.campaign\.reference_weight_percent"/,
  ]) assert.match(template, pattern);
});

test('MSHV template exposes canonical native schema-v1 filters and attempt tuning', () => {
  const template = fs.readFileSync('frontend/templates/modal-config.html', 'utf8');
  for (const contract of [
    'mshvAutoDxSettings.filter_new[dimension]',
    'mshvAutoDxSettings.filter_new_on_band[dimension]',
    'mshvAutoDxSettings.filter_continents',
    'mshvAutoDxSettings.allow_band_dxcc_outside_continent',
    'mshvAutoDxSettings.filter_lotw_only',
    'mshvAutoDxSettings.treat_73_as_cq',
    'mshvAutoDxSettings.watch_unconfirmed_dxcc',
    'mshvAutoDxSettings.call_window_seconds',
    'mshvAutoDxSettings.max_consecutive_windows',
    'mshvAutoDxSettings.same_target_revisit_delay_seconds',
    'mshvAutoDxSettings.recent_qso_cooldown_seconds',
    'mshvAutoDxSettings.min_band_dwell_seconds',
    'mshvAutoDxSettings.engaged_completion_grace_seconds',
    'mshvAutoDxSettings.target_priority.non_europe',
    'mshvAutoDxSettings.selection_order',
  ]) assert.ok(template.includes(contract), contract);
  assert.match(template, /LoTW-membership data/);
  assert.match(template, /saved but intentionally inactive until this switch is enabled/);
  assert.match(template, /absolute cap is the normal attempt budget plus this grace/);
  assert.match(template, /min="15" max="120" step="15"/);
  assert.match(template, /Recent-QSO cooldown \(seconds\)/);
  assert.match(template, /set 0 to disable that cooldown/);
  assert.match(template, /<option value="score">Highest score<\/option>/);
  assert.match(template, /<option value="last">Most recently decoded<\/option>/);
  assert.doesNotMatch(template, /target_priority\.new_call/);
  assert.doesNotMatch(template, /target_priority\.new_continent/);
});

test('MSHV status panel renders native planner observability without controls', () => {
  const { instance } = fixture(async () => ({ ok: true, json: async () => ({}) }));
  instance.digitalEngineStatus = {
    autodx_status: { target: { call: 'VK9AA', band_index: 8, grid: 'QF56' }, active_schedule: {band: '20m'}, selection_score: 10000 },
  };
  assert.equal(instance.mshvTargetText(), 'VK9AA · 20m · QF56');
  assert.equal(instance.mshvAutoDxStatus().selection_score, 10000);
  const template = fs.readFileSync('frontend/templates/modal-config.html', 'utf8');
  for (const label of ['AutoDX telemetry:', 'Selected:', 'Next retry:', 'Band dwell:', 'Next QSY:', 'Last directed caller:', 'Wavelog:', 'Recent skips:']) {
    assert.ok(template.includes(label), label);
  }
});

test('MSHV exposes one canonical external-source US-only control', () => {
  const template = fs.readFileSync('frontend/templates/modal-config.html', 'utf8');
  assert.match(template, /id="mshv-runtime-us-only"/);
  assert.match(template, /Prefer US spotters \(rare-DX exceptions\)/);
  assert.doesNotMatch(template, /id="mshv-spots-us-only"/);
  assert.equal((template.match(/v-model="mshvAutoDxSettings\.spot_sources\.us_only"/g) || []).length, 1);
});

test('MSHV effective AutoDX reports unknown when native state is absent', () => {
  const { instance } = fixture(async () => ({ ok: true, json: async () => ({}) }));
  assert.equal(instance.mshvEffectiveAutoDxText({ effective: { status: 'native-runtime-config-not-reported' } }), 'unknown');
  assert.equal(instance.mshvEffectiveAutoDxText({ effective: { effective_enabled: false } }), 'off');
  assert.equal(instance.mshvEffectiveAutoDxText({ effective: { effective_enabled: true } }), 'on');
  assert.equal(instance.mshvEffectiveAutoDxText({ effective: null }), 'engine stopped');
});

test('MSHV runtime parity distinguishes match, drift, and unknown', () => {
  const { instance } = fixture(async () => ({ ok: true, json: async () => ({}) }));
  assert.equal(instance.mshvRuntimeParityText({ runtime_parity: { status: 'match', drift: [] } }), 'matched');
  assert.equal(instance.mshvRuntimeParityText({ runtime_parity: { status: 'drift', drift: ['min_snr', 'spot_sources'] } }), 'drift: min_snr, spot_sources');
  assert.equal(instance.mshvRuntimeParityText({ runtime_parity: { status: 'unknown' } }), 'unknown');
  assert.equal(instance.mshvRuntimeParityText({}), 'unknown');
});

test('MSHV cluster editor preserves the composable draft and queues persistence', () => {
  const { instance } = fixture(async () => {});
  instance.mshvAutoDxSettings = {
    spot_sources: { dx_cluster: { servers: [] } },
  };
  instance.addMshvDxClusterServer();
  assert.equal(instance.mshvAutoDxSettings.spot_sources.dx_cluster.servers.length, 1);
  assert.equal(instance.mshvAutoDxSettings.spot_sources.dx_cluster.servers[0].enabled, false);
  assert.equal(instance.mshvAutoDxDirty, true);
  instance.removeMshvDxClusterServer(0);
  assert.equal(instance.mshvAutoDxSettings.spot_sources.dx_cluster.servers.length, 0);
  clearTimeout(instance.mshvAutoDxSaveTimer);
  instance.mshvAutoDxSaveTimer = null;
});
