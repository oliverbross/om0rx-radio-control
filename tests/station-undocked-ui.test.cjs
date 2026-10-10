// Offline contracts for the separate Station Management window.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const PANEL_PARTIALS = [
  ['station-path', 'station-path-dashboard'],
  ['station-history', 'station-history-panel'],
  ['station-workflow', 'station-workflow-panel'],
  ['station-training-preview', 'station-training-preview'],
  ['station-configuration', 'station-configuration-panel'],
  ['station-commissioning', 'station-commissioning-panel'],
];

test('main controls contain one launcher and no station-management panels', () => {
  const row = fs.readFileSync('frontend/templates/controls-row1.html', 'utf8');
  const index = fs.readFileSync('frontend/index.html', 'utf8');

  assert.equal((row.match(/id="station-management-launcher"/g) || []).length, 1);
  for (const [name, id] of PANEL_PARTIALS) {
    assert.doesNotMatch(row, new RegExp(`@include templates/partials/${name}\\.html`));
    assert.doesNotMatch(row, new RegExp(`id="${id}"`));
    assert.doesNotMatch(index, new RegExp(`js/${name}\\.js`));
    assert.doesNotMatch(index, new RegExp(`${name}\\.css`));
  }
});

test('launcher opens and reuses the exact local Station Management page', () => {
  const listeners = new Map();
  const window = {};
  const document = { addEventListener: (name, callback) => listeners.set(name, callback) };
  vm.runInNewContext(
    fs.readFileSync('frontend/js/station-launcher.js', 'utf8'),
    { window, document, Object },
  );

  const calls = [];
  let focusCount = 0;
  const opened = window.StationManagementLauncher.openStationManagement((...args) => {
    calls.push(args);
    return { focus: () => { focusCount += 1; } };
  });

  assert.ok(opened);
  assert.equal(window.StationManagementLauncher.STATION_PAGE, '/station.html');
  assert.equal(calls[0][0], '/station.html');
  assert.equal(calls[0][1], 'om0rxStationManagement');
  assert.match(calls[0][2], /resizable=yes/);
  assert.equal(focusCount, 1);
  assert.ok(listeners.has('click'));
});

test('path launcher opens one reusable compact popup synchronously', () => {
  const listeners = new Map();
  const window = {};
  const document = { addEventListener: (name, callback) => listeners.set(name, callback) };
  vm.runInNewContext(
    fs.readFileSync('frontend/js/station-launcher.js', 'utf8'),
    { window, document, Object, Boolean },
  );

  const calls = [];
  let focusCount = 0;
  const popup = { opener: window, focus: () => { focusCount += 1; } };
  const opened = window.StationManagementLauncher.openStationWidget((...args) => {
    calls.push(args);
    return popup;
  }, window);

  assert.ok(opened);
  assert.equal(window.StationManagementLauncher.WIDGET_PAGE, '/station-widget.html');
  assert.equal(calls[0][0], '/station-widget.html');
  assert.equal(calls[0][1], 'om0rxStationPathWidget');
  assert.match(calls[0][2], /width=1120/);
  assert.equal(focusCount, 1);
  assert.equal(popup.opener, null);
});

test('station management makes Radio Control the widget owner so the widget survives its close', async () => {
  const listeners = new Map();
  let focusCount = 0;
  const calls = [];
  let callOwner = null;
  const popup = { opener: null, focus: () => { focusCount += 1; } };
  const radioWindow = {
    closed: false,
    open(...args) {
      callOwner = this;
      calls.push(args);
      popup.opener = this;
      return popup;
    },
  };
  const window = {
    name: 'om0rxStationManagement',
    opener: radioWindow,
  };
  const document = { addEventListener: (name, callback) => listeners.set(name, callback) };
  vm.runInNewContext(
    fs.readFileSync('frontend/js/station-launcher.js', 'utf8'),
    { window, document, Object, Boolean },
  );

  const result = await window.StationManagementLauncher.openStationWidget(null, window);

  assert.ok(result);
  assert.equal(callOwner, radioWindow);
  assert.equal(calls[0][0], '/station-widget.html');
  assert.equal(calls[0][1], 'om0rxStationPathWidget');
  assert.equal(focusCount, 1);
  assert.equal(popup.opener, null);
});

