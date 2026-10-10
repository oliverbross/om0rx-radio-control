// Offline contracts for the compact station path and guarded KPA control widget.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('widget contains exactly the four ordered live path cards', () => {
  const page = fs.readFileSync('frontend/station-widget.html', 'utf8');
  const ids = [...page.matchAll(/data-path-segment="([^"]+)"/g)].map(match => match[1]);

  assert.deepEqual(ids, ['flex', 'kpa500', 'kat500', 'antenna']);
  assert.match(page, /js\/station-path\.js/);
  assert.match(page, /js\/station-widget\.js/);
  assert.match(page, /station-widget\.css/);
  assert.match(page, /data-kpa-toggle/);
  assert.match(page, />Switch<\/button>/);
  assert.match(page, /role="switch"/);
  assert.match(page, /station-widget-status-message/);
  assert.match(page, /data-path-role="tx-power"/);
  assert.match(page, /data-path-value="rf-power"/);
  const kpaCard = page.match(/data-path-segment="kpa500"[\s\S]*?<\/article>/)?.[0] || '';
  assert.doesNotMatch(kpaCard, /data-path-role="state"/);
  assert.doesNotMatch(kpaCard, /data-path-role="secondary"/);
  assert.doesNotMatch(page, /\/api\/(?:elecraft\/(?:raw|command|write)|station\/action)/i);
});

