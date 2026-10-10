const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('template loader limits concurrent fetches and mounts the complete manifest', async () => {
  const source = fs.readFileSync('frontend/templates-loader.js', 'utf8');
  const targets = new Map(
    ['app', 'controls-section', 'logging-panel-section', 'dx-spots-section', 'modals-section']
      .map(id => [id, {
        id,
        fragments: [],
        insertAdjacentHTML(_position, html) { this.fragments.push(html); },
        replaceChildren() {},
      }]),
  );
  let activeFetches = 0;
  let maximumFetches = 0;
  let requestCount = 0;
  let resolveLoaded;
  let rejectLoaded;
  const loaded = new Promise((resolve, reject) => {
    resolveLoaded = resolve;
    rejectLoaded = reject;
  });

  class CustomEvent {
    constructor(type, options = {}) {
      this.type = type;
      this.detail = options.detail;
    }
  }

  const context = {
    AbortController,
    CustomEvent,
    console,
    setTimeout,
    clearTimeout,
    window: { location: { reload() {} } },
    document: {
      body: targets.get('app'),
      createElement() {
        return {
          append() {},
          addEventListener() {},
          setAttribute() {},
          textContent: '',
          type: '',
        };
      },
      getElementById(id) { return targets.get(id) || null; },
      dispatchEvent(event) {
        if (event.type === 'templates-loaded') resolveLoaded();
        if (event.type === 'templates-failed') rejectLoaded(new Error(event.detail.failures.join(', ')));
      },
    },
    async fetch(path) {
      requestCount += 1;
      activeFetches += 1;
      maximumFetches = Math.max(maximumFetches, activeFetches);
      await new Promise(resolve => setTimeout(resolve, 2));
      activeFetches -= 1;
      return {
        ok: true,
        async text() { return `<div data-template="${path}"></div>`; },
      };
    },
  };

  vm.runInNewContext(source, context);
  await Promise.race([
    loaded,
    new Promise((_, reject) => setTimeout(() => reject(new Error('template load timed out')), 2000)),
  ]);

  assert.equal(requestCount, 14);
  assert.ok(maximumFetches <= 6, `expected at most 6 concurrent fetches, saw ${maximumFetches}`);
  assert.equal(context.window.om0rxTemplateReady.state, 'loaded');
  assert.equal(context.window.om0rxTemplateReady.result.ok, true);
  assert.equal(
    [...targets.values()].reduce((count, target) => count + target.fragments.length, 0),
    14,
  );
});