test('widget uses a normal popup even when document Picture-in-Picture is available', async () => {
  const listeners = new Map();
  const calls = [];
  let pipRequests = 0;
  let focused = 0;
  const popup = { opener: null, focus: () => { focused += 1; } };
  const window = {
    localStorage: { getItem: () => null },
    open(...args) {
      calls.push(args);
      return popup;
    },
    documentPictureInPicture: {
      requestWindow: async () => {
        pipRequests += 1;
        throw new Error('must not request always-on-top Picture-in-Picture');
      },
    },
  };
  const document = { addEventListener: (name, callback) => listeners.set(name, callback) };
  vm.runInNewContext(
    fs.readFileSync('frontend/js/station-launcher.js', 'utf8'),
    { window, document, Object, Boolean },
  );

  const result = await window.StationManagementLauncher.openStationWidget(null, window);

  assert.equal(result, popup);
  assert.equal(pipRequests, 0);
  assert.equal(calls[0][0], '/station-widget.html');
  assert.equal(calls[0][1], 'om0rxStationPathWidget');
  assert.match(calls[0][2], /popup=yes/);
  assert.equal(focused, 1);
});

test('desktop launcher uses a native chromeless widget with normal z-order', async () => {
  const listeners = new Map();
  const calls = [];
  let popupCalls = 0;
  const window = {
    localStorage: { getItem: () => null },
    pywebview: {
      api: {
        open_station_widget: async (...args) => {
          calls.push(args);
          return { success: true, native: true, reused: false };
        },
      },
    },
    open() {
      popupCalls += 1;
      return null;
    },
  };
  const document = { addEventListener: (name, callback) => listeners.set(name, callback) };
  vm.runInNewContext(
    fs.readFileSync('frontend/js/station-launcher.js', 'utf8'),
    { window, document, Object, Boolean },
  );

  const result = await window.StationManagementLauncher.openStationWidget(null, window);

  assert.equal(result.native, true);
  assert.equal(popupCalls, 0);
  assert.deepEqual(Array.from(calls[0]), ['horizontal', 1120, 250]);
});

test('widget launcher opens at the saved orientation dimensions', async () => {
  const listeners = new Map();
  let requestedFeatures = null;
  const popup = { opener: null, focus() {} };
  const window = {
    localStorage: {
      getItem: key => key === 'om0rx.stationWidget.orientation'
        ? 'vertical'
        : key === 'om0rx.stationWidget.size.vertical'
          ? JSON.stringify({ width: 515, height: 640 })
          : null,
    },
    open(path, name, features) {
      requestedFeatures = features;
      return popup;
    },
  };
  const document = { addEventListener: (name, callback) => listeners.set(name, callback) };
  vm.runInNewContext(
    fs.readFileSync('frontend/js/station-launcher.js', 'utf8'),
    { window, document, Object, Boolean },
  );

  await window.StationManagementLauncher.openStationWidget(null, window);

  assert.match(requestedFeatures, /width=515/);
  assert.match(requestedFeatures, /height=640/);
});

test('radio and management windows both expose the path widget launcher', () => {
  const row = fs.readFileSync('frontend/templates/controls-row1.html', 'utf8');
  const stationPage = fs.readFileSync('frontend/station.html', 'utf8');

  assert.equal((row.match(/id="station-widget-launcher"/g) || []).length, 1);
  assert.equal((stationPage.match(/id="station-widget-launcher"/g) || []).length, 1);
  assert.match(stationPage, /js\/station-launcher\.js/);
});