test('action failures remain visibly rendered instead of being screen-reader-only', () => {
  const page = fs.readFileSync('frontend/station-widget.html', 'utf8');
  const css = fs.readFileSync('frontend/station-widget.css', 'utf8');
  const source = fs.readFileSync('frontend/js/station-path.js', 'utf8');

  assert.match(page, /class="station-widget-status-message"[^>]*data-path-role="message"/);
  assert.match(css, /\.station-widget-status-message\s*\{[^}]*font-size:\s*11px/s);
  assert.match(source, /latestActionError\s*\?\s*`KPA500 action blocked:/);
  const streamHandler = source.match(/function applyStreamPayload[\s\S]*?(?=\n    function connectStream)/)?.[0] || '';
  assert.doesNotMatch(streamHandler, /latestActionError\s*=\s*null/);
});

test('operate and standby switch immediately without a confirmation popup', () => {
  const source = fs.readFileSync('frontend/js/station-path.js', 'utf8');
  const handler = source.match(/async function handleKpaToggle\(\)[\s\S]*?(?=\n    function bindActions)/)?.[0] || '';

  assert.match(handler, /await postAction\(model\.target\)/);
  assert.match(handler, /await fetchStatus\(\)/);
  assert.doesNotMatch(handler, /fetchStatus\(true\)/);
  assert.doesNotMatch(handler, /window\.confirm/);
  assert.doesNotMatch(handler, /postAction\('prepare-route'\)/);
});

test('the KPA control uses one compact Switch label while accessibility names the transition', () => {
  const source = fs.readFileSync('frontend/js/station-path.js', 'utf8');
  const model = source.match(/function kpaControlModel\(\)[\s\S]*?(?=\n    function renderKpaControl)/)?.[0] || '';

  assert.match(model, /: 'Switch'/);
  assert.match(source, /Hardware readback:/);
  assert.match(source, /\? 'OPERATE' : 'STANDBY'/);
});

test('an interrupted amplifier key line is treated as a recoverable failed operate state', () => {
  const source = fs.readFileSync('frontend/js/station-path.js', 'utf8');
  const model = source.match(/function kpaControlModel\(\)[\s\S]*?(?=\n    function renderKpaControl)/)?.[0] || '';

  assert.match(model, /kat\.amp_key_interrupted !== true/);
  assert.match(model, /const target = operating \? 'standby' : 'operate'/);
  assert.match(model, /const canPrepare = target === 'operate'/);
});

test('widget stylesheet supports explicit horizontal and vertical layouts', () => {
  const css = fs.readFileSync('frontend/station-widget.css', 'utf8');

  assert.match(css, /grid-template-columns:\s*repeat\(4/);
  assert.doesNotMatch(css, /data-widget-orientation="horizontal"[^}]*min-width:\s*900px/s);
  assert.match(css, /data-widget-orientation="vertical"/);
  assert.match(css, /grid-template-columns:\s*minmax\(240px, 1fr\)/);
  assert.match(css, /html,[\s\S]*?body\s*\{[^}]*overflow:\s*hidden/s);
  assert.match(css, /grid-template-rows:\s*repeat\(4,\s*minmax\(0,\s*1fr\)\)/);
  assert.match(css, /\.station-path-primary[^}]*font-size:\s*19px/s);
  assert.match(css, /\.station-path-values dd[^}]*font-size:\s*13px/s);
  assert.match(css, /\.station-antenna-tx[^}]*font-size:\s*23px/s);
  assert.match(css, /data-amplifier-state="operate"[^}]*\.station-path-primary\s*\{[^}]*color:\s*#4ade80/s);
  assert.match(css, /data-amplifier-state="standby"[^}]*\.station-path-primary\s*\{[^}]*color:\s*#fbbf24/s);
  assert.match(css, /data-amplifier-state="tx"[^}]*\.station-path-primary[^{]*\{[^}]*color:\s*#fb7185/s);
  assert.match(css, /station-kpa-toggle\[data-target-action="standby"\][^}]*border-color:\s*#f59e0b/s);
});

test('orientation is persisted and the shared path monitor is started', () => {
  const listeners = new Map();
  const buttons = [
    { dataset: { widgetOrientation: 'horizontal' }, setAttribute(name, value) { this[name] = value; } },
    { dataset: { widgetOrientation: 'vertical' }, setAttribute(name, value) { this[name] = value; } },
  ];
  const stored = new Map([['om0rx.stationWidget.orientation', 'vertical']]);
  const dispatched = [];
  const resizeCalls = [];
  const windowListeners = new Map();
  const body = { dataset: {} };
  const root = {
    getBoundingClientRect: () => ({ height: body.dataset.widgetOrientation === 'vertical' ? 620 : 194 }),
  };
  const document = {
    readyState: 'loading',
    body,
    addEventListener: (name, callback) => listeners.set(name, callback),
    dispatchEvent: event => dispatched.push(event.type),
    getElementById: id => id === 'station-path-dashboard' ? root : null,
    querySelector: () => null,
    querySelectorAll: selector => selector === '[data-widget-orientation]' ? buttons : [],
  };
  const window = {
    __om0rxWidgetStorage: {
      getItem: key => stored.get(key),
      setItem: (key, value) => stored.set(key, value),
    },
    outerWidth: 474,
    innerWidth: 430,
    outerHeight: 690,
    innerHeight: 627,
    resizeTo(width, height) {
      resizeCalls.push([width, height]);
      this.outerWidth = width;
      this.outerHeight = height;
      this.innerWidth = width - 44;
      this.innerHeight = height - 63;
    },
    addEventListener: (name, callback) => windowListeners.set(name, callback),
  };
  class CustomEvent { constructor(type) { this.type = type; } }

  vm.runInNewContext(
    fs.readFileSync('frontend/js/station-widget.js', 'utf8'),
    { window, document, CustomEvent, MutationObserver: undefined, Set, Object },
  );
  listeners.get('DOMContentLoaded')();

  assert.equal(document.body.dataset.widgetOrientation, 'vertical');
  assert.equal(window.StationPathWidget.preferenceStorage(), window.__om0rxWidgetStorage);
  assert.equal(buttons[0]['aria-pressed'], 'false');
  assert.equal(buttons[1]['aria-pressed'], 'true');
  assert.deepEqual(dispatched, ['vue-mounted']);
  assert.deepEqual(resizeCalls, []);

  window.StationPathWidget.setOrientation('horizontal', { resize: true });
  assert.equal(document.body.dataset.widgetOrientation, 'horizontal');
  assert.equal(stored.get('om0rx.stationWidget.orientation'), 'horizontal');
  assert.deepEqual(resizeCalls, [[1164, 690], [1164, 257]]);

  window.innerWidth = 610;
  window.innerHeight = 330;
  assert.equal(window.StationPathWidget.rememberSize(), true);
  assert.equal(stored.get('om0rx.stationWidget.size.horizontal'), JSON.stringify({ width: 610, height: 330 }));
  assert.ok(windowListeners.has('resize'));
});

test('only orientation toolbar buttons can resize the widget', () => {
  const source = fs.readFileSync('frontend/js/station-widget.js', 'utf8');
  const handler = source.match(/function handleClick\(event\)[\s\S]*?(?=\n    function start)/)?.[0] || '';

  assert.match(handler, /closest\?\.\('button\[data-widget-orientation\]'\)/);
  assert.doesNotMatch(handler, /closest\?\.\('\[data-widget-orientation\]'\)/);
});
