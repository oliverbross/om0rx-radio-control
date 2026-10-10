const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function fixture() {
  const requests = [];
  const physicalMoves = [];
  const logs = [];
  const window = {
    Logger: { log(level, topic, ...args) { logs.push([level, topic, ...args]); } },
    addEventListener() {},
    vueInstance: {
      configData: { WSJTX_AUTO_ROTATE: true, ROTOR_AUTO_ENABLED: true },
      loggingForm: {},
      clearLoggingForm() {},
      loadQRZProfile() { return Promise.resolve(); },
      $nextTick(callback) { callback(); },
    },
  };
  const fetch = async (url, options) => {
    const body = JSON.parse(options.body);
    requests.push({ url, body });
    const allowed = body.frequency_hz >= 24_800_000 && body.frequency_hz <= 25_000_000;
    if (allowed) physicalMoves.push(body.call);
    return {
      ok: true,
      async json() {
        return allowed
          ? { success: true, bearing: 238.9, adjusted_bearing: 238.9 }
          : { success: false, skipped: true, policy: 'band-disabled', reason: 'Rotor not enabled for band 40m' };
      },
    };
  };
  const context = {
    window,
    fetch,
    console: { log() {}, warn() {}, error() {} },
    document: { readyState: 'loading', addEventListener() {} },
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
  };
  vm.runInNewContext(fs.readFileSync('frontend/js/wsjtx-handler.js', 'utf8'), context);
  return { context, requests, physicalMoves, logs };
}

function status(call, grid, dialFrequency) {
  return { dxCall: call, dxGrid: grid, dialFrequency, txRst: '', rxRst: '' };
}

test('stale target across a band change is handled once per band without a command flood', async () => {
  const { context, requests, physicalMoves } = fixture();

  context.handleWsjtxStatus(status('pt7sf', 'hi02', 24_915_000));
  context.handleWsjtxStatus(status('PT7SF', 'HI02', 24_919_000));
  context.handleWsjtxStatus(status('PT7SF', 'HI02', 24_915_000));
  assert.equal(requests.length, 1);
  assert.deepEqual(physicalMoves, ['pt7sf']);

  context.handleWsjtxStatus(status('PT7SF', 'HI02', 7_074_000));
  context.handleWsjtxStatus(status('PT7SF', 'HI02', 7_074_000));
  context.handleWsjtxStatus(status('PT7SF', 'HI02', 7_074_000));
  assert.equal(requests.length, 2);
  assert.equal(requests[1].body.frequency_hz, 7_074_000);
  assert.deepEqual(physicalMoves, ['pt7sf']);

  await new Promise(resolve => setImmediate(resolve));
});

test('clearing a target resets dedupe and target, grid, or band changes each trigger once', () => {
  const { context, requests } = fixture();

  context.handleWsjtxStatus(status('PT7SF', 'HI02', 24_915_000));
  context.handleWsjtxStatus(status('', '', 24_915_000));
  context.handleWsjtxStatus(status('PT7SF', 'HI02', 24_915_000));
  context.handleWsjtxStatus(status('PT7SF', 'HI03', 24_915_000));
  context.handleWsjtxStatus(status('HR6MLC', 'AL63', 24_915_000));
  context.handleWsjtxStatus(status('HR6MLC', 'AL63', 14_074_000));
  context.handleWsjtxStatus(status('HR6MLC', 'AL63', 14_095_000));

  assert.equal(requests.length, 5);
  assert.deepEqual(
    requests.map(request => [request.body.call, request.body.grid, request.body.frequency_hz]),
    [
      ['PT7SF', 'HI02', 24_915_000],
      ['PT7SF', 'HI02', 24_915_000],
      ['PT7SF', 'HI03', 24_915_000],
      ['HR6MLC', 'AL63', 24_915_000],
      ['HR6MLC', 'AL63', 14_074_000],
    ],
  );
});
