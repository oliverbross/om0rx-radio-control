// Offline contracts for the read-only station telemetry history panel.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function history() {
  const window = { addEventListener() {} };
  const context = {
    window, console, URLSearchParams, AbortController,
    setInterval, clearInterval, setTimeout, clearTimeout,
  };
  vm.runInNewContext(fs.readFileSync('frontend/js/station-history.js', 'utf8'), context);
  return window.StationHistory;
}

test('builds bounded GET history URLs for the selected metric and window', () => {
  const api = history();
  const urls = api.buildUrls('kat.swr', 3600, Date.parse('2026-10-04T10:00:00Z'));
  assert.match(urls.telemetry, /^\/api\/station\/telemetry\?/);
  assert.match(urls.telemetry, /metric=kat.swr/);
  assert.match(urls.telemetry, /bucket_seconds=15/);
  assert.match(urls.events, /^\/api\/station\/events\?/);
  assert.match(urls.tunes, /^\/api\/station\/tunes\?/);
  assert.equal(urls.end - urls.start, 3600 * 1000);
});

test('normalizes raw and bucketed samples into a dependency-free chart model', () => {
  const api = history();
  const start = Date.parse('2026-10-04T09:00:00Z');
  const end = Date.parse('2026-10-04T10:00:00Z');
  const model = api.buildChartModel({
    metric: 'kpa.swr', start, end,
    telemetry: [
      { observed_at: '2026-10-04T09:10:00Z', value: 1.4 },
      { observed_at: '2026-10-04T09:20:00Z', min: 1.1, avg: 1.2, max: 1.5 },
    ],
    events: [{ occurred_at: '2026-10-04T09:15:00Z', event_type: 'fault' }],
    tunes: [{ completed_at: '2026-10-04T09:30:00Z', outcome: 'succeeded' }],
  });
  assert.equal(model.points.length, 2);
  assert.match(model.path, /^M/);
  assert.equal(model.markers.length, 2);
  assert.equal(model.markers[0].kind, 'event');
  assert.equal(model.config.label, 'KPA SWR');
});

test('reports unavailable telemetry and degraded auxiliary history explicitly', () => {
  const api = history();
  assert.equal(api.availabilityState([
    { available: false }, { available: true }, { available: true },
  ], 0), 'unavailable');
  assert.equal(api.availabilityState([
    { available: true }, { available: false }, { available: true },
  ], 2), 'degraded');
  assert.equal(api.availabilityState([
    { available: true }, { available: true }, { available: true },
  ], 0), 'empty');
});

test('recent activity merges events and tune outcomes newest-first', () => {
  const items = history().recentItems(
    [{ occurred_at: '2026-10-04T09:10:00Z', event_type: 'route_changed', details: { message: 'ANT2' } }],
    [{ completed_at: '2026-10-04T09:30:00Z', outcome: 'matched', route_id: '40m-ant2', swr_after: 1.18 }],
  );
  assert.equal(items[0].kind, 'tune');
  assert.match(items[0].detail, /SWR 1\.18/);
  assert.equal(items[1].label, 'route changed');
});

test('panel is integrated as read-only history with no action endpoints', () => {
  const template = fs.readFileSync('frontend/templates/partials/station-history.html', 'utf8');
  const source = fs.readFileSync('frontend/js/station-history.js', 'utf8');
  const shell = fs.readFileSync('frontend/js/station-shell.js', 'utf8');
  const page = fs.readFileSync('frontend/station.html', 'utf8');
  assert.doesNotMatch(template, /<button|@click/);
  assert.match(template, /data-history-role="metric"/);
  assert.match(template, /data-history-role="window"/);
  assert.match(shell, /templates\/partials\/station-history\.html/);
  assert.doesNotMatch(source, /method\s*:\s*['"]POST|\/api\/station\/actions|\/api\/elecraft/);
  assert.match(page, /js\/station-history\.js/);
  assert.match(page, /station-history\.css/);
});