test('station popup returns to its original Radio Control window instead of navigating itself', () => {
  const listeners = new Map();
  let openerFocuses = 0;
  let closes = 0;
  const opener = { closed: false, focus: () => { openerFocuses += 1; } };
  const window = {
    name: 'om0rxStationManagement',
    opener,
    close: () => { closes += 1; },
  };
  const document = {
    readyState: 'loading',
    addEventListener: (name, callback) => listeners.set(name, callback),
  };
  vm.runInNewContext(
    fs.readFileSync('frontend/js/station-launcher.js', 'utf8'),
    { window, document, Object, Boolean },
  );

  assert.equal(window.StationManagementLauncher.returnToOpener(), true);
  assert.equal(openerFocuses, 1);
  assert.equal(closes, 1);
});

test('station page return control focuses its opener and closes the popup', () => {
  const listeners = new Map();
  let openerFocuses = 0;
  let closes = 0;
  const window = {
    opener: { closed: false, focus: () => { openerFocuses += 1; } },
    close: () => { closes += 1; },
    location: { assign: () => { throw new Error('should not navigate'); } },
  };
  const document = { addEventListener: (name, callback) => listeners.set(name, callback) };
  vm.runInNewContext(
    fs.readFileSync('frontend/js/station-navigation.js', 'utf8'),
    { window, document, Object },
  );

  assert.equal(window.StationWindowNavigation.returnToRadioControl(), 'opener');
  assert.equal(openerFocuses, 1);
  assert.equal(closes, 1);
  assert.match(fs.readFileSync('frontend/station.html', 'utf8'), /Close &amp; return to Radio Control/);
});

test('dedicated page loads all six shared panels and no raw Elecraft command route', () => {
  const page = fs.readFileSync('frontend/station.html', 'utf8');
  const shell = fs.readFileSync('frontend/js/station-shell.js', 'utf8');
  const sources = [page, shell];

  assert.match(page, /id="station-management-panels"/);
  assert.match(page, /js\/station-navigation\.js/);
  assert.doesNotMatch(page, /vue(?:\.global)?(?:\.prod)?\.js/i);
  for (const [name, id] of PANEL_PARTIALS) {
    const partialPath = `frontend/templates/partials/${name}.html`;
    const partial = fs.readFileSync(partialPath, 'utf8');
    sources.push(partial);
    assert.match(shell, new RegExp(`templates/partials/${name}\\.html`));
    assert.match(page, new RegExp(`js/${name}\\.js`));
    assert.match(page, new RegExp(`${name}\\.css`));
    assert.match(partial, new RegExp(`id="${id}"`));
  }

  assert.doesNotMatch(sources.join('\n'), /\/api\/elecraft\/(?:raw|command|write)/i);
});

test('full station page applies the large-display readability layer last', () => {
  const page = fs.readFileSync('frontend/station.html', 'utf8');
  const readable = fs.readFileSync('frontend/station-readability.css', 'utf8');
  const widget = fs.readFileSync('frontend/station-widget.html', 'utf8');

  assert.ok(page.indexOf('station-readability.css') > page.indexOf('station-commissioning.css'));
  assert.doesNotMatch(widget, /station-readability\.css/);
  assert.match(readable, /max-width:\s*2400px/);
  assert.match(readable, /\.station-config-routing-table\s*\{[^}]*font-size:\s*13px/s);
  assert.match(readable, /\.station-workflow-actions button\s*\{[^}]*font-size:\s*14px/s);
  assert.doesNotMatch(readable, /font-size:\s*(?:[0-9]|10)px/);
});

test('station shell inserts every partial before either startup event', () => {
  const shell = fs.readFileSync('frontend/js/station-shell.js', 'utf8');
  const insertAt = shell.indexOf("root.innerHTML = panels.join('\\n')");
  const templatesAt = shell.indexOf("new CustomEvent('templates-loaded')");
  const modulesAt = shell.indexOf("new CustomEvent('vue-mounted')");

  assert.ok(insertAt >= 0);
  assert.ok(templatesAt > insertAt);
  assert.ok(modulesAt > templatesAt);
  assert.match(shell, /await Promise\.all\(PARTIALS\.map/);
  assert.match(shell, /resolveIncludes/);
});
